//! The `EXTD` chunk: vendor and future-standard extensions
//! ([`spec/10-scene-chunks.md`] section 4.12).

use crate::check::Check;
use crate::container::CHUNK_FLAG_ENCRYPTED;
use crate::error::{Error, Result};
use crate::io::{Reader, Writer};

/// The fixed part of the extension payload: `ext_version` and `ext_type`.
pub const EXTD_FRAME_LEN: usize = 8;

/// Where the `vendor_id` field sits in the descriptor flags.
///
/// `vendor_id` is a registered label, not a dispatch key: the registry lives in
/// the specification (section 4.12.1) and this crate never consults it. A value
/// it does not know is an extension its caller does not implement, which the
/// `critical` bit decides what to do about.
pub const VENDOR_ID_SHIFT: u32 = 8;
/// The `vendor_id` field's mask.
pub const VENDOR_ID_MASK: u32 = 0xFFFF << VENDOR_ID_SHIFT;
/// `vendor_id` `0x0000` marks an ORA standard extension.
pub const VENDOR_ID_ORA: u16 = 0x0000;
/// The `critical` bit: an unimplemented critical extension makes a file unprintable.
pub const CRITICAL_BIT: u32 = 1 << 24;
/// Reserved flag bits: 0-3, 5-7 and 25-31.
pub const EXTD_RESERVED_MASK: u32 = (0xFF & !crate::container::CHUNK_FLAG_ENCRYPTED) | (0x7F << 25);

/// One `EXTD` chunk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Extension {
    /// Extension format version.
    pub ext_version: u32,
    /// Four-character ASCII type code.
    pub ext_type: [u8; 4],
    /// Vendor identifier, `0` for an ORA standard extension.
    pub vendor_id: u16,
    /// Whether a reader that does not implement this extension must refuse the file.
    pub critical: bool,
    /// Whether the payload is sealed.
    pub encrypted: bool,
    /// The extension's own payload.
    pub data: Vec<u8>,
}

impl Extension {
    /// Parse a payload and its descriptor flags.
    pub fn parse(payload: &[u8], flags: u32) -> Result<Extension> {
        let mut r = Reader::checked(payload, Check::ExtdFrame);
        let ext_version = r.u32()?;
        let ext_type = r.array::<4>()?;
        if !ext_type.is_ascii() {
            return Err(Error::new(
                Check::ExtdExtType,
                format!("ext_type {ext_type:02x?} is not four ASCII characters"),
            ));
        }
        if flags & EXTD_RESERVED_MASK != 0 {
            return Err(Error::new(
                Check::ExtdFlags,
                format!("extension flags {flags:#010x} set a reserved bit"),
            ));
        }
        Ok(Extension {
            ext_version,
            ext_type,
            vendor_id: ((flags & VENDOR_ID_MASK) >> VENDOR_ID_SHIFT) as u16,
            critical: flags & CRITICAL_BIT != 0,
            encrypted: flags & CHUNK_FLAG_ENCRYPTED != 0,
            data: r.rest().to_vec(),
        })
    }

    /// Serialize the payload.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut w = Writer::with_capacity(EXTD_FRAME_LEN + self.data.len());
        w.u32(self.ext_version);
        w.bytes(&self.ext_type);
        w.bytes(&self.data);
        w.into_vec()
    }

    /// The descriptor flags a writer sets for this extension.
    pub fn to_flags(&self) -> u32 {
        let mut flags = u32::from(self.vendor_id) << VENDOR_ID_SHIFT;
        if self.critical {
            flags |= CRITICAL_BIT;
        }
        if self.encrypted {
            flags |= CHUNK_FLAG_ENCRYPTED;
        }
        flags
    }

    /// The type code as text.
    pub fn tag(&self) -> String {
        String::from_utf8_lossy(&self.ext_type).into_owned()
    }

    /// Whether this crate implements the extension.
    ///
    /// It implements none: an extension's payload is vendor-defined and is
    /// copied through, never interpreted (section 4.12). A downstream reader
    /// that does implement one overrides this.
    pub fn is_implemented(&self) -> bool {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extension_flags_round_trip() {
        let flags = (0x00ABu32 << VENDOR_ID_SHIFT) | CRITICAL_BIT | CHUNK_FLAG_ENCRYPTED;
        let mut payload = Vec::new();
        payload.extend_from_slice(&1u32.to_le_bytes());
        payload.extend_from_slice(b"SIGN");
        payload.extend_from_slice(&[9, 8, 7]);
        let ext = Extension::parse(&payload, flags).unwrap();
        assert_eq!(ext.ext_version, 1);
        assert_eq!(&ext.ext_type, b"SIGN");
        assert_eq!(ext.vendor_id, 0x00AB);
        assert!(ext.critical);
        assert!(ext.encrypted);
        assert_eq!(ext.data, vec![9, 8, 7]);
        assert_eq!(ext.to_flags(), flags);
        assert_eq!(ext.tag(), "SIGN");

        let reparsed = Extension::parse(&ext.to_bytes(), ext.to_flags()).unwrap();
        assert_eq!(reparsed, ext);
    }

    #[test]
    fn extension_rejects_bad_frames_types_and_flags() {
        assert_eq!(
            Extension::parse(&[1, 2, 3], 0).unwrap_err().check(),
            Check::ExtdFrame
        );
        let non_ascii = [1u32.to_le_bytes(), [0xC3, 0xA9, 0x00, 0x00]].concat();
        assert_eq!(
            Extension::parse(&non_ascii, 0).unwrap_err().check(),
            Check::ExtdExtType
        );
        let payload = [1u32.to_le_bytes(), *b"TEST"].concat();
        assert_eq!(
            Extension::parse(&payload, 1 << 0).unwrap_err().check(),
            Check::ExtdFlags
        );
        assert_eq!(
            Extension::parse(&payload, 1 << 25).unwrap_err().check(),
            Check::ExtdFlags
        );
        // The ENCRYPTED bit is not reserved.
        assert!(Extension::parse(&payload, CHUNK_FLAG_ENCRYPTED).is_ok());
    }
}
