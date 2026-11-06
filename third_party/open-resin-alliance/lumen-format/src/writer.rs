//! Writing a file: [`Encoder`], which assembles a conforming `.lumen` container.
//!
//! The encoder owns the choices the specification leaves to it (section 5.7): it
//! picks a tag per layer, picks how many layers a `LAYR` chunk spans, and decides
//! whether to train a dictionary. Layer masks are encoded as they are pushed, so
//! the encoder never holds the pixel data of the whole print - only its run-end
//! encoded form.
//!
//! The layer axis is cut into groups of [`DEFAULT_LAYERS_PER_CHUNK`] layers (or
//! whatever [`Encoder::set_layers_per_chunk`] asks for), and each (sector,
//! layer-group) becomes one `LAYR` chunk holding that sector's masks for the
//! group as a single zstd frame. `LTBL` then records, per (layer, sector), which
//! chunk holds the layer's run, where in that chunk's decompressed output the
//! run sits, and which `LROV` chunk carries the (layer, sector)'s overrides.
//!
//! Two of `finish`'s passes are a function of one item each: one zstd frame per
//! (sector, layer-group) chunk, and one `LHAS` leaf per layer. Neither reads
//! another's result, so both run across worker threads
//! ([`Encoder::set_worker_threads`]) - which is where the time of a long print
//! sits once its masks are encoded. The file does not depend on how many: an
//! item is placed by the index it came from, not by the order it finished in.
//!
//! `finish` produces the container in the order section 3 recommends: `HEAD`,
//! `META`, the optional chunks, `LTBL`, `LAYR`, and the directory at the end.
//! Payloads are 8-byte aligned, as section 3.2 prefers, and the trailer's
//! CRC-32C covers every preceding byte.
//!
//! Encryption follows section 9.1 exactly: `HEAD`, `AUTH`, `LTBL`, `LHAS` and the
//! `LAYR` version fields stay plaintext; `META`, `PROF`, `LROV`, `VOXL` and
//! `ZDIC` are sealed as single units; each `LAYR` frame is its own unit, bound by
//! its associated data to the chunk's directory index. `PREV` and `EXTD` are
//! written in the clear, which section 9.1 permits and which keeps a thumbnail
//! usable without a key.

use crate::check::Check;
use crate::chunks::extd::Extension;
use crate::chunks::head::Head;
use crate::chunks::lhas::{self, LayerHashes};
use crate::chunks::ltbl::{LayerEntry, LayerTable};
use crate::chunks::preview::PreviewRole;
use crate::chunks::zdic::ZstdDictionary;
use crate::chunks::{self, json_chunks, layr};
use crate::container::{
    self, ChunkDescriptor, ChunkType, Directory, FileHeader, CHUNK_FLAG_ENCRYPTED, FLAG_ENCRYPTED,
    FLAG_MULTI_SECTOR,
};
use crate::crypto::{self, Auth, Cipher, RecipientEntry, SessionKey};
use crate::error::{Error, Result};
use crate::io::Writer;
use crate::json::{Meta, Profile, Sector, Timing};
use crate::ree::{self, EncodeMode, Run};
use std::collections::HashMap;
use std::sync::atomic::{AtomicUsize, Ordering};

/// Argon2id parameters for password-mode encryption.
///
/// The defaults sit well inside the ceilings a reader is required to enforce
/// (§11.4: iterations <= 10, memory <= 4 GiB, lanes <= 16), so a file this crate
/// writes is one every conforming reader must be willing to open. The encoder
/// does not police the values it is handed: a caller who deliberately asks for
/// more is writing a file that readers MUST refuse rather than attempt, and the
/// conformance corpus contains exactly such a file on purpose.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Argon2Params {
    /// Time cost.
    pub iterations: u32,
    /// Memory cost in KiB.
    pub memory_kib: u32,
    /// Lanes.
    pub parallelism: u8,
}

impl Default for Argon2Params {
    fn default() -> Self {
        // Print-file decryption happens on printer hardware, so the cost has to
        // land between "a weak password is cheap to attack" and "the printer
        // takes a minute to start". A caller who wants more can say so.
        Argon2Params {
            iterations: 3,
            memory_kib: 65_536,
            parallelism: 1,
        }
    }
}

/// How to encrypt the file being written.
#[derive(Debug, Clone)]
pub struct EncryptOptions {
    /// The AEAD cipher.
    pub cipher: Cipher,
    /// Wrap the session key under this password.
    pub password: Option<String>,
    /// Wrap the session key for each of these X25519 public keys.
    pub recipients: Vec<[u8; 32]>,
    /// Argon2id parameters, used when a password is set.
    pub argon2: Argon2Params,
}

impl EncryptOptions {
    /// Password-mode encryption with default Argon2id parameters.
    pub fn password(password: impl Into<String>) -> EncryptOptions {
        EncryptOptions {
            cipher: Cipher::Aes256Gcm,
            password: Some(password.into()),
            recipients: Vec::new(),
            argon2: Argon2Params::default(),
        }
    }
}

/// The layers one `LAYR` chunk spans, which a fresh encoder starts with
/// (section 4.9 recommends 32-64).
pub const DEFAULT_LAYERS_PER_CHUNK: u32 = 64;
/// The zstd level a fresh encoder starts with.
pub const DEFAULT_ZSTD_LEVEL: i32 = 6;
/// The zstd level for the small JSON chunks (section 6.3).
pub const JSON_ZSTD_LEVEL: i32 = 3;
/// How many 1 KiB windows the dictionary may be sampled from (section 6.2).
///
/// The unit is a window, not a layer: this constant was read as a layer count and
/// applied to the windows of the print's *first* chunks, which made the training set
/// the print's bottom layers - 256 KiB, a couple of layers at 12K.
pub const DICTIONARY_SAMPLE_WINDOWS: usize = 256;

/// The largest dictionary the specification allows, in bytes.
const DICTIONARY_MAX_BYTES: usize = 112_640;

/// The most bytes the pays-probe compresses in each direction.
const DICTIONARY_PROBE_BYTES: usize = 4 * 1024 * 1024;

/// The plaintext size below which the probe is not trusted, in bytes.
///
/// On a small print the probe's noise and the dictionary's own bytes are the same
/// order of magnitude, so the writer keeps the specification's behavior and writes
/// the dictionary it trained. Above this, the data decides.
const DICTIONARY_PROBE_MIN_PLAINTEXT: usize = 8 * 1024 * 1024;

/// The margin a dictionary must beat by, as a fraction of the probe, to be written.
const DICTIONARY_PROBE_MARGIN: f64 = 0.002;

/// One `(layer, sector)`'s timing delta, written as its own `LROV` chunk.
///
/// A delta replaces only the fields it carries; every field it leaves out keeps
/// the value the pipeline resolved for that (layer, sector) from `META`, the
/// sector's `META.sectors` entry and the bottom/transition blend.
#[derive(Debug, Clone, PartialEq)]
pub struct Override {
    /// The layer the delta applies to.
    pub layer: u32,
    /// The sector it applies to. `0` is the primary sector.
    pub sector_id: u32,
    /// The fields the delta replaces, in META's names and units.
    pub timing: Timing,
}

/// A layer's encoded form, ready to store: what `push_layer` builds internally.
#[derive(Debug, Clone)]
pub enum EncodedLayer {
    /// The empty layer: no sector carries bytes.
    Empty,
    /// `(sector_id, tag plus REE stream)`, ascending by `sector_id`, with the
    /// empty sectors omitted.
    Sectors(Vec<(u32, Vec<u8>)>),
}

impl EncodedLayer {
    /// One sector's stream, as sector 0 of a layer.
    ///
    /// `stream` is exactly what [`ree::encode`] or [`ree::encode_runs`] returned:
    /// the REE tag, then the stream. A stream with no tag cannot be stored - an
    /// all-black sector is the empty-layer form - so it is rejected here rather
    /// than reaching the layer table.
    pub fn single(stream: Vec<u8>) -> Result<Self> {
        check_stream(&stream)?;
        Ok(EncodedLayer::Sectors(vec![(0, stream)]))
    }

    /// The pushed stream for one sector, when this layer has data for it.
    fn stream(&self, sector_id: u32) -> Option<&[u8]> {
        match self {
            EncodedLayer::Empty => None,
            EncodedLayer::Sectors(list) => list
                .iter()
                .find(|(id, _)| *id == sector_id)
                .map(|(_, stream)| stream.as_slice()),
        }
    }
}

