//! Little-endian, bounds-checked byte reading and writing.
//!
//! Every read is checked against the buffer, and every failure carries the
//! [`Check`] the caller attached to the reader, so a truncated payload in a
//! `HEAD` chunk reports `head.*` rather than a generic parse error.

use crate::check::Check;
use crate::error::{Error, Result};

/// A cursor over a byte slice with checked little-endian reads.
#[derive(Debug, Clone)]
pub struct Reader<'a> {
    buf: &'a [u8],
    pos: usize,
    check: Check,
}

impl<'a> Reader<'a> {
    /// A reader that reports truncation as [`Check::DirChunkExtent`].
    ///
    /// Callers parsing a specific structure should prefer [`Reader::checked`].
    pub fn new(buf: &'a [u8]) -> Self {
        Reader {
            buf,
            pos: 0,
            check: Check::DirChunkExtent,
        }
    }

    /// A reader whose truncation errors report `check`.
    pub fn checked(buf: &'a [u8], check: Check) -> Self {
        Reader { buf, pos: 0, check }
    }

    /// The same reader with a different truncation check.
    pub fn with_check(mut self, check: Check) -> Self {
        self.check = check;
        self
    }

    /// The check reported when a read runs past the end.
    pub fn check(&self) -> Check {
        self.check
    }

    /// Bytes consumed so far.
    pub fn pos(&self) -> usize {
        self.pos
    }

    /// Bytes left.
    pub fn remaining(&self) -> usize {
        self.buf.len() - self.pos
    }

    /// Whether the reader is exhausted.
    pub fn is_empty(&self) -> bool {
        self.pos == self.buf.len()
    }

    /// The whole underlying buffer.
    pub fn buffer(&self) -> &'a [u8] {
        self.buf
    }

    /// The not-yet-consumed tail.
    pub fn tail(&self) -> &'a [u8] {
        &self.buf[self.pos..]
    }

    fn truncate(&self, want: usize) -> Result<()> {
        if self.remaining() < want {
            return Err(Error::new(
                self.check,
                format!(
                    "truncated: need {want} byte(s) at offset {}, {} remaining",
                    self.pos,
                    self.remaining()
                ),
            ));
        }
        Ok(())
    }

    /// Read one byte.
    pub fn u8(&mut self) -> Result<u8> {
        self.truncate(1)?;
        let v = self.buf[self.pos];
        self.pos += 1;
        Ok(v)
    }

    /// Read a `u16`.
    pub fn u16(&mut self) -> Result<u16> {
        Ok(u16::from_le_bytes(self.array::<2>()?))
    }

    /// Read a `u32`.
    pub fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.array::<4>()?))
    }

    /// Read a `u64`.
    pub fn u64(&mut self) -> Result<u64> {
        Ok(u64::from_le_bytes(self.array::<8>()?))
    }

    /// Read a fixed-size array.
    pub fn array<const N: usize>(&mut self) -> Result<[u8; N]> {
        self.truncate(N)?;
        let mut out = [0u8; N];
        out.copy_from_slice(&self.buf[self.pos..self.pos + N]);
        self.pos += N;
        Ok(out)
    }

    /// Borrow the next `n` bytes.
    pub fn bytes(&mut self, n: usize) -> Result<&'a [u8]> {
        self.truncate(n)?;
        let out = &self.buf[self.pos..self.pos + n];
        self.pos += n;
        Ok(out)
    }

    /// Borrow the whole tail.
    pub fn rest(&mut self) -> &'a [u8] {
        let out = &self.buf[self.pos..];
        self.pos = self.buf.len();
        out
    }

    /// Skip `n` bytes.
    pub fn skip(&mut self, n: usize) -> Result<()> {
        self.truncate(n)?;
        self.pos += n;
        Ok(())
    }

    /// Read a varint ([`section 5.2`](crate::varint)).
    pub fn varint(&mut self) -> Result<u64> {
        crate::varint::decode(self)
    }

    /// Read a varint bounded by `max`, rejecting a value above it before allocation.
    pub fn varint_bounded(&mut self, max: u64) -> Result<u64> {
        let v = self.varint()?;
        if v > max {
            return Err(Error::new(
                self.check,
                format!("varint value {v} exceeds the bound {max}"),
            ));
        }
        Ok(v)
    }

    /// Read a UTF-8 string of `n` bytes.
    pub fn utf8(&mut self, n: usize) -> Result<&'a str> {
        let bytes = self.bytes(n)?;
        core::str::from_utf8(bytes).map_err(|e| {
            Error::new(
                self.check,
                format!("invalid UTF-8 at offset {}: {e}", self.pos - n),
            )
        })
    }
}

/// A growable little-endian output buffer.
#[derive(Debug, Default, Clone)]
pub struct Writer {
    buf: Vec<u8>,
}

impl Writer {
    /// An empty writer.
    pub fn new() -> Self {
        Writer { buf: Vec::new() }
    }

    /// An empty writer with `capacity` bytes preallocated.
    pub fn with_capacity(capacity: usize) -> Self {
        Writer {
            buf: Vec::with_capacity(capacity),
        }
    }

    /// Bytes written so far.
    pub fn len(&self) -> usize {
        self.buf.len()
    }

    /// Whether nothing has been written.
    pub fn is_empty(&self) -> bool {
        self.buf.is_empty()
    }

    /// The bytes written so far.
    pub fn as_slice(&self) -> &[u8] {
        &self.buf
    }

    /// Consume the writer, yielding its bytes.
    pub fn into_vec(self) -> Vec<u8> {
        self.buf
    }

    /// Append one byte.
    pub fn u8(&mut self, v: u8) {
        self.buf.push(v);
    }

    /// Append a `u16`.
    pub fn u16(&mut self, v: u16) {
        self.buf.extend_from_slice(&v.to_le_bytes());
    }

    /// Append a `u32`.
    pub fn u32(&mut self, v: u32) {
        self.buf.extend_from_slice(&v.to_le_bytes());
    }

    /// Append a `u64`.
    pub fn u64(&mut self, v: u64) {
        self.buf.extend_from_slice(&v.to_le_bytes());
    }

    /// Append raw bytes.
    pub fn bytes(&mut self, v: &[u8]) {
        self.buf.extend_from_slice(v);
    }

    /// Append a varint.
    pub fn varint(&mut self, v: u64) {
        crate::varint::encode(self, v);
    }

    /// Pad with zero bytes until the length is a multiple of `align`.
    pub fn pad_to(&mut self, align: usize) {
        debug_assert!(align.is_power_of_two());
        while self.buf.len() % align != 0 {
            self.buf.push(0);
        }
    }

    /// Overwrite the `u32` at `at`.
    ///
    /// Used for back-patching offsets once a layout is known.
    pub fn patch_u32(&mut self, at: usize, v: u32) {
        self.buf[at..at + 4].copy_from_slice(&v.to_le_bytes());
    }

    /// Overwrite the `u64` at `at`.
    pub fn patch_u64(&mut self, at: usize, v: u64) {
        self.buf[at..at + 8].copy_from_slice(&v.to_le_bytes());
    }

    /// Overwrite the bytes at `at` with `v`.
    pub fn patch_bytes(&mut self, at: usize, v: &[u8]) {
        self.buf[at..at + v.len()].copy_from_slice(v);
    }
}
