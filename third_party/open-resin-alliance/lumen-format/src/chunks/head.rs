//! The `HEAD` chunk: display dimensions, layer count and encoder identity
//! ([`spec/04-head.md`] section 4.1).

use crate::check::Check;
use crate::error::{Error, Result};
use crate::io::{Reader, Writer};

/// Bytes of `HEAD` other than `encoder_name`: 4 before it and 40 after.
pub const HEAD_FIXED_LEN: usize = 44;
/// Longest permitted `encoder_name`.
pub const ENCODER_NAME_MAX: usize = 256;

/// The `HEAD` chunk body.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Head {
    /// Layout version. `1` for this specification.
    pub head_version: u32,
    /// UTF-8 encoder identity, e.g. `DragonFruit 1.0`.
    pub encoder_name: String,
    /// Creation timestamp in Unix seconds.
    pub created_unix_sec: u64,
    /// Display width in pixels: the layer mask grid.
    pub display_width_px: u32,
    /// Display height in pixels: the layer mask grid.
    pub display_height_px: u32,
    /// Build plate X dimension in micrometers.
    pub build_width_um: u32,
    /// Build plate Y dimension in micrometers.
    pub build_depth_um: u32,
    /// Build plate Z dimension in micrometers.
    pub build_height_um: u32,
    /// Default layer thickness in micrometers.
    pub layer_height_um: u32,
    /// Total layer count, which `LTBL.layer_count` must equal.
    pub total_layers: u32,
}

impl Head {
    /// Parse the chunk payload.
    pub fn parse(payload: &[u8]) -> Result<Head> {
        let mut r = Reader::checked(payload, Check::HeadFrame);
        let head_version = r.u32()?;
        if head_version != 1 {
            return Err(Error::new(
                Check::HeadVersion,
                format!("unsupported head_version {head_version}"),
            ));
        }
        let encoder_name_len = r.u32()?;
        if encoder_name_len as usize > ENCODER_NAME_MAX {
            return Err(Error::new(
                Check::HeadFrame,
                format!(
                    "encoder_name_len {encoder_name_len} exceeds the {ENCODER_NAME_MAX} byte limit"
                ),
            ));
        }
        let encoder_name = r.utf8(encoder_name_len as usize)?.to_owned();
        let created_unix_sec = r.u64()?;
        let display_width_px = r.u32()?;
        let display_height_px = r.u32()?;
        let build_width_um = r.u32()?;
        let build_depth_um = r.u32()?;
        let build_height_um = r.u32()?;
        let layer_height_um = r.u32()?;
        let total_layers = r.u32()?;
        // Section 11.2: the chunk holds the fixed fields and the name and nothing
        // else. A longer one is a layout this reader does not know - a `HEAD` written
        // against another revision of these fields - and parsing its prefix would
        // report values that are not the ones they are named for.
        let expected = HEAD_FIXED_LEN + encoder_name_len as usize;
        if payload.len() != expected {
            return Err(Error::new(
                Check::HeadFrame,
                format!(
                    "HEAD is {} bytes, not the {expected} its fields and name total",
                    payload.len()
                ),
            ));
        }
        Ok(Head {
            head_version,
            encoder_name,
            created_unix_sec,
            display_width_px,
            display_height_px,
            build_width_um,
            build_depth_um,
            build_height_um,
            layer_height_um,
            total_layers,
        })
    }

    /// Serialize the chunk payload.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut w = Writer::with_capacity(HEAD_FIXED_LEN + self.encoder_name.len());
        w.u32(self.head_version);
        w.u32(self.encoder_name.len() as u32);
        w.bytes(self.encoder_name.as_bytes());
        w.u64(self.created_unix_sec);
        w.u32(self.display_width_px);
        w.u32(self.display_height_px);
        w.u32(self.build_width_um);
        w.u32(self.build_depth_um);
        w.u32(self.build_height_um);
        w.u32(self.layer_height_um);
        w.u32(self.total_layers);
        w.into_vec()
    }

    /// Pixels in one layer mask: `display_width_px * display_height_px`.
    pub fn total_pixels(&self) -> u32 {
        self.display_width_px.saturating_mul(self.display_height_px)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample(name: &str) -> Head {
        Head {
            head_version: 1,
            encoder_name: name.to_owned(),
            created_unix_sec: 1_710_000_000,
            display_width_px: 64,
            display_height_px: 48,
            build_width_um: 218_000,
            build_depth_um: 123_000,
            build_height_um: 250_000,
            layer_height_um: 50,
            total_layers: 4,
        }
    }

    #[test]
    fn hdr_round_trips_with_a_multibyte_name() {
        let head = sample("DragonFruit 1.0 \u{2713}");
        let bytes = head.to_bytes();
        // `encoder_name_len` counts bytes, not characters: the check mark is three.
        assert_eq!(bytes.len(), HEAD_FIXED_LEN + head.encoder_name.len());
        assert_eq!(
            u32::from_le_bytes(bytes[4..8].try_into().unwrap()) as usize,
            head.encoder_name.len()
        );
        let parsed = Head::parse(&bytes).unwrap();
        assert_eq!(parsed, head);
    }

    #[test]
    fn hdr_rejects_a_length_measured_in_characters() {
        let head = sample("DragonFruit \u{2713}");
        let mut bytes = head.to_bytes();
        // A writer that confused characters for bytes declares too few bytes,
        // so the name no longer decodes as UTF-8.
        let chars = head.encoder_name.chars().count() as u32;
        bytes[4..8].copy_from_slice(&chars.to_le_bytes());
        let err = Head::parse(&bytes).unwrap_err();
        assert_eq!(err.check(), Check::HeadFrame);
    }

    #[test]
    fn hdr_rejects_an_oversized_or_truncated_frame() {
        let mut bytes = sample("DragonFruit 1.0").to_bytes();
        bytes[4..8].copy_from_slice(&(ENCODER_NAME_MAX as u32 + 1).to_le_bytes());
        assert_eq!(Head::parse(&bytes).unwrap_err().check(), Check::HeadFrame);

        let bytes = sample("DragonFruit 1.0").to_bytes();
        assert_eq!(
            Head::parse(&bytes[..bytes.len() - 1]).unwrap_err().check(),
            Check::HeadFrame
        );
        assert_eq!(
            Head::parse(&bytes[..4]).unwrap_err().check(),
            Check::HeadFrame
        );

        // A `HEAD` longer than these fields is a layout this revision does not know,
        // not padding: a reader that parsed the prefix would report values under names
        // they do not have, which is how a pre-removal 52-byte `HEAD` turned into a
        // layer count of 235000 instead of the 800 the file holds.
        let mut longer = bytes.clone();
        longer.extend_from_slice(&[0u8; 8]);
        assert_eq!(Head::parse(&longer).unwrap_err().check(), Check::HeadFrame);
    }

    #[test]
    fn hdr_rejects_unknown_versions_and_any_extra_bytes() {
        let mut bytes = sample("X").to_bytes();
        bytes[0..4].copy_from_slice(&2u32.to_le_bytes());
        assert_eq!(Head::parse(&bytes).unwrap_err().check(), Check::HeadVersion);

        // Section 11.2 makes the frame exact, and the rule earns its keep: these fields
        // were eight bytes longer once, so a reader that ignored what followed them read
        // the old build height as `total_layers` and reported a file of 800 layers as one
        // of 235000.
        let mut bytes = sample("X").to_bytes();
        bytes.push(0);
        assert_eq!(Head::parse(&bytes).unwrap_err().check(), Check::HeadFrame);
    }
}