/// Reject a stream that does not begin with a layer encoding tag.
///
/// An empty stream is not degenerate but different: it is the empty-layer form,
/// which [`EncodedLayer::Empty`] carries and no sector's data does. The messages
/// match the reader's, so a caller sees the same words either side of the file.
/// A single-sector layer record for a maybe-empty encoding.
///
/// `None` is the empty-layer form, and the returned mask data carries its tag,
/// which is what a layer stores.
fn single_sector(encoded: Option<(u8, Vec<u8>)>) -> EncodedLayer {
    match encoded {
        None => EncodedLayer::Empty,
        Some((_tag, mask)) => EncodedLayer::Sectors(vec![(0, mask)]),
    }
}

fn check_stream(stream: &[u8]) -> Result<()> {
    match stream.first() {
        None => Err(Error::new(
            Check::ReeTag,
            "layer mask data is empty: the empty-layer form carries no bytes",
        )),
        Some(&(ree::TAG_BINARY | ree::TAG_GRAYSCALE | ree::TAG_SPLIT | ree::TAG_ATTACHED)) => {
            Ok(())
        }
        Some(&tag) => Err(Error::new(
            Check::ReeTag,
            format!("unknown layer encoding tag 0x{tag:02X}"),
        )),
    }
}

/// A layer group's plaintext under one candidate encoding, with the entries that
/// place each layer's slice inside it.
struct ChunkCandidate {
    plaintext: Vec<u8>,
    placement: Vec<(u32, u64, u32)>,
}

/// A chunk ready to be laid out.
#[derive(Debug)]
struct Pending {
    chunk_type: ChunkType,
    /// The bytes as they will sit on disk.
    stored: Vec<u8>,
    /// What the descriptor's `size_uncompressed` field reports.
    size_uncompressed: u64,
    /// The stored length when it differs from the raw payload, else zero.
    size_compressed: u64,
    flags: u32,
}

/// Builds a `.lumen` file.
#[derive(Debug)]
pub struct Encoder {
    head: Head,
    meta: Meta,
    profile: Option<Profile>,
    overrides: Vec<Override>,
    previews: Vec<(PreviewRole, Vec<u8>)>,
    extensions: Vec<Extension>,
    voxl: Option<Vec<u8>>,
    layers_per_chunk: u32,
    zstd_level: i32,
    dictionary: bool,
    layer_hashes: bool,
    worker_threads: usize,
    encryption: Option<EncryptOptions>,
    session: Option<SessionKey>,
    /// Whether each layer group is encoded both ways and the smaller kept
    /// ([`Encoder::set_tag_probe`]).
    tag_probe: bool,
    /// One entry per layer: its mask data as [`EncodeMode::Auto`] chose it, and
    /// the alternative tag 0x03 encoding the probe compares it against, for a
    /// layer that was pushed under `Auto` while the probe was on.
    layers: Vec<(EncodedLayer, Option<EncodedLayer>)>,
}

impl Encoder {
    /// Start a file with the given `HEAD` and `META`.
    ///
    /// `head.total_layers` must equal the number of layers pushed.
    pub fn new(head: Head, meta: Meta) -> Encoder {
        Encoder {
            head,
            meta,
            profile: None,
            overrides: Vec::new(),
            previews: Vec::new(),
            extensions: Vec::new(),
            voxl: None,
            layers_per_chunk: DEFAULT_LAYERS_PER_CHUNK,
            zstd_level: DEFAULT_ZSTD_LEVEL,
            dictionary: true,
            layer_hashes: true,
            worker_threads: 0,
            encryption: None,
            session: None,
            tag_probe: true,
            layers: Vec::new(),
        }
    }

    /// Attach a reusable print profile.
    pub fn set_profile(&mut self, profile: Profile) {
        self.profile = Some(profile);
    }

    /// Declare the non-zero sectors this print uses, as `META.sectors`.
    ///
    /// Sector 0 is implicit and must not appear; a sector carries no material
    /// until its entry names one.
    pub fn set_sectors(&mut self, sectors: Vec<Sector>) {
        self.meta.sectors = Some(sectors);
    }

    /// Attach the per-(layer, sector) timing deltas.
    ///
    /// Each pair's matching `LTBL` entry points at an `LROV` chunk, and pairs
    /// whose deltas are equal share one: a delta set on a range - or on any set of
    /// pairs - costs one chunk, and every entry that names it applies it. A layer
    /// emitted here also gets a table entry for that sector even when the layer
    /// holds no data for it, which is how an override reaches a sector a layer does
    /// not print.
    pub fn set_overrides(&mut self, overrides: Vec<Override>) -> Result<()> {
        let mut overrides = overrides;
        overrides.sort_by_key(|over| (over.layer, over.sector_id));
        for pair in overrides.windows(2) {
            if pair[0].layer == pair[1].layer && pair[0].sector_id == pair[1].sector_id {
                return Err(Error::new(
                    Check::LrovOrphan,
                    format!(
                        "layer {} sector {} carries two override sets; a (layer, sector) has one \
                         or none",
                        pair[0].layer, pair[0].sector_id
                    ),
                ));
            }
        }
        self.overrides = overrides;
        Ok(())
    }

    /// Add a PNG preview.
    pub fn add_preview(&mut self, role: PreviewRole, png: Vec<u8>) {
        self.previews.push((role, png));
    }

    /// Add a vendor or standard extension.
    pub fn add_extension(&mut self, extension: Extension) {
        self.extensions.push(extension);
    }

    /// Embed the scene that produced this print, verbatim.
    pub fn set_voxl(&mut self, voxl: Vec<u8>) {
        self.voxl = Some(voxl);
    }

    /// How many layers one `LAYR` chunk spans.
    pub fn set_layers_per_chunk(&mut self, layers: u32) {
        self.layers_per_chunk = layers.max(1);
    }

    /// Whether to encode each layer group both ways and keep the smaller.
    ///
    /// On by default. A group's layers are encoded with the tag
    /// [`EncodeMode::Auto`] chooses and with [`EncodeMode::Attached`], both are
    /// compressed exactly as the file will frame them, and the smaller result is
    /// kept. The comparison is what makes the attached form a gain rather than a
    /// gamble: its raw size is not a guide to its compressed size, so an encoder
    /// that picked it by bytes alone would lose on a print whose layers barely
    /// change.
    ///
    /// The probe costs one extra encoding and one extra compression of every
    /// layer group, and it measures without the `ZDIC` dictionary, which is only
    /// trained once the whole print has been pushed. Turning it off means every
    /// layer is stored with the tag [`EncodeMode::Auto`] picks.
    pub fn set_tag_probe(&mut self, enabled: bool) {
        self.tag_probe = enabled;
    }

    /// zstd compression level for the layer chunks.
    pub fn set_zstd_level(&mut self, level: i32) {
        self.zstd_level = level;
    }

    /// Whether to train and emit a `ZDIC` dictionary (section 6.2).
    ///
    /// Enabled, the writer samples the print, trains a dictionary and writes it *if
    /// the data says it pays* - see [`dictionary_pays`]. Disabled, it compresses every
    /// frame without one, which is a smaller file than a dictionary that does not fit
    /// the print.
    pub fn set_dictionary(&mut self, enabled: bool) {
        self.dictionary = enabled;
    }

    /// Whether to emit an `LHAS` integrity tree.
    pub fn set_layer_hashes(&mut self, enabled: bool) {
        self.layer_hashes = enabled;
    }

    /// How many threads `finish` may frame chunks and hash layers on.
    ///
    /// `0`, what a fresh encoder starts with, means one per available core, and
    /// a request above that is capped by it: this is CPU-bound work on data
    /// already in memory, so a thread beyond the cores available would take time
    /// from another rather than spend a wait. `1` is the serial path, and it
    /// writes the same bytes any other count does - the output of this encoder
    /// is a function of its input and settings alone, as section 5.7 intends.
    pub fn set_worker_threads(&mut self, threads: usize) {
        self.worker_threads = threads;
    }

    /// The worker count `finish` will use, never zero.
    fn workers(&self) -> usize {
        match self.worker_threads {
            0 => available_parallelism(),
            threads => threads.min(available_parallelism()),
        }
    }

    /// Encrypt the file.
    pub fn set_encryption(&mut self, options: EncryptOptions) {
        self.session = Some(SessionKey::generate());
        self.encryption = Some(options);
    }

    /// The session key this encoder uses, for a caller that wants to keep it.
    pub fn session_key(&self) -> Option<SessionKey> {
        self.session
    }

