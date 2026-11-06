//! The container: 32-byte file header, 32-byte chunk descriptors, the directory
//! at the end of the file, and the 8-byte trailer ([`spec/02-file-structure.md`]).

use crate::check::Check;
use crate::error::{Error, Result};
use crate::io::Reader;

/// File magic, `LUMN`.
pub const MAGIC: [u8; 4] = *b"LUMN";
/// Trailer magic, `LEND`.
pub const TRAILER_MAGIC: [u8; 4] = *b"LEND";
/// Size of the fixed file header at offset 0.
pub const FILE_HEADER_SIZE: usize = 32;
/// Size of one chunk descriptor.
pub const CHUNK_DESCRIPTOR_SIZE: usize = 32;
/// Size of the directory trailer.
pub const TRAILER_SIZE: usize = 8;

/// `header.flags` bit 1: the file uses sector-based layer encoding.
pub const FLAG_MULTI_SECTOR: u32 = 1 << 1;
/// `header.flags` bit 3: an `AUTH` chunk is present and content chunks are sealed.
pub const FLAG_ENCRYPTED: u32 = 1 << 3;
/// Bits a conforming v1 writer must leave clear: 0, 2, 4 and 5-31.
pub const FILE_HEADER_RESERVED_MASK: u32 = !(FLAG_MULTI_SECTOR | FLAG_ENCRYPTED);

/// Chunk descriptor bit 4: this payload is sealed.
pub const CHUNK_FLAG_ENCRYPTED: u32 = 1 << 4;

/// CRC-32C (Castagnoli) as the container and the `LTBL`/trailer use it.
pub fn crc32c(data: &[u8]) -> u32 {
    crc32c::crc32c(data)
}

/// The check value the specification's generators self-test against.
#[cfg(test)]
const CRC32C_CHECK_VALUE: u32 = 0xE306_9283;

#[cfg(test)]
mod crc_tests {
    use super::*;

    #[test]
    fn standard_check_value() {
        assert_eq!(crc32c(b"123456789"), CRC32C_CHECK_VALUE);
    }
}

/// A four-byte chunk type tag.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ChunkType(pub [u8; 4]);

impl ChunkType {
    /// `HEAD` - display dimensions, layer count, encoder identity.
    pub const HEAD: ChunkType = ChunkType(*b"HEAD");
    /// `META` - print parameters as JSON.
    pub const META: ChunkType = ChunkType(*b"META");
    /// `PROF` - reusable named print profile.
    pub const PROF: ChunkType = ChunkType(*b"PROF");
    /// `AUTH` - encryption metadata.
    pub const AUTH: ChunkType = ChunkType(*b"AUTH");
    /// `LROV` - one (layer, sector)'s timing overrides.
    pub const LROV: ChunkType = ChunkType(*b"LROV");
    /// `PREV` - PNG preview image.
    pub const PREV: ChunkType = ChunkType(*b"PREV");
    /// `LTBL` - layer table, mapping (layer, sector) pairs to chunks.
    pub const LTBL: ChunkType = ChunkType(*b"LTBL");
    /// `ZDIC` - zstd dictionary shared by the `LAYR` frames.
    pub const ZDIC: ChunkType = ChunkType(*b"ZDIC");
    /// `LAYR` - one sector's mask data for one layer group, as a zstd frame.
    pub const LAYR: ChunkType = ChunkType(*b"LAYR");
    /// `LHAS` - per-layer hashes and Merkle root.
    pub const LHAS: ChunkType = ChunkType(*b"LHAS");
    /// `VOXL` - embedded scene, opaque to LUMEN.
    pub const VOXL: ChunkType = ChunkType(*b"VOXL");
    /// `EXTD` - vendor or future-standard extension.
    pub const EXTD: ChunkType = ChunkType(*b"EXTD");

    /// Every chunk type this specification defines.
    pub const ALL: [ChunkType; 12] = [
        ChunkType::HEAD,
        ChunkType::META,
        ChunkType::PROF,
        ChunkType::AUTH,
        ChunkType::LROV,
        ChunkType::PREV,
        ChunkType::LTBL,
        ChunkType::ZDIC,
        ChunkType::LAYR,
        ChunkType::LHAS,
        ChunkType::VOXL,
        ChunkType::EXTD,
    ];

