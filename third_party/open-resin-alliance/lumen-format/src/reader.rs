//! Reading a file: [`LumenFile`], including random access to one layer.
//!
//! Opening validates, then parses only what is needed: the fixed header, the
//! directory, `LTBL` and the chunks that describe the print. Layer masks are
//! decoded on demand, one `LAYR` chunk at a time, so reading layer 1 of a
//! 2,000-layer print decompresses the one chunk that holds it rather than the
//! whole file. For a firmware reader that pulls layers through a fixed buffer,
//! that is the whole point of the chunked design ([`spec/12-compression.md`]
//! section 6.2), and the cache here holds exactly one decompressed chunk at a
//! time - the one last asked for.
//!
//! A `(layer, sector)` is addressed by its `LTBL` entry: the entry names the
//! `LAYR` chunk holding the layer's run and the slice of that chunk's output the
//! layer occupies, so a single-sector layer costs one chunk read and a
//! multi-sector layer costs as many as it has sectors. A reader that prints one
//! material reads the layer's first entry and nothing else, which is what
//! [`LumenFile::layer`] does; [`LumenFile::layer_sectors`] reads every sector,
//! and [`LumenFile::is_single_material_complete`] says whether the first way
//! loses anything.
//!
//! Opening validates and then parses, so a caller that also runs
//! [`crate::validate`] separately pays for the container walk twice. Callers
//! that want only a verdict should not open the file.

use crate::check::Check;
use crate::chunkio;
use crate::chunks::extd::Extension;
use crate::chunks::head::Head;
use crate::chunks::lhas::{self, LayerHashes};
use crate::chunks::ltbl::{LayerEntry, LayerTable};
use crate::chunks::preview::Preview;
use crate::chunks::zdic::ZstdDictionary;
use crate::chunks::{self, json_chunks};
use crate::container::{self, ChunkDescriptor, ChunkType, Directory, FileHeader};
use crate::crypto::{self, Auth, Cipher, SessionKey};
use crate::error::{Error, Result};
use crate::json::{Meta, Profile, Timing};
use crate::ree::{self, DecodedLayer};
use crate::timing::{self, Resolved};
use crate::validate::{Level, Validator};
use std::cell::RefCell;

/// One sector's decoded mask on one layer.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecodedSector {
    /// The sector this mask belongs to.
    pub sector_id: u32,
    /// The decoded mask.
    pub layer: DecodedLayer,
}

/// One `LAYR` chunk: a sector's masks for one group of layers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LayrChunk {
    /// The chunk's index in the directory, which is what an `LTBL` entry names
    /// and what a sealed frame's associated data binds it to.
    pub index: u32,
    /// The chunk's directory entry.
    pub descriptor: ChunkDescriptor,
}

/// An open LUMEN file.
#[derive(Debug)]
pub struct LumenFile<'a> {
    buf: &'a [u8],
    header: FileHeader,
    directory: Directory,
    head: Head,
    meta: Meta,
    profile: Option<Profile>,
    previews: Vec<Preview>,
    extensions: Vec<Extension>,
    dictionary: Option<ZstdDictionary>,
    layer_hashes: Option<LayerHashes>,
    layer_table: LayerTable,
    layr_chunks: Vec<LayrChunk>,
    voxl: Option<Vec<u8>>,
    auth: Option<Auth>,
    cipher: Option<Cipher>,
    key: Option<SessionKey>,
    level: Level,
    cache: RefCell<Option<(u32, Vec<u8>)>>,
}