    /// Push one layer's mask, choosing its encoding per [`EncodeMode::Auto`].
    ///
    /// The mask is sector 0's: it is what a single-material reader prints.
    pub fn push_layer(&mut self, pixels: &[u8]) -> Result<()> {
        self.push_layer_with_mode(pixels, EncodeMode::Auto)
    }

    /// Push one layer's mask with an explicit encoding.
    pub fn push_layer_with_mode(&mut self, pixels: &[u8], mode: EncodeMode) -> Result<()> {
        let total_pixels = self.total_pixels();
        check_mask(pixels, total_pixels, "the layer")?;
        let record = single_sector(ree::encode(pixels, total_pixels, mode)?);
        let alternative = match (mode, self.tag_probe) {
            (EncodeMode::Auto, true) => Some(single_sector(ree::encode(
                pixels,
                total_pixels,
                EncodeMode::Attached,
            )?)),
            _ => None,
        };
        self.layers.push((record, alternative));
        Ok(())
    }

    /// Push one layer as a set of sectors, each with its own mask.
    ///
    /// Sector 0 is implicit, so a layer whose only content is sector 0 is pushed
    /// with [`Encoder::push_layer`] instead. A sector with no exposed pixel is
    /// omitted, and a layer whose every sector is empty is stored as the
    /// empty-layer form. The pairs are sorted by sector, which is the order the
    /// layer table requires.
    pub fn push_layer_sectors(&mut self, sectors: &[(u32, Vec<u8>)]) -> Result<()> {
        let total_pixels = self.total_pixels();
        let mut masks: Vec<(u32, Vec<u8>)> = Vec::new();
        let mut alternatives: Vec<(u32, Vec<u8>)> = Vec::new();
        for (sector_id, pixels) in sectors {
            check_mask(
                pixels,
                total_pixels,
                &format!("sector {sector_id} of the layer"),
            )?;
            if sectors.iter().filter(|(id, _)| id == sector_id).count() > 1 {
                return Err(Error::new(
                    Check::LtblSectorIdUnique,
                    format!("sector {sector_id} appears twice in one layer"),
                ));
            }
            if let Some((_tag, mask)) = ree::encode(pixels, total_pixels, EncodeMode::Auto)? {
                masks.push((*sector_id, mask));
                if self.tag_probe {
                    if let Some((_tag, other)) =
                        ree::encode(pixels, total_pixels, EncodeMode::Attached)?
                    {
                        alternatives.push((*sector_id, other));
                    }
                }
            }
        }
        if masks.is_empty() {
            self.layers.push((EncodedLayer::Empty, None));
        } else {
            masks.sort_by_key(|(sector_id, _)| *sector_id);
            alternatives.sort_by_key(|(sector_id, _)| *sector_id);
            let alternative =
                (!alternatives.is_empty()).then_some(EncodedLayer::Sectors(alternatives));
            self.layers
                .push((EncodedLayer::Sectors(masks), alternative));
        }
        Ok(())
    }

    /// Push one layer given as runs instead of pixels, as sector 0.
    ///
    /// Equivalent to [`Encoder::push_layer`] on the mask the runs describe,
    /// except that the mask is never built: a slicer's run-length rasterizer
    /// output goes straight to the encoder. The runs must be canonical and cover
    /// the layer, as [`ree::encode_runs`] requires.
    pub fn push_layer_runs(&mut self, runs: &[Run], mode: EncodeMode) -> Result<()> {
        let total_pixels = self.total_pixels();
        let record = single_sector(ree::encode_runs(runs, total_pixels, mode)?);
        let alternative = match (mode, self.tag_probe) {
            (EncodeMode::Auto, true) => Some(single_sector(ree::encode_runs(
                runs,
                total_pixels,
                EncodeMode::Attached,
            )?)),
            _ => None,
        };
        self.layers.push((record, alternative));
        Ok(())
    }

    /// Push a layer that is already encoded.
    ///
    /// This is the parallel path: workers turn one layer's runs into bytes with
    /// [`ree::encode_runs`], and the writer stores each result in layer order
    /// without ever seeing pixel data. The streams are checked to carry a layer
    /// encoding tag, the sectors are sorted by id as the layer table requires,
    /// and a layer with no sector data becomes the empty-layer form.
    pub fn push_encoded_layer(&mut self, layer: EncodedLayer) -> Result<()> {
        self.push_encoded_layer_pair(layer, None)
    }

    /// Push a layer that is already encoded, with the other encoding the tag probe
    /// should weigh it against.
    ///
    /// [`Encoder::push_encoded_layer`] is this with no alternative. A caller that
    /// encodes layers on its own threads - the slicer adapter does, one worker per
    /// layer - can hand over the tag `0x03` stream of the same layer as well, and
    /// the probe then has two candidates to compress when the group closes. Both
    /// must describe the same pixels: the probe's choice is a choice of encoding,
    /// and nothing checks that they agree.
    ///
    /// The alternative is stored as it is when the probe is off, which costs the
    /// caller nothing but the encoding it computed.
    pub fn push_encoded_layer_pair(
        &mut self,
        layer: EncodedLayer,
        alternative: Option<EncodedLayer>,
    ) -> Result<()> {
        if let Some(other) = alternative.as_ref() {
            match other {
                EncodedLayer::Empty => {}
                EncodedLayer::Sectors(list) => {
                    for (_, stream) in list {
                        check_stream(stream)?;
                    }
                }
            }
        }
        let record = match layer {
            EncodedLayer::Empty => EncodedLayer::Empty,
            EncodedLayer::Sectors(mut list) => {
                for (_, stream) in &list {
                    check_stream(stream)?;
                }
                list.sort_by_key(|(sector_id, _)| *sector_id);
                for pair in list.windows(2) {
                    if pair[0].0 == pair[1].0 {
                        return Err(Error::new(
                            Check::LtblSectorIdUnique,
                            format!("sector {} appears twice in one layer", pair[0].0),
                        ));
                    }
                }
                if list.is_empty() {
                    EncodedLayer::Empty
                } else {
                    EncodedLayer::Sectors(list)
                }
            }
        };
        self.layers.push((record, alternative));
        Ok(())
    }

    fn total_pixels(&self) -> u32 {
        self.head.total_pixels()
    }

