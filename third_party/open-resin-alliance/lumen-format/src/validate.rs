//! The checks of [`spec/17-validation.md`] section 11.
//!
//! Validation returns the **first** failure, in the order the specification
//! presents the checks: file framing, then presence, then each chunk's semantic
//! rules, then layer data, then the integrity tree, then encryption.
//!
//! That ordering is load-bearing. The conformance corpus asserts that each
//! invalid vector fails its advertised check *first*, so a check that runs
//! earlier than the specification's order can mask the one a vector pins. Three
//! orderings are chosen against the tempting alternative:
//!
//! - `presence.auth` runs before `crypt.chunk_flags`. A file whose header sets
//!   `ENCRYPTED` with no `AUTH` chunk fails both, and the corpus pins the
//!   presence check for that vector.
//! - Every check over a chunk payload runs *after* `crypt.chunk_flags`. A
//!   descriptor that claims a payload is sealed while the file has no key would
//!   otherwise be read as plaintext and reported as a JSON error rather than a
//!   flag inconsistency.
//! - The integer rule for durations runs over the raw JSON, before the typed
//!   parse of the chunk carrying it. A fractional duration is a defective value,
//!   not a defective document, so it reports the named check (`meta.time_integer`
//!   and its siblings) rather than the generic JSON error a failed
//!   deserialization would produce.
//!
//! A sealed file validated without a key is checked as far as its plaintext
//! allows. The directory, `HEAD`, `AUTH`, `LTBL`, the `LAYR` version fields and
//! `LHAS` are plaintext by construction (section 9.1), so those checks all run;
//! the ones that need decrypted content are skipped rather than guessed at.
//! Supply the key with [`Validator::with_key`] to run them.

use crate::check::Check;
use crate::chunkio;
use crate::chunks::extd::{Extension, CRITICAL_BIT, EXTD_RESERVED_MASK};
use crate::chunks::head::Head;
use crate::chunks::layr;
use crate::chunks::lhas::{self, LayerHashes};
use crate::chunks::ltbl::{LayerEntry, LayerTable};
use crate::chunks::preview::{self, PreviewRole};
use crate::chunks::voxl;
use crate::chunks::zdic::ZstdDictionary;
use crate::chunks::{self};
use crate::container::{
    self, ChunkDescriptor, ChunkType as Tag, Directory, FileHeader, CHUNK_FLAG_ENCRYPTED,
    FILE_HEADER_SIZE,
};
use crate::crypto::{self, Cipher, SessionKey};
use crate::error::{Error, Result};
use crate::json::{Material, Meta, Profile, Timing, REQUIRED_META_FIELDS};
use crate::ree;
use serde_json::{Map, Value};
use std::borrow::Cow;
use std::cell::{Cell, RefCell};

/// Header flag bits 0, 2 and 4: reserved, and required to be zero.
///
/// Bits 5-31 are reserved for future use and a reader must ignore them
/// (section 3.1), so they are outside this mask.
const HEADER_MUST_BE_ZERO: u32 = (1 << 0) | (1 << 2) | (1 << 4);

/// The highest duty `light_pwm` and `bottom_light_pwm` may carry (section 4.2):
/// the value is a fraction of full power over `0..=255`, not an arbitrary count.
const PWM_MAX: u32 = 255;

/// The durations the timing namespace defines, in whole milliseconds: META
/// (section 4.2, its `sectors` entries included), a `PROF`'s `settings` block
/// (4.3) and an `LROV` payload (4.5) all draw on these keys.
///
/// They are listed rather than taken from [`Timing`] because the rule is checked
/// against the raw JSON, before the typed parse: a `*_ms` key the namespace does
/// not define is an unknown field, which is preserved rather than measured.
const TIME_MS_FIELDS: [&str; 8] = [
    "normal_exposure_ms",
    "bottom_exposure_ms",
    "wait_time_before_cure_ms",
    "wait_time_after_cure_ms",
    "wait_time_after_lift_ms",
    "bottom_wait_time_before_cure_ms",
    "bottom_wait_time_after_cure_ms",
    "bottom_wait_time_after_lift_ms",
];

/// META's own duration, informational and outside the namespace a sector
/// entry, a `PROF.settings` block or an `LROV` payload draws on (section 4.2).
/// It is the
/// one duration in whole seconds rather than milliseconds: an estimate that
/// spans hours has no millisecond precision to report.
const ESTIMATED_PRINT_TIME_SEC: &str = "estimated_print_time_sec";

/// The chunk types that carry content and must therefore be sealed whenever the
/// file is (section 9.1).
const CONTENT_CHUNKS: &[Tag] = &[
    Tag::META,
    Tag::PROF,
    Tag::LROV,
    Tag::VOXL,
    Tag::ZDIC,
    Tag::LAYR,
];

/// The chunk types that must never be sealed, because a reader needs them
/// before it has a key.
const CLEARTEXT_CHUNKS: &[Tag] = &[Tag::HEAD, Tag::AUTH, Tag::LTBL, Tag::LHAS];

/// Record `[start, end)` of one sector's slice as exposed.
///
/// `covered` holds what the layer's earlier sectors exposed and `mine` what this
/// one has, both as one bit per pixel. A pixel in `covered` that is not in `mine`
/// was exposed by another sector of the same layer, which section 7.3 forbids.
/// The ranges are marked a word at a time: a whole 64-pixel word of a detailed
/// 16K layer costs one test rather than sixty-four.
fn expose(
    covered: &mut [u64],
    mine: &mut [u64],
    start: u64,
    end: u64,
    layer: u32,
    sector: u32,
) -> Result<()> {
    if start >= end {
        return Ok(());
    }
    let first = start as usize / 64;
    let last = (end - 1) as usize / 64;
    for word in first..=last {
        let low = if word == first {
            start as usize % 64
        } else {
            0
        };
        let high = if word == last {
            (end - 1) as usize % 64
        } else {
            63
        };
        let bits = (u64::MAX << low) & (u64::MAX >> (63 - high));
        if covered[word] & bits & !mine[word] != 0 {
            return Err(Error::new(
                Check::SectorPartition,
                format!(
                    "layer {layer}: sector {sector} exposes a pixel another sector already exposes"
                ),
            ));
        }
        covered[word] |= bits;
        mine[word] |= bits;
    }
    Ok(())
}

/// How thoroughly to validate.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Level {
    /// Default for printing: accept structurally valid files, skip what is
    /// unknown, and do not enforce canonical encodings.
    #[default]
    Loose,
    /// For verification tools: enforce every rule, including the strict-mode
    /// ones marked in section 11.
    Strict,
}

impl Level {
    /// Whether this level enforces the strict-mode checks.
    pub fn is_strict(self) -> bool {
        matches!(self, Level::Strict)
    }
}

/// A configured validator.
#[derive(Debug, Clone, Default)]
pub struct Validator {
    level: Level,
    key: Option<SessionKey>,
}

impl Validator {
    /// A validator at `level`, with no key.
    pub fn new(level: Level) -> Validator {
        Validator { level, key: None }
    }

