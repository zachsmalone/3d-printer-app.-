//! The `ZDIC` chunk: the zstd dictionary shared by every `LAYR` frame
//! ([`spec/09-layer-data.md`] section 4.8).

use crate::check::Check;
use crate::error::{Error, Result};
use crate::io::{Reader, Writer};

/// The `ZDIC` chunk header: `zdic_version`, `dict_id`, `dict_size`.
pub const ZDIC_HEADER_LEN: usize = 12;
/// zstd's `ZDICT_DICTSIZE_MAX`.
pub const ZDIC_DICTSIZE_MAX: usize = 112_640;

/// The `ZDIC` chunk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ZstdDictionary {
    /// Layout version. `1` for this specification.
    pub zdic_version: u32,
    /// The dictionary ID, which every `LAYR` frame must report.
    pub dict_id: u32,
    /// Raw dictionary bytes, exactly as `ZDICT_trainFromBuffer` produced them.
    pub dict_bytes: Vec<u8>,
}

impl ZstdDictionary {
    /// Parse the chunk payload.
    pub fn parse(payload: &[u8]) -> Result<ZstdDictionary> {
        let mut r = Reader::checked(payload, Check::ZdicDictSize);
        let zdic_version = r.u32()?;
        if zdic_version != 1 {
            return Err(Error::new(
                Check::ZdicVersion,
                format!("unsupported zdic_version {zdic_version}"),
            ));
        }
        let dict_id = r.u32()?;
        let dict_size = r.u32()?;
        if dict_size as usize > ZDIC_DICTSIZE_MAX {
            return Err(Error::new(
                Check::ZdicDictSize,
                format!("dict_size {dict_size} exceeds zstd's {ZDIC_DICTSIZE_MAX} byte maximum"),
            ));
        }
        let dict_bytes = r.bytes(dict_size as usize)?.to_vec();
        Ok(ZstdDictionary {
            zdic_version,
            dict_id,
            dict_bytes,
        })
    }

    /// Serialize the chunk payload.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut w = Writer::with_capacity(ZDIC_HEADER_LEN + self.dict_bytes.len());
        w.u32(self.zdic_version);
        w.u32(self.dict_id);
        w.u32(self.dict_bytes.len() as u32);
        w.bytes(&self.dict_bytes);
        w.into_vec()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn zdic_round_trips() {
        let dict = ZstdDictionary {
            zdic_version: 1,
            dict_id: 0x1234_5678,
            dict_bytes: vec![1, 2, 3, 4, 5],
        };
        let bytes = dict.to_bytes();
        assert_eq!(bytes.len(), ZDIC_HEADER_LEN + 5);
        assert_eq!(ZstdDictionary::parse(&bytes).unwrap(), dict);
    }

    #[test]
    fn zdic_rejects_bad_version_size_and_truncation() {
        let oversize = ZstdDictionary {
            zdic_version: 1,
            dict_id: 0,
            dict_bytes: vec![0; ZDIC_DICTSIZE_MAX + 1],
        };
        assert_eq!(
            ZstdDictionary::parse(&oversize.to_bytes())
                .unwrap_err()
                .check(),
            Check::ZdicDictSize
        );

        let dict = ZstdDictionary {
            zdic_version: 1,
            dict_id: 7,
            dict_bytes: vec![1, 2, 3],
        };
        let mut bytes = dict.to_bytes();
        bytes[0..4].copy_from_slice(&2u32.to_le_bytes());
        assert_eq!(
            ZstdDictionary::parse(&bytes).unwrap_err().check(),
            Check::ZdicVersion
        );

        let mut bytes = dict.to_bytes();
        bytes[8..12].copy_from_slice(&4u32.to_le_bytes()); // declares one byte too many
        assert_eq!(
            ZstdDictionary::parse(&bytes).unwrap_err().check(),
            Check::ZdicDictSize
        );
    }
}