    /// Assemble the container.
    ///
    /// Fails if the number of pushed layers disagrees with `head.total_layers`.
    pub fn finish(self) -> Result<Vec<u8>> {
        let pushed = self.layers.len() as u32;
        if pushed != self.head.total_layers {
            return Err(Error::new(
                Check::HeadTotalLayers,
                format!(
                    "HEAD declares {} layers but {pushed} were pushed",
                    self.head.total_layers
                ),
            ));
        }

        // 1. META's own shape rules, so the encoder cannot write a file its own
        //    validator would reject.
        if let Some(sectors) = self.meta.sectors.as_deref() {
            let mut seen: Vec<u32> = Vec::with_capacity(sectors.len());
            for (i, sector) in sectors.iter().enumerate() {
                if sector.sector_id == 0 {
                    return Err(Error::new(
                        Check::MetaSectorsShape,
                        format!(
                            "META.sectors[{i}] uses sector_id 0, which names the implicit primary \
                             sector"
                        ),
                    ));
                }
                if seen.contains(&sector.sector_id) {
                    return Err(Error::new(
                        Check::MetaSectorsShape,
                        format!("sector_id {} appears twice", sector.sector_id),
                    ));
                }
                seen.push(sector.sector_id);
            }
        }

        // 2. Which sectors each layer's table entry set covers: sector 0, every
        //    sector it holds data for, and every sector an override targets.
        let sector_sets = self.sector_sets()?;

        // 3. One LAYR chunk per (sector, layer-group): the group's masks for that
        //    sector, concatenated in ascending layer order. The placement of each
        //    layer's run inside its chunk is what LTBL records.
        let group_size = self.layers_per_chunk.max(1) as usize;
        // Per (group, sector): the plaintext the file frames, the placement of
        // each layer's slice inside it, and - when the probe computed one - the
        // same pair for the tag 0x03 encoding of the very same layers. The choice
        // between them is made in step 5, with the dictionary the frames will
        // actually use: an encoding's raw size is no guide, and neither is its
        // compressed size without the dictionary that will compress it.
        let mut chunk_plaintexts: Vec<Vec<u8>> = Vec::new();
        let mut chunk_placements: Vec<Vec<(u32, u64, u32)>> = Vec::new();
        let mut chunk_alternatives: Vec<Option<ChunkCandidate>> = Vec::new();
        let mut chunk_sectors: Vec<u32> = Vec::new();
        for group_start in (0..pushed as usize).step_by(group_size) {
            let group_end = (group_start + group_size).min(pushed as usize);
            let mut sectors: Vec<u32> = sector_sets[group_start..group_end]
                .iter()
                .flatten()
                .copied()
                .collect();
            sectors.sort_unstable();
            sectors.dedup();
            let probed = self.layers[group_start..group_end]
                .iter()
                .any(|(_, alternative)| alternative.is_some());
            for sector in sectors {
                let mut plaintext = Vec::new();
                let mut placed: Vec<(u32, u64, u32)> = Vec::new();
                let mut alternative_text = Vec::new();
                let mut alternative_placed: Vec<(u32, u64, u32)> = Vec::new();
                for (index, (record, alternative)) in self
                    .layers
                    .iter()
                    .enumerate()
                    .take(group_end)
                    .skip(group_start)
                {
                    if let Some(mask) = record.stream(sector) {
                        placed.push((index as u32, plaintext.len() as u64, mask.len() as u32));
                        plaintext.extend_from_slice(mask);
                    }
                    // A layer without an alternative is its own alternative, so
                    // the two candidates always describe the same layers.
                    let chosen = alternative.as_ref().unwrap_or(record);
                    if let Some(mask) = chosen.stream(sector) {
                        alternative_placed.push((
                            index as u32,
                            alternative_text.len() as u64,
                            mask.len() as u32,
                        ));
                        alternative_text.extend_from_slice(mask);
                    }
                }
                // A sector enters a layer's entries for other reasons too - an
                // override with no data behind it - so a group may name a sector
                // that holds nothing here. It gets no chunk.
                if plaintext.is_empty() {
                    continue;
                }
                chunk_plaintexts.push(plaintext);
                chunk_placements.push(placed);
                chunk_alternatives.push(
                    (probed && alternative_text != chunk_plaintexts[chunk_plaintexts.len() - 1])
                        .then_some(ChunkCandidate {
                            plaintext: alternative_text,
                            placement: alternative_placed,
                        }),
                );
                chunk_sectors.push(sector);
            }
        }
        // A file carries at least one LAYR chunk even when every layer is empty
        // (section 3's presence rule).
        if chunk_plaintexts.is_empty() {
            chunk_plaintexts.push(Vec::new());
            chunk_placements.push(Vec::new());
            chunk_alternatives.push(None);
            chunk_sectors.push(0);
        }

        // 4. The dictionary: trained on samples spread across the print, and written
        //    only when it earns its own bytes back (section 6.2).
        let dictionary = if self.dictionary {
            let samples = dictionary_samples(&chunk_plaintexts);
            match chunks::train_dictionary(&samples, DICTIONARY_MAX_BYTES) {
                Ok(bytes) if !bytes.is_empty() && chunks::dictionary_id(&bytes) != 0 => {
                    if dictionary_pays(&chunk_plaintexts, &bytes, self.zstd_level)? {
                        Some(ZstdDictionary {
                            zdic_version: 1,
                            dict_id: chunks::dictionary_id(&bytes),
                            dict_bytes: bytes,
                        })
                    } else {
                        // A dictionary that makes the frames larger is bytes nobody
                        // asked for, and the specification permits omitting it.
                        None
                    }
                }
                // Training fails on a degenerate print - too little or too
                // uniform data. The specification's answer is to omit ZDIC and
                // compress without a dictionary.
                _ => None,
            }
        } else {
            None
        };
        let dict_bytes = dictionary.as_ref().map(|d| d.dict_bytes.as_slice());

        // 5. Compress each chunk's plaintext into its frame, on the worker
        //    threads: one frame is a function of one plaintext and the
        //    dictionary, and no frame is a function of another.
        let workers = self.workers();
        let level = self.zstd_level;
        let alternatives = &chunk_alternatives;
        let choices: Vec<(Vec<u8>, bool)> =
            map_ordered(&chunk_plaintexts, workers, |index, plaintext| {
                let frame = |text: &[u8]| -> Result<Vec<u8>> {
                    let frame = chunks::compress(text, level, dict_bytes)?;
                    // A reader sizes the frame's output from the frame's own
                    // header, so a writer must set its content size; refusing here
                    // keeps the guarantee in the writer rather than in a comment.
                    chunks::frame_content_size(&frame)?;
                    Ok(frame)
                };
                let primary = frame(plaintext)?;
                match &alternatives[index] {
                    // The smaller frame wins, and a tie keeps the encoding
                    // `EncodeMode::Auto` chose.
                    Some(candidate) => match frame(&candidate.plaintext) {
                        Ok(other) if other.len() < primary.len() => Ok((other, true)),
                        Ok(_) | Err(_) => Ok((primary, false)),
                    },
                    None => Ok((primary, false)),
                }
            })?;

        // The placement a reader needs is the chosen encoding's, and LTBL is the
        // only thing that says where a slice sits.
        let mut placement: HashMap<(u32, u32), (u32, u64, u32)> = HashMap::new();
        let mut frames: Vec<Vec<u8>> = Vec::with_capacity(choices.len());
        for (index, (frame, chose_alternative)) in choices.into_iter().enumerate() {
            let sector = chunk_sectors[index];
            let entries = if chose_alternative {
                let candidate = chunk_alternatives[index]
                    .take()
                    .expect("an alternative that was compressed");
                chunk_plaintexts[index] = candidate.plaintext;
                candidate.placement
            } else {
                std::mem::take(&mut chunk_placements[index])
            };
            for (layer, offset, size) in entries {
                placement.insert((layer, sector), (index as u32, offset, size));
            }
            frames.push(frame);
        }

        // 6. LHAS, over each layer's slices concatenated in ascending sector_id -
        //    read back out of the chunk plaintexts, so the leaves are over the
        //    very bytes a reader will reconstruct - and on the worker threads,
        //    a leaf being a function of one layer and nothing else.
        let hashes = if self.layer_hashes {
            let leaves = map_ordered(&sector_sets, workers, |index, sectors| {
                let mut data = Vec::new();
                for sector in sectors {
                    let key = (index as u32, *sector);
                    if let Some(&(ordinal, offset, size)) = placement.get(&key) {
                        let start = offset as usize;
                        data.extend_from_slice(
                            &chunk_plaintexts[ordinal as usize][start..start + size as usize],
                        );
                    }
                }
                Ok(lhas::leaf_hash(&data))
            })?;
            Some(LayerHashes {
                hash_algorithm: lhas::HASH_ALGORITHM_SHA256,
                hash_size: lhas::HASH_SIZE_SHA256,
                layer_count: leaves.len() as u32,
                merkle_root: lhas::merkle_root(&leaves),
                layer_hashes: leaves,
            })
        } else {
            None
        };

        // 7. Everything before LTBL, then LTBL, then everything after: the LAYR
        //    chunks need their directory indices, and LTBL needs them too, so the
        //    one slot LTBL occupies and the optional LHAS slot are what the LAYR
        //    indices are computed from.
        let mut flags = 0u32;
        if self
            .layers
            .iter()
            .any(|(record, _)| matches!(record, EncodedLayer::Sectors(list) if list.len() > 1))
        {
            flags |= FLAG_MULTI_SECTOR;
        }
        let sealed = self.session.is_some() && self.encryption.is_some();
        if self.encryption.is_some() {
            flags |= FLAG_ENCRYPTED;
        }

        let mut pending = Vec::new();
        pending.push(Pending::raw(ChunkType::HEAD, self.head.to_bytes()));
        pending.push(self.seal_if_needed(
            ChunkType::META,
            json_chunks::meta_to_bytes(&self.meta)?,
            true,
        )?);
        if let Some(profile) = self.profile.as_ref() {
            pending.push(self.seal_if_needed(
                ChunkType::PROF,
                json_chunks::profile_to_bytes(profile)?,
                true,
            )?);
        }
        if let Some(auth) = self.build_auth()? {
            pending.push(Pending::raw(ChunkType::AUTH, crypto::encode_auth(&auth)));
        }
        // The overrides are already sorted by (layer, sector), so their chunks are
        // too, and each (layer, sector) remembers which index it landed at. Two pairs
        // whose deltas are identical share one chunk: a delta that covers a range, or
        // any set of pairs, is written once and every entry that names it applies it
        // (section 4.5). The map is keyed by the serialized payload, so a slicer that
        // builds each pair's delta the same way gets the sharing for free.
        let mut lrov_index: HashMap<(u32, u32), u32> = HashMap::new();
        let mut shared: HashMap<Vec<u8>, u32> = HashMap::new();
        for over in &self.overrides {
            let payload = json_chunks::lrov_to_bytes(&over.timing)?;
            let index = match shared.get(&payload) {
                Some(index) => *index,
                None => {
                    let index = pending.len() as u32;
                    pending.push(self.seal_if_needed(ChunkType::LROV, payload.clone(), true)?);
                    shared.insert(payload, index);
                    index
                }
            };
            lrov_index.insert((over.layer, over.sector_id), index);
        }
        if let Some(dictionary) = dictionary.as_ref() {
            pending.push(self.seal_if_needed(ChunkType::ZDIC, dictionary.to_bytes(), false)?);
        }
        for (role, png) in &self.previews {
            pending.push(Pending::raw_with_flags(
                ChunkType::PREV,
                png.clone(),
                role.to_flags(),
            ));
        }
        if let Some(voxl) = self.voxl.as_ref() {
            pending.push(self.seal_if_needed(ChunkType::VOXL, voxl.clone(), true)?);
        }

        let layr_base = pending.len() as u32 + 1 + u32::from(hashes.is_some());
        let entries =
            self.table_entries(pushed, &sector_sets, &placement, layr_base, &lrov_index)?;
        let table = LayerTable::new(entries, pushed)?;
        pending.push(Pending::raw(ChunkType::LTBL, table.to_bytes()));
        if let Some(hashes) = hashes.as_ref() {
            pending.push(Pending::raw(ChunkType::LHAS, hashes.to_bytes()));
        }
        debug_assert_eq!(
            pending.len() as u32,
            layr_base,
            "the LAYR chunks start where their indices say they do"
        );

        for (ordinal, frame) in frames.iter().enumerate() {
            let directory_index = layr_base + ordinal as u32;
            let container = if sealed {
                let sealed_frame = crypto::seal(
                    self.cipher()?,
                    self.session.as_ref().expect("set with encryption"),
                    ChunkType::LAYR,
                    directory_index,
                    frame,
                )?;
                layr::to_bytes(&sealed_frame)
            } else {
                layr::to_bytes(frame)
            };
            pending.push(Pending {
                chunk_type: ChunkType::LAYR,
                stored: container,
                size_uncompressed: layr::container_len(frame.len()),
                size_compressed: if sealed {
                    // The container's stored length: the version field, the
                    // frame, and the one sealed unit's nonce and tag.
                    layr::container_len(frame.len()) + crypto::UNIT_OVERHEAD as u64
                } else {
                    0
                },
                flags: if sealed { CHUNK_FLAG_ENCRYPTED } else { 0 },
            });
        }
        for extension in &self.extensions {
            pending.push(Pending::raw_with_flags(
                ChunkType::EXTD,
                extension.to_bytes(),
                extension.to_flags(),
            ));
        }

        // 8. Lay out: header, payloads at 8-byte alignment, directory, trailer.
        let mut out = Writer::with_capacity(
            pending.iter().map(|p| p.stored.len() + 8).sum::<usize>() + 64 + pending.len() * 32,
        );
        out.bytes(&[0u8; 32]);
        let mut directory = Directory::new();
        let mut total_uncompressed = 0u64;
        for chunk in &pending {
            out.pad_to(8);
            let offset = out.len() as u64;
            out.bytes(&chunk.stored);
            total_uncompressed += chunk.size_uncompressed;
            directory.push(ChunkDescriptor {
                chunk_type: chunk.chunk_type,
                offset,
                size_uncompressed: chunk.size_uncompressed,
                size_compressed: chunk.size_compressed,
                flags: chunk.flags,
            });
        }
        out.pad_to(8);
        let dir_offset = out.len() as u64;
        out.bytes(&directory.to_bytes());
        let header = FileHeader {
            version: 1,
            dir_offset,
            chunk_count: directory.descriptors.len() as u32,
            flags,
            total_uncompressed_size: total_uncompressed,
        };
        out.patch_bytes(0, &header.to_bytes());
        let crc = container::crc32c(out.as_slice());
        out.bytes(&container::TRAILER_MAGIC);
        out.u32(crc);
        Ok(out.into_vec())
    }