    /// A loose validator.
    pub fn loose() -> Validator {
        Validator::new(Level::Loose)
    }

    /// A strict validator.
    pub fn strict() -> Validator {
        Validator::new(Level::Strict)
    }

    /// Supply the session key, which enables the checks that need to open
    /// sealed units: `crypt.tag_verify`, and every check over decrypted content.
    pub fn with_key(mut self, key: SessionKey) -> Validator {
        self.key = Some(key);
        self
    }

    /// The configured level.
    pub fn level(&self) -> Level {
        self.level
    }

    /// The configured key, if any.
    pub fn key(&self) -> Option<&SessionKey> {
        self.key.as_ref()
    }

    /// Validate, returning the first failure.
    pub fn validate(&self, buf: &[u8]) -> Result<()> {
        let mut ctx = Ctx::new(buf, self.level, self.key)?;
        ctx.check_framing()?;
        ctx.check_chunk_flags()?;

        let head = ctx.read_hdr()?;
        check_hdr(&head)?;
        ctx.display_pixels.set(head.total_pixels());

        let auth = ctx.read_auth()?;
        ctx.cipher = auth.as_ref().map(|a| a.cipher);

        let meta = ctx.read_meta()?;
        if let Some(meta) = meta.as_ref() {
            check_meta(meta)?;
        }
        let profile = ctx.read_profile()?;
        if let Some(profile) = profile.as_ref() {
            check_profile(profile)?;
        }

        ctx.check_lrov_payloads()?;

        ctx.check_previews()?;
        ctx.check_extensions()?;
        ctx.check_voxl()?;

        let ltbl = ctx.read_ltbl()?;
        let zdic = ctx.read_zdic()?;
        ctx.check_layer_data(&head, &ltbl, &zdic)?;
        let hashes = ctx.check_hashes(&head)?;
        if let Some(hashes) = hashes.as_ref() {
            ctx.check_leaves(&ltbl, &zdic, hashes)?;
        }

        if let (Some(key), Some(cipher)) = (ctx.key.as_ref(), ctx.cipher) {
            ctx.check_sealed_units(key, cipher)?;
        }
        Ok(())
    }
}

/// Validate `buf` at `level`, returning the first failure.
pub fn validate(buf: &[u8], level: Level) -> Result<()> {
    Validator::new(level).validate(buf)
}

/// Validate an encrypted file, opening sealed units with `key`.
pub fn validate_with_key(buf: &[u8], level: Level, key: SessionKey) -> Result<()> {
    Validator::new(level).with_key(key).validate(buf)
}

/// A validator's parse of the container, shared by every check.
struct Ctx<'a> {
    buf: &'a [u8],
    header: FileHeader,
    dir: Directory,
    level: Level,
    key: Option<SessionKey>,
    cipher: Option<Cipher>,
    /// One decompressed `LAYR` chunk, so a walk that revisits a chunk - a
    /// multi-sector layer's second sector, or a strict second pass - does not
    /// decompress it twice.
    cache: RefCell<Option<(u32, Vec<u8>)>>,
    /// The display's pixel count, set once `HEAD` is parsed. A frame's declared
    /// output is bounded per slice of it (section 11.3), and the chunk walks run
    /// after the header, so by then it is known.
    display_pixels: Cell<u32>,
}

impl<'a> Ctx<'a> {
    fn new(buf: &'a [u8], level: Level, key: Option<SessionKey>) -> Result<Ctx<'a>> {
        container::verify_trailer_crc(buf)?;
        let header = FileHeader::parse(buf)?;
        let dir = container::parse_directory(buf, &header)?;
        Ok(Ctx {
            buf,
            header,
            dir,
            level,
            key,
            cipher: None,
            cache: RefCell::new(None),
            display_pixels: Cell::new(0),
        })
    }

    /// The stored bytes of a chunk, sealed or not.
    fn stored(&self, d: &ChunkDescriptor) -> Result<&'a [u8]> {
        chunkio::stored(self.buf, d)
    }

    /// The plaintext bytes of a chunk, or `None` when it is sealed and no key is
    /// available.
    fn plaintext(&self, d: &ChunkDescriptor) -> Result<Option<Vec<u8>>> {
        let stored = self.stored(d)?;
        chunkio::plaintext(d, stored, self.cipher, self.key.as_ref())
    }

    /// The decrypted, decompressed payload of a chunk, or `None` when it cannot
    /// be read.
    fn payload(&self, d: &ChunkDescriptor) -> Result<Option<Vec<u8>>> {
        let stored = self.stored(d)?;
        chunkio::payload(d, stored, self.cipher, self.key.as_ref())
    }

    // -- phase 1: framing ---------------------------------------------------

    fn check_framing(&mut self) -> Result<()> {
        if self.header.flags & HEADER_MUST_BE_ZERO != 0 {
            return Err(Error::new(
                Check::HeaderFlagsReserved,
                format!(
                    "header.flags {:#010x} sets a reserved bit",
                    self.header.flags
                ),
            ));
        }

        let dir_start = self.header.dir_offset;
        let mut ranges: Vec<(u64, u64, Tag)> = Vec::new();
        for d in self.dir.entries() {
            let (start, end) = d.extent();
            if start < FILE_HEADER_SIZE as u64 || end > dir_start {
                return Err(Error::new(
                    Check::DirChunkExtent,
                    format!(
                        "chunk {} occupies {start}..{end}, outside the {}..{dir_start} payload region",
                        d.chunk_type, FILE_HEADER_SIZE
                    ),
                ));
            }
            ranges.push((start, end, d.chunk_type));
        }
        ranges.sort_by_key(|r| r.0);
        for pair in ranges.windows(2) {
            if pair[1].0 < pair[0].1 {
                return Err(Error::new(
                    Check::DirOverlap,
                    format!(
                        "chunk {} at {}..{} overlaps chunk {} at {}..{}",
                        pair[0].2, pair[0].0, pair[0].1, pair[1].2, pair[1].0, pair[1].1
                    ),
                ));
            }
        }

        if self.header.total_uncompressed_size != 0 {
            let sum = self.dir.total_uncompressed_size();
            if sum != self.header.total_uncompressed_size {
                return Err(Error::new(
                    Check::HeaderTotalUncompressedSize,
                    format!(
                        "header declares {} uncompressed bytes, the directory sums to {sum}",
                        self.header.total_uncompressed_size
                    ),
                ));
            }
        }

        if self.dir.find(Tag::HEAD).is_none() {
            return Err(Error::new(Check::PresenceHead, "no HEAD chunk"));
        }
        match self.dir.first_entry_index() {
            Some(i) if self.dir.descriptors[i].chunk_type == Tag::HEAD => {}
            _ => {
                return Err(Error::new(
                    Check::DirHeadFirst,
                    "the first chunk is not HEAD",
                ))
            }
        }
        if self.dir.find(Tag::META).is_none() {
            return Err(Error::new(Check::PresenceMeta, "no META chunk"));
        }
        if self.dir.find(Tag::LTBL).is_none() {
            return Err(Error::new(Check::PresenceLtbl, "no LTBL chunk"));
        }
        // Exactly one: two layer tables can disagree about which chunk holds a
        // layer's data and where its slice starts, and nothing in the file
        // resolves that (section 11.1).
        let tables = self.dir.find_all(Tag::LTBL).count();
        if tables > 1 {
            return Err(Error::new(
                Check::PresenceLtbl,
                format!("{tables} LTBL chunks; a file carries exactly one layer table"),
            ));
        }
        if self.dir.find(Tag::LAYR).is_none() {
            return Err(Error::new(Check::PresenceLayr, "no LAYR chunk"));
        }
        if self.header.encrypted() && self.dir.find(Tag::AUTH).is_none() {
            return Err(Error::new(
                Check::PresenceAuth,
                "the header sets ENCRYPTED but the file carries no AUTH chunk",
            ));
        }
        Ok(())
    }