impl<'a> LumenFile<'a> {
    /// Open without checking the whole of section 11 first.
    ///
    /// [`LumenFile::open`] runs every check of section 11 before it returns, and
    /// one of them walks each slice's stream. A caller that wants a single layer,
    /// a layer preview for instance, pays for that walk without asking. This
    /// parses the container and its chunks and checks nothing: it leaves the
    /// streams to [`LumenFile::layer`], which reports a malformed one when it
    /// reaches it.
    pub fn open_unvalidated(buf: &'a [u8]) -> Result<LumenFile<'a>> {
        LumenFile::assemble(buf, None, None)
    }

    /// Open a plaintext file, validating it against `level`.
    pub fn open(buf: &'a [u8], level: Level) -> Result<LumenFile<'a>> {
        LumenFile::assemble(buf, Some(level), None)
    }

    /// Open a file whose session key is already known.
    pub fn open_with_key(buf: &'a [u8], level: Level, key: SessionKey) -> Result<LumenFile<'a>> {
        LumenFile::assemble(buf, Some(level), Some(key))
    }

    /// Open a password-protected file.
    pub fn open_with_password(
        buf: &'a [u8],
        level: Level,
        password: &str,
    ) -> Result<LumenFile<'a>> {
        let auth = auth_of(buf)?;
        let key = crypto::unwrap_password(&auth, password)?;
        LumenFile::assemble(buf, Some(level), Some(key))
    }

    /// Open a machine-bound file with the recipient's X25519 private key.
    pub fn open_with_machine_key(
        buf: &'a [u8],
        level: Level,
        private_key: &[u8; 32],
    ) -> Result<LumenFile<'a>> {
        let auth = auth_of(buf)?;
        let key = crypto::unwrap_machine(&auth, private_key)?;
        LumenFile::assemble(buf, Some(level), Some(key))
    }

    fn assemble(
        buf: &'a [u8],
        level: Option<Level>,
        key: Option<SessionKey>,
    ) -> Result<LumenFile<'a>> {
        if let Some(level) = level {
            let mut validator = Validator::new(level);
            if let Some(key) = key {
                validator = validator.with_key(key);
            }
            validator.validate(buf)?;
        }

        let header = FileHeader::parse(buf)?;
        let directory = container::parse_directory(buf, &header)?;
        let auth = match directory.find(ChunkType::AUTH) {
            None => None,
            Some(d) => Some(crypto::parse_auth(chunkio::stored(buf, d)?)?),
        };
        let cipher = auth.as_ref().map(|a| a.cipher);
        let parts = Parts {
            buf,
            dir: &directory,
            cipher,
            key: key.as_ref(),
        };

        let head = Head::parse(&parts.required(ChunkType::HEAD)?)?;
        let meta = json_chunks::parse_meta(&parts.required(ChunkType::META)?)?;
        let profile = match parts.optional_required(ChunkType::PROF)? {
            None => None,
            Some(bytes) => Some(json_chunks::parse_profile(&bytes)?),
        };
        let mut previews = Vec::new();
        for d in directory.find_all(ChunkType::PREV).collect::<Vec<_>>() {
            let stored = chunkio::stored(buf, d)?;
            let Some(bytes) = chunkio::payload(d, stored, cipher, key.as_ref())? else {
                continue;
            };
            previews.push(Preview {
                role: crate::chunks::preview::PreviewRole::from_flags(d.flags)?,
                png: bytes,
            });
        }
        let mut extensions = Vec::new();
        for d in directory.find_all(ChunkType::EXTD).collect::<Vec<_>>() {
            let stored = chunkio::stored(buf, d)?;
            let Some(frame) = chunkio::payload(d, stored, cipher, key.as_ref())? else {
                continue;
            };
            // Validation has already rejected a malformed frame on a payload it
            // could read, so a failure here means the descriptor did not say the
            // payload was a frame - an extension we do not implement, whose bytes
            // are opaque to us.
            if let Ok(ext) = Extension::parse(&frame, d.flags) {
                extensions.push(ext);
            }
        }
        let dictionary = match parts.optional_required(ChunkType::ZDIC)? {
            None => None,
            Some(bytes) => Some(ZstdDictionary::parse(&bytes)?),
        };
        let layer_hashes = match directory.find(ChunkType::LHAS) {
            None => None,
            Some(d) => Some(LayerHashes::parse(chunkio::stored(buf, d)?)?),
        };
        let layer_table = LayerTable::parse(&parts.required(ChunkType::LTBL)?)?;
        let layr_chunks = directory
            .descriptors
            .iter()
            .enumerate()
            .filter(|(_, d)| !d.is_null() && d.chunk_type == ChunkType::LAYR)
            .map(|(index, d)| LayrChunk {
                index: index as u32,
                descriptor: *d,
            })
            .collect();
        let voxl = parts.optional_required(ChunkType::VOXL)?;

        Ok(LumenFile {
            buf,
            header,
            directory,
            head,
            meta,
            profile,
            previews,
            extensions,
            dictionary,
            layer_hashes,
            layer_table,
            layr_chunks,
            voxl,
            auth,
            cipher,
            key,
            // An unvalidated open has no level to carry; reading is then loose,
            // which is what a caller that skipped validation wants anyway.
            level: level.unwrap_or_default(),
            cache: RefCell::new(None),
        })
    }