    /// The sectors each layer's entries cover, ascending, sector 0 first.
    fn sector_sets(&self) -> Result<Vec<Vec<u32>>> {
        let mut sets: Vec<Vec<u32>> = self
            .layers
            .iter()
            .map(|(record, _)| match record {
                EncodedLayer::Empty => Vec::new(),
                EncodedLayer::Sectors(list) => list.iter().map(|(id, _)| *id).collect(),
            })
            .collect();
        for over in &self.overrides {
            let index = over.layer as usize;
            let Some(ids) = sets.get_mut(index) else {
                return Err(Error::new(
                    Check::LtblLayerIndexRange,
                    format!(
                        "an override names layer {} of {}",
                        over.layer,
                        self.layers.len()
                    ),
                ));
            };
            if !ids.contains(&over.sector_id) {
                ids.push(over.sector_id);
            }
        }
        for ids in &mut sets {
            if !ids.contains(&0) {
                ids.push(0);
            }
            ids.sort_unstable();
            ids.dedup();
        }
        Ok(sets)
    }

    /// The layer table's entries, one per (layer, sector), in table order.
    fn table_entries(
        &self,
        pushed: u32,
        sector_sets: &[Vec<u32>],
        placement: &HashMap<(u32, u32), (u32, u64, u32)>,
        layr_base: u32,
        lrov_index: &HashMap<(u32, u32), u32>,
    ) -> Result<Vec<LayerEntry>> {
        let mut entries = Vec::new();
        for index in 0..pushed {
            let ids = &sector_sets[index as usize];
            let additional = (ids.len() - 1) as u32;
            // Every entry names a `LAYR` chunk, as section 4.9 requires, even
            // when the (layer, sector) holds no bytes: an entry with no run of
            // its own takes the chunk of the layer's first run, or the file's
            // first chunk when the layer has none at all.
            let home = ids
                .iter()
                .find_map(|sector| placement.get(&(index, *sector)))
                .map_or(layr_base, |(ordinal, _, _)| layr_base + *ordinal);
            for (position, sector) in ids.iter().enumerate() {
                let run = placement.get(&(index, *sector));
                entries.push(LayerEntry {
                    data_size: run.map_or(0, |(_, _, size)| *size),
                    first_lrov: lrov_index.get(&(index, *sector)).copied().unwrap_or(0),
                    first_layr: run.map_or(home, |(ordinal, _, _)| layr_base + *ordinal),
                    additional_sector_count: if position == 0 { additional } else { 0 },
                    data_offset: run.map_or(0, |(_, offset, _)| *offset),
                    sector_id: *sector,
                });
            }
        }
        Ok(entries)
    }

    fn cipher(&self) -> Result<Cipher> {
        Ok(self
            .encryption
            .as_ref()
            .expect("cipher asked for without encryption")
            .cipher)
    }

    /// Compress and seal a content chunk when the file is encrypted.
    ///
    /// These are one-unit chunks, so their associated data names slot zero; a
    /// `LAYR` frame is sealed by the layout step instead, bound to the chunk's
    /// directory index.
    fn seal_if_needed(
        &self,
        chunk_type: ChunkType,
        plaintext: Vec<u8>,
        compress: bool,
    ) -> Result<Pending> {
        let payload = if compress {
            chunks::compress(&plaintext, JSON_ZSTD_LEVEL, None)?
        } else {
            plaintext.clone()
        };
        let compressed_len = if compress { payload.len() as u64 } else { 0 };
        match self.session.as_ref() {
            None => Ok(Pending {
                chunk_type,
                stored: payload,
                size_uncompressed: plaintext.len() as u64,
                size_compressed: compressed_len,
                flags: 0,
            }),
            Some(key) => {
                let sealed = crypto::seal(self.cipher()?, key, chunk_type, 0, &payload)?;
                Ok(Pending {
                    chunk_type,
                    size_uncompressed: plaintext.len() as u64,
                    stored: sealed,
                    size_compressed: payload.len() as u64 + crypto::UNIT_OVERHEAD as u64,
                    flags: CHUNK_FLAG_ENCRYPTED,
                })
            }
        }
    }