    /// The raw tag bytes.
    pub fn as_bytes(&self) -> &[u8; 4] {
        &self.0
    }

    /// Whether this is a chunk type v1 defines.
    pub fn is_known(&self) -> bool {
        ChunkType::ALL.contains(self)
    }

    /// Whether the payload carries a zstd frame, per the normative table in
    /// [`spec/12-compression.md`] section 6.3.
    ///
    /// `LAYR` is excluded, and not because it is uncompressed: its payload is a
    /// version field plus a frame the container does not itself decompress, in
    /// the same way `EXTD`'s compression is per-extension and `PREV`'s is none.
    /// `EXTD` is excluded too: the frame is opaque to this crate, so the caller
    /// decides.
    pub fn is_compressed(&self) -> bool {
        matches!(
            *self,
            ChunkType::META | ChunkType::PROF | ChunkType::LROV | ChunkType::VOXL
        )
    }

    /// The tag as a display string, with `HEAD` rendered as `HEAD`.
    pub fn tag(&self) -> String {
        let trimmed: Vec<u8> = self.0.iter().copied().take_while(|b| *b != 0).collect();
        String::from_utf8_lossy(&trimmed).into_owned()
    }
}

impl core::fmt::Display for ChunkType {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.write_str(&self.tag())
    }
}

/// The fixed 32-byte file header at offset 0.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FileHeader {
    /// Container format version. `1` for this specification.
    pub version: u32,
    /// Byte offset from the start of the file to the chunk directory.
    pub dir_offset: u64,
    /// Number of chunks, matching the directory entries.
    pub chunk_count: u32,
    /// Bitfield: bit 1 `MULTI_SECTOR`, bit 3 `ENCRYPTED`.
    pub flags: u32,
    /// Sum of uncompressed chunk sizes, or `0` when unknown.
    pub total_uncompressed_size: u64,
}

impl FileHeader {
    /// Parse the fixed header.
    pub fn parse(buf: &[u8]) -> Result<FileHeader> {
        let mut r = Reader::checked(buf, Check::HeaderMagic);
        let magic = r.array::<4>()?;
        if magic != MAGIC {
            return Err(Error::new(
                Check::HeaderMagic,
                format!("expected LUMN, found {}", ChunkType(magic).tag()),
            ));
        }
        let version = r.u32()?;
        if version != 1 {
            return Err(Error::new(
                Check::HeaderVersion,
                format!("unsupported container version {version}"),
            ));
        }
        let dir_offset = r.u64()?;
        let chunk_count = r.u32()?;
        let flags = r.u32()?;
        let total_uncompressed_size = r.u64()?;
        Ok(FileHeader {
            version,
            dir_offset,
            chunk_count,
            flags,
            total_uncompressed_size,
        })
    }

    /// Serialize to exactly 32 bytes.
    pub fn to_bytes(&self) -> [u8; FILE_HEADER_SIZE] {
        let mut out = [0u8; FILE_HEADER_SIZE];
        out[0..4].copy_from_slice(&MAGIC);
        out[4..8].copy_from_slice(&self.version.to_le_bytes());
        out[8..16].copy_from_slice(&self.dir_offset.to_le_bytes());
        out[16..20].copy_from_slice(&self.chunk_count.to_le_bytes());
        out[20..24].copy_from_slice(&self.flags.to_le_bytes());
        out[24..32].copy_from_slice(&self.total_uncompressed_size.to_le_bytes());
        out
    }

    /// Whether the file declares sector-based layer encoding.
    pub fn multi_sector(&self) -> bool {
        self.flags & FLAG_MULTI_SECTOR != 0
    }

    /// Whether the file declares an `AUTH` chunk and sealed content.
    pub fn encrypted(&self) -> bool {
        self.flags & FLAG_ENCRYPTED != 0
    }

    /// Flags a v1 writer must leave clear.
    pub fn reserved_flags(&self) -> u32 {
        self.flags & FILE_HEADER_RESERVED_MASK
    }
}

