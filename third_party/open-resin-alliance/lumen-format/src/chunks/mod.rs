//! One codec per chunk type ([`spec/03-chunks.md`], [`spec/09-layer-data.md`],
//! [`spec/10-scene-chunks.md`]).
//!
//! Each codec deals in *plaintext payload bytes*: decryption and the zstd layer
//! are the caller's business, because whether a chunk carries a zstd frame is a
//! property of its type (section 6.3) while whether it is sealed is a property
//! of its descriptor.

pub mod extd;
pub mod head;
pub mod json_chunks;
pub mod layr;
pub mod lhas;
pub mod ltbl;
pub mod preview;
pub mod voxl;
pub mod zdic;

pub use extd::Extension;
pub use head::Head;
pub use lhas::LayerHashes;
pub use ltbl::{LayerEntry, LayerTable};
pub use preview::{Preview, PreviewRole};
pub use zdic::ZstdDictionary;

use crate::check::Check;
use crate::error::{Error, Result};
use zstd::bulk::{Compressor, Decompressor};

/// Compress a chunk payload into a zstd frame, optionally against a dictionary.
pub fn compress(payload: &[u8], level: i32, dictionary: Option<&[u8]>) -> Result<Vec<u8>> {
    let mut compressor = match dictionary {
        Some(dictionary) => Compressor::with_dictionary(level, dictionary),
        None => Compressor::new(level),
    }
    .map_err(|e| {
        Error::new(
            Check::LayrFrameDecompressedSize,
            format!("could not start the zstd compressor: {e}"),
        )
    })?;
    compressor.compress(payload).map_err(|e| {
        Error::new(
            Check::LayrFrameDecompressedSize,
            format!("zstd compression failed: {e}"),
        )
    })
}

/// Decompress a zstd frame, checking the result is exactly `uncompressed_size`.
///
/// The size is bounded by what the frame's own bytes can justify, which is a
/// coarse guard for a payload whose bound is unknown until the chunk around it is
/// parsed. A `LAYR` frame has a better bound - the slices that point into it -
/// so it goes through [`decompress_frame`] instead (section 11.3).
pub fn decompress(
    frame: &[u8],
    uncompressed_size: u64,
    dictionary: Option<&[u8]>,
) -> Result<Vec<u8>> {
    let bound = (frame.len() as u64).saturating_mul(MAX_ZSTD_RATIO as u64);
    decompress_within(frame, uncompressed_size, dictionary, bound)
}

/// Decompress a zstd frame, refusing a declared size above `bound`.
pub fn decompress_within(
    frame: &[u8],
    uncompressed_size: u64,
    dictionary: Option<&[u8]>,
    bound: u64,
) -> Result<Vec<u8>> {
    // Refuse to reserve memory the file's own structure cannot justify before the
    // decompressor allocates for the declared size (section 11.3).
    check_allocation(uncompressed_size, bound, frame.len())?;
    let capacity = usize::try_from(uncompressed_size).map_err(|_| {
        Error::new(
            Check::LayrFrameDecompressedSize,
            format!("declared uncompressed size {uncompressed_size} is not addressable"),
        )
    })?;
    let mut decompressor = match dictionary {
        Some(dictionary) => Decompressor::with_dictionary(dictionary),
        None => Decompressor::new(),
    }
    .map_err(|e| {
        Error::new(
            Check::LayrFrameDecompressedSize,
            format!("could not start the zstd decompressor: {e}"),
        )
    })?;
    let decoded = decompressor.decompress(frame, capacity).map_err(|e| {
        Error::new(
            Check::LayrFrameDecompressedSize,
            format!("zstd decompression failed: {e}"),
        )
    })?;
    if decoded.len() as u64 != uncompressed_size {
        return Err(Error::new(
            Check::LayrFrameDecompressedSize,
            format!(
                "the frame expands to {} bytes, not the declared {uncompressed_size}",
                decoded.len()
            ),
        ));
    }
    Ok(decoded)
}