    /// Build the `AUTH` chunk, when the file is encrypted.
    fn build_auth(&self) -> Result<Option<Auth>> {
        let Some(options) = self.encryption.as_ref() else {
            return Ok(None);
        };
        let session = self.session.as_ref().expect("set with encryption");
        let mut mode = 0u32;
        let mut password = None;
        let mut recipients: Vec<RecipientEntry> = Vec::new();
        if let Some(secret) = options.password.as_deref() {
            mode |= crypto::MODE_PASSWORD;
            let params = options.argon2;
            password = Some(crypto::wrap_password(
                session,
                secret,
                params.iterations,
                params.memory_kib,
                params.parallelism,
            )?);
        }
        for public in &options.recipients {
            mode |= crypto::MODE_MACHINE;
            recipients.push(crypto::wrap_machine(session, public)?);
        }
        if mode == 0 {
            return Err(Error::new(
                Check::CryptModeEmpty,
                "encryption was requested with neither a password nor a recipient",
            ));
        }
        Ok(Some(Auth {
            cipher: options.cipher,
            auth_version: 1,
            mode,
            password: password.map(Option::Some).unwrap_or(None),
            recipients,
        }))
    }
}

/// One worker per core the platform reports, and one where it reports none.
///
/// `wasm32-unknown-unknown` is a target this crate is built for - DragonFruit
/// renders its UI with it - and it can neither report parallelism nor spawn a
/// thread, so an encoder running there takes the serial path however many workers
/// it is asked for.
fn available_parallelism() -> usize {
    #[cfg(target_arch = "wasm32")]
    {
        1
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        std::thread::available_parallelism().map_or(1, |threads| threads.get())
    }
}

/// Map `items` through `f` on up to `workers` threads, keeping the input order.
///
/// This is what `finish` runs its per-item passes on. Work is handed out one item
/// at a time rather than as a block per thread: the items are not equally
/// expensive - a dense layer's zstd frame costs many times an empty one's - so a
/// block-sized slice of the print would leave every other worker waiting behind
/// whichever one of them drew the hard chunk.
///
/// A result is placed by the index it came from and never by the order it
/// completed in, so the returned vector is the one a single thread would have
/// built. `f` sees the item's index because an item may need to say where it
/// sits: an `LHAS` leaf names the layer it hashes.
fn map_ordered<T, R>(
    items: &[T],
    workers: usize,
    f: impl Fn(usize, &T) -> Result<R> + Sync,
) -> Result<Vec<R>>
where
    T: Sync,
    R: Send,
{
    if workers <= 1 || items.len() <= 1 {
        return items
            .iter()
            .enumerate()
            .map(|(index, item)| f(index, item))
            .collect();
    }
    let next = AtomicUsize::new(0);
    let mut ordered: Vec<Option<R>> = (0..items.len()).map(|_| None).collect();
    std::thread::scope(|scope| -> Result<()> {
        let handles: Vec<_> = (0..workers.min(items.len()))
            .map(|_| {
                scope.spawn(|| -> Result<Vec<(usize, R)>> {
                    let mut finished = Vec::new();
                    loop {
                        // Relaxed: the counter orders nothing but itself, and
                        // every value it hands out is filled by whoever took it.
                        let index = next.fetch_add(1, Ordering::Relaxed);
                        let Some(item) = items.get(index) else {
                            break;
                        };
                        finished.push((index, f(index, item)?));
                    }
                    Ok(finished)
                })
            })
            .collect();
        for handle in handles {
            for (index, value) in handle.join().expect("a worker does not panic")? {
                ordered[index] = Some(value);
            }
        }
        Ok(())
    })?;
    Ok(ordered
        .into_iter()
        .map(|value| value.expect("every index is taken by one worker"))
        .collect())
}

/// Reject a mask whose pixel count disagrees with the display.
fn check_mask(pixels: &[u8], total_pixels: u32, what: &str) -> Result<()> {
    if pixels.len() != total_pixels as usize {
        return Err(Error::new(
            Check::ReeDataSize,
            format!(
                "{what} has {} pixels but the display holds {total_pixels}",
                pixels.len()
            ),
        ));
    }
    Ok(())
}

impl Pending {
    fn raw(chunk_type: ChunkType, payload: Vec<u8>) -> Pending {
        let len = payload.len() as u64;
        Pending {
            chunk_type,
            stored: payload,
            size_uncompressed: len,
            size_compressed: 0,
            flags: 0,
        }
    }

    fn raw_with_flags(chunk_type: ChunkType, payload: Vec<u8>, flags: u32) -> Pending {
        let mut pending = Pending::raw(chunk_type, payload);
        pending.flags = flags;
        pending
    }
}

/// Split a chunk's plaintext into samples for dictionary training.
///
/// The boundaries between layers are not recoverable from the concatenation
/// alone, so this yields the whole chunk as one sample per fixed stride, which is
/// what `ZDICT_trainFromBuffer` wants: many samples of similar data. Layer data is
/// already highly redundant, so a sample per 1 KiB window trains well and costs
/// nothing to compute.
fn split_samples(plaintext: &[u8]) -> Vec<&[u8]> {
    const WINDOW: usize = 1024;
    if plaintext.is_empty() {
        return Vec::new();
    }
    plaintext.chunks(WINDOW).collect()
}

/// Training samples spread across the whole print (section 6.2).
///
/// The samples span the print - evenly over the chunks, and evenly within each - rather
/// than coming from its start, because the start of a print is its raft and its bottom
/// layers. Measured on a 12K print: samples taken from the start compressed 3% worse
/// than *no* dictionary on a binary print and 5% worse on an anti-aliased one, while
/// samples spread across the print were the best set of the three. A dictionary is
/// worth its own 112 KiB only when it describes the data it is used on.
fn dictionary_samples(plaintexts: &[Vec<u8>]) -> Vec<&[u8]> {
    let windows: Vec<Vec<&[u8]>> = plaintexts.iter().map(|p| split_samples(p)).collect();
    let mut samples = Vec::with_capacity(DICTIONARY_SAMPLE_WINDOWS);
    if windows.is_empty() {
        return samples;
    }
    // With more chunks than the budget allows, visit a stride of them and take one
    // window each; with fewer, take an equal share from every chunk.
    let chunk_stride = windows.len().div_ceil(DICTIONARY_SAMPLE_WINDOWS).max(1);
    let per_chunk = (DICTIONARY_SAMPLE_WINDOWS / (windows.len() / chunk_stride).max(1)).max(1);
    for (index, chunk) in windows.iter().enumerate() {
        if index % chunk_stride != 0 || chunk.is_empty() {
            continue;
        }
        let step = (chunk.len() / per_chunk).max(1);
        for window in (0..chunk.len()).step_by(step).take(per_chunk) {
            if samples.len() == DICTIONARY_SAMPLE_WINDOWS {
                return samples;
            }
            samples.push(chunk[window]);
        }
    }
    samples
}

