//! Protocol-Buffers-style varints ([`spec/11-layer-encoding.md`] section 5.2).
//!
//! Seven data bits per byte, least-significant group first, MSB set means more
//! bytes follow. The shortest form is mandatory: an overlong encoding is
//! malformed, as is anything longer than 10 bytes or a varint that runs past the
//! end of its buffer.

use crate::check::Check;
use crate::error::{Error, Result};
use crate::io::{Reader, Writer};

/// The longest legal varint: a 64-bit value needs at most 10 bytes.
pub const MAX_LEN: usize = 10;

/// Decode one varint, advancing the reader past it.
///
/// Every failure reports [`Check::ReeVarint`], the corpus name for this rule.
pub fn decode(reader: &mut Reader<'_>) -> Result<u64> {
    let start = reader.pos();
    let mut result: u64 = 0;
    let mut shift: u32 = 0;
    let mut count = 0usize;
    loop {
        if count == MAX_LEN {
            return Err(Error::new(
                Check::ReeVarint,
                format!("varint at offset {start} is longer than {MAX_LEN} bytes"),
            ));
        }
        let byte = match reader.u8() {
            Ok(b) => b,
            Err(_) => {
                return Err(Error::new(
                    Check::ReeVarint,
                    format!("varint at offset {start} runs past the end of its buffer"),
                ))
            }
        };
        count += 1;
        if count == MAX_LEN && byte > 0x01 {
            return Err(Error::new(
                Check::ReeVarint,
                format!("varint at offset {start} overflows 64 bits"),
            ));
        }
        result |= u64::from(byte & 0x7F) << shift;
        if byte & 0x80 == 0 {
            if count > 1 && byte == 0 {
                return Err(Error::new(
                    Check::ReeVarint,
                    format!("varint at offset {start} is not minimally encoded"),
                ));
            }
            return Ok(result);
        }
        shift += 7;
    }
}

/// Append `value` in its shortest form.
pub fn encode(out: &mut Writer, value: u64) {
    let mut v = value;
    while v >= 0x80 {
        out.u8((v as u8) | 0x80);
        v >>= 7;
    }
    out.u8(v as u8);
}

/// The number of bytes [`encode`] would write.
pub fn encoded_len(value: u64) -> usize {
    let mut len = 1;
    let mut v = value >> 7;
    while v != 0 {
        len += 1;
        v >>= 7;
    }
    len
}

/// Encode to a fresh `Vec`.
pub fn to_vec(value: u64) -> Vec<u8> {
    let mut w = Writer::with_capacity(encoded_len(value));
    encode(&mut w, value);
    w.into_vec()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn round_trip(value: u64) {
        let bytes = to_vec(value);
        assert_eq!(bytes.len(), encoded_len(value));
        let mut r = Reader::new(&bytes);
        assert_eq!(r.varint().unwrap(), value);
        assert!(r.is_empty());
    }

    #[test]
    fn spec_examples() {
        assert_eq!(to_vec(0), vec![0x00]);
        assert_eq!(to_vec(128), vec![0x80, 0x01]);
        assert_eq!(to_vec(2_073_600).len(), 3); // 1920 x 1080
        assert_eq!(to_vec(74_649_600).len(), 4); // 11520 x 6480
    }

    #[test]
    fn round_trips_boundaries() {
        for value in [
            0,
            1,
            127,
            128,
            16_383,
            16_384,
            2_097_151,
            2_097_152,
            268_435_455,
            268_435_456,
            u64::MAX,
        ] {
            round_trip(value);
        }
    }

    #[test]
    fn overlong_is_rejected() {
        let mut r = Reader::new(&[0x80, 0x00]);
        let err = r.varint().unwrap_err();
        assert_eq!(err.check(), Check::ReeVarint);
    }

    #[test]
    fn truncated_is_rejected() {
        let mut r = Reader::new(&[0x80]);
        assert_eq!(r.varint().unwrap_err().check(), Check::ReeVarint);
    }

    #[test]
    fn overflow_is_rejected() {
        // Eleven continuation bytes, then a value bit.
        let mut bytes = vec![0xFFu8; 10];
        bytes.push(0x01);
        let mut r = Reader::new(&bytes);
        assert_eq!(r.varint().unwrap_err().check(), Check::ReeVarint);
    }

    #[test]
    fn max_u64_round_trips_in_ten_bytes() {
        let bytes = to_vec(u64::MAX);
        assert_eq!(bytes.len(), 10);
        let mut r = Reader::new(&bytes);
        assert_eq!(r.varint().unwrap(), u64::MAX);
    }
}