    /// Section 11.4: the sealed bit on each descriptor agrees with the header.
    fn check_chunk_flags(&self) -> Result<()> {
        let encrypted_file = self.header.encrypted();
        for d in self.dir.entries() {
            let sealed = d.flags & CHUNK_FLAG_ENCRYPTED != 0;
            if !encrypted_file {
                if sealed {
                    return Err(Error::new(
                        Check::CryptChunkFlags,
                        format!(
                            "{} sets the sealed bit, but the file is not encrypted and no key could open it",
                            d.chunk_type
                        ),
                    ));
                }
                continue;
            }
            if CLEARTEXT_CHUNKS.contains(&d.chunk_type) {
                if sealed {
                    return Err(Error::new(
                        Check::CryptChunkFlags,
                        format!("{} must stay plaintext", d.chunk_type),
                    ));
                }
            } else if CONTENT_CHUNKS.contains(&d.chunk_type) && !sealed {
                return Err(Error::new(
                    Check::CryptChunkFlags,
                    format!(
                        "{} is content and must be sealed in an encrypted file",
                        d.chunk_type
                    ),
                ));
            }
        }
        Ok(())
    }

    // -- phase 2: the plaintext chunks -------------------------------------

    fn read_hdr(&self) -> Result<Head> {
        let d = self.dir.find(Tag::HEAD).expect("presence checked");
        let payload = self
            .plaintext(d)?
            .expect("HEAD is never sealed, so it is always readable");
        Head::parse(&payload)
    }

    fn read_auth(&self) -> Result<Option<crypto::Auth>> {
        let Some(d) = self.dir.find(Tag::AUTH) else {
            return Ok(None);
        };
        let payload = self
            .plaintext(d)?
            .expect("AUTH is never sealed, so it is always readable");
        let auth = crypto::parse_auth(&payload)?;
        if let Some(password) = auth.password.as_ref() {
            // The budget is checked here, before any caller can derive a key
            // from these parameters.
            crypto::check_argon2_budget(password)?;
        }
        Ok(Some(auth))
    }

    /// Every `LAYR` chunk, in directory order: its index and its descriptor.
    fn layr_chunks(&self) -> Vec<(u32, ChunkDescriptor)> {
        self.dir
            .descriptors
            .iter()
            .enumerate()
            .filter(|(_, d)| !d.is_null() && d.chunk_type == Tag::LAYR)
            .map(|(index, d)| (index as u32, *d))
            .collect()
    }

