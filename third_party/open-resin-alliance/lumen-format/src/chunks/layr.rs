//! The `LAYR` chunk: one sector's mask data for one group of layers, as a
//! single zstd frame ([`spec/09-layer-data.md`] section 4.9).
//!
//! A `LAYR` chunk is a pair: `layr_version` in the clear, then one zstd frame
//! over the concatenation of that sector's layer data for the chunk's layer
//! group, layers in ascending order. A file carries one chunk per (sector,
//! layer-group), so a reader reaches one sector's masks with one decryption and
//! one decompression.
//!
//! The frame is the unit a sealed file seals (section 9.3): the version field
//! stays plaintext, so the container is readable without a key, and only the
//! frame is bound to the chunk's directory index by its associated data - which
//! is what stops one chunk's ciphertext being moved to another's.
//!
//! The container's sizes therefore describe the *container*, not the frame's
//! output: `size_uncompressed` is `layr_version` plus the stored frame, and
//! `size_compressed` is zero while the frame is in the clear and the same total
//! when it is sealed. The frame's output length is not in the descriptor at all:
//! a writer MUST set the frame's content size, which is what a reader allocates
//! from ([`crate::chunks::frame_content_size`]).

use crate::check::Check;
use crate::error::{Error, Result};
use crate::io::Reader;

/// The `LAYR` header: `layr_version`.
pub const LAYR_HEADER_LEN: usize = 4;
/// Layout version. `1` for this specification.
pub const LAYR_VERSION: u32 = 1;

/// Split a container payload into its version and its frame.
pub fn parse(payload: &[u8]) -> Result<(&[u8], u32)> {
    let mut r = Reader::checked(payload, Check::LayrVersion);
    let layr_version = r.u32()?;
    if layr_version != LAYR_VERSION {
        return Err(Error::new(
            Check::LayrVersion,
            format!("unsupported layr_version {layr_version}"),
        ));
    }
    Ok((&payload[LAYR_HEADER_LEN..], layr_version))
}

/// The frame bytes of a container payload.
pub fn frame(payload: &[u8]) -> Result<&[u8]> {
    parse(payload).map(|(frame, _)| frame)
}

/// The container payload of one frame: the version field, then the frame.
pub fn to_bytes(frame: &[u8]) -> Vec<u8> {
    let mut out = crate::io::Writer::with_capacity(LAYR_HEADER_LEN + frame.len());
    out.u32(LAYR_VERSION);
    out.bytes(frame);
    out.into_vec()
}

/// The container's byte length for a frame of `frame_len` bytes.
pub fn container_len(frame_len: usize) -> u64 {
    (LAYR_HEADER_LEN + frame_len) as u64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_payload_is_a_version_then_the_frame() {
        let payload = to_bytes(b"a zstd frame");
        assert_eq!(payload.len(), LAYR_HEADER_LEN + 12);
        assert_eq!(&payload[..4], &1u32.to_le_bytes());
        assert_eq!(frame(&payload).unwrap(), b"a zstd frame");
        assert_eq!(parse(&payload).unwrap().1, 1);
        assert_eq!(container_len(12), payload.len() as u64);
    }

    #[test]
    fn a_bad_version_or_a_short_payload_is_rejected() {
        let mut bad = to_bytes(b"frame");
        bad[0..4].copy_from_slice(&2u32.to_le_bytes());
        assert_eq!(frame(&bad).unwrap_err().check(), Check::LayrVersion);

        assert_eq!(
            frame(&[1, 0, 0]).unwrap_err().check(),
            Check::LayrVersion,
            "a payload shorter than the version field"
        );

        // The version field alone is a frame of no bytes: a corrupt frame, but
        // not a framing error.
        assert_eq!(frame(&to_bytes(b"")).unwrap(), b"");
    }
}