    /// Recover the session key from a password, without reopening.
    pub fn recover_password(&self, password: &str) -> Result<SessionKey> {
        let auth = self
            .auth
            .as_ref()
            .ok_or_else(|| Error::new(Check::CryptNoKey, "the file has no AUTH chunk"))?;
        crypto::unwrap_password(auth, password)
    }

    /// Recover the session key from a recipient private key, without reopening.
    pub fn recover_machine_key(&self, private_key: &[u8; 32]) -> Result<SessionKey> {
        let auth = self
            .auth
            .as_ref()
            .ok_or_else(|| Error::new(Check::CryptNoKey, "the file has no AUTH chunk"))?;
        crypto::unwrap_machine(auth, private_key)
    }

    /// The file's bytes.
    pub fn bytes(&self) -> &'a [u8] {
        self.buf
    }

    /// The fixed file header.
    pub fn header(&self) -> &FileHeader {
        &self.header
    }

    /// The chunk directory.
    pub fn directory(&self) -> &Directory {
        &self.directory
    }

    /// The `HEAD` chunk.
    pub fn head(&self) -> &Head {
        &self.head
    }

    /// The `META` chunk.
    pub fn meta(&self) -> &Meta {
        &self.meta
    }

    /// The `PROF` chunk, if present. A file carries at most one.
    pub fn profile(&self) -> Option<&Profile> {
        self.profile.as_ref()
    }

    /// Every sector `META` defines, in the order it lists them.
    ///
    /// Sector 0 is implicit and has no entry here.
    pub fn meta_sectors(&self) -> &[crate::json::Sector] {
        self.meta.sectors.as_deref().unwrap_or_default()
    }

    /// Every `PREV` chunk, in file order.
    pub fn previews(&self) -> &[Preview] {
        &self.previews
    }

    /// Every `EXTD` chunk whose frame could be read, in file order.
    pub fn extensions(&self) -> &[Extension] {
        &self.extensions
    }

    /// The `ZDIC` chunk, if present.
    pub fn dictionary(&self) -> Option<&ZstdDictionary> {
        self.dictionary.as_ref()
    }

    /// The `LHAS` chunk, if present.
    pub fn layer_hashes(&self) -> Option<&LayerHashes> {
        self.layer_hashes.as_ref()
    }

    /// The `LTBL` chunk.
    pub fn layer_table(&self) -> &LayerTable {
        &self.layer_table
    }

    /// Every `LAYR` chunk, in directory order.
    pub fn layr_chunks(&self) -> &[LayrChunk] {
        &self.layr_chunks
    }

    /// The `VOXL` payload, if present, verbatim.
    pub fn voxl(&self) -> Option<&[u8]> {
        self.voxl.as_deref()
    }

    /// The `AUTH` chunk, if present.
    pub fn auth(&self) -> Option<&Auth> {
        self.auth.as_ref()
    }

    /// The layer count.
    pub fn layer_count(&self) -> u32 {
        self.head.total_layers
    }

    /// Pixels in one layer mask.
    pub fn total_pixels(&self) -> u32 {
        self.head.total_pixels()
    }

    /// Whether the file declares sector-based layer encoding, i.e. whether some
    /// layer carries more than one sector (`head.multi_sector_flag`).
    ///
    /// This is informational: which sectors a layer carries is read from its
    /// `LTBL` entries, not from this flag.
    pub fn multi_sector(&self) -> bool {
        self.header.multi_sector()
    }

    /// Whether the validation level this file was opened at is strict.
    pub fn level(&self) -> Level {
        self.level
    }

    /// Whether the file has a session key available.
    pub fn is_unlocked(&self) -> bool {
        self.key.is_some()
    }

    /// The decompressed, decrypted output of the `LAYR` chunk at directory index
    /// `index`: the concatenation of every slice the table places in it.
    pub fn layr_chunk_data(&self, index: u32) -> Result<Vec<u8>> {
        self.with_chunk(index, |data| Ok(data.to_vec()))
    }

    /// Run `f` over the decompressed output of the `LAYR` chunk at directory
    /// index `index`, decompressing it first if it is not the cached one.
    ///
    /// The cache holds one chunk, so fetching the layers of one chunk is free
    /// after the first, and walking layers in order costs one decompression per
    /// chunk a layer touches.
    fn with_chunk<T>(&self, index: u32, f: impl FnOnce(&[u8]) -> Result<T>) -> Result<T> {
        if self.cache.borrow().as_ref().map(|(k, _)| *k) != Some(index) {
            let data = self.decompress_chunk(index)?;
            *self.cache.borrow_mut() = Some((index, data));
        }
        let guard = self.cache.borrow();
        let (_, data) = guard.as_ref().expect("filled immediately above");
        f(data)
    }

    /// The descriptor of the `LAYR` chunk at directory index `index`.
    fn layr_descriptor(&self, index: u32) -> Result<&ChunkDescriptor> {
        let descriptor = self
            .directory
            .descriptors
            .get(index as usize)
            .filter(|d| !d.is_null() && d.chunk_type == ChunkType::LAYR)
            .ok_or_else(|| {
                Error::new(
                    Check::LtblFirstLayrInRange,
                    format!("directory index {index} is not a LAYR chunk"),
                )
            })?;
        Ok(descriptor)
    }

    fn decompress_chunk(&self, index: u32) -> Result<Vec<u8>> {
        let descriptor = self.layr_descriptor(index)?;
        let stored = chunkio::stored(self.buf, descriptor)?;
        let frame = chunkio::layr_frame(descriptor, index, stored, self.cipher, self.key.as_ref())?
            .ok_or_else(|| {
                Error::new(
                    Check::CryptNoKey,
                    "the frame is sealed and no session key is available",
                )
            })?;
        let dict = self.dictionary.as_ref().map(|d| d.dict_bytes.as_slice());
        // The bound is the file's own: the layers whose entries point into this
        // chunk, each of which can hold at most a grayscale REE stream of this
        // display. A frame's bytes cannot say how far it legitimately expands -
        // a block of repeating layers compresses past any ratio an encoder's own
        // output could justify - so the layer table is what bounds it, and a
        // reader that used a ratio instead would refuse conforming files.
        let bound = chunks::allocation_bound(self.slices_into(index), self.total_pixels());
        chunks::decompress_frame(&frame, dict, bound)
    }

    /// How many slices the layer table points into `index`, floored at one.
    ///
    /// The same definition the validator uses for `frame.allocation_bound`, so the
    /// bound this reader allocates against is the bound the specification states:
    /// an entry that carries bytes counts, an entry that carries none does not,
    /// and a chunk nothing points into still gets one layer's worth.
    fn slices_into(&self, index: u32) -> u64 {
        let count = (0..self.layer_table.layer_count)
            .map(|layer| {
                self.layer_table
                    .layer_entries(layer)
                    .iter()
                    .filter(|entry| !entry.is_empty() && entry.first_layr == index)
                    .count() as u64
            })
            .sum::<u64>();
        count.max(1)
    }

    /// One entry's slice of its `LAYR` chunk's decompressed output.
    fn slice(&self, entry: &LayerEntry) -> Result<Vec<u8>> {
        if entry.is_empty() {
            return Ok(Vec::new());
        }
        let start = entry.data_offset as usize;
        let len = entry.data_size as usize;
        self.with_chunk(entry.first_layr, |chunk| {
            chunk
                .get(start..start.saturating_add(len))
                .map(|slice| slice.to_vec())
                .ok_or_else(|| {
                    Error::new(
                        Check::LtblOffsetWithinChunk,
                        format!(
                            "a slice of {len} bytes at offset {start} lies outside its chunk's \
                             {} bytes",
                            chunk.len()
                        ),
                    )
                })
        })
    }

    /// The stored bytes of layer `index`: its sectors' slices, concatenated in
    /// ascending `sector_id`.
    ///
    /// This is the byte range `LHAS` hashes for the layer (section 4.10), which
    /// is why it is the concatenation rather than any one sector's data.
    fn layer_data(&self, index: u32) -> Result<Vec<u8>> {
        let entries = self.entries_of(index)?;
        let mut out = Vec::new();
        for entry in entries {
            out.extend_from_slice(&self.slice(entry)?);
        }
        Ok(out)
    }

    /// The `LTBL` entries of layer `index`.
    fn entries_of(&self, index: u32) -> Result<&[LayerEntry]> {
        let entries = self.layer_table.layer_entries(index);
        if entries.is_empty() {
            return Err(Error::new(
                Check::LtblLayerIndexRange,
                format!("layer {index} does not exist"),
            ));
        }
        Ok(entries)
    }

    /// The decoded mask of layer `index` as a single-material reader prints it.
    ///
    /// That reader reads the layer's first entry - sector 0's, which every layer
    /// with data has - and skips the rest, so this is sector 0's mask and not the
    /// union of every sector's. A layer whose first entry carries no data is
    /// empty here even when a later sector holds data;
    /// [`LumenFile::is_single_material_complete`] reports that case, and
    /// [`LumenFile::layer_sectors`] reaches the other sectors.
    pub fn layer(&self, index: u32) -> Result<DecodedLayer> {
        let total_pixels = self.total_pixels();
        let entries = self.entries_of(index)?;
        let entry = &entries[0];
        if entry.is_empty() {
            return Ok(DecodedLayer::empty(total_pixels));
        }
        let data = self.slice(entry)?;
        ree::decode(&data, total_pixels, self.level.is_strict())
    }

    /// Every sector's decoded mask on layer `index`, in ascending `sector_id`.
    ///
    /// A sector with no data on this layer has no mask and is not reported.
    pub fn layer_sectors(&self, index: u32) -> Result<Vec<DecodedSector>> {
        let total_pixels = self.total_pixels();
        let entries = self.entries_of(index)?;
        let mut out = Vec::new();
        for entry in entries {
            if entry.is_empty() {
                continue;
            }
            let data = self.slice(entry)?;
            out.push(DecodedSector {
                sector_id: entry.sector_id,
                layer: ree::decode(&data, total_pixels, self.level.is_strict())?,
            });
        }
        Ok(out)
    }

    /// Whether a single-material reader would print every layer faithfully.
    ///
    /// False when any layer carries data in a sector other than 0, which is
    /// content such a reader never reads and would drop silently: it must report
    /// the file incomplete rather than complete (section 7.2).
    pub fn is_single_material_complete(&self) -> bool {
        !(0..self.layer_count()).any(|layer| {
            self.layer_table
                .layer_entries(layer)
                .iter()
                .any(|entry| entry.sector_id != 0 && !entry.is_empty())
        })
    }

    /// Resolve one `(layer, sector)`'s timing.
    ///
    /// The returned values already carry the sector's `META.sectors` entry, the
    /// bottom and transition blend with the counts that sector carries or
    /// inherits, and the `(layer, sector)`'s own `LROV` payload. Overrides are
    /// not opt-in ([`spec/08-print-control.md`] section 4.5): a reader that does
    /// not apply them must refuse a file that carries an `LROV` chunk, because
    /// printing the layer at META's exposure instead of its override fails
    /// quietly. This method is therefore the only supported way to read a
    /// layer's timing.
    pub fn timing_for(&self, layer: u32, sector_id: u32) -> Result<Resolved> {
        self.entries_of(layer)?;
        let sector = match sector_id {
            0 => None,
            _ => self
                .meta
                .sectors
                .as_deref()
                .and_then(|sectors| sectors.iter().find(|s| s.sector_id == sector_id)),
        };
        let overrides = self.overrides_for(layer, sector_id)?;
        timing::resolve(&self.meta, sector, overrides.as_ref(), layer, sector_id)
    }

    /// The `LROV` payload of `(layer, sector)`, when it has one.
    fn overrides_for(&self, layer: u32, sector_id: u32) -> Result<Option<Timing>> {
        let Some(entry) = self.layer_table.entry(layer, sector_id) else {
            return Ok(None);
        };
        if entry.first_lrov == 0 {
            return Ok(None);
        }
        let descriptor = self
            .directory
            .descriptors
            .get(entry.first_lrov as usize)
            .filter(|d| !d.is_null() && d.chunk_type == ChunkType::LROV)
            .ok_or_else(|| {
                Error::new(
                    Check::LtblFirstLrovInRange,
                    format!(
                        "layer {layer} sector {sector_id} names directory index {}, which is not \
                         an LROV chunk",
                        entry.first_lrov
                    ),
                )
            })?;
        let stored = chunkio::stored(self.buf, descriptor)?;
        let bytes = chunkio::payload(descriptor, stored, self.cipher, self.key.as_ref())?
            .ok_or_else(|| {
                Error::new(
                    Check::CryptNoKey,
                    "the LROV payload is sealed and no session key is available",
                )
            })?;
        Ok(Some(json_chunks::parse_lrov(&bytes)?))
    }

    /// Verify layer `index` against the `LHAS` leaf table and Merkle path.
    pub fn verify_layer(&self, index: u32) -> Result<()> {
        let hashes = self
            .layer_hashes
            .as_ref()
            .ok_or_else(|| Error::new(Check::LhasFrame, "the file carries no LHAS chunk"))?;
        let stored_leaf = *hashes.layer_hashes.get(index as usize).ok_or_else(|| {
            Error::new(
                Check::LhasLayerCount,
                format!("layer {index} is outside the hash table"),
            )
        })?;
        let data = self.layer_data(index)?;
        let leaf = lhas::leaf_hash(&data);
        if leaf != stored_leaf {
            return Err(Error::new(
                Check::LhasLeafMatch,
                format!("layer {index} does not hash to its stored leaf"),
            ));
        }
        let path = lhas::merkle_path(&hashes.layer_hashes, index as usize);
        if !lhas::verify_leaf(&leaf, &path, index as usize, &hashes.merkle_root) {
            return Err(Error::new(
                Check::LhasRootRecompute,
                format!("layer {index}'s Merkle path does not reach the stored root"),
            ));
        }
        Ok(())
    }

    /// Verify every layer and the Merkle root.
    pub fn verify_all(&self) -> Result<()> {
        let hashes = self
            .layer_hashes
            .as_ref()
            .ok_or_else(|| Error::new(Check::LhasFrame, "the file carries no LHAS chunk"))?;
        for index in 0..self.layer_count() {
            let data = self.layer_data(index)?;
            let leaf = lhas::leaf_hash(&data);
            match hashes.layer_hashes.get(index as usize) {
                Some(stored) if *stored == leaf => {}
                Some(_) => {
                    return Err(Error::new(
                        Check::LhasLeafMatch,
                        format!("layer {index} does not hash to its stored leaf"),
                    ))
                }
                None => {
                    return Err(Error::new(
                        Check::LhasLayerCount,
                        format!("the hash table holds no layer {index}"),
                    ))
                }
            }
        }
        if lhas::merkle_root(&hashes.layer_hashes) != hashes.merkle_root {
            return Err(Error::new(
                Check::LhasRootRecompute,
                "the stored Merkle root is not the root of the stored leaf hashes",
            ));
        }
        Ok(())
    }
}