    /// The plaintext frame of a `LAYR` chunk, or `None` when it is sealed and no
    /// key is available.
    ///
    /// `index` is the chunk's directory index, which is what its frame's
    /// associated data binds it to.
    fn layr_frame<'b>(&'b self, index: u32, d: &ChunkDescriptor) -> Result<Option<Cow<'b, [u8]>>> {
        chunkio::layr_frame(
            d,
            index,
            chunkio::stored(self.buf, d)?,
            self.cipher,
            self.key.as_ref(),
        )
    }

    /// Run `f` over the decompressed output of a `LAYR` chunk, decompressing it
    /// first if it is not the cached one.
    fn with_chunk<T>(
        &self,
        index: u32,
        dictionary: Option<&[u8]>,
        f: impl FnOnce(&[u8]) -> Result<T>,
    ) -> Result<T> {
        if self.cache.borrow().as_ref().map(|(k, _)| *k) != Some(index) {
            let data = {
                let descriptor = self.layr_descriptor(index)?;
                let frame = self.layr_frame(index, descriptor)?.ok_or_else(|| {
                    Error::new(
                        Check::CryptNoKey,
                        "the frame is sealed and no session key is available",
                    )
                })?;
                // The frame is released before the output is cached, so the two
                // are never live at the same time. Its declared output is bounded
                // by the slices the layer table points into this chunk, which is
                // the specification's rule (section 11.3) - a ratio guard cannot
                // stand in for it, because a block of repeating layers compresses
                // past any fixed ratio and is still conforming.
                let bound = self.chunk_bound(index, frame.len());
                chunks::decompress_frame(&frame, dictionary, bound)?
            };
            *self.cache.borrow_mut() = Some((index, data));
        }
        let guard = self.cache.borrow();
        let (_, data) = guard.as_ref().expect("filled immediately above");
        f(data)
    }

    /// How many slices the layer table points into a `LAYR` chunk.
    ///
    /// A slice is an entry that carries bytes, and the count is floored at one so
    /// that a chunk nothing points into is still allowed one layer's worth: this
    /// is the bound of section 11.3, and the reader uses the same definition so a
    /// file cannot pass one and fail the other.
    fn chunk_bound(&self, index: u32, frame_len: usize) -> u64 {
        let pixels = self.display_pixels.get();
        if pixels == 0 {
            // Unreachable through `validate`, which reads the header first; a
            // bound from the frame's own bytes is the fallback that cannot be
            // tighter than a conforming file.
            return (frame_len as u64).saturating_mul(chunks::MAX_ZSTD_RATIO as u64);
        }
        chunks::allocation_bound(self.slices_into(index), pixels)
    }

    fn slices_into(&self, index: u32) -> u64 {
        let Ok(Some(table)) = self.read_ltbl() else {
            return 1;
        };
        let count = table
            .entries
            .iter()
            .filter(|entry| !entry.is_empty() && entry.first_layr == index)
            .count() as u64;
        count.max(1)
    }

    /// The descriptor of the `LAYR` chunk at directory index `index`.
    fn layr_descriptor(&self, index: u32) -> Result<&ChunkDescriptor> {
        self.dir
            .descriptors
            .get(index as usize)
            .filter(|d| !d.is_null() && d.chunk_type == Tag::LAYR)
            .ok_or_else(|| {
                Error::new(
                    Check::LtblFirstLayrInRange,
                    format!("directory index {index} is not a LAYR chunk"),
                )
            })
    }

    /// One entry's slice of its `LAYR` chunk's decompressed output.
    fn slice_of(&self, entry: &LayerEntry, dictionary: Option<&[u8]>) -> Result<Vec<u8>> {
        if entry.is_empty() {
            return Ok(Vec::new());
        }
        let start = entry.data_offset as usize;
        let len = entry.data_size as usize;
        self.with_chunk(entry.first_layr, dictionary, |chunk| {
            chunk
                .get(start..start.saturating_add(len))
                .map(|slice| slice.to_vec())
                .ok_or_else(|| {
                    Error::new(
                        Check::LtblOffsetWithinChunk,
                        format!(
                            "a slice of {len} bytes at offset {start} lies outside its chunk's {} bytes",
                            chunk.len()
                        ),
                    )
                })
        })
    }

    /// The stored bytes of a layer: its sectors' slices, concatenated in
    /// ascending `sector_id`.
    fn layer_bytes(&self, entries: &[LayerEntry], dictionary: Option<&[u8]>) -> Result<Vec<u8>> {
        let mut out = Vec::new();
        for entry in entries {
            out.extend_from_slice(&self.slice_of(entry, dictionary)?);
        }
        Ok(out)
    }

    fn read_ltbl(&self) -> Result<Option<LayerTable>> {
        match self.dir.find(Tag::LTBL) {
            None => Ok(None),
            Some(d) => {
                let payload = self
                    .plaintext(d)?
                    .expect("LTBL is never sealed, so it is always readable");
                Ok(Some(LayerTable::parse(&payload)?))
            }
        }
    }

    fn read_zdic(&self) -> Result<Option<ZstdDictionary>> {
        let mut found = self.dir.find_all(Tag::ZDIC);
        let Some(d) = found.next() else {
            return Ok(None);
        };
        if found.next().is_some() {
            return Err(Error::new(
                Check::ZdicSingle,
                "more than one ZDIC chunk is present",
            ));
        }
        match self.plaintext(d)? {
            None => Ok(None),
            Some(raw) => Ok(Some(ZstdDictionary::parse(&raw)?)),
        }
    }

    // -- phase 3: the JSON chunks ------------------------------------------

    /// Parse a `META` payload while keeping its raw object, which is the only
    /// way to tell an absent required field from one that is `null`.
    fn read_meta(&self) -> Result<Option<Meta>> {
        let Some(d) = self.dir.find(Tag::META) else {
            return Ok(None);
        };
        let Some(bytes) = self.payload(d)? else {
            return Ok(None);
        };
        let value: Value = serde_json::from_slice(&bytes).map_err(json_error)?;
        let object = value
            .as_object()
            .ok_or_else(|| Error::new(Check::MetaJson, "META is not a JSON object"))?;
        let missing = Timing::missing_from(object, &REQUIRED_META_FIELDS);
        if !missing.is_empty() {
            return Err(Error::new(
                Check::MetaRequiredFields,
                format!("META is missing {}", missing.join(", ")),
            ));
        }
        check_integer_durations(
            object,
            TIME_MS_FIELDS
                .iter()
                .copied()
                .chain(std::iter::once(ESTIMATED_PRINT_TIME_SEC)),
            Check::MetaTimeInteger,
        )?;
        check_sectors_shape(object)?;
        let meta: Meta = serde_json::from_value(value).map_err(json_error)?;
        Ok(Some(meta))
    }

    fn read_profile(&self) -> Result<Option<Profile>> {
        let Some(d) = self.dir.find(Tag::PROF) else {
            return Ok(None);
        };
        let Some(bytes) = self.payload(d)? else {
            return Ok(None);
        };
        let value: Value = serde_json::from_slice(&bytes).map_err(json_error)?;
        // A profile's durations live in its `settings` block, which draws on
        // META's own field names. Anything else about the block's shape is the
        // typed parse's business.
        if let Some(settings) = value.get("settings").and_then(Value::as_object) {
            check_integer_durations(
                settings,
                TIME_MS_FIELDS.iter().copied(),
                Check::ProfSettingsTimeInteger,
            )?;
        }
        Ok(Some(serde_json::from_value(value).map_err(json_error)?))
    }

    /// Every `LROV` chunk's payload rules: the integer rule for the durations a
    /// delta carries, and nothing else - a delta has no layer, range or sector
    /// field to check, because the `LTBL` entry that points at it is what places
    /// it (`lrov.orphan` checks that placement, and needs the table).
    fn check_lrov_payloads(&self) -> Result<()> {
        for d in self.dir.find_all(Tag::LROV).collect::<Vec<_>>() {
            let Some(bytes) = self.payload(d)? else {
                continue;
            };
            let value: Value = serde_json::from_slice(&bytes).map_err(|e| {
                Error::new(
                    Check::LrovJson,
                    format!("the LROV payload is not a valid object: {e}"),
                )
            })?;
            let object = value
                .as_object()
                .ok_or_else(|| Error::new(Check::LrovJson, "LROV is not a JSON object"))?;
            check_integer_durations(
                object,
                TIME_MS_FIELDS.iter().copied(),
                Check::LrovTimeInteger,
            )?;
            check_pwm_object(object, "LROV")?;
        }
        Ok(())
    }

    fn check_previews(&self) -> Result<()> {
        for d in self.dir.find_all(Tag::PREV).collect::<Vec<_>>() {
            PreviewRole::from_flags(d.flags)?;
            if self.level.is_strict() {
                if let Some(bytes) = self.payload(d)? {
                    preview::check_png(&bytes)?;
                }
            }
        }
        Ok(())
    }

    /// `EXTD` frame checks.
    ///
    /// A sealed extension is checked only for its flag rules: the specification
    /// leaves its compression to the extension, and no extension is implemented,
    /// so its payload is opaque - which is how a reader treats any extension it
    /// does not implement. The `critical` rule binds either way.
    fn check_extensions(&self) -> Result<()> {
        for d in self.dir.find_all(Tag::EXTD).collect::<Vec<_>>() {
            if d.is_encrypted() {
                check_opaque_extension(d.flags)?;
                continue;
            }
            let Some(frame) = self.payload(d)? else {
                continue;
            };
            let ext = Extension::parse(&frame, d.flags)?;
            check_extension(&ext)?;
        }
        Ok(())
    }

    fn check_voxl(&self) -> Result<()> {
        if !self.level.is_strict() {
            return Ok(());
        }
        for d in self.dir.find_all(Tag::VOXL).collect::<Vec<_>>() {
            if let Some(bytes) = self.payload(d)? {
                voxl::require_voxl(&bytes)?;
            }
        }
        Ok(())
    }

    // -- phase 4: layer data -----------------------------------------------

    /// The `LAYR` chunks, `LTBL`, and every (layer, sector)'s REE stream.
    ///
    /// The chunk walk is what keeps peak memory at one chunk: a frame is
    /// decompressed, its slices are checked, and it is released before the next
    /// one is read. The `LTBL` rules that need only the table and the frames'
    /// declared output lengths run first, so a table that lies about where a
    /// layer sits is reported before anything is decompressed.
    fn check_layer_data(
        &self,
        head: &Head,
        ltbl: &Option<LayerTable>,
        zdic: &Option<ZstdDictionary>,
    ) -> Result<()> {
        let Some(ltbl) = ltbl.as_ref() else {
            return Ok(());
        };
        let total_layers = head.total_layers;
        let total_pixels = head.total_pixels();
        let dict_bytes = zdic.as_ref().map(|z| z.dict_bytes.as_slice());

        if ltbl.layer_count != total_layers {
            return Err(Error::new(
                Check::LtblLayerCount,
                format!(
                    "LTBL describes {} layers, HEAD says {total_layers}",
                    ltbl.layer_count
                ),
            ));
        }

        // Section 4.9: MULTI_SECTOR is set exactly when some layer carries more
        // than one sector with data, so the flag and the table must agree either
        // way round.
        if self.header.multi_sector() != ltbl.is_multi_sector() {
            return Err(Error::new(
                Check::HeadMultiSectorFlag,
                if self.header.multi_sector() {
                    "MULTI_SECTOR is set but no layer carries more than one sector".to_string()
                } else {
                    "a layer carries more than one sector but MULTI_SECTOR is clear".to_string()
                },
            ));
        }

        // How many slices each chunk holds, which is what bounds its frame's
        // declared output.
        let mut slices_per_chunk: std::collections::HashMap<u32, u64> =
            std::collections::HashMap::new();
        for entry in &ltbl.entries {
            if !entry.is_empty() {
                *slices_per_chunk.entry(entry.first_layr).or_insert(0) += 1;
            }
        }

        // Each chunk's declared output length, by directory index: what the
        // offset rule measures against. `None` marks a chunk whose frame could
        // not be opened, which happens only when it is sealed and no key was
        // supplied.
        let chunks = self.layr_chunks();
        let mut output_size: Vec<Option<u64>> = vec![None; self.dir.descriptors.len()];
        let mut dictionary_used = false;
        let mut unreadable = false;
        for (index, descriptor) in &chunks {
            let stored = self.stored(descriptor)?;
            // A sealed frame is at least one AEAD unit (section 11.4).
            if descriptor.flags & CHUNK_FLAG_ENCRYPTED != 0
                && stored.len() < layr::LAYR_HEADER_LEN + crypto::UNIT_OVERHEAD
            {
                return Err(Error::new(
                    Check::CryptChunkFlags,
                    format!(
                        "the frame at directory index {index} is {} bytes, smaller than one \
                         sealed unit",
                        stored.len()
                    ),
                ));
            }
            let Some(frame) = self.layr_frame(*index, descriptor)? else {
                // Sealed with no key: the version field is plaintext and already
                // checked by `layr_frame`, and the frame is not ours to read.
                unreadable = true;
                continue;
            };
            let size = chunks::frame_content_size(&frame)?;
            output_size[*index as usize] = Some(size);
            let slices = slices_per_chunk.get(index).copied().unwrap_or(0).max(1);
            let bound = chunks::allocation_bound(slices, total_pixels);
            if size > bound {
                return Err(Error::new(
                    Check::FrameAllocationBound,
                    format!(
                        "the frame at directory index {index} declares {size} bytes; {slices} \
                         slices of {total_pixels} pixels bound it at {bound}"
                    ),
                ));
            }
            match (chunks::frame_dict_id(&frame)?, zdic.as_ref()) {
                // A frame that reports no dictionary is not this rule's business
                // either way: an encoder may compress one frame without the
                // dictionary another uses, and "the file's dictionary is used by
                // nothing" is the presence rule below, not this one.
                (0, _) => {}
                (id, Some(z)) if id == z.dict_id => dictionary_used = true,
                // The frames' half of the agreement: with no `ZDIC` in the file
                // they must all report none, and none of them may name a
                // dictionary the file does not carry.
                (id, None) => {
                    return Err(Error::new(
                        Check::LayrDictIdAbsent,
                        format!(
                            "the frame at directory index {index} reports dictionary {id} but \
                             the file carries no ZDIC"
                        ),
                    ))
                }
                (id, Some(z)) => {
                    return Err(Error::new(
                        Check::LayrDictIdMatch,
                        format!(
                            "the frame at directory index {index} reports dictionary {id}, ZDIC \
                             declares {}",
                            z.dict_id
                        ),
                    ))
                }
            }
        }
        if !unreadable && zdic.is_some() && !dictionary_used {
            return Err(Error::new(
                Check::PresenceZdic,
                "ZDIC is present but no LAYR frame uses a dictionary",
            ));
        }

        // The `LTBL` rules that need the table and the declared output lengths.
        let mut slices: Vec<(u32, u64, u64)> = Vec::with_capacity(ltbl.entries.len());
        let mut references: std::collections::HashMap<u32, u32> = std::collections::HashMap::new();
        for (i, entry) in ltbl.entries.iter().enumerate() {
            // Every entry names a `LAYR` chunk, the ones with no run included:
            // section 4.9 has no null convention for this field, unlike
            // `first_lrov`.
            if self.layr_descriptor(entry.first_layr).is_err() {
                return Err(Error::new(
                    Check::LtblFirstLayrInRange,
                    format!(
                        "entry {i} names directory index {} for its run, which is not a LAYR chunk",
                        entry.first_layr
                    ),
                ));
            }
            if let Some(size) = output_size
                .get(entry.first_layr as usize)
                .copied()
                .flatten()
            {
                let end = entry.data_offset.saturating_add(u64::from(entry.data_size));
                if end > size {
                    return Err(Error::new(
                        Check::LtblOffsetWithinChunk,
                        format!(
                            "entry {i} claims {} bytes at offset {}, past its chunk's {size} \
                             bytes",
                            entry.data_size, entry.data_offset
                        ),
                    ));
                }
                if !entry.is_empty() {
                    slices.push((entry.first_layr, entry.data_offset, end));
                }
            }
            if entry.first_lrov != 0 {
                let is_lrov = self
                    .dir
                    .descriptors
                    .get(entry.first_lrov as usize)
                    .is_some_and(|d| !d.is_null() && d.chunk_type == Tag::LROV);
                if !is_lrov {
                    return Err(Error::new(
                        Check::LtblFirstLrovInRange,
                        format!(
                            "entry {i} names directory index {} for its overrides, which is not \
                             an LROV chunk",
                            entry.first_lrov
                        ),
                    ));
                }
                *references.entry(entry.first_lrov).or_insert(0) += 1;
            }
        }

        // Slices of one chunk do not overlap (section 4.9).
        slices.sort_unstable();
        for pair in slices.windows(2) {
            if pair[0].0 == pair[1].0 && pair[1].1 < pair[0].2 {
                return Err(Error::new(
                    Check::LtblSlicesDisjoint,
                    format!(
                        "two slices of the chunk at directory index {} overlap: {}..{} and \
                         {}..{}",
                        pair[0].0, pair[0].1, pair[0].2, pair[1].1, pair[1].2
                    ),
                ));
            }
        }

        // An entry's `0` says that `(layer, sector)` has no overrides. What
        // contradicts it is an override set nothing applies: an `LROV` chunk no
        // entry names whose payload no named chunk also carries
        // (`ltbl.first_lrov_null`). A chunk no entry names whose payload a named
        // chunk *does* carry contradicts nothing - those values are applied at
        // the pair that names their twin - so that file is the orphan case below
        // rather than this one.
        let mut named_payloads: Vec<Vec<u8>> = Vec::new();
        let mut unnamed: Vec<usize> = Vec::new();
        for (index, descriptor) in self.dir.descriptors.iter().enumerate() {
            if descriptor.is_null() || descriptor.chunk_type != Tag::LROV {
                continue;
            }
            if references.get(&(index as u32)).copied().unwrap_or(0) > 0 {
                if let Ok(Some(plain)) = self.plaintext(descriptor) {
                    named_payloads.push(plain);
                }
            } else {
                unnamed.push(index);
            }
        }
        for index in unnamed {
            let descriptor = &self.dir.descriptors[index];
            let Ok(Some(plain)) = self.plaintext(descriptor) else {
                // Sealed and unreadable without a key: this reader cannot tell
                // whether the payload is applied elsewhere, so it does not claim
                // the entry's `0` is a lie.
                continue;
            };
            if !named_payloads.contains(&plain) {
                return Err(Error::new(
                    Check::LtblFirstLrovNull,
                    format!(
                        "the LROV chunk at directory index {index} carries overrides that no entry \
                         applies, so an entry's first_lrov of 0 does not hold"
                    ),
                ));
            }
        }

        // Every LROV chunk is referenced by at least one entry (`lrov.orphan`). A
        // chunk several entries name is an override set that covers all of them -
        // how a range, or any set of pairs sharing one delta, is written (4.5) - so
        // only a chunk nobody names fails here.
        for (index, descriptor) in self.dir.descriptors.iter().enumerate() {
            if descriptor.is_null() || descriptor.chunk_type != Tag::LROV {
                continue;
            }
            if references.get(&(index as u32)).copied().unwrap_or(0) == 0 {
                return Err(Error::new(
                    Check::LrovOrphan,
                    format!("the LROV chunk at directory index {index} is referenced by no entry"),
                ));
            }
        }

        // Every (layer, sector)'s REE stream, one chunk at a time.
        for (index, _) in &chunks {
            if output_size
                .get(*index as usize)
                .copied()
                .flatten()
                .is_none()
            {
                continue;
            }
            self.with_chunk(*index, dict_bytes, |plain| {
                for (i, entry) in ltbl.entries.iter().enumerate() {
                    if entry.first_layr != *index || entry.is_empty() {
                        continue;
                    }
                    let start = entry.data_offset as usize;
                    let end = start.checked_add(entry.data_size as usize).ok_or_else(|| {
                        Error::new(Check::LtblOffsetWithinChunk, "the slice range overflows")
                    })?;
                    let data = plain.get(start..end).ok_or_else(|| {
                        Error::new(
                            Check::LtblOffsetWithinChunk,
                            format!("entry {i} runs past its chunk's decompressed output"),
                        )
                    })?;
                    self.check_layer_stream(i, data, total_pixels)?;
                }
                Ok(())
            })?;
        }

        self.check_partition(ltbl, total_pixels, dict_bytes)
    }

    /// The REE rules for one (layer, sector)'s stored bytes.
    fn check_layer_stream(&self, i: usize, data: &[u8], total_pixels: u32) -> Result<()> {
        let used = ree::validate_stream(data, total_pixels, self.level.is_strict())?;
        if used != data.len() {
            return Err(Error::new(
                Check::ReeNoTrailingBytes,
                format!(
                    "entry {i} stores {} bytes but its stream uses {used}",
                    data.len()
                ),
            ));
        }
        Ok(())
    }

    /// Section 7.3's strict rule that one layer's sectors do not overlap.
    ///
    /// A layer's sectors live in different chunks now, so this is a walk over
    /// layers rather than over one chunk's plaintext: it holds two bitmaps, reused
    /// across layers, plus whatever the chunk cache holds. It reads the pixels a
    /// slice exposes off the stream rather than out of a decoded mask, which is
    /// what keeps a 16K layer's four sectors from costing four 94 MB buffers.
    /// The rule's other half - that the sectors cover every pixel - is what
    /// "their union is exactly the layer's exposed image" means, and the exposed
    /// image need not be every pixel, so coverage is not enforced here.
    fn check_partition(
        &self,
        ltbl: &LayerTable,
        total_pixels: u32,
        dictionary: Option<&[u8]>,
    ) -> Result<()> {
        if !self.level.is_strict() || !self.layer_chunks_readable() {
            return Ok(());
        }
        // `covered` is what the layer's earlier sectors exposed, `mine` what the
        // sector being walked has. A split stream reports a pixel twice - once
        // from the core's run and once from the overlay that carries it - so a
        // pixel this sector has already exposed is not another sector's. Both are
        // allocated at the first layer that has more than one sector: a file
        // whose layers each carry one never pays for them.
        let words = (total_pixels as usize).div_ceil(64);
        let mut covered: Vec<u64> = Vec::new();
        let mut mine: Vec<u64> = Vec::new();
        for layer in 0..ltbl.layer_count {
            let carrying: Vec<&LayerEntry> = ltbl
                .layer_entries(layer)
                .iter()
                .filter(|entry| !entry.is_empty())
                .collect();
            if carrying.len() < 2 {
                continue;
            }
            if covered.len() != words {
                covered.resize(words, 0);
                mine.resize(words, 0);
            }
            covered.fill(0);
            for entry in carrying {
                mine.fill(0);
                let sector = entry.sector_id;
                let data = self.slice_of(entry, dictionary)?;
                ree::exposed_ranges(&data, total_pixels, |start, end| {
                    expose(&mut covered, &mut mine, start, end, layer, sector)
                })?;
            }
        }
        Ok(())
    }

    /// Whether every `LAYR` frame can be read.
    ///
    /// A sealed file without a key cannot have its frames opened, and the checks
    /// that need their content are skipped rather than guessed at.
    fn layer_chunks_readable(&self) -> bool {
        self.key.is_some() || self.layr_chunks().iter().all(|(_, d)| !d.is_encrypted())
    }

    /// `LHAS`: the Merkle root always, and every leaf in strict mode.
    fn check_hashes(&self, head: &Head) -> Result<Option<LayerHashes>> {
        let Some(d) = self.dir.find(Tag::LHAS) else {
            return Ok(None);
        };
        let payload = self
            .plaintext(d)?
            .expect("LHAS is never sealed, so it is always readable");
        let hashes = LayerHashes::parse(&payload)?;
        if hashes.layer_count != head.total_layers {
            return Err(Error::new(
                Check::LhasLayerCount,
                format!(
                    "LHAS covers {} layers, HEAD says {}",
                    hashes.layer_count, head.total_layers
                ),
            ));
        }
        let recomputed = lhas::merkle_root(&hashes.layer_hashes);
        if recomputed != hashes.merkle_root {
            return Err(Error::new(
                Check::LhasRootRecompute,
                "the stored Merkle root is not the root of the stored leaf hashes",
            ));
        }
        Ok(Some(hashes))
    }

    /// Section 11.3's strict rule that each layer hashes to its stored leaf.
    ///
    /// A layer's leaf covers its sectors' slices concatenated in ascending
    /// `sector_id` (section 4.10), which is what a reader reconstructs. This is a
    /// second pass over the chunks, so that the REE checks keep their place in the
    /// check order.
    fn check_leaves(
        &self,
        ltbl: &Option<LayerTable>,
        zdic: &Option<ZstdDictionary>,
        hashes: &LayerHashes,
    ) -> Result<()> {
        if !self.level.is_strict() || !self.layer_chunks_readable() {
            return Ok(());
        }
        let Some(ltbl) = ltbl.as_ref() else {
            return Ok(());
        };
        let dict_bytes = zdic.as_ref().map(|z| z.dict_bytes.as_slice());
        for layer in 0..ltbl.layer_count {
            let Some(stored_leaf) = hashes.layer_hashes.get(layer as usize) else {
                continue;
            };
            // An empty layer stores no bytes, so it hashes the empty slice.
            let data = self.layer_bytes(ltbl.layer_entries(layer), dict_bytes)?;
            if lhas::leaf_hash(&data) != *stored_leaf {
                return Err(Error::new(
                    Check::LhasLeafMatch,
                    format!("layer {layer} does not hash to its stored leaf"),
                ));
            }
        }
        Ok(())
    }

    /// Section 11.4's final row: every sealed unit's tag must verify.
    ///
    /// A `LAYR` frame is its own unit, bound by its associated data to the
    /// chunk's directory index, so opening it is what proves that binding.
    fn check_sealed_units(&self, key: &SessionKey, cipher: Cipher) -> Result<()> {
        for (index, d) in self.dir.descriptors.iter().enumerate() {
            if d.is_null() || d.flags & CHUNK_FLAG_ENCRYPTED == 0 {
                continue;
            }
            if d.chunk_type == Tag::LAYR {
                self.layr_frame(index as u32, d)?;
            } else {
                crypto::open(cipher, key, d.chunk_type, 0, self.stored(d)?)?;
            }
        }
        Ok(())
    }
}