/// The dictionary ID a frame reports, or `0` when the frame used no dictionary.
pub fn frame_dict_id(frame: &[u8]) -> Result<u32> {
    Ok(zstd::zstd_safe::get_dict_id_from_frame(frame)
        .map(|id| id.get())
        .unwrap_or(0))
}

/// The decompressed length a frame's own header declares.
///
/// A `LAYR` frame MUST carry its content size: the chunk descriptor describes
/// the container, not the frame's output, so this header field is the only place
/// a reader can learn how large that output is before it allocates.
pub fn frame_content_size(frame: &[u8]) -> Result<u64> {
    match zstd::zstd_safe::get_frame_content_size(frame) {
        Ok(Some(size)) => Ok(size),
        Ok(None) => Err(Error::new(
            Check::LayrContentSizePresent,
            "the frame carries no content size, so its output cannot be sized",
        )),
        Err(e) => Err(Error::new(
            Check::LayrContentSizePresent,
            format!("the frame's content size is unreadable: {e}"),
        )),
    }
}

/// Decompress a `LAYR` frame, sizing its output from the frame's own header and
/// bounding it by `bound`.
///
/// The bound is the caller's, because a `LAYR` frame's plausible output is
/// derived from the file rather than from the frame: it is
/// [`allocation_bound`] over the slices the layer table points into this chunk.
/// A ratio guard cannot stand in for it - an encoder may write a block whose
/// layers repeat, and zstd then compresses far past any fixed ratio, which is a
/// conforming file rather than a hostile one.
pub fn decompress_frame(frame: &[u8], dictionary: Option<&[u8]>, bound: u64) -> Result<Vec<u8>> {
    let size = frame_content_size(frame)?;
    decompress_within(frame, size, dictionary, bound)
}

/// The dictionary ID a raw dictionary reports.
pub fn dictionary_id(dictionary: &[u8]) -> u32 {
    zstd::zstd_safe::get_dict_id_from_dict(dictionary)
        .map(|id| id.get())
        .unwrap_or(0)
}

/// Train a zstd dictionary from layer samples (section 6.2).
pub fn train_dictionary(samples: &[&[u8]], max_size: usize) -> Result<Vec<u8>> {
    zstd::dict::from_samples(samples, max_size).map_err(|e| {
        Error::new(
            Check::ZdicDictSize,
            format!("zstd dictionary training failed: {e}"),
        )
    })
}

/// The decompressed-size bound a `LAYR` chunk's frame may not exceed.
///
/// Grayscale REE costs at most about 5 bytes per pixel plus framing, which is
/// what a reader checks a frame's declared content size against before
/// allocating, over the layers whose slices the chunk holds (section 11.3).
pub fn allocation_bound(layers: u64, total_pixels: u32) -> u64 {
    layers.saturating_mul(u64::from(total_pixels).saturating_mul(5).saturating_add(64))
}

/// Reject a declared size above the bound the file's own structure allows.
pub fn check_allocation(uncompressed_size: u64, bound: u64, payload_len: usize) -> Result<()> {
    if uncompressed_size > bound {
        return Err(Error::new(
            Check::FrameAllocationBound,
            format!(
                "declared uncompressed size {uncompressed_size} exceeds the {bound} bytes the \
                 structure allows for {payload_len} stored bytes"
            ),
        ));
    }
    Ok(())
}