/// The chunk-payload reader for one container walk.
struct Parts<'a> {
    buf: &'a [u8],
    dir: &'a Directory,
    cipher: Option<Cipher>,
    key: Option<&'a SessionKey>,
}

impl Parts<'_> {
    /// A chunk's payload, or `None` when the chunk is absent or unreadable.
    fn payload(&self, chunk_type: ChunkType) -> Result<Option<Vec<u8>>> {
        let Some(d) = self.dir.find(chunk_type) else {
            return Ok(None);
        };
        let stored = chunkio::stored(self.buf, d)?;
        chunkio::payload(d, stored, self.cipher, self.key)
    }

    /// A required chunk's payload, distinguishing "missing" from "sealed".
    fn required(&self, chunk_type: ChunkType) -> Result<Vec<u8>> {
        let Some(bytes) = self.payload(chunk_type)? else {
            return Err(self.unreadable(chunk_type));
        };
        Ok(bytes)
    }

    /// An optional chunk's payload: `None` when absent, an error when the chunk
    /// is present but cannot be opened.
    fn optional_required(&self, chunk_type: ChunkType) -> Result<Option<Vec<u8>>> {
        if self.dir.find(chunk_type).is_none() {
            return Ok(None);
        }
        match self.payload(chunk_type)? {
            Some(bytes) => Ok(Some(bytes)),
            None => Err(self.unreadable(chunk_type)),
        }
    }

    /// The error for a chunk that is present but sealed with no key.
    fn unreadable(&self, chunk_type: ChunkType) -> Error {
        Error::new(
            Check::CryptNoKey,
            format!(
                "{chunk_type} is sealed and no session key is available; open the file with a password or a recipient key"
            ),
        )
    }
}

/// Parse the `AUTH` chunk without a key.
fn auth_of(buf: &[u8]) -> Result<Auth> {
    let header = FileHeader::parse(buf)?;
    let directory = container::parse_directory(buf, &header)?;
    let d = directory
        .find(ChunkType::AUTH)
        .ok_or_else(|| Error::new(Check::CryptNoKey, "the file carries no AUTH chunk"))?;
    crypto::parse_auth(chunkio::stored(buf, d)?)
}