fn json_error(err: serde_json::Error) -> Error {
    Error::new(Check::MetaJson, err.to_string())
}

/// Enforce the integer rule for the durations named in `names`.
///
/// A duration is an exact whole number of milliseconds, so a value with a
/// fractional part is a type violation rather than a range one, and a loose
/// reader rejects it too (section 11.5). Reading the raw numbers is what makes
/// the named check the *first* failure: a fractional duration cannot
/// deserialize into the integer field it belongs to, so the typed parse would
/// report a generic JSON error instead. A reader MAY also reject integral
/// floating-point syntax, and this one does: `2500.0` is written as a
/// floating-point number, and a negative or too-large one is no more a
/// millisecond count this format can express.
fn check_integer_durations<'a>(
    object: &Map<String, Value>,
    names: impl Iterator<Item = &'a str>,
    check: Check,
) -> Result<()> {
    for name in names {
        let Some(value) = object.get(name) else {
            continue;
        };
        // A non-number is a shape error another check owns. A number that is not
        // a whole count inside the field's range is not a duration this format
        // can express: `2500.0` has no `as_u64`, and neither has a negative or
        // an over-large value.
        if value.is_number() && value.as_u64().is_none_or(|n| n > u64::from(u32::MAX)) {
            return Err(Error::new(
                check,
                format!("{name} is {value}, which is not a whole number of milliseconds"),
            ));
        }
    }
    Ok(())
}