/// One 32-byte chunk directory entry.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChunkDescriptor {
    /// Four-letter chunk type tag.
    pub chunk_type: ChunkType,
    /// Absolute byte offset of the payload. `0` marks a null descriptor.
    pub offset: u64,
    /// Payload size after decompression.
    pub size_uncompressed: u64,
    /// Stored size including any AEAD framing, or `0` for a raw payload.
    pub size_compressed: u64,
    /// Chunk-specific flags: bit 4 is `ENCRYPTED`, and `PREV`/`EXTD` define more.
    pub flags: u32,
}

impl ChunkDescriptor {
    /// A descriptor occupying no space, as a writer pre-allocating directory
    /// slots would leave it.
    pub const NULL: ChunkDescriptor = ChunkDescriptor {
        chunk_type: ChunkType([0, 0, 0, 0]),
        offset: 0,
        size_uncompressed: 0,
        size_compressed: 0,
        flags: 0,
    };

    /// Parse one descriptor.
    pub fn parse(buf: &[u8]) -> Result<ChunkDescriptor> {
        let mut r = Reader::checked(buf, Check::DirDescriptor);
        let chunk_type = ChunkType(r.array::<4>()?);
        let offset = r.u64()?;
        let size_uncompressed = r.u64()?;
        let size_compressed = r.u64()?;
        let flags = r.u32()?;
        Ok(ChunkDescriptor {
            chunk_type,
            offset,
            size_uncompressed,
            size_compressed,
            flags,
        })
    }

    /// Serialize to exactly 32 bytes.
    pub fn to_bytes(&self) -> [u8; CHUNK_DESCRIPTOR_SIZE] {
        let mut out = [0u8; CHUNK_DESCRIPTOR_SIZE];
        out[0..4].copy_from_slice(&self.chunk_type.0);
        out[4..12].copy_from_slice(&self.offset.to_le_bytes());
        out[12..20].copy_from_slice(&self.size_uncompressed.to_le_bytes());
        out[20..28].copy_from_slice(&self.size_compressed.to_le_bytes());
        out[28..32].copy_from_slice(&self.flags.to_le_bytes());
        out
    }

    /// Whether this slot holds no chunk.
    pub fn is_null(&self) -> bool {
        self.offset == 0
    }

    /// Whether this payload is sealed.
    pub fn is_encrypted(&self) -> bool {
        self.flags & CHUNK_FLAG_ENCRYPTED != 0
    }

    /// The on-disk byte length of this chunk: `size_uncompressed` for a raw
    /// payload, `size_compressed` when the chunk is compressed or sealed.
    ///
    /// A `LAYR` chunk reads both ways round without ambiguity: its
    /// `size_uncompressed` is the container's byte length - the version field
    /// plus the frame - and `size_compressed` is zero while that frame is in the
    /// clear and the same total once it is sealed.
    pub fn stored_len(&self) -> u64 {
        if self.size_compressed == 0 {
            self.size_uncompressed
        } else {
            self.size_compressed
        }
    }

    /// The half-open byte range this chunk occupies in the file.
    pub fn extent(&self) -> (u64, u64) {
        (self.offset, self.offset + self.stored_len())
    }
}

/// Read and verify the directory trailer, returning its CRC-32C.
pub fn parse_trailer(buf: &[u8]) -> Result<u32> {
    if buf.len() < TRAILER_SIZE {
        return Err(Error::new(
            Check::TrailerMagic,
            format!("file of {} bytes is too short for a trailer", buf.len()),
        ));
    }
    let tail = &buf[buf.len() - TRAILER_SIZE..];
    let magic = &tail[0..4];
    if magic != TRAILER_MAGIC {
        return Err(Error::new(
            Check::TrailerMagic,
            format!("expected LEND, found {}", ChunkType::from_tag_bytes(magic)),
        ));
    }
    Ok(u32::from_le_bytes([tail[4], tail[5], tail[6], tail[7]]))
}

impl ChunkType {
    fn from_tag_bytes(bytes: &[u8]) -> String {
        let mut raw = [0u8; 4];
        raw[..bytes.len().min(4)].copy_from_slice(&bytes[..bytes.len().min(4)]);
        ChunkType(raw).tag()
    }
}

