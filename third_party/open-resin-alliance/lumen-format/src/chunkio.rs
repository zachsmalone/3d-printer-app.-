//! Reading a chunk payload off disk: stored bytes, decryption, decompression.
//!
//! This is the one place that knows which chunk types carry a zstd frame and how
//! a sealed payload is framed, so the validator and the reader cannot disagree
//! about either.
//!
//! `LAYR` is the exception that shapes the rest: its frame is the sealed unit
//! (section 9.3), its associated data binds that frame to the chunk's
//! *directory index*, and the container's other units - one per chunk - bind to
//! index zero. [`layr_frame`] exists so no caller can accidentally open a layer
//! frame under the wrong slot.

use crate::check::Check;
use crate::chunks;
use crate::container::{ChunkDescriptor, ChunkType};
use crate::crypto::{self, Cipher, SessionKey};
use crate::error::{Error, Result};
use std::borrow::Cow;

/// The stored bytes of a chunk, sealed or not.
pub(crate) fn stored<'a>(buf: &'a [u8], d: &ChunkDescriptor) -> Result<&'a [u8]> {
    let start = d.offset as usize;
    let end = start
        .checked_add(d.stored_len() as usize)
        .ok_or_else(|| Error::new(Check::DirChunkExtent, "chunk extent overflows"))?;
    buf.get(start..end).ok_or_else(|| {
        Error::new(
            Check::DirChunkExtent,
            format!(
                "chunk {} at {start}..{end} lies outside the {} byte file",
                d.chunk_type,
                buf.len()
            ),
        )
    })
}

/// The plaintext bytes of a one-unit chunk, or `None` when it is sealed and no
/// key is available.
///
/// A `LAYR` payload is never read this way: its clear prefix is a version field
/// and its frame is sealed on its own, bound to the chunk's directory index
/// rather than to slot zero. Callers use [`layr_frame`] for those.
pub(crate) fn plaintext(
    d: &ChunkDescriptor,
    stored: &[u8],
    cipher: Option<Cipher>,
    key: Option<&SessionKey>,
) -> Result<Option<Vec<u8>>> {
    if !d.is_encrypted() {
        return Ok(Some(stored.to_vec()));
    }
    match (cipher, key) {
        (Some(cipher), Some(key)) => Ok(Some(crypto::open(cipher, key, d.chunk_type, 0, stored)?)),
        _ => Ok(None),
    }
}

/// The plaintext frame of a `LAYR` chunk, or `None` when it is sealed and no key
/// is available.
///
/// `unit_index` is the chunk's directory index. A frame that will not authenticate
/// there is opened once more under index `0`, because that single retry is what
/// separates the two defects a failed AEAD open can mean: a file that sealed its
/// frames under the wrong index authenticates under `0` (`crypt.unit_index_binding`),
/// while a corrupted ciphertext or tag authenticates under neither (`crypt.tag_verify`).
/// Reporting both as the binding would tell a reader its file was mis-bound when the
/// bytes are simply wrong.
///
/// An unsealed frame is borrowed from the file rather than copied: a container is
/// the largest thing in a print, and a reader that only decompresses it has no
/// reason to hold a second copy.
pub(crate) fn layr_frame<'a>(
    d: &ChunkDescriptor,
    unit_index: u32,
    stored: &'a [u8],
    cipher: Option<Cipher>,
    key: Option<&SessionKey>,
) -> Result<Option<Cow<'a, [u8]>>> {
    let frame = chunks::layr::frame(stored)?;
    if !d.is_encrypted() {
        return Ok(Some(Cow::Borrowed(frame)));
    }
    match (cipher, key) {
        (Some(cipher), Some(key)) => {
            let open = |unit: u32| crypto::open(cipher, key, ChunkType::LAYR, unit, frame);
            match open(unit_index) {
                Ok(plain) => Ok(Some(Cow::Owned(plain))),
                Err(reason) => {
                    if open(0).is_ok() {
                        Err(Error::new(
                            Check::CryptUnitIndexBinding,
                            format!(
                                "the frame at directory index {unit_index} does not authenticate \
                                 there, but does under unit index 0"
                            ),
                        ))
                    } else {
                        Err(Error::new(
                            Check::CryptTagVerify,
                            format!(
                                "the frame at directory index {unit_index} does not authenticate: \
                                 {reason}"
                            ),
                        ))
                    }
                }
            }
        }
        _ => Ok(None),
    }
}

/// The decrypted, decompressed payload of a chunk, or `None` when it cannot be
/// read.
///
/// Whether a payload carries a zstd frame is a property of the chunk type
/// (section 6.3) - except for `EXTD`, whose compression is per-extension. For
/// `EXTD` the descriptor answers instead: section 3.2 defines
/// `size_compressed` as zero for a raw payload, so a non-zero value on an
/// unsealed extension means a zstd frame. A sealed extension's payload is left
/// alone, because its framing hides whether a frame is inside and no implemented
/// extension exists to say.
pub(crate) fn payload(
    d: &ChunkDescriptor,
    stored: &[u8],
    cipher: Option<Cipher>,
    key: Option<&SessionKey>,
) -> Result<Option<Vec<u8>>> {
    let Some(plain) = plaintext(d, stored, cipher, key)? else {
        return Ok(None);
    };
    let compressed = d.chunk_type.is_compressed()
        || (d.chunk_type == ChunkType::EXTD && !d.is_encrypted() && d.size_compressed != 0);
    if !compressed {
        return Ok(Some(plain));
    }
    Ok(Some(chunks::decompress(&plain, d.size_uncompressed, None)?))
}