/// `HEAD` rules from sections 11.1 and 11.2.
fn check_hdr(head: &Head) -> Result<()> {
    if head.total_layers == 0 {
        return Err(Error::new(
            Check::HeadTotalLayers,
            "HEAD declares no layers",
        ));
    }
    if head.layer_height_um == 0 {
        return Err(Error::new(
            Check::HeadLayerHeight,
            "layer_height_um is zero",
        ));
    }
    if head.build_width_um == 0 || head.build_depth_um == 0 || head.build_height_um == 0 {
        return Err(Error::new(
            Check::HeadBuildDims,
            "a build dimension is zero",
        ));
    }
    if head.total_pixels() == 0 {
        return Err(Error::new(
            Check::HeadDisplayPixels,
            "the display has no pixels",
        ));
    }
    Ok(())
}

/// Every PWM a parsed payload carries is a duty over `0..=255` (section 4.2).
///
/// The range is checked rather than clamped: a duty of `3000` is a slicer that has
/// mistaken a percentage or a wider scale for the field, and silently clamping it
/// would print at a different power from a reader that used it as written.
fn check_pwm(timing: &Timing, at: &str) -> Result<()> {
    for (name, value) in [
        ("light_pwm", timing.light_pwm),
        ("bottom_light_pwm", timing.bottom_light_pwm),
    ] {
        if let Some(value) = value {
            if value > PWM_MAX {
                return Err(Error::new(
                    Check::PwmRange,
                    format!("{at}: {name} is {value}, outside 0..={PWM_MAX}"),
                ));
            }
        }
    }
    Ok(())
}