/// Verify the trailer CRC-32C covers every preceding byte.
pub fn verify_trailer_crc(buf: &[u8]) -> Result<()> {
    let stored = parse_trailer(buf)?;
    let computed = crc32c(&buf[..buf.len() - TRAILER_SIZE]);
    if stored != computed {
        return Err(Error::new(
            Check::TrailerCrc32c,
            format!("trailer CRC-32C {stored:#010x} does not match file bytes {computed:#010x}"),
        ));
    }
    Ok(())
}

/// Parse the chunk directory.
///
/// Returns every descriptor in file order, including null ones; use
/// [`Directory::entries`] to iterate only the present chunks.
pub fn parse_directory(buf: &[u8], header: &FileHeader) -> Result<Directory> {
    let dir_offset = header.dir_offset as usize;
    let count = header.chunk_count as usize;
    if dir_offset < FILE_HEADER_SIZE || dir_offset > buf.len() {
        return Err(Error::new(
            Check::HeaderDirOffset,
            format!(
                "directory offset {dir_offset} is outside the {} bytes of file",
                buf.len()
            ),
        ));
    }
    let end = dir_offset
        .checked_add(count * CHUNK_DESCRIPTOR_SIZE)
        .ok_or_else(|| Error::new(Check::HeaderDirOffset, "directory length overflows"))?;
    if end + TRAILER_SIZE > buf.len() {
        return Err(Error::new(
            Check::HeaderDirOffset,
            format!("{count} descriptors at {dir_offset} do not fit before the trailer"),
        ));
    }
    let mut descriptors = Vec::with_capacity(count);
    let mut r = Reader::checked(&buf[dir_offset..end], Check::DirDescriptor);
    for _ in 0..count {
        descriptors.push(ChunkDescriptor::parse(r.bytes(CHUNK_DESCRIPTOR_SIZE)?)?);
    }
    Ok(Directory { descriptors })
}

/// The chunk directory: one descriptor per chunk, in file order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Directory {
    /// Every descriptor, including null ones.
    pub descriptors: Vec<ChunkDescriptor>,
}

impl Directory {
    /// An empty directory.
    pub fn new() -> Self {
        Directory {
            descriptors: Vec::new(),
        }
    }

    /// Non-null chunks, in file order.
    pub fn entries(&self) -> impl Iterator<Item = &ChunkDescriptor> {
        self.descriptors.iter().filter(|d| !d.is_null())
    }

    /// Non-null chunks carrying `chunk_type`, in file order.
    pub fn find_all(&self, chunk_type: ChunkType) -> impl Iterator<Item = &ChunkDescriptor> {
        self.entries().filter(move |d| d.chunk_type == chunk_type)
    }

    /// The first non-null chunk of `chunk_type`.
    ///
    /// Where the specification says a chunk appears at most once (`PROF`,
    /// `LROV`, `VOXL`, `ZDIC`), readers use the first.
    pub fn find(&self, chunk_type: ChunkType) -> Option<&ChunkDescriptor> {
        self.find_all(chunk_type).next()
    }

    /// Whether any non-null chunk carries `chunk_type`.
    pub fn contains(&self, chunk_type: ChunkType) -> bool {
        self.find(chunk_type).is_some()
    }

    /// The index of the first non-null descriptor, i.e. the first chunk.
    pub fn first_entry_index(&self) -> Option<usize> {
        self.descriptors.iter().position(|d| !d.is_null())
    }

    /// Push a descriptor.
    pub fn push(&mut self, descriptor: ChunkDescriptor) {
        self.descriptors.push(descriptor);
    }

    /// Serialize every descriptor, in order.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(self.descriptors.len() * CHUNK_DESCRIPTOR_SIZE);
        for d in &self.descriptors {
            out.extend_from_slice(&d.to_bytes());
        }
        out
    }

    /// The sum of every non-null chunk's `size_uncompressed`.
    pub fn total_uncompressed_size(&self) -> u64 {
        self.entries().map(|d| d.size_uncompressed).sum()
    }
}

impl Default for Directory {
    fn default() -> Self {
        Directory::new()
    }
}

/// The chunk type of the first chunk, or `None` if the directory is all null.
pub fn first_chunk_type(directory: &Directory) -> Option<ChunkType> {
    directory
        .first_entry_index()
        .map(|i| directory.descriptors[i].chunk_type)
}