/// The largest expansion zstd can produce for a chunk payload, used as a coarse
/// guard before a bound specific to the chunk is available.
pub const MAX_ZSTD_RATIO: usize = 4096;

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn zstd_round_trips_with_and_without_a_dictionary() {
        let payload: Vec<u8> = (0..4096u32).map(|i| (i % 17) as u8).collect();

        let framed = compress(&payload, 3, None).unwrap();
        assert_eq!(frame_dict_id(&framed).unwrap(), 0);
        assert_eq!(
            decompress(&framed, payload.len() as u64, None).unwrap(),
            payload
        );

        // Training needs a corpus of similar samples.
        let samples: Vec<Vec<u8>> = (0..256u32)
            .map(|s| (0..256u32).map(|i| ((i + s) % 23) as u8).collect())
            .collect();
        let refs: Vec<&[u8]> = samples.iter().map(|s| s.as_slice()).collect();
        let dictionary = train_dictionary(&refs, 512).unwrap();
        let dict_id = dictionary_id(&dictionary);
        assert_ne!(dict_id, 0, "a trained dictionary reports its ID");

        let framed = compress(&payload, 3, Some(&dictionary)).unwrap();
        assert_eq!(frame_dict_id(&framed).unwrap(), dict_id);
        assert_eq!(
            decompress(&framed, payload.len() as u64, Some(&dictionary)).unwrap(),
            payload
        );

        // A frame that does not expand to the declared size is rejected.
        let err = decompress(&framed, payload.len() as u64 + 1, Some(&dictionary)).unwrap_err();
        assert_eq!(err.check(), Check::LayrFrameDecompressedSize);
    }

    #[test]
    fn a_writer_frame_declares_the_size_it_expands_to() {
        let payload: Vec<u8> = (0..4096u32).map(|i| (i % 17) as u8).collect();
        let framed = compress(&payload, 3, None).unwrap();
        assert_eq!(frame_content_size(&framed).unwrap(), payload.len() as u64);
        // A bound generous enough for anything this frame could expand to: the
        // test is about the header, not about the bound.
        let bound = (framed.len() as u64).saturating_mul(MAX_ZSTD_RATIO as u64);
        assert_eq!(decompress_frame(&framed, None, bound).unwrap(), payload);

        // A `LAYR` frame is sized from its own header, because the chunk
        // descriptor describes the container and not the frame's output. A frame
        // written by a streaming encoder declares no content size, and a reader
        // refuses one rather than guessing what to allocate.
        let streamed = {
            let mut encoder = zstd::stream::write::Encoder::new(Vec::new(), 3).unwrap();
            encoder.write_all(&payload).unwrap();
            encoder.finish().unwrap()
        };
        assert_eq!(
            frame_content_size(&streamed).unwrap_err().check(),
            Check::LayrContentSizePresent
        );
    }

    #[test]
    fn check_allocation_bounds_the_declared_size() {
        let bound = (MAX_ZSTD_RATIO - 1) as u64;
        assert!(check_allocation(bound, bound, 1).is_ok());
        assert_eq!(
            check_allocation(bound + 1, bound, 1).unwrap_err().check(),
            Check::FrameAllocationBound
        );
        assert!(allocation_bound(2, 1000) > 0);
    }

    /// A frame may compress far past the ratio guard and still be conforming: a
    /// block whose layers repeat does exactly that. What bounds it is the slices
    /// the layer table points into its chunk, so a `LAYR` frame is decompressed
    /// against that bound instead of against the ratio.
    #[test]
    fn a_layr_frame_is_bounded_by_its_slices_not_by_a_ratio() {
        let payload = vec![0u8; 1 << 20];
        let frame = compress(&payload, 3, None).unwrap();
        let ratio = payload.len() as f64 / frame.len() as f64;
        assert!(
            ratio > MAX_ZSTD_RATIO as f64,
            "this test needs a frame past the ratio guard, got {ratio:.0}:1"
        );

        // The ratio guard refuses it, which is why it cannot be the LAYR rule.
        assert_eq!(
            decompress_frame(&frame, None, (frame.len() as u64) * MAX_ZSTD_RATIO as u64)
                .unwrap_err()
                .check(),
            Check::FrameAllocationBound
        );

        // A bound from the file's own structure accepts it, and the output is
        // exactly the declared size.
        let total_pixels = 1 << 20;
        let bound = allocation_bound(1, total_pixels);
        assert!(bound >= payload.len() as u64);
        assert_eq!(decompress_frame(&frame, None, bound).unwrap(), payload);
    }
}