/// [`check_pwm`] for a payload that is still raw JSON, which is how an `LROV`
/// delta is read: it is a sparse object, not a `Timing`.
fn check_pwm_object(object: &Map<String, Value>, at: &str) -> Result<()> {
    for name in ["light_pwm", "bottom_light_pwm"] {
        let Some(value) = object.get(name) else {
            continue;
        };
        if value.is_null() {
            continue;
        }
        if !value
            .as_u64()
            .is_some_and(|duty| duty <= u64::from(PWM_MAX))
        {
            return Err(Error::new(
                Check::PwmRange,
                format!("{at}: {name} is {value}, outside the integer range 0..={PWM_MAX}"),
            ));
        }
    }
    Ok(())
}

/// `META` rules from section 11.2.
fn check_meta(meta: &Meta) -> Result<()> {
    match meta.meta_version {
        Some(1) => {}
        Some(other) => {
            return Err(Error::new(
                Check::MetaVersion,
                format!("unsupported meta_version {other}"),
            ))
        }
        None => return Err(Error::new(Check::MetaVersion, "no meta_version")),
    }
    let timing = &meta.timing;
    if timing.normal_exposure_ms.unwrap_or(0) == 0 {
        return Err(Error::new(
            Check::MetaExposure,
            "normal_exposure_ms is not positive",
        ));
    }
    if timing.bottom_exposure_ms.unwrap_or(0) == 0 {
        return Err(Error::new(
            Check::MetaExposure,
            "bottom_exposure_ms is not positive",
        ));
    }
    if timing.layer_height_um.unwrap_or(0) == 0 {
        return Err(Error::new(
            Check::MetaLayerHeight,
            "layer_height_um is not positive",
        ));
    }
    if let Some(materials) = meta.materials.as_ref() {
        check_materials(materials, Check::MetaMaterialsShape)?;
        // A sector's material index is bounded against the library the same META
        // carries; a print with no library has nothing to bound against.
        for sector in meta.sectors.as_deref().unwrap_or_default() {
            if let Some(index) = sector.material_index {
                if index as usize >= materials.len() {
                    return Err(Error::new(
                        Check::MetaSectorMaterialIndex,
                        format!(
                            "sector {} names material {index}, which the material library does \
                             not contain",
                            sector.sector_id
                        ),
                    ));
                }
            }
        }
    }
    if let Some(curve) = timing.cure_curve.as_ref() {
        check_cure_curve(curve, Check::MetaCureCurve)?;
    }
    check_pwm(timing, "META")?;
    for sector in meta.sectors.as_deref().unwrap_or_default() {
        check_pwm(
            &sector.timing,
            &format!("META.sectors entry for sector {}", sector.sector_id),
        )?;
    }
    for temperature in [timing.chamber_temperature_c, timing.vat_temperature_c]
        .into_iter()
        .flatten()
    {
        if !(0.0..=120.0).contains(&temperature) {
            return Err(Error::new(
                Check::MetaTemperatureRange,
                format!("temperature {temperature} is outside 0..=120 degrees Celsius"),
            ));
        }
    }
    Ok(())
}

