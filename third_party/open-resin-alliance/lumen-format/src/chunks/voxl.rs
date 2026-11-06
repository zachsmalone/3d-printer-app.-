//! The `VOXL` chunk: an embedded scene, opaque to LUMEN
//! ([`spec/10-scene-chunks.md`] section 4.11).
//!
//! Nothing here parses a scene. The transport contract is that the bytes come
//! back out unchanged; recognizing which generation a payload is, so a slicer
//! knows what it is about to hand to the VOXL parser, is all a LUMEN reader can
//! do without knowing VOXL.

use crate::check::Check;
use crate::error::{Error, Result};

/// The VOXL V2 binary magic.
pub const VOXL_V2_MAGIC: [u8; 4] = *b"VOXL";
/// The first byte of a VOXL V1 JSON document.
pub const VOXL_V1_MARKER: u8 = b'{';

/// Whether a payload is recognizably a VOXL file of either generation.
pub fn is_voxl(payload: &[u8]) -> bool {
    payload.starts_with(&VOXL_V2_MAGIC) || payload.first() == Some(&VOXL_V1_MARKER)
}

/// Reject a payload that is neither VOXL generation, as strict mode requires.
pub fn require_voxl(payload: &[u8]) -> Result<()> {
    if is_voxl(payload) {
        return Ok(());
    }
    Err(Error::new(
        Check::VoxlSignature,
        format!(
            "payload begins with {:02x?}, which is neither the VOXL V2 magic nor a V1 document",
            &payload[..payload.len().min(4)]
        ),
    ))
}
