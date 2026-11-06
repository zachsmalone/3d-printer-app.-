//! The `PREV` chunk: a PNG preview, with its role in the descriptor flags
//! ([`spec/08-print-control.md`] section 4.6).

use crate::check::Check;
use crate::container::CHUNK_FLAG_ENCRYPTED;
use crate::error::{Error, Result};

/// The eight-byte PNG signature.
pub const PNG_SIGNATURE: [u8; 8] = [0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A];

/// The descriptor flag bits holding the preview role.
pub const PREVIEW_ROLE_MASK: u32 = 0x0F;

/// What a preview is for; a reader picks the best fit for its display.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum PreviewRole {
    /// No stated role.
    #[default]
    Unspecified = 0,
    /// Large preview, recommended 400x300.
    Large = 1,
    /// Small preview, recommended 200x125.
    Small = 2,
    /// Icon, at most 64x64.
    Icon = 3,
}

impl PreviewRole {
    /// Decode the role from a descriptor's flags.
    pub fn from_flags(flags: u32) -> Result<PreviewRole> {
        // Bit 4 is the descriptor's ENCRYPTED flag, not reserved (section 4.6):
        // a sealed preview still names its role.
        let reserved = !(PREVIEW_ROLE_MASK | CHUNK_FLAG_ENCRYPTED);
        if flags & reserved != 0 {
            return Err(Error::new(
                Check::PrevFlags,
                format!("preview flags {flags:#010x} set a reserved bit"),
            ));
        }
        match flags & PREVIEW_ROLE_MASK {
            0 => Ok(PreviewRole::Unspecified),
            1 => Ok(PreviewRole::Large),
            2 => Ok(PreviewRole::Small),
            3 => Ok(PreviewRole::Icon),
            role => Err(Error::new(
                Check::PrevFlags,
                format!("preview role {role} is reserved"),
            )),
        }
    }

    /// The flag bits a writer sets for this role.
    pub fn to_flags(self) -> u32 {
        self as u32
    }
}

/// One `PREV` chunk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Preview {
    /// The role the descriptor advertises.
    pub role: PreviewRole,
    /// The PNG file, verbatim.
    pub png: Vec<u8>,
}

/// Whether a payload starts with the PNG signature.
pub fn is_png(payload: &[u8]) -> bool {
    payload.len() >= 8 && payload[..8] == PNG_SIGNATURE
}

/// Check the signature and the `IHDR` chunk, as strict mode requires.
pub fn check_png(payload: &[u8]) -> Result<()> {
    // PNG is the one big-endian structure in LUMEN: the first chunk's length
    // and the IHDR fields are network byte order.
    if payload.len() < 25 || !is_png(payload) {
        return Err(Error::new(
            Check::PrevPngSignature,
            format!(
                "a {} byte payload does not begin with the PNG signature",
                payload.len()
            ),
        ));
    }
    let declared = u32::from_be_bytes([payload[8], payload[9], payload[10], payload[11]]);
    if declared != 13 {
        return Err(Error::new(
            Check::PrevPngSignature,
            format!("the first PNG chunk declares {declared} bytes; IHDR is 13"),
        ));
    }
    if &payload[12..16] != b"IHDR" {
        return Err(Error::new(
            Check::PrevPngSignature,
            "the first PNG chunk is not IHDR",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A well-formed signature, IHDR length, type and body.
    fn minimal_png() -> Vec<u8> {
        let mut png = Vec::from(PNG_SIGNATURE);
        png.extend_from_slice(&13u32.to_be_bytes());
        png.extend_from_slice(b"IHDR");
        png.extend_from_slice(&1u32.to_be_bytes()); // width
        png.extend_from_slice(&1u32.to_be_bytes()); // height
        png.extend_from_slice(&[8, 6, 0, 0, 0]); // bit depth, color, compression, filter, interlace
        png
    }

    #[test]
    fn check_png_accepts_a_minimal_png_and_rejects_other_bytes() {
        assert!(check_png(&minimal_png()).is_ok());
        assert_eq!(
            check_png(b"this is not a PNG at all, not even close")
                .unwrap_err()
                .check(),
            Check::PrevPngSignature
        );
        // A PNG signature followed by a chunk that is not IHDR is rejected.
        let mut wrong_type = minimal_png();
        wrong_type[12..16].copy_from_slice(b"IDAT");
        assert_eq!(
            check_png(&wrong_type).unwrap_err().check(),
            Check::PrevPngSignature
        );
        // A declared IHDR length other than 13 is rejected.
        let mut wrong_len = minimal_png();
        wrong_len[8..12].copy_from_slice(&14u32.to_be_bytes());
        assert_eq!(
            check_png(&wrong_len).unwrap_err().check(),
            Check::PrevPngSignature
        );
    }

    #[test]
    fn preview_roles_reject_reserved_values_but_allow_sealing() {
        assert_eq!(PreviewRole::from_flags(1).unwrap(), PreviewRole::Large);
        // Role 4 is reserved even though bit 4 is the (allowed) ENCRYPTED flag.
        assert_eq!(
            PreviewRole::from_flags(4).unwrap_err().check(),
            Check::PrevFlags
        );
        assert_eq!(
            PreviewRole::from_flags(15).unwrap_err().check(),
            Check::PrevFlags
        );
        // Reserved bit 5 is rejected.
        assert_eq!(
            PreviewRole::from_flags(1 | (1 << 5)).unwrap_err().check(),
            Check::PrevFlags
        );
        // A sealed preview still decodes its role.
        let flags = PreviewRole::Icon.to_flags() | CHUNK_FLAG_ENCRYPTED;
        assert_eq!(PreviewRole::from_flags(flags).unwrap(), PreviewRole::Icon);
    }
}