/// `PROF` rules from section 11.2.
fn check_profile(profile: &Profile) -> Result<()> {
    match profile.profile_type.as_deref() {
        Some("material") | Some("printer") | Some("combined") => {}
        Some(other) => {
            return Err(Error::new(
                Check::ProfProfileType,
                format!("unknown profile_type {other:?}"),
            ))
        }
        None => return Err(Error::new(Check::ProfProfileType, "no profile_type")),
    }
    if profile.profile_name.is_empty() || profile.profile_version.is_empty() {
        return Err(Error::new(
            Check::ProfProfileIdentity,
            "profile_name and profile_version must be non-empty",
        ));
    }
    if profile.settings.normal_exposure_ms.unwrap_or(0) == 0
        || profile.settings.bottom_exposure_ms.unwrap_or(0) == 0
    {
        return Err(Error::new(
            Check::ProfSettingsExposure,
            "a profile exposure time is not positive",
        ));
    }
    if profile.settings.layer_height_um.unwrap_or(0) == 0 {
        return Err(Error::new(
            Check::ProfSettingsLayerHeight,
            "the profile's layer_height_um is not positive",
        ));
    }
    check_pwm(&profile.settings, "PROF.settings")?;
    if let Some(curve) = profile.settings.cure_curve.as_ref() {
        check_cure_curve(curve, Check::ProfCureCurve)?;
    }
    if let Some(uuid) = profile.profile_uuid.as_deref() {
        if !is_uuid(uuid) {
            return Err(Error::new(
                Check::ProfProfileUuid,
                format!("{uuid:?} is not a UUID"),
            ));
        }
    }
    if let Some(materials) = profile.materials.as_ref() {
        check_materials(materials, Check::ProfMaterialsShape)?;
    }
    Ok(())
}

/// A materials array must be non-empty and every entry must be named.
fn check_materials(materials: &[Material], check: Check) -> Result<()> {
    if materials.is_empty() {
        return Err(Error::new(check, "the array is empty"));
    }
    if let Some(index) = materials.iter().position(|m| m.name.is_empty()) {
        return Err(Error::new(check, format!("material {index} has no name")));
    }
    Ok(())
}

/// `META.sectors`: an array of objects, each with a unique `sector_id` >= 1.
///
/// Read from the raw JSON so the named check is the *first* failure: an id that
/// is absent or not an integer cannot deserialize into the entry's field, and the
/// typed parse would report a generic JSON error instead. The durations inside an
/// entry are checked here too, under META's own integer rule, because they are
/// META's fields in the same namespace.
fn check_sectors_shape(object: &Map<String, Value>) -> Result<()> {
    let Some(sectors) = object.get("sectors") else {
        return Ok(());
    };
    let Some(entries) = sectors.as_array() else {
        return Err(Error::new(
            Check::MetaSectorsShape,
            "META.sectors is not an array",
        ));
    };
    let mut seen: Vec<u64> = Vec::with_capacity(entries.len());
    for (i, entry) in entries.iter().enumerate() {
        let Some(entry) = entry.as_object() else {
            return Err(Error::new(
                Check::MetaSectorsShape,
                format!("META.sectors[{i}] is not an object"),
            ));
        };
        let Some(id) = entry.get("sector_id").and_then(Value::as_u64) else {
            return Err(Error::new(
                Check::MetaSectorsShape,
                format!("META.sectors[{i}] carries no integer sector_id"),
            ));
        };
        if id == 0 {
            return Err(Error::new(
                Check::MetaSectorsShape,
                format!(
                    "META.sectors[{i}] uses sector_id 0, which names the implicit primary sector"
                ),
            ));
        }
        if id > u64::from(u32::MAX) {
            return Err(Error::new(
                Check::MetaSectorsShape,
                format!("META.sectors[{i}] uses sector_id {id}, which does not fit a u32"),
            ));
        }
        if seen.contains(&id) {
            return Err(Error::new(
                Check::MetaSectorsShape,
                format!("sector_id {id} appears twice"),
            ));
        }
        seen.push(id);
        check_integer_durations(
            entry,
            TIME_MS_FIELDS.iter().copied(),
            Check::MetaTimeInteger,
        )?;
    }
    Ok(())
}

/// A cure curve must be physically meaningful, and a NaN is not a number the
/// Beer-Lambert model can use, so each bound rejects it explicitly rather than
/// relying on how a negated comparison treats an incomparable value.
fn check_cure_curve(curve: &crate::json::CureCurve, check: Check) -> Result<()> {
    if curve.dp_um.is_nan() || curve.dp_um <= 0.0 {
        return Err(Error::new(check, "dp_um is not positive"));
    }
    if curve.ec_mj_cm2.is_nan() || curve.ec_mj_cm2 <= 0.0 {
        return Err(Error::new(check, "ec_mj_cm2 is not positive"));
    }
    if curve.e0_mj_cm2.is_nan() || curve.e0_mj_cm2 < 0.0 {
        return Err(Error::new(check, "e0_mj_cm2 is negative"));
    }
    Ok(())
}

fn is_uuid(text: &str) -> bool {
    let bytes = text.as_bytes();
    if bytes.len() != 36 {
        return false;
    }
    for (i, b) in bytes.iter().enumerate() {
        let dashed = matches!(i, 8 | 13 | 18 | 23);
        if dashed {
            if *b != b'-' {
                return false;
            }
        } else if !b.is_ascii_hexdigit() {
            return false;
        }
    }
    true
}

/// `EXTD` rules from sections 11.2 and 4.12.
fn check_extension(ext: &Extension) -> Result<()> {
    if ext.critical && !ext.is_implemented() {
        return Err(Error::new(
            Check::ExtdCritical,
            format!(
                "extension {}{:?} is critical and unimplemented",
                ext.tag(),
                ext.vendor_id
            ),
        ));
    }
    Ok(())
}

/// The reserved-flag and critical rules, for an extension whose payload cannot
/// be read.
fn check_opaque_extension(flags: u32) -> Result<()> {
    if flags & EXTD_RESERVED_MASK != 0 {
        return Err(Error::new(
            Check::ExtdFlags,
            format!("EXTD flags {flags:#010x} set a reserved bit"),
        ));
    }
    if flags & CRITICAL_BIT != 0 {
        return Err(Error::new(
            Check::ExtdCritical,
            "a critical extension is unimplemented",
        ));
    }
    Ok(())
}