/// Whether a trained dictionary earns its own bytes back on this print (section 6.2).
///
/// The answer is a property of the data rather than of the format. An anti-aliased
/// print's greyscale planes are high-entropy, and a dictionary built from the print's
/// own statistics made its frames 4.7% *larger* on a measured 800-layer 12K print,
/// while a binary print's run-length planes are matched by one. So the writer
/// compresses a bounded probe of the print both ways - a share of the first, middle and
/// last chunks, so the probe spans the print - and keeps the dictionary only when the
/// probe says it wins by more than noise, with the dictionary's own bytes charged
/// against it at the share of the print the probe covers. Below
/// [`DICTIONARY_PROBE_MIN_PLAINTEXT`] the probe is not trusted and the dictionary stands.
fn dictionary_pays(plaintexts: &[Vec<u8>], dictionary: &[u8], level: i32) -> Result<bool> {
    let total: usize = plaintexts.iter().map(Vec::len).sum();
    if total < DICTIONARY_PROBE_MIN_PLAINTEXT {
        return Ok(true);
    }
    let share = DICTIONARY_PROBE_BYTES / 3;
    let last = plaintexts.len() - 1;
    let mut probe = Vec::with_capacity(DICTIONARY_PROBE_BYTES);
    for index in [0, last / 2, last] {
        let plaintext = &plaintexts[index];
        probe.extend_from_slice(&plaintext[..plaintext.len().min(share)]);
    }
    if probe.is_empty() {
        return Ok(true);
    }
    let with = chunks::compress(&probe, level, Some(dictionary))?.len();
    let without = chunks::compress(&probe, level, None)?.len();
    // The dictionary is stored once and the probe is one slice of the print, so its
    // own bytes are charged at the share of the print the probe stands for.
    let charge = dictionary.len() as f64 * probe.len() as f64 / total as f64;
    Ok((with as f64 + charge) < without as f64 * (1.0 - DICTIONARY_PROBE_MARGIN))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json::{Meta, Timing};

    const WIDTH: u32 = 8;
    const HEIGHT: u32 = 4;
    const PIXELS: usize = (WIDTH * HEIGHT) as usize;

    fn head(layers: u32) -> Head {
        Head {
            head_version: 1,
            encoder_name: "lumen writer tests".to_string(),
            created_unix_sec: 1_750_000_000,
            display_width_px: WIDTH,
            display_height_px: HEIGHT,
            build_width_um: 40_000,
            build_depth_um: 20_000,
            build_height_um: 20_000,
            layer_height_um: 50,
            total_layers: layers,
        }
    }

    fn meta() -> Meta {
        let mut timing = Timing {
            layer_height_um: Some(50),
            ..Timing::default()
        };
        timing.extra.clear();
        Meta {
            meta_version: Some(1),
            timing,
            ..Meta::default()
        }
    }

    /// The canonical runs of a mask.
    fn runs_of(pixels: &[u8]) -> Vec<Run> {
        let mut runs: Vec<Run> = Vec::new();
        for &pixel in pixels {
            match runs.last_mut() {
                Some(last) if last.value == pixel => last.length += 1,
                _ => runs.push(Run::new(1, pixel)),
            }
        }
        runs
    }

    /// One mask per encoding, plus the empty layer: binary stripes, an
    /// anti-aliased edge, and a mask neither tag can shrink.
    fn masks() -> Vec<Vec<u8>> {
        let mut stripes = vec![0u8; PIXELS];
        for (index, pixel) in stripes.iter_mut().enumerate() {
            if index % 3 == 0 {
                *pixel = 255;
            }
        }
        let mut edge = vec![0u8; PIXELS];
        edge[PIXELS / 2 - 1] = 90;
        edge[PIXELS / 2] = 200;
        let gradient: Vec<u8> = (0..PIXELS).map(|index| (index * 8) as u8).collect();
        vec![vec![0u8; PIXELS], stripes, edge, gradient]
    }

    /// Runs pushed with `push_layer_runs` must produce the same file plain
    /// pixels do, and an already-encoded layer must store those same bytes.
    #[test]
    fn the_run_path_writes_the_same_file_as_the_pixel_path() {
        let masks = masks();
        let layers = masks.len() as u32;

        let mut from_masks = Encoder::new(head(layers), meta());
        let mut from_runs = Encoder::new(head(layers), meta());
        let mut encoded = Encoder::new(head(layers), meta());
        for pixels in &masks {
            from_masks.push_layer(pixels).expect("a pushable mask");
            from_runs
                .push_layer_runs(&runs_of(pixels), EncodeMode::Auto)
                .expect("a pushable run list");
            let record = match ree::encode(pixels, PIXELS as u32, EncodeMode::Auto).unwrap() {
                None => EncodedLayer::Empty,
                Some((_tag, stream)) => EncodedLayer::single(stream).expect("a tagged stream"),
            };
            encoded
                .push_encoded_layer(record)
                .expect("a storable layer");
        }

        let expected = from_masks.finish().expect("a writable file");
        assert_eq!(from_runs.finish().expect("a writable file"), expected);
        assert_eq!(encoded.finish().expect("a writable file"), expected);
    }

    /// The worker threads `finish` uses are a wall-clock knob, not a format one:
    /// a print written on a machine asked for two threads is the file it would
    /// have been on one asked for eight, `LHAS` and all.
    #[test]
    fn the_worker_thread_count_does_not_change_the_file() {
        let masks = masks();
        let layers = masks.len() as u32;

        let write = |threads: usize| {
            let mut encoder = Encoder::new(head(layers), meta());
            // One layer per chunk, so `finish` has one item per layer to hand to
            // its workers and the parallel path is the one that runs.
            encoder.set_layers_per_chunk(1);
            encoder.set_worker_threads(threads);
            for pixels in &masks {
                encoder.push_layer(pixels).expect("a pushable mask");
            }
            encoder.finish().expect("a writable file")
        };

        let serial = write(1);
        for threads in [2, 4, 8] {
            assert_eq!(write(threads), serial, "with {threads} workers");
        }
    }

    /// A layer's sectors are sorted by id, and a layer with no sector data is the
    /// empty-layer form rather than a table entry per sector.
    #[test]
    fn an_encoded_layer_is_sorted_and_may_be_empty() {
        let masks = masks();
        let mut sectors = Encoder::new(head(2), meta());
        sectors
            .push_encoded_layer(EncodedLayer::Sectors(vec![
                (
                    1,
                    ree::encode(&masks[1], PIXELS as u32, EncodeMode::Auto)
                        .unwrap()
                        .unwrap()
                        .1,
                ),
                (
                    0,
                    ree::encode(&masks[2], PIXELS as u32, EncodeMode::Auto)
                        .unwrap()
                        .unwrap()
                        .1,
                ),
            ]))
            .expect("a storable layer");
        sectors
            .push_encoded_layer(EncodedLayer::Sectors(Vec::new()))
            .expect("a storable empty layer");

        let mut from_masks = Encoder::new(head(2), meta());
        from_masks
            .push_layer_sectors(&[(0, masks[2].clone()), (1, masks[1].clone())])
            .expect("a pushable layer");
        from_masks
            .push_layer_sectors(&[])
            .expect("a pushable empty layer");

        assert_eq!(
            sectors.finish().expect("a writable file"),
            from_masks.finish().expect("a writable file")
        );
    }

    /// The META minima section 11.2 requires, so a test can validate a file it
    /// wrote rather than only read its structure back.
    fn conforming_meta() -> Meta {
        Meta {
            meta_version: Some(1),
            timing: Timing {
                normal_exposure_ms: Some(2500),
                bottom_exposure_ms: Some(30000),
                bottom_layer_count: Some(2),
                transition_layer_count: Some(2),
                layer_height_um: Some(50),
                lift_slow_distance_um: Some(5000),
                lift_slow_speed_um_min: Some(65000),
                retract_fast_distance_um: Some(5000),
                retract_fast_speed_um_min: Some(150000),
                ..Timing::default()
            },
            ..Meta::default()
        }
    }

    /// Overrides whose deltas are equal share one `LROV` chunk, so a delta set on a
    /// range costs one chunk while a delta that differs by one field is its own; and
    /// each pair still resolves from the chunk its own entry names (section 4.5).
    #[test]
    fn equal_override_deltas_share_one_chunk() {
        use crate::reader::LumenFile;
        use crate::validate::Level;

        let exposure = |ms: u32| Timing {
            normal_exposure_ms: Some(ms),
            ..Timing::default()
        };
        let mut encoder = Encoder::new(head(4), conforming_meta());
        for _ in 0..4 {
            encoder.push_layer(&[0u8; PIXELS]).expect("a layer");
        }
        encoder
            .set_overrides(vec![
                Override {
                    layer: 0,
                    sector_id: 0,
                    timing: exposure(2800),
                },
                Override {
                    layer: 1,
                    sector_id: 0,
                    timing: exposure(2800),
                },
                Override {
                    layer: 2,
                    sector_id: 0,
                    timing: exposure(2800),
                },
                Override {
                    layer: 3,
                    sector_id: 0,
                    timing: exposure(3000),
                },
            ])
            .expect("one override set per (layer, sector)");

        let bytes = encoder.finish().expect("a writable file");
        let file =
            LumenFile::open(&bytes, Level::Strict).expect("a shared chunk is a conforming file");
        let first_lrov = |layer: u32| {
            file.layer_table()
                .entry(layer, 0)
                .expect("an entry for every layer")
                .first_lrov
        };
        assert_eq!(first_lrov(0), first_lrov(1), "equal deltas share a chunk");
        assert_eq!(first_lrov(1), first_lrov(2), "equal deltas share a chunk");
        assert_ne!(
            first_lrov(2),
            first_lrov(3),
            "a delta that differs is its own chunk"
        );
        let chunks = file
            .directory()
            .entries()
            .filter(|d| d.chunk_type == crate::container::ChunkType::LROV)
            .count();
        assert_eq!(chunks, 2, "four overrides with two distinct deltas");

        // The sharing is an encoding detail: every pair still resolves from the
        // chunk its entry names.
        for layer in 0..3 {
            assert_eq!(
                file.timing_for(layer, 0).expect("resolvable").exposure_ms,
                2800
            );
        }
        assert_eq!(file.timing_for(3, 0).expect("resolvable").exposure_ms, 3000);
    }

    /// The dictionary's training samples come from across the print rather than from
    /// its first chunks: the start of a print is its raft and its bottom layers, and a
    /// dictionary trained on those describes the rest of the file badly.
    #[test]
    fn dictionary_samples_span_the_print() {
        // Sixteen chunks, each filled with its own byte value, so every sample says by
        // its content which chunk it came from. Each chunk is four windows long.
        let plaintexts: Vec<Vec<u8>> = (1u8..=16).map(|value| vec![value; 4096]).collect();

        let samples = dictionary_samples(&plaintexts);

        let chunks: std::collections::BTreeSet<u8> = samples.iter().map(|s| s[0]).collect();
        assert_eq!(chunks.len(), 16, "every chunk of the print contributes");
        assert!(
            samples.len() <= DICTIONARY_SAMPLE_WINDOWS,
            "the budget holds"
        );
        assert!(
            samples.iter().all(|sample| sample.len() == 1024),
            "a sample is one window"
        );
        assert_eq!(
            samples,
            dictionary_samples(&plaintexts),
            "sampling is deterministic"
        );
    }

    /// A print a dictionary cannot help is written without one: high-entropy
    /// greyscale, which is what an anti-aliased print's planes look like.
    #[test]
    fn a_dictionary_that_does_not_pay_is_not_written() {
        let layers = 8u32;
        let mut head = head(layers);
        head.display_width_px = 1024;
        head.display_height_px = 1024;
        let pixels = (head.display_width_px * head.display_height_px) as usize;

        let mut state = 0x2545_F491_4F6C_DD1Du64;
        let mut random = || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            state >> 24
        };
        let mut encoder = Encoder::new(head, conforming_meta());
        encoder.set_dictionary(true);
        for _ in 0..layers {
            let mask: Vec<u8> = (0..pixels).map(|_| random() as u8).collect();
            encoder.push_layer(&mask).expect("a layer");
        }

        let bytes = encoder.finish().expect("a writable file");
        let file = crate::reader::LumenFile::open(&bytes, crate::validate::Level::Strict)
            .expect("a conforming file");
        assert!(
            file.dictionary().is_none(),
            "a dictionary that makes the frames larger is not written"
        );
    }

    /// A stream that carries no tag is not a layer, and the encoder says so
    /// before it reaches the layer table.
    /// A print whose layers barely move: a white band per row whose left edge
    /// advances one pixel per layer, so every layer's run lengths are close to its
    /// neighbours' without being equal. This is the shape the attached encoding is
    /// for, and the shape a byte-counting encoder would get wrong the other way -
    /// on a print this smooth the plain form's bytes are the ones that compress.
    fn moving_band_layers(count: u32) -> Vec<Vec<u8>> {
        const SIDE: usize = 64;
        let mut layers = Vec::new();
        for index in 0..count as usize {
            let mut pixels = vec![0u8; SIDE * SIDE];
            for (row, line) in pixels.chunks_mut(SIDE).enumerate() {
                // A lens that walks one pixel to the right per layer: its chord
                // grows and shrinks smoothly down the rows, and its boundaries
                // move between layers without the run lengths repeating.
                let half = if row < 32 { row / 2 } else { (63 - row) / 2 };
                let centre = 24 + index;
                let start = centre.saturating_sub(half);
                let end = (centre + half + 1).min(SIDE);
                if start < end {
                    line[start..end].fill(255);
                }
            }
            layers.push(pixels);
        }
        layers
    }

    /// The band fixture's pixels per layer.
    const PIXELS_BAND: u32 = 64 * 64;

    fn band_head(layers: u32) -> Head {
        Head {
            display_width_px: 64,
            display_height_px: 64,
            ..head(layers)
        }
    }

    fn written_with_probe(probe: bool) -> (Vec<u8>, Vec<Vec<u8>>) {
        let layers = moving_band_layers(8);
        let mut encoder = Encoder::new(band_head(layers.len() as u32), conforming_meta());
        encoder.set_tag_probe(probe);
        for layer in &layers {
            encoder.push_layer(layer).expect("a pushable layer");
        }
        (encoder.finish().expect("a writable file"), layers)
    }

    #[test]
    fn the_tag_probe_keeps_the_smaller_encoding() {
        let (probed, layers) = written_with_probe(true);
        let (plain, _) = written_with_probe(false);

        // The probe changes bytes, never content: both files decode to the layers
        // that were pushed.
        for bytes in [&probed, &plain] {
            let file = crate::LumenFile::open(bytes, crate::validate::Level::Strict)
                .expect("a conforming file");
            for (index, mask) in layers.iter().enumerate() {
                assert_eq!(&file.layer(index as u32).unwrap().pixels, mask);
            }
        }

        // Whichever way it decided, it did not write a larger file, and on this
        // print it decided the other way from the plain encoding.
        assert!(
            probed.len() <= plain.len(),
            "the probe must not write a larger file: {} against {}",
            probed.len(),
            plain.len()
        );
        assert!(
            probed.len() < plain.len(),
            "a print whose layers barely move is where the attached form wins: \
             {} against {}",
            probed.len(),
            plain.len()
        );
    }

    #[test]
    fn a_pre_encoded_layer_can_carry_its_alternative() {
        // The parallel path: a caller encodes a layer on its own thread and hands
        // over both encodings, so the probe still has something to weigh when the
        // group closes. Both files decode to the same layers, and the pair is never
        // larger than the plain one.
        let layers = moving_band_layers(8);
        let mut paired = Encoder::new(band_head(layers.len() as u32), conforming_meta());
        let mut plain = Encoder::new(band_head(layers.len() as u32), conforming_meta());
        for layer in &layers {
            let (tag, primary) = ree::encode(layer, PIXELS_BAND, EncodeMode::Auto)
                .unwrap()
                .expect("a non-empty layer");
            assert_eq!(tag, ree::TAG_BINARY);
            let (other_tag, alternative) = ree::encode(layer, PIXELS_BAND, EncodeMode::Attached)
                .unwrap()
                .expect("a non-empty layer");
            assert_eq!(other_tag, ree::TAG_ATTACHED);
            paired
                .push_encoded_layer_pair(
                    EncodedLayer::single(primary).unwrap(),
                    Some(EncodedLayer::single(alternative).unwrap()),
                )
                .expect("a pair of encodings of one layer");
            plain
                .push_encoded_layer_pair(
                    EncodedLayer::single(
                        ree::encode(layer, PIXELS_BAND, EncodeMode::Auto)
                            .unwrap()
                            .expect("a non-empty layer")
                            .1,
                    )
                    .unwrap(),
                    None,
                )
                .expect("one encoding");
        }
        let paired = paired.finish().expect("a writable file");
        let plain = plain.finish().expect("a writable file");
        for bytes in [&paired, &plain] {
            let file = crate::LumenFile::open(bytes, crate::validate::Level::Strict)
                .expect("a conforming file");
            for (index, mask) in layers.iter().enumerate() {
                assert_eq!(&file.layer(index as u32).unwrap().pixels, mask);
            }
        }
        assert!(
            paired.len() < plain.len(),
            "the pair decides what the probe would have decided: {} against {}",
            paired.len(),
            plain.len()
        );
    }

    #[test]
    fn the_tag_probe_can_be_turned_off() {
        let (probed, _) = written_with_probe(true);
        let (plain, _) = written_with_probe(false);
        assert_eq!(
            plain.len(),
            written_with_probe(false).0.len(),
            "the same input writes the same file"
        );
        assert_ne!(probed.len(), plain.len());
    }

    #[test]
    fn an_encoded_layer_is_checked_before_it_is_stored() {
        let mut encoder = Encoder::new(head(1), meta());
        for empty_or_unknown in [Vec::new(), vec![0x04, 0x00], vec![0xFF]] {
            assert_eq!(
                EncodedLayer::single(empty_or_unknown.clone())
                    .unwrap_err()
                    .check(),
                Check::ReeTag
            );
            assert_eq!(
                encoder
                    .push_encoded_layer(EncodedLayer::Sectors(vec![(0, empty_or_unknown)]))
                    .unwrap_err()
                    .check(),
                Check::ReeTag
            );
        }

        // One sector id twice on a layer is not a sector list.
        let stream = vec![ree::TAG_GRAYSCALE, 0x01, 0x00, PIXELS as u8];
        assert_eq!(
            encoder
                .push_encoded_layer(EncodedLayer::Sectors(vec![
                    (2, stream.clone()),
                    (2, stream)
                ]))
                .unwrap_err()
                .check(),
            Check::LtblSectorIdUnique
        );

        // Nothing rejected above was pushed.
        assert!(encoder.layers.is_empty());
    }
}
