//! Run-end encoded layer masks ([`spec/11-layer-encoding.md`] section 5).
//!
//! Four tags are defined: binary REE (`0x00`), grayscale REE (`0x01`), split REE
//! (`0x02`) and attached split REE (`0x03`). A layer whose pixels are all zero has no stream at all - the
//! empty-layer form lives in the `LTBL` entry, not in the layer data.
//!
//! Every run-length or position array is stored as four significance planes
//! ([`spec/11-layer-encoding.md`] section 5.3.1): the four plane lengths, then the
//! bytes of plane 0, plane 1, plane 2 and plane 3. A varint's byte `j` belongs to
//! plane `j`, so a length's high byte stops sitting between two noisy low bytes and
//! the compressor can see that it is nearly constant along a scanline.

use crate::check::Check;
use crate::error::{Error, Result};
use crate::io::{Reader, Writer};

/// Tag for binary REE, used when every pixel is `0x00` or `0xFF`.
pub const TAG_BINARY: u8 = 0x00;
/// Tag for grayscale REE, used when pixels may hold any 8-bit value.
pub const TAG_GRAYSCALE: u8 = 0x01;
/// Tag for binary REE plus a sparse anti-aliasing overlay.
pub const TAG_SPLIT: u8 = 0x02;
/// Tag for split REE whose core lengths are parity-split and self-delta coded and
/// whose overlay pixels hang off the core's run boundaries.
pub const TAG_ATTACHED: u8 = 0x03;

/// Which encoding an encoder should use for a layer.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum EncodeMode {
    /// Smallest of the applicable encodings; ties go to grayscale (section 5.7).
    #[default]
    Auto,
    /// Binary REE. Requires every pixel to be `0x00` or `0xFF`.
    Binary,
    /// Grayscale REE.
    Grayscale,
    /// Split REE. The thresholded mask thresholds at `v >= 128`.
    Split,
    /// Attached split REE: the same thresholded core and overlay, with the core's
    /// lengths parity-split and self-delta coded and the overlay's positions
    /// implied by the core's run boundaries.
    ///
    /// [`EncodeMode::Auto`] never picks this one: its raw size is not a guide to
    /// its compressed size, so a caller that wants it - or the writer's own probe
    /// - asks for it and compares the compressed result.
    Attached,
}

/// One maximal run of equal pixels, in row-major order.
///
/// A run list is a mask's canonical decomposition: adjacent runs never carry the
/// same value and the lengths sum to the layer's pixel count. A rasterizer that
/// produces runs hands them to [`encode_runs`] directly, so the pixel mask a
/// layer decodes to never has to exist.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Run {
    /// How many pixels the run covers. At least 1.
    pub length: u32,
    /// The value every pixel of the run carries.
    pub value: u8,
}

impl Run {
    /// A run of `length` pixels carrying `value`.
    pub fn new(length: u32, value: u8) -> Self {
        Run { length, value }
    }
}

/// A decoded layer mask.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecodedLayer {
    /// One byte per pixel, in row-major order, `total_pixels` long.
    pub pixels: Vec<u8>,
    /// The tag the stream carried, or `None` for the empty-layer form.
    pub tag: Option<u8>,
}

impl DecodedLayer {
    /// All-black layer, carrying no stream: every `LTBL` entry of the layer has
    /// `data_size == 0`.
    pub fn empty(total_pixels: u32) -> DecodedLayer {
        DecodedLayer {
            pixels: vec![0u8; total_pixels as usize],
            tag: None,
        }
    }

    /// Whether this is the empty-layer form.
    pub fn is_empty(&self) -> bool {
        self.tag.is_none()
    }

    /// Whether every pixel is `0x00` or `0xFF`.
    pub fn is_binary(&self) -> bool {
        self.pixels.iter().all(|p| *p == 0 || *p == 255)
    }
}

/// The binary threshold of section 5.5: `255 if v >= 128 else 0`.
pub fn threshold(pixel: u8) -> u8 {
    if pixel >= 128 {
        255
    } else {
        0
    }
}

/// Decode a layer's mask data, exclusive of any sector framing.
///
/// `data` is the one-byte encoding tag followed by the stream, so it is never
/// empty: the empty-layer form carries no bytes at all. Bytes past the end of
/// the stream are not part of the mask and are ignored.
///
/// In `strict` mode the canonical-form rules of section 5.7 are enforced.
/// A loose read accepts any stream that satisfies sections 5.3-5.5. A stream
/// that ends before its structure is complete reports [`Check::ReeVarint`], the
/// check the varint decoder already uses for a truncated stream.
pub fn decode(data: &[u8], total_pixels: u32, strict: bool) -> Result<DecodedLayer> {
    decode_counted(data, total_pixels, strict).map(|(layer, _)| layer)
}

/// Decode a layer mask and report how many bytes the stream used.
///
/// The length is what lets a caller notice bytes after the end of the stream:
/// the mask data a layer stores is exactly `[tag][stream]`, so any surplus is
/// padding the encoder did not intend and a reader must not silently accept
/// (`ree` rule, section 11.3).
pub fn decode_counted(
    data: &[u8],
    total_pixels: u32,
    strict: bool,
) -> Result<(DecodedLayer, usize)> {
    let (tag, mut reader) = tag_and_stream(data)?;
    let mut pixels = vec![0u8; total_pixels as usize];
    read(
        tag,
        Sink::Mask(&mut pixels),
        &mut reader,
        total_pixels,
        strict,
    )?;
    Ok((
        DecodedLayer {
            pixels,
            tag: Some(tag),
        },
        1 + reader.pos(),
    ))
}

/// The encoding tag and the stream that follows it.
///
/// The tag is one of the four section 5.1 defines; anything else is rejected
/// here, so a caller's arms never see a tag the format does not have.
fn tag_and_stream(data: &[u8]) -> Result<(u8, Reader<'_>)> {
    let Some((&tag, stream)) = data.split_first() else {
        return Err(Error::new(
            Check::ReeTag,
            "layer mask data is empty: the empty-layer form carries no bytes",
        ));
    };
    match tag {
        TAG_BINARY | TAG_GRAYSCALE | TAG_SPLIT | TAG_ATTACHED => {}
        other => {
            return Err(Error::new(
                Check::ReeTag,
                format!("unknown layer encoding tag 0x{other:02X}"),
            ))
        }
    }
    Ok((tag, Reader::checked(stream, Check::ReeVarint)))
}

/// Apply a tag's rules to its stream, filling `sink` as it decodes.
///
/// This is the one entry point both readers use, so a validator's walk and a
/// decoder's cannot drift apart: they read the same bytes under the same rules
/// and differ only in where the pixels go.
fn read(
    tag: u8,
    sink: Sink<'_>,
    reader: &mut Reader<'_>,
    total_pixels: u32,
    strict: bool,
) -> Result<()> {
    match tag {
        TAG_BINARY => read_binary(sink, reader, total_pixels, strict),
        TAG_GRAYSCALE => read_grayscale(sink, reader, total_pixels, strict),
        TAG_SPLIT => read_split(sink, reader, total_pixels, strict),
        TAG_ATTACHED => read_attached(sink, reader, total_pixels, strict),
        // `tag_and_stream` rejects every other tag before its stream is read.
        _ => unreachable!("tag_and_stream accepts 0x00, 0x01, 0x02 and 0x03 only"),
    }
}

/// Read a run count and reject one above the section 5.2 bound before any buffer
/// is sized from it: a run covers at least one pixel, so a stream cannot hold
/// more than `total_pixels + 1` runs.
fn read_run_count(reader: &mut Reader<'_>, total_pixels: u64) -> Result<u64> {
    let bound = total_pixels + 1;
    let run_count = reader.varint()?;
    if run_count > bound {
        return Err(Error::new(
            Check::ReeRunLengths,
            format!("run_count {run_count} exceeds total_pixels + 1 ({bound})"),
        ));
    }
    Ok(run_count)
}

/// How many significance planes a varint array is stored in (section 5.3.1).
const PLANES: usize = 4;

/// The significance planes of a varint array (section 5.3.1), read in step.
///
/// Byte `j` of a varint - least-significant seven bits first - is stored in plane
/// `j`, so reading a varint takes one byte from plane 0, another from plane 1
/// while the continuation bit is set, and so on. A `k`-byte varint therefore
/// occupies planes `0..k`, and the four plane lengths are what let a reader find
/// each plane's end without being told how many varints the array holds.
struct Planes<'a> {
    planes: [&'a [u8]; PLANES],
    at: [usize; PLANES],
}

impl<'a> Planes<'a> {
    /// Read `PLANES(n)`: four plane lengths, then the planes they describe.
    ///
    /// The four lengths are written unconditionally, so a stream whose array is
    /// empty still carries them as four zero bytes.
    fn read(reader: &mut Reader<'a>, strict: bool) -> Result<Planes<'a>> {
        let mut lengths = [0usize; PLANES];
        for (plane, length) in lengths.iter_mut().enumerate() {
            let value = reader.varint()?;
            *length = usize::try_from(value).map_err(|_| {
                Error::new(
                    Check::ReePlanes,
                    format!("plane {plane} length {value} does not fit in memory"),
                )
            })?;
        }
        if strict {
            // Prefix-closure: a varint that reaches plane `j` also occupies every
            // plane below it, so a non-empty plane may not follow an empty one.
            for plane in 1..PLANES {
                if lengths[plane] > 0 && lengths[plane - 1] == 0 {
                    return Err(Error::new(
                        Check::ReePlanes,
                        format!(
                            "plane {plane} holds {} bytes after empty plane {}: the planes are \
                             not prefix-closed",
                            lengths[plane],
                            plane - 1
                        ),
                    ));
                }
            }
        }
        let mut planes = [&[][..]; PLANES];
        for (plane, length) in planes.iter_mut().zip(lengths) {
            *plane = reader.bytes(length)?;
        }
        Ok(Planes {
            planes,
            at: [0; PLANES],
        })
    }

    /// The planes of an array that stores no varints at all.
    ///
    /// The non-canonical `run_count == 0` form of section 5.3 carries no length
    /// array, and the single run it decodes to reads nothing from this.
    fn empty() -> Planes<'a> {
        Planes {
            planes: [&[]; PLANES],
            at: [0; PLANES],
        }
    }

    /// The same planes, ready to be read again from the start.
    ///
    /// A split stream's overlay is walked more than once - to check it, to
    /// compare it against the thresholded core, and to write it - and none of
    /// those walks keeps a decoded position, so each reads the same bytes.
    fn rewind(&self) -> Planes<'a> {
        Planes {
            planes: self.planes,
            at: [0; PLANES],
        }
    }

    /// The next varint, or `None` once plane 0 is exhausted.
    ///
    /// A varint always takes its first byte from plane 0, so plane 0's length is
    /// the number of varints the array holds.
    fn next(&mut self) -> Result<Option<u64>> {
        if self.at[0] == self.planes[0].len() {
            return Ok(None);
        }
        let mut value = 0u64;
        for plane in 0..PLANES {
            let Some(&byte) = self.planes[plane].get(self.at[plane]) else {
                return Err(Error::new(
                    Check::ReeVarint,
                    format!("a varint continues into plane {plane}, which holds no more bytes"),
                ));
            };
            self.at[plane] += 1;
            value |= u64::from(byte & 0x7F) << (7 * plane);
            if byte & 0x80 == 0 {
                if plane > 0 && byte == 0 {
                    return Err(Error::new(
                        Check::ReeVarint,
                        "a varint crossing planes is not minimally encoded",
                    ));
                }
                return Ok(Some(value));
            }
        }
        Err(Error::new(
            Check::ReeVarint,
            "a varint continues past plane 3, which is the last plane",
        ))
    }

    /// The next varint of an array the stream's own count says holds another one.
    fn varint(&mut self) -> Result<u64> {
        self.next()?.ok_or_else(|| {
            Error::new(
                Check::ReeVarint,
                "the planes hold fewer varints than the stream's count",
            )
        })
    }

    /// In strict mode the planes must hold exactly the varints read from them: a
    /// leftover byte describes no varint (section 5.3.1).
    fn check_consumed(&self) -> Result<()> {
        for plane in 0..PLANES {
            let len = self.planes[plane].len();
            if self.at[plane] != len {
                return Err(Error::new(
                    Check::ReePlanes,
                    format!(
                        "plane {plane} holds {len} bytes, {} of which describe a varint",
                        self.at[plane]
                    ),
                ));
            }
        }
        Ok(())
    }
}

/// Where a stream's pixels go as a reader walks it.
///
/// The section 11.3 checks need a stream's structure and not its pixel values,
/// so they walk the same bytes as a decoder and throw the pixels away. On a 16K
/// layer the mask a decoder fills is 94 MB per slice, and a validator never
/// allocates it.
enum Sink<'m> {
    /// Fill a mask as the runs are walked.
    Mask(&'m mut [u8]),
    /// Report the pixels that are not `0x00`, as `[start, end)` ranges.
    ///
    /// A split stream is walked in two parts - the thresholded core's runs, then
    /// the overlay it carries - so a range may cover a pixel an earlier range
    /// already covered, and a caller wants their union.
    Exposed(&'m mut dyn FnMut(u64, u64) -> Result<()>),
    /// Keep nothing: the rules apply, the pixels do not.
    None,
}

impl Sink<'_> {
    /// Fill `[start, end)` with `value`.
    ///
    /// A walk rejects an end past `total_pixels` before it calls, so a mask is
    /// exactly as long as the range it is filled over.
    #[inline]
    fn fill(&mut self, start: u64, end: u64, value: u8) -> Result<()> {
        match self {
            Sink::Mask(mask) => mask[start as usize..end as usize].fill(value),
            Sink::Exposed(report) => {
                if value != 0x00 && start < end {
                    report(start, end)?;
                }
            }
            Sink::None => {}
        }
        Ok(())
    }

    /// Write the value an overlay pixel carries: the one place a mask is written
    /// outside a run.
    #[inline]
    fn set(&mut self, position: u64, value: u8) -> Result<()> {
        match self {
            Sink::Mask(mask) => mask[position as usize] = value,
            Sink::Exposed(report) => {
                if value != 0x00 {
                    report(position, position + 1)?;
                }
            }
            Sink::None => {}
        }
        Ok(())
    }
}

/// A walk over the runs of a run-length stream: the lengths a planes array
/// stores, then the implicit final run that ends at `total_pixels`.
///
/// The end positions, the empty-run rule and the exact-use rule of a planes
/// array live here once. A mask decoder fills each run it steps into, a
/// validator takes the same ranges and keeps none of them, and the split
/// threshold rule asks which run holds a pixel - so no two readers of one stream
/// can disagree about it.
struct Runs<'a> {
    lengths: LengthSource<'a>,
    /// The lengths still to read, the implicit final run included.
    left: u64,
    /// The run the walk is in, as `[start, end)`.
    start: u64,
    end: u64,
    /// How many runs the walk has stepped into.
    walked: u64,
    total: u64,
    /// What the stream is called in a failure: "binary REE", "grayscale REE".
    kind: &'static str,
    /// Whether a run held no pixels.
    empty: bool,
}

impl<'a> Runs<'a> {
    fn new(lengths: LengthSource<'a>, count: u64, total: u64, kind: &'static str) -> Runs<'a> {
        Runs {
            lengths,
            left: count,
            start: 0,
            end: 0,
            walked: 0,
            total,
            kind,
            empty: false,
        }
    }

    /// Step into the next run, reporting its index, or `None` once every run has
    /// been stepped into.
    ///
    /// The ranges are in order and cover `[0, total_pixels)`. A stored length of
    /// 0 is legal to a loose read: the walk counts it in [`Runs::empty_run`]
    /// rather than failing, because the check that rejects it is a later one.
    fn step(&mut self) -> Result<Option<u64>> {
        if self.left == 0 {
            return Ok(None);
        }
        self.left -= 1;
        // The last run's length is implicit: it ends at `total_pixels`.
        let end = if self.left == 0 {
            self.total
        } else {
            let index = self.walked;
            self.end
                .checked_add(self.lengths.next(index)?)
                .ok_or_else(|| {
                    Error::new(
                        Check::ReeEndPositions,
                        format!("{} run lengths overflow", self.kind),
                    )
                })?
        };
        let (start, index) = (self.end, self.walked);
        if end > self.total {
            return Err(Error::new(
                Check::ReeEndPositions,
                format!(
                    "{} run {index} ends at {end}, past total_pixels {}",
                    self.kind, self.total
                ),
            ));
        }
        self.empty |= end == start;
        self.start = start;
        self.end = end;
        self.walked = index + 1;
        Ok(Some(index))
    }

    /// Step into the run that holds `position`, reporting its index.
    ///
    /// Positions are asked in non-decreasing order, so the runs are stepped
    /// through once. The stream covers `[0, total_pixels)` and a caller asks
    /// about pixels below it, so a run is always there to step into.
    fn seek(&mut self, position: u64) -> Result<u64> {
        while self.end <= position {
            if self.step()?.is_none() {
                return Err(Error::new(
                    Check::ReeEndPositions,
                    format!("{} holds no run covering pixel {position}", self.kind),
                ));
            }
        }
        Ok(self.walked.saturating_sub(1))
    }

    /// The run the walk is in, as `[start, end)`.
    fn range(&self) -> (u64, u64) {
        (self.start, self.end)
    }

    /// Whether a run held no pixels: every stored length is at least 1 and the
    /// implicit final run has something left for it (section 5.7).
    fn empty_run(&self) -> bool {
        self.empty
    }

    /// The strict rule that the length array holds exactly the lengths read from
    /// it (section 5.3.1).
    fn check_consumed(&self) -> Result<()> {
        self.lengths.check_consumed()
    }
}

/// Where a run walk reads its lengths.
///
/// Tags `0x00`, `0x01` and `0x02` store one planes array of lengths; tag `0x03`
/// stores two, split by parity. Everything else about a walk - the end positions,
/// the implicit final run, the empty-run rule, the ranges a caller asks about -
/// is the same either way, and lives in [`Runs`] once so no two readers of one
/// stream can disagree about it.
enum LengthSource<'a> {
    /// One planes array, read in order.
    Planes(Planes<'a>),
    /// Two planes arrays, one per parity, each self-delta coded.
    Parity(Parity<'a>),
}

impl LengthSource<'_> {
    /// The length of run `index`, which the stream must still hold.
    fn next(&mut self, index: u64) -> Result<u64> {
        match self {
            LengthSource::Planes(planes) => planes.varint(),
            LengthSource::Parity(parity) => {
                let length = parity.next(index)?;
                u64::try_from(length).map_err(|_| {
                    Error::new(
                        Check::ReeEndPositions,
                        format!("attached REE run {index} has a negative length"),
                    )
                })
            }
        }
    }

    /// The strict rule that a length array holds exactly the lengths read from it.
    fn check_consumed(&self) -> Result<()> {
        match self {
            LengthSource::Planes(planes) => planes.check_consumed(),
            LengthSource::Parity(parity) => {
                parity.streams[0].check_consumed()?;
                parity.streams[1].check_consumed()
            }
        }
    }
}

/// The length array of an attached stream (section 5.6): the core's run lengths
/// with the even stored indices in one planes array and the odd ones in the
/// other, each entry a difference from the entry two runs earlier.
///
/// A row-major run list alternates between the boundary leaving the geometry and
/// the boundary entering it, so one array interleaves two sequences that are each
/// smooth; splitting them by parity is what lets the differences be small enough
/// for the planes to collapse.
struct Parity<'a> {
    streams: [Planes<'a>; 2],
    /// The last length each parity produced: what the next delta of that parity
    /// is a difference from.
    last: [i64; 2],
}

impl<'a> Parity<'a> {
    /// Read the two planes arrays.
    fn read(reader: &mut Reader<'a>, strict: bool) -> Result<Parity<'a>> {
        Ok(Parity {
            streams: [Planes::read(reader, strict)?, Planes::read(reader, strict)?],
            last: [0; 2],
        })
    }

    /// The length of run `index`, which the stream must still hold.
    ///
    /// The first two lengths are stored as they are: a difference needs an entry
    /// two runs earlier to be a difference from, and the first two runs have none.
    fn next(&mut self, index: u64) -> Result<i64> {
        let parity = (index % 2) as usize;
        let stored = self.streams[parity].varint()?;
        if index < 2 {
            let length = i64::try_from(stored).map_err(|_| {
                Error::new(
                    Check::ReeEndPositions,
                    format!("attached REE run {index} is {stored} pixels long"),
                )
            })?;
            self.last[parity] = length;
            return Ok(length);
        }
        let length = self.last[parity]
            .checked_add(unzigzag(stored))
            .ok_or_else(|| {
                Error::new(Check::ReeEndPositions, "attached REE run lengths overflow")
            })?;
        self.last[parity] = length;
        Ok(length)
    }
}

/// Zigzag: map a signed difference to an unsigned value, small magnitudes first.
///
/// An attached stream differences run lengths and overlay values, and a difference
/// is negative as often as positive; zigzag is what keeps either sign one varint
/// wide, which is what the planes of section 5.3.1 then exploit.
#[inline]
fn zigzag(value: i64) -> u64 {
    ((value as u64) << 1) ^ ((value >> 63) as u64)
}

/// The inverse of [`zigzag`].
#[inline]
fn unzigzag(value: u64) -> i64 {
    ((value >> 1) as i64) ^ -((value & 1) as i64)
}

/// The binary REE core of section 5.3: the value its runs alternate from, and
/// the lengths of every one but the last.
///
/// Section 5.5 reuses it as a split stream's thresholded component, which is why
/// it is read once and walked as often as its callers need.
struct Core<'a> {
    first_value: u8,
    count: u64,
    total: u64,
    planes: Planes<'a>,
}

impl<'a> Core<'a> {
    /// Read the core's header and length planes.
    fn read(reader: &mut Reader<'a>, total_pixels: u32, strict: bool) -> Result<Core<'a>> {
        let total = u64::from(total_pixels);
        let first_value = reader.u8()?;
        if first_value != 0x00 && first_value != 0xFF {
            return Err(Error::new(
                Check::ReeFirstValue,
                format!("binary REE first_value is 0x{first_value:02X}, not 0x00 or 0xFF"),
            ));
        }
        let count = read_run_count(reader, total)?;
        if count == 0 {
            if strict {
                return Err(Error::new(
                    Check::ReeNoRunCountZero,
                    "binary REE uses the non-canonical run_count == 0 form",
                ));
            }
            // The non-canonical form is one black run over the whole layer: it
            // stores no length, and no plane bytes for one to live in.
            return Ok(Core {
                first_value: 0x00,
                count: 1,
                total,
                planes: Planes::empty(),
            });
        }
        Ok(Core {
            first_value,
            count,
            total,
            planes: Planes::read(reader, strict)?,
        })
    }

    /// The value run `index` carries: the runs alternate from `first_value`.
    #[inline]
    fn value(&self, index: u64) -> u8 {
        if index % 2 == 0 {
            self.first_value
        } else {
            255 - self.first_value
        }
    }

    /// A walk over the runs, from the first.
    fn runs(&self) -> Runs<'a> {
        Runs::new(
            LengthSource::Planes(self.planes.rewind()),
            self.count,
            self.total,
            "binary REE",
        )
    }

    /// Apply the binary REE rules of sections 5.3 and 5.7: walk every run into
    /// `sink`, and in strict mode refuse a stream that stores an empty run or
    /// leaves bytes in its planes.
    fn apply(&self, sink: &mut Sink<'_>, strict: bool) -> Result<()> {
        let mut runs = self.runs();
        while let Some(index) = runs.step()? {
            let (start, end) = runs.range();
            sink.fill(start, end, self.value(index))?;
        }
        if strict {
            if runs.empty_run() {
                return Err(Error::new(
                    Check::ReeRunLengths,
                    "binary REE stores an empty run",
                ));
            }
            runs.check_consumed()?;
        }
        Ok(())
    }
}

/// Binary REE (tag `0x00`, section 5.3).
fn read_binary(
    mut sink: Sink<'_>,
    reader: &mut Reader<'_>,
    total_pixels: u32,
    strict: bool,
) -> Result<()> {
    Core::read(reader, total_pixels, strict)?.apply(&mut sink, strict)
}

/// Grayscale REE (tag `0x01`, section 5.4): the run count, every run's value,
/// then the planes of every length but the last.
fn read_grayscale(
    mut sink: Sink<'_>,
    reader: &mut Reader<'_>,
    total_pixels: u32,
    strict: bool,
) -> Result<()> {
    let total = u64::from(total_pixels);
    let run_count = read_run_count(reader, total)?;
    if run_count == 0 {
        if strict {
            return Err(Error::new(
                Check::ReeNoRunCountZero,
                "grayscale REE uses the non-canonical run_count == 0 form",
            ));
        }
        // The non-canonical form is one black run over the whole layer: it
        // stores no values and no lengths.
        return sink.fill(0, total, 0x00);
    }

    // The values are hoisted out of the run loop, one byte per run.
    let values = reader.bytes(run_count as usize)?;
    let mut runs = Runs::new(
        LengthSource::Planes(Planes::read(reader, strict)?),
        run_count,
        total,
        "grayscale REE",
    );
    let mut previous: Option<u8> = None;
    while let Some(index) = runs.step()? {
        let (start, end) = runs.range();
        let value = values[index as usize];
        if strict && previous == Some(value) {
            return Err(Error::new(
                Check::ReeGrayscaleRuns,
                format!("grayscale REE repeats value 0x{value:02X} in adjacent runs"),
            ));
        }
        sink.fill(start, end, value)?;
        previous = Some(value);
    }
    if strict {
        if runs.empty_run() {
            return Err(Error::new(
                Check::ReeGrayscaleRuns,
                "grayscale REE stores a zero-length run",
            ));
        }
        runs.check_consumed()?;
        // Every run covers at least one pixel here, so a value the mask holds is
        // a value this array holds: a stream of nothing but 0x00/0xFF is a layer
        // that must use tag 0x00.
        if values.iter().all(|value| *value == 0x00 || *value == 0xFF) {
            return Err(Error::new(
                Check::ReeGrayscaleAllBinary,
                "grayscale REE holds only 0x00/0xFF pixels; such a layer must use tag 0x00",
            ));
        }
    }
    Ok(())
}

/// Walk an overlay's positions, which are delta-encoded and must increase.
///
/// `f` sees each position in the order the stream stores it, and nothing is kept
/// between walks: the passes that need the positions read them again from the
/// same planes.
fn walk_positions(
    planes: &mut Planes<'_>,
    count: u64,
    total: u64,
    mut f: impl FnMut(u64, usize) -> Result<()>,
) -> Result<()> {
    let mut position = 0u64;
    for i in 0..count {
        let delta = planes.varint()?;
        position = position.checked_add(delta).ok_or_else(|| {
            Error::new(Check::ReeSplitPositions, "split overlay positions overflow")
        })?;
        if i > 0 && delta == 0 {
            return Err(Error::new(
                Check::ReeSplitPositions,
                format!("split overlay position {position} repeats its predecessor"),
            ));
        }
        if position >= total {
            return Err(Error::new(
                Check::ReeSplitPositions,
                format!("split overlay position {position} is not below total_pixels {total}"),
            ));
        }
        f(position, i as usize)?;
    }
    Ok(())
}

/// Split REE (tag `0x02`, section 5.5): a binary REE component followed by a
/// delta-encoded sparse overlay of anti-aliasing pixels.
fn read_split(
    mut sink: Sink<'_>,
    reader: &mut Reader<'_>,
    total_pixels: u32,
    strict: bool,
) -> Result<()> {
    let total = u64::from(total_pixels);
    let core = Core::read(reader, total_pixels, strict)?;
    // The component's own rules come first: a reader applies them before it
    // looks at the overlay.
    core.apply(&mut sink, strict)?;

    let aa_count = reader.varint()?;
    let bound = total + 1;
    if aa_count > bound {
        return Err(Error::new(
            Check::ReeSplitPositions,
            format!("aa_pixel_count {aa_count} exceeds total_pixels + 1 ({bound})"),
        ));
    }
    // The positions are stored as planes, then the values as one byte each.
    let positions = Planes::read(reader, strict)?;
    let values = reader.bytes(aa_count as usize)?;

    if strict {
        // Every position is checked, and the planes are required to hold exactly
        // them, before any position is compared with the core: a reader that
        // reported a threshold failure ahead of a later malformed position would
        // name the wrong check. None of the three walks keeps a position, so
        // each reads the same bytes. A loose read needs only the last one.
        let mut checked = positions.rewind();
        walk_positions(&mut checked, aa_count, total, |_, _| Ok(()))?;
        checked.check_consumed()?;
        // Section 5.5: an overlay value is neither 0x00 nor 0xFF, and it
        // thresholds to the core it overrides. The positions and the core's runs
        // both increase, so one walk over the two compares every overlay pixel,
        // and nothing has to hold a mask to ask which value the core carries.
        let mut runs = core.runs();
        walk_positions(&mut positions.rewind(), aa_count, total, |position, i| {
            let value = values[i];
            let binary = core.value(runs.seek(position)?);
            if value == 0x00 || value == 0xFF || threshold(value) != binary {
                return Err(Error::new(
                    Check::ReeSplitThreshold,
                    format!(
                        "split overlay pixel {position} holds 0x{value:02X} over binary \
                         0x{binary:02X}"
                    ),
                ));
            }
            Ok(())
        })?;
        // Every overlay pixel is neither 0x00 nor 0xFF, so an overlay that holds
        // no pixel at all is the one case where the decoded slice is all
        // 0x00/0xFF: it has no anti-aliasing to carry, and section 5.7 asks for
        // tag 0x00.
        if aa_count == 0 {
            return Err(Error::new(
                Check::ReeSplitAllBinary,
                "split REE holds only 0x00/0xFF pixels: it has no anti-aliasing to overlay, \
                 and such a layer must use tag 0x00",
            ));
        }
    }
    // The overlay is written once it has been checked - and, for a loose read,
    // checked as it is written: a mask never holds a value a strict reader
    // rejected.
    walk_positions(&mut positions.rewind(), aa_count, total, |position, i| {
        sink.set(position, values[i])
    })
}

/// The two attachment bits of every core run (section 5.6).
///
/// Run `r` owns the two bits at `2 * (r % 4)` of byte `r / 4`: the first says the
/// run's first pixel is an overlay pixel, the second that its last one is. Two bits
/// per run is what a run boundary needs - an overlay pixel either hangs off an end
/// of its run or is listed among the escapes - and it costs a quarter of a byte per
/// run where a position per pixel cost a varint.
struct AttachBits<'a> {
    bytes: &'a [u8],
}

impl<'a> AttachBits<'a> {
    /// Read `ceil(runs / 4)` bytes, addressing `runs` runs.
    ///
    /// The count is the stream's own `run_count`, so the non-canonical
    /// `run_count == 0` form reads no bits and its walk asks for none.
    fn read(reader: &mut Reader<'a>, runs: u64) -> Result<AttachBits<'a>> {
        Ok(AttachBits {
            bytes: reader.bytes(runs.div_ceil(4) as usize)?,
        })
    }

    /// Whether the stream carries no bits at all, which only the non-canonical
    /// `run_count == 0` form does.
    fn is_empty(&self) -> bool {
        self.bytes.is_empty()
    }

    /// Bit `end` of run `index`: 0 is the run's first pixel, 1 its last.
    ///
    /// A caller walks runs the array addresses, so the byte is always there.
    #[inline]
    fn get(&self, index: u64, end: u64) -> bool {
        self.bytes[(index / 4) as usize] & (1 << ((index % 4) * 2 + end)) != 0
    }

    /// Whether the bits past the last run are clear. They address no run, so a
    /// stream that sets them carries something the encoder did not mean.
    fn padding_clear(&self, runs: u64) -> bool {
        match runs % 4 {
            0 => true,
            used => {
                let last = self.bytes[(runs / 4) as usize];
                last & (!0u8 << (used * 2)) == 0
            }
        }
    }
}

/// An attached stream's overlay values, in the order its pixels are placed.
///
/// The first is stored as it is; every later one is the previous value plus a
/// zigzagged difference. A band's coverage ramp is therefore a handful of small
/// numbers rather than eight bits of unrelated magnitude per pixel.
struct AttachValues<'a> {
    planes: Planes<'a>,
    /// How many values have been handed out.
    index: u64,
    previous: u8,
}

impl<'a> AttachValues<'a> {
    fn read(reader: &mut Reader<'a>, strict: bool) -> Result<AttachValues<'a>> {
        Ok(AttachValues {
            planes: Planes::read(reader, strict)?,
            index: 0,
            previous: 0,
        })
    }

    /// The next value, which the stream's own count says is there.
    ///
    /// Asking past the count is how a stream whose bits and escapes describe more
    /// pixels than it stores values reports itself.
    fn next_within(&mut self, count: u64) -> Result<u8> {
        if self.index == count {
            return Err(Error::new(
                Check::ReeAttachCount,
                format!(
                    "the attachment bits and escapes describe more overlay pixels than the {count}                      the stream stores values for"
                ),
            ));
        }
        let stored = self.planes.varint()?;
        let value = if self.index == 0 {
            // The first value is stored as it is: there is nothing before it to be
            // a difference from.
            u8::try_from(stored).map_err(|_| {
                Error::new(
                    Check::ReeAttachCount,
                    format!("attached REE overlay value {stored} is not a byte"),
                )
            })?
        } else {
            let sum = i64::from(self.previous) + unzigzag(stored);
            u8::try_from(sum).map_err(|_| {
                Error::new(
                    Check::ReeAttachCount,
                    format!("attached REE overlay value {sum} is not a byte"),
                )
            })?
        };
        self.index += 1;
        self.previous = value;
        Ok(value)
    }
}

/// The strict rule that an overlay pixel is a real anti-aliasing pixel: neither
/// `0x00` nor `0xFF`, and on the side of the threshold its core run is on.
///
/// The two halves are one statement about the decoded mask - its thresholded form
/// is the core the stream carries - seen from the value side: a `0x00` over a
/// `0xFF` run breaks it, and so does a `0x40` over a `0xFF` run.
fn check_attached_value(value: u8, core_value: u8, position: u64) -> Result<()> {
    if value == 0x00 || value == 0xFF || threshold(value) != core_value {
        return Err(Error::new(
            Check::ReeAttachThreshold,
            format!(
                "attached REE overlay pixel {position} holds 0x{value:02X} over binary                  0x{core_value:02X}"
            ),
        ));
    }
    Ok(())
}

/// Attached split REE (tag `0x03`, section 5.6): a thresholded core whose run
/// lengths are split by parity and self-delta coded, then the overlay the core's
/// run boundaries imply.
fn read_attached(
    mut sink: Sink<'_>,
    reader: &mut Reader<'_>,
    total_pixels: u32,
    strict: bool,
) -> Result<()> {
    let total = u64::from(total_pixels);
    let declared_value = reader.u8()?;
    if declared_value != 0x00 && declared_value != 0xFF {
        return Err(Error::new(
            Check::ReeFirstValue,
            format!("attached REE first_value is 0x{declared_value:02X}, not 0x00 or 0xFF"),
        ));
    }
    let run_count = read_run_count(reader, total)?;
    if run_count == 0 && strict {
        return Err(Error::new(
            Check::ReeNoRunCountZero,
            "attached REE uses the non-canonical run_count == 0 form",
        ));
    }
    // A loose read of the non-canonical form is one black run over the whole
    // layer, exactly as tag 0x00 reads it; the overlay fields that follow then
    // describe pixels over a core that is black everywhere.
    let first_value = if run_count == 0 { 0x00 } else { declared_value };
    let mut runs = Runs::new(
        LengthSource::Parity(Parity::read(reader, strict)?),
        run_count.max(1),
        total,
        "attached REE",
    );

    let aa_count = reader.varint()?;
    let bound = total + 1;
    if aa_count > bound {
        return Err(Error::new(
            Check::ReeAttachCount,
            format!("aa_pixel_count {aa_count} exceeds total_pixels + 1 ({bound})"),
        ));
    }
    let bits = AttachBits::read(reader, run_count)?;
    let escape_count = reader.varint()?;
    if escape_count > aa_count {
        return Err(Error::new(
            Check::ReeAttachCount,
            format!("escape_count {escape_count} exceeds aa_pixel_count {aa_count}"),
        ));
    }
    let mut escapes = Planes::read(reader, strict)?;
    let mut values = AttachValues::read(reader, strict)?;

    // One walk places every overlay pixel and writes every core pixel: the run's
    // first pixel when its first bit claims it, then the escapes strictly inside
    // it in ascending order, then its last pixel when its second bit claims it -
    // which is the order the value array is stored in.
    let mut placed = 0u64;
    let mut previous_escape = 0u64;
    let mut escape_index = 0u64;
    let mut pending: Option<u64> = None;

    while let Some(index) = runs.step()? {
        let (start, end) = runs.range();
        let core_value = if index % 2 == 0 {
            first_value
        } else {
            255 - first_value
        };
        sink.fill(start, end, core_value)?;

        // A run a loose read stepped into can hold no pixel - a stored length of 0
        // is legal until a strict reader refuses it - and a bit that claims such a
        // run's first or last pixel names a pixel that does not exist. It places
        // nothing, which is also why the pixels the bits describe stop matching
        // `aa_pixel_count`.
        let empty = start == end;
        if !empty && !bits.is_empty() && bits.get(index, 0) {
            let value = values.next_within(aa_count)?;
            if strict {
                check_attached_value(value, core_value, start)?;
            }
            sink.set(start, value)?;
            placed += 1;
        }

        loop {
            let position = match pending {
                Some(position) => position,
                None => {
                    if escape_index == escape_count {
                        break;
                    }
                    let delta = escapes.varint()?;
                    if escape_index > 0 && delta == 0 {
                        return Err(Error::new(
                            Check::ReeAttachPositions,
                            format!("attached REE escape {escape_index} repeats its predecessor"),
                        ));
                    }
                    let position = previous_escape.checked_add(delta).ok_or_else(|| {
                        Error::new(
                            Check::ReeAttachPositions,
                            "attached REE escape positions overflow",
                        )
                    })?;
                    if position >= total {
                        return Err(Error::new(
                            Check::ReeAttachPositions,
                            format!(
                                "attached REE escape {position} is not below total_pixels {total}"
                            ),
                        ));
                    }
                    previous_escape = position;
                    escape_index += 1;
                    pending = Some(position);
                    continue;
                }
            };
            if position >= end {
                break;
            }
            if position == start || position + 1 == end {
                return Err(Error::new(
                    Check::ReeAttachPositions,
                    format!(
                        "attached REE escape {position} is not strictly inside the core run                          [{start}, {end}) it attaches to"
                    ),
                ));
            }
            let value = values.next_within(aa_count)?;
            if strict {
                check_attached_value(value, core_value, position)?;
            }
            sink.set(position, value)?;
            placed += 1;
            pending = None;
        }

        if !empty && !bits.is_empty() && bits.get(index, 1) {
            if strict && end - start == 1 {
                return Err(Error::new(
                    Check::ReeAttachBits,
                    format!("attached REE run {index} holds one pixel and sets both of its bits"),
                ));
            }
            // A one-pixel run with both bits set places the same pixel twice in a
            // loose read - the second bit names the pixel the first one did - so a
            // stream that counts the duplicate still balances.
            let value = values.next_within(aa_count)?;
            if strict {
                check_attached_value(value, core_value, end - 1)?;
            }
            sink.set(end - 1, value)?;
            placed += 1;
        }
    }

    if let Some(position) = pending {
        return Err(Error::new(
            Check::ReeAttachPositions,
            format!("attached REE escape {position} sits past the last core run"),
        ));
    }
    if placed != aa_count {
        return Err(Error::new(
            Check::ReeAttachCount,
            format!(
                "the attachment bits and escapes describe {placed} overlay pixels,                  aa_pixel_count says {aa_count}"
            ),
        ));
    }
    if strict {
        if runs.empty_run() {
            return Err(Error::new(
                Check::ReeRunLengths,
                "attached REE stores an empty run",
            ));
        }
        runs.check_consumed()?;
        escapes.check_consumed()?;
        values.planes.check_consumed()?;
        if !bits.padding_clear(run_count) {
            return Err(Error::new(
                Check::ReeAttachBits,
                "attached REE sets attachment bits past the last run",
            ));
        }
    }
    Ok(())
}

/// Reject a mask whose length is not the layer's pixel count.
fn check_mask(pixels: &[u8], total_pixels: u32) -> Result<()> {
    if pixels.len() != total_pixels as usize {
        return Err(Error::new(
            Check::ReeDataSize,
            format!(
                "mask holds {} pixels, total_pixels is {total_pixels}",
                pixels.len()
            ),
        ));
    }
    Ok(())
}

/// A zero-pixel layer is the empty-layer form: it has no encodable stream.
fn require_pixels(pixels: &[u8]) -> Result<()> {
    if pixels.is_empty() {
        return Err(Error::new(
            Check::ReeDataSize,
            "a zero-pixel layer has no encodable stream: it is the empty-layer form",
        ));
    }
    Ok(())
}

/// Reject a run list that is not a canonical cover of `total_pixels` pixels.
///
/// The two canonical-form rules report the check a strict reader reports for the
/// same stream: `ree.run_lengths` for a zero-length run and `ree.grayscale_runs`
/// for a value repeated by adjacent runs - they would be a single run. A cover of
/// the wrong size is the run form of a mask of the wrong length, so it reports
/// `ree.data_size` like [`encode`] does.
fn check_runs(runs: &[Run], total_pixels: u32) -> Result<()> {
    let mut covered = 0u64;
    let mut previous: Option<u8> = None;
    for run in runs {
        if run.length == 0 {
            return Err(Error::new(
                Check::ReeRunLengths,
                "run length 0: a run covers at least one pixel",
            ));
        }
        if previous == Some(run.value) {
            return Err(Error::new(
                Check::ReeGrayscaleRuns,
                format!(
                    "adjacent runs both carry 0x{:02X}: they are a single run",
                    run.value
                ),
            ));
        }
        covered += u64::from(run.length);
        previous = Some(run.value);
    }
    if covered != u64::from(total_pixels) {
        return Err(Error::new(
            Check::ReeDataSize,
            format!("runs cover {covered} pixels, total_pixels is {total_pixels}"),
        ));
    }
    Ok(())
}

/// A layer's runs, from either a pixel mask or a caller's run slice.
///
/// One walk yields every maximal run in row-major order and does so lazily: the
/// pixel form derives each run as it goes and never materializes them, which is
/// what keeps a dense 16K layer - up to 94 million runs - from needing a vector
/// of runs. `map` is applied to each value and adjacent equal mapped values are
/// merged, so the split tag's thresholded core sees the same runs either way.
#[derive(Clone, Copy)]
enum RunSource<'a> {
    /// One byte per pixel, in row-major order.
    Pixels(&'a [u8]),
    /// Runs already checked to be a canonical cover of the layer.
    Runs(&'a [Run]),
}

impl RunSource<'_> {
    /// Call `f(length, value)` once per run, in row-major order, with every value
    /// passed through `map` and adjacent equal mapped values merged.
    fn walk<F>(self, map: impl Fn(u8) -> u8 + Copy, mut f: F) -> Result<()>
    where
        F: FnMut(u64, u8) -> Result<()>,
    {
        match self {
            RunSource::Pixels(pixels) => {
                let mut pixels = pixels.iter().copied();
                let Some(first) = pixels.next() else {
                    return Ok(());
                };
                let mut value = map(first);
                let mut length = 1u64;
                for pixel in pixels {
                    let mapped = map(pixel);
                    if mapped == value {
                        length += 1;
                        continue;
                    }
                    f(length, value)?;
                    value = mapped;
                    length = 1;
                }
                f(length, value)
            }
            RunSource::Runs(runs) => {
                let mut pending: Option<(u64, u8)> = None;
                for run in runs {
                    let value = map(run.value);
                    match pending {
                        Some((length, previous)) if previous == value => {
                            pending = Some((length + u64::from(run.length), value));
                        }
                        Some((length, previous)) => {
                            f(length, previous)?;
                            pending = Some((u64::from(run.length), value));
                        }
                        None => pending = Some((u64::from(run.length), value)),
                    }
                }
                match pending {
                    Some((length, value)) => f(length, value),
                    None => Ok(()),
                }
            }
        }
    }

    /// Whether every pixel is `0x00`: that layer is the empty-layer form and has
    /// no stream at all.
    fn is_all_black(self) -> bool {
        match self {
            RunSource::Pixels(pixels) => pixels.iter().all(|pixel| *pixel == 0),
            RunSource::Runs(runs) => runs.iter().all(|run| run.value == 0),
        }
    }

    /// Whether every pixel is `0x00` or `0xFF`, which tag `0x00` requires.
    fn is_binary(self) -> bool {
        match self {
            RunSource::Pixels(pixels) => pixels.iter().all(|pixel| *pixel == 0 || *pixel == 255),
            RunSource::Runs(runs) => runs.iter().all(|run| run.value == 0 || run.value == 255),
        }
    }
}

/// The byte lengths of the four significance planes of a varint array.
#[derive(Debug, Default, Clone, Copy)]
struct PlaneSizes([u64; PLANES]);

impl PlaneSizes {
    /// Account for one varint: a `k`-byte varint adds one byte to planes `0..k`.
    ///
    /// A value needing more than [`PLANES`] bytes is out of bounds here and is
    /// reported by [`write_plane_byte`] when the plane it would need is written,
    /// so this only has to keep the count in range.
    fn add(&mut self, value: u64) {
        let len = crate::varint::encoded_len(value).min(PLANES);
        for size in &mut self.0[..len] {
            *size += 1;
        }
    }

    /// Write the four lengths ahead of the planes.
    fn write(&self, writer: &mut Writer) {
        for size in self.0 {
            writer.varint(size);
        }
    }
}

/// Append byte `plane` of `value`'s varint, if the varint reaches that plane.
///
/// A value needing more than [`PLANES`] bytes has no representation in the
/// format, so the encoder reports it rather than writing a varint whose top byte
/// is missing.
fn write_plane_byte(writer: &mut Writer, value: u64, plane: usize) -> Result<()> {
    let shifted = value >> (7 * plane);
    if plane > 0 && shifted == 0 {
        // The varint ended in an earlier plane.
        return Ok(());
    }
    let more = shifted >= 0x80;
    if more && plane + 1 == PLANES {
        return Err(Error::new(
            Check::ReePlanes,
            format!("the value {value} needs more than {PLANES} significance planes"),
        ));
    }
    writer.u8((shifted & 0x7F) as u8 | if more { 0x80 } else { 0 });
    Ok(())
}

/// Write `PLANES(n)` for the varints a walk yields: the four plane lengths, then
/// the bytes of plane 0, plane 1, plane 2 and plane 3.
///
/// `walk` runs once per plane, because a plane's length is written ahead of its
/// bytes while the varints arrive in order. Nothing is materialized: `sizes` is
/// what a sizing walk counted, and each plane walk re-derives the varints it
/// needs from the same source.
fn write_planes(
    writer: &mut Writer,
    sizes: PlaneSizes,
    mut walk: impl FnMut(&mut Writer, usize) -> Result<()>,
) -> Result<()> {
    sizes.write(writer);
    for plane in 0..PLANES {
        walk(writer, plane)?;
    }
    Ok(())
}

/// Write the tagless binary REE stream of section 5.3 for `source`, mapping each
/// value through `map` so the split encoder can threshold without materializing a
/// second mask.
fn write_binary_stream(
    writer: &mut Writer,
    source: RunSource<'_>,
    map: impl Fn(u8) -> u8 + Copy,
) -> Result<()> {
    // Runs alternate strictly, so the value after the first is determined.
    let mut first_value: Option<u8> = None;
    let mut last: Option<u8> = None;
    let mut run_count = 0u64;
    let mut sizes = PlaneSizes::default();
    // Every run but the last is stored, and a run is only known not to be the
    // last once another one arrives.
    let mut pending: Option<u64> = None;
    source.walk(map, |length, value| {
        match last {
            None => {
                if value != 0x00 && value != 0xFF {
                    return Err(Error::new(
                        Check::ReeFirstValue,
                        format!("binary REE first_value is 0x{value:02X}, not 0x00 or 0xFF"),
                    ));
                }
                first_value = Some(value);
            }
            Some(previous) if value != 255 - previous => {
                return Err(Error::new(
                    Check::ReeFirstValue,
                    format!("binary REE cannot hold pixel 0x{value:02X}"),
                ));
            }
            Some(_) => {}
        }
        last = Some(value);
        run_count += 1;
        if let Some(previous) = pending.replace(length) {
            sizes.add(previous);
        }
        Ok(())
    })?;
    let Some(first_value) = first_value else {
        return Err(Error::new(
            Check::ReeDataSize,
            "a binary stream needs at least one pixel",
        ));
    };

    writer.u8(first_value);
    writer.varint(run_count);
    // The lengths of the first `run_count - 1` runs; the last ends at
    // `total_pixels`, which the reader already knows.
    write_planes(writer, sizes, |writer, plane| {
        let mut remaining = run_count;
        source.walk(map, |length, _| {
            remaining -= 1;
            if remaining > 0 {
                write_plane_byte(writer, length, plane)?;
            }
            Ok(())
        })
    })
}

/// Write the tagless grayscale REE stream of section 5.4 for `source`: the run
/// count, every run's value, then the planes of every run length but the last.
fn write_grayscale_stream(writer: &mut Writer, source: RunSource<'_>) -> Result<()> {
    let mut run_count = 0u64;
    let mut sizes = PlaneSizes::default();
    let mut pending: Option<u64> = None;
    source.walk(
        |value| value,
        |length, _| {
            run_count += 1;
            if let Some(previous) = pending.replace(length) {
                sizes.add(previous);
            }
            Ok(())
        },
    )?;
    writer.varint(run_count);

    // Every run's value, hoisted out of the run loop: an edge's values are a few
    // repeated bytes, and keeping them out of the lengths leaves those planes
    // smooth.
    source.walk(
        |value| value,
        |_, value| {
            writer.u8(value);
            Ok(())
        },
    )?;

    // The last run ends at `total_pixels`, which the reader already knows.
    write_planes(writer, sizes, |writer, plane| {
        let mut remaining = run_count;
        source.walk(
            |value| value,
            |length, _| {
                remaining -= 1;
                if remaining > 0 {
                    write_plane_byte(writer, length, plane)?;
                }
                Ok(())
            },
        )
    })
}

/// Write the tagless split REE stream of section 5.5 for `source`: a binary core
/// over the thresholded values, then the sparse overlay of the anti-aliasing
/// pixels.
///
/// The overlay costs one varint per anti-aliasing pixel, which is unavoidable:
/// those bytes *are* the stream. The run walk around them stays lazy, so no
/// per-pixel data is ever materialized.
fn write_split_stream(writer: &mut Writer, source: RunSource<'_>) -> Result<()> {
    write_binary_stream(writer, source, threshold)?;

    // The overlay is exactly the pixels whose value is neither 0x00 nor 0xFF.
    // Within a run of them every delta after the first is 1.
    let mut count = 0u64;
    let mut sizes = PlaneSizes::default();
    let mut start = 0u64;
    let mut previous = 0u64;
    source.walk(
        |value| value,
        |length, value| {
            if value != 0x00 && value != 0xFF {
                count += length;
                sizes.add(start - previous);
                for _ in 1..length {
                    sizes.add(1);
                }
                previous = start + length - 1;
            }
            start += length;
            Ok(())
        },
    )?;
    writer.varint(count);

    // Positions are absolute then delta-encoded, and strictly increasing, so
    // every delta after the first is at least 1.
    write_planes(writer, sizes, |writer, plane| {
        let mut start = 0u64;
        let mut previous = 0u64;
        source.walk(
            |value| value,
            |length, value| {
                if value != 0x00 && value != 0xFF {
                    write_plane_byte(writer, start - previous, plane)?;
                    for _ in 1..length {
                        write_plane_byte(writer, 1, plane)?;
                    }
                    previous = start + length - 1;
                }
                start += length;
                Ok(())
            },
        )
    })?;

    // The values, in the same order.
    source.walk(
        |value| value,
        |length, value| {
            if value != 0x00 && value != 0xFF {
                for _ in 0..length {
                    writer.u8(value);
                }
            }
            Ok(())
        },
    )
}

/// Whether a pixel value is an overlay value: neither `0x00` nor `0xFF`.
#[inline]
fn is_aa(value: u8) -> bool {
    value != 0x00 && value != 0xFF
}

/// The values an attached length array stores, replayed.
///
/// The array holds every core run's length but the last, split by parity: a
/// parity's first entry is a length and every later one is the zigzag of its
/// difference from the entry two runs earlier. Sizing the planes and writing each
/// of them walk the same runs and derive the same sequence, so nothing is held
/// between those walks.
struct StoredLengths {
    /// The last length each parity produced.
    last: [u64; 2],
    index: u64,
}

impl StoredLengths {
    fn new() -> StoredLengths {
        StoredLengths {
            last: [0; 2],
            index: 0,
        }
    }

    /// The value the array stores for the next length, and which parity's array
    /// it belongs to.
    fn next(&mut self, length: u64) -> (u64, usize) {
        let parity = (self.index % 2) as usize;
        let value = if self.index < 2 {
            length
        } else {
            zigzag(length as i64 - self.last[parity] as i64)
        };
        self.last[parity] = length;
        self.index += 1;
        (value, parity)
    }
}

/// Walk the overlay structure of an attached stream over the layer's runs.
///
/// `run` sees every core run in order, with whether its first and its last pixel
/// carry an overlay pixel; `escape` sees every overlay pixel no bit covers, with
/// its position and its delta from the previous escape. Both are called in the
/// order the stream stores them, and nothing is kept between walks, so a stream is
/// sized by walking it once and written by walking it again per plane.
///
/// The core run being built closes when a run maps to the other binary value, and
/// its last pixel is the overlay pixel still pending at that moment - which is why
/// the pixel is held back rather than emitted: only the close says whether it is
/// the run's end or a pixel strictly inside it.
fn walk_overlay(
    source: RunSource<'_>,
    mut run: impl FnMut(u64, bool, bool) -> Result<()>,
    mut escape: impl FnMut(u64, u64) -> Result<()>,
) -> Result<()> {
    let mut index = 0u64;
    let mut at = 0u64;
    let mut start = 0u64;
    let mut mapped: Option<u8> = None;
    let mut first_aa = false;
    let mut pending: Option<u64> = None;
    let mut previous_escape = 0u64;

    source.walk(
        |value| value,
        |length, value| {
            let binary = threshold(value);
            if mapped != Some(binary) {
                if mapped.is_some() {
                    run(index, first_aa, pending.is_some())?;
                    index += 1;
                }
                mapped = Some(binary);
                start = at;
                first_aa = is_aa(value);
                pending = None;
            }
            if is_aa(value) {
                for position in at..at + length {
                    if position == start && first_aa {
                        // The run's first bit covers it.
                        continue;
                    }
                    if let Some(previous) = pending.take() {
                        escape(previous, previous - previous_escape)?;
                        previous_escape = previous;
                    }
                    pending = Some(position);
                }
            } else if let Some(previous) = pending.take() {
                // A binary pixel follows inside the same core run, so the overlay
                // pixel before it is strictly inside the run and needs an escape.
                escape(previous, previous - previous_escape)?;
                previous_escape = previous;
            }
            at += length;
            Ok(())
        },
    )?;
    if mapped.is_some() {
        run(index, first_aa, pending.is_some())?;
    }
    Ok(())
}

/// Write the tagless attached stream of section 5.6 for `source`: the thresholded
/// core with its lengths split by parity and self-delta coded, then the overlay
/// the core's run boundaries imply.
fn write_attached_stream(writer: &mut Writer, source: RunSource<'_>) -> Result<()> {
    // One walk over the thresholded core sizes the length arrays and fixes the
    // core's run count and first value. Every run but the last is stored, and a
    // run is only known not to be the last once another one arrives.
    let mut first_value: Option<u8> = None;
    let mut run_count = 0u64;
    let mut pending: Option<u64> = None;
    let mut stored = StoredLengths::new();
    let mut sizes = [PlaneSizes::default(); 2];
    let mut last: Option<u8> = None;
    source.walk(threshold, |length, value| {
        match last {
            None => {
                if value != 0x00 && value != 0xFF {
                    return Err(Error::new(
                        Check::ReeFirstValue,
                        format!("attached REE first_value is 0x{value:02X}, not 0x00 or 0xFF"),
                    ));
                }
                first_value = Some(value);
            }
            Some(previous) if value != 255 - previous => {
                return Err(Error::new(
                    Check::ReeFirstValue,
                    format!("attached REE cannot hold pixel 0x{value:02X}"),
                ));
            }
            Some(_) => {}
        }
        last = Some(value);
        if let Some(previous) = pending.replace(length) {
            let (value, parity) = stored.next(previous);
            sizes[parity].add(value);
        }
        run_count += 1;
        Ok(())
    })?;
    let Some(first_value) = first_value else {
        return Err(Error::new(
            Check::ReeDataSize,
            "an attached stream needs at least one pixel",
        ));
    };

    // A second walk sizes the attachment bits, the escapes and the values. The
    // bits are the one thing this stream has to hold: they are written as a byte
    // array, and a run's second bit is only known when the run closes.
    let mut bits: Vec<u8> = Vec::new();
    let mut escape_sizes = PlaneSizes::default();
    let mut escape_count = 0u64;
    let mut value_sizes = PlaneSizes::default();
    let mut value_count = 0u64;
    let mut previous_value = 0u8;
    walk_overlay(
        source,
        |index, first, last| {
            let byte = (index / 4) as usize;
            if bits.len() <= byte {
                bits.resize(byte + 1, 0);
            }
            if first {
                bits[byte] |= 1 << ((index % 4) * 2);
            }
            if last {
                bits[byte] |= 2 << ((index % 4) * 2);
            }
            Ok(())
        },
        |_, delta| {
            escape_sizes.add(delta);
            escape_count += 1;
            Ok(())
        },
    )?;
    source.walk(
        |value| value,
        |length, value| {
            if is_aa(value) {
                for _ in 0..length {
                    let stored = if value_count == 0 {
                        u64::from(value)
                    } else {
                        zigzag(i64::from(value) - i64::from(previous_value))
                    };
                    value_sizes.add(stored);
                    value_count += 1;
                    previous_value = value;
                }
            }
            Ok(())
        },
    )?;
    bits.resize(run_count.div_ceil(4) as usize, 0);

    // Then write it: the core's header, the two parity arrays plane by plane, the
    // bits, the escapes, and the values.
    writer.u8(first_value);
    writer.varint(run_count);
    for (parity, size) in sizes.iter().enumerate() {
        size.write(writer);
        for plane in 0..PLANES {
            let mut replay = StoredLengths::new();
            let mut pending: Option<u64> = None;
            source.walk(threshold, |length, _| {
                if let Some(previous) = pending.replace(length) {
                    let (value, at) = replay.next(previous);
                    if at == parity {
                        write_plane_byte(writer, value, plane)?;
                    }
                }
                Ok(())
            })?;
        }
    }
    writer.varint(value_count);
    writer.bytes(&bits);
    writer.varint(escape_count);
    escape_sizes.write(writer);
    for plane in 0..PLANES {
        walk_overlay(
            source,
            |_, _, _| Ok(()),
            |_, delta| write_plane_byte(writer, delta, plane),
        )?;
    }
    value_sizes.write(writer);
    for plane in 0..PLANES {
        let mut index = 0u64;
        let mut previous = 0u8;
        source.walk(
            |value| value,
            |length, value| {
                if is_aa(value) {
                    for _ in 0..length {
                        let stored = if index == 0 {
                            u64::from(value)
                        } else {
                            zigzag(i64::from(value) - i64::from(previous))
                        };
                        write_plane_byte(writer, stored, plane)?;
                        index += 1;
                        previous = value;
                    }
                }
                Ok(())
            },
        )?;
    }
    Ok(())
}

/// Encode a layer mask, choosing the tag per `mode`.
///
/// Returns `None` for an all-black layer, which is stored as the empty-layer
/// form with no bytes at all.
///
/// The returned bytes are the mask data a layer stores: the tag, then the
/// stream. The tag is returned alongside them so a caller can log or branch on
/// the choice, not so it can be re-prepended.
///
/// The mask is walked run by run as it is encoded, so no vector of runs is built
/// for it; [`encode_runs`] is the same encoder for a caller who already holds the
/// runs.
pub fn encode(pixels: &[u8], total_pixels: u32, mode: EncodeMode) -> Result<Option<(u8, Vec<u8>)>> {
    check_mask(pixels, total_pixels)?;
    encode_source(RunSource::Pixels(pixels), mode)
}

/// Encode a layer given as runs rather than pixels, choosing the tag per `mode`.
///
/// Same tags, same canonical rules, same bytes as [`encode`] does for the mask
/// the runs describe - without anyone ever building that mask. A rasterizer whose
/// output is run-length encoded therefore feeds the encoder directly.
///
/// The run list must be canonical: every `length` is at least 1, no two adjacent
/// runs carry the same `value` (they would be one run), and the lengths sum to
/// `total_pixels`. Returns `None` for an all-black layer, which is stored as the
/// empty-layer form with no bytes at all.
pub fn encode_runs(
    runs: &[Run],
    total_pixels: u32,
    mode: EncodeMode,
) -> Result<Option<(u8, Vec<u8>)>> {
    check_runs(runs, total_pixels)?;
    encode_source(RunSource::Runs(runs), mode)
}

/// Encode one layer's runs, choosing the tag per `mode`. The source's runs are
/// already known to be a canonical cover of the layer, so the walk needs no
/// further validation.
fn encode_source(source: RunSource<'_>, mode: EncodeMode) -> Result<Option<(u8, Vec<u8>)>> {
    if source.is_all_black() {
        return Ok(None);
    }
    let encoded = match mode {
        EncodeMode::Binary => (TAG_BINARY, encode_binary_source(source)?),
        EncodeMode::Grayscale => (TAG_GRAYSCALE, encode_grayscale_source(source)?),
        EncodeMode::Split => (TAG_SPLIT, encode_split_source(source)?),
        EncodeMode::Attached => (TAG_ATTACHED, encode_attached_source(source)?),
        EncodeMode::Auto => {
            if source.is_binary() {
                (TAG_BINARY, encode_binary_source(source)?)
            } else {
                // Section 5.7: the encoder picks the smaller of the two, and a
                // tie goes to grayscale.
                let grayscale = encode_grayscale_source(source)?;
                let split = encode_split_source(source)?;
                if split.len() < grayscale.len() {
                    (TAG_SPLIT, split)
                } else {
                    (TAG_GRAYSCALE, grayscale)
                }
            }
        }
    };
    Ok(Some(encoded))
}

/// Encode with tag `0x00`; the returned bytes include the tag.
pub fn encode_binary(pixels: &[u8], total_pixels: u32) -> Result<Vec<u8>> {
    check_mask(pixels, total_pixels)?;
    require_pixels(pixels)?;
    encode_binary_source(RunSource::Pixels(pixels))
}

/// Tag `0x00` for a source already known to hold at least one pixel.
fn encode_binary_source(source: RunSource<'_>) -> Result<Vec<u8>> {
    let mut writer = Writer::new();
    writer.u8(TAG_BINARY);
    write_binary_stream(&mut writer, source, |pixel| pixel)?;
    Ok(writer.into_vec())
}

/// Encode with tag `0x01`; the returned bytes include the tag.
pub fn encode_grayscale(pixels: &[u8], total_pixels: u32) -> Result<Vec<u8>> {
    check_mask(pixels, total_pixels)?;
    require_pixels(pixels)?;
    encode_grayscale_source(RunSource::Pixels(pixels))
}

/// Tag `0x01` for a source already known to hold at least one pixel.
fn encode_grayscale_source(source: RunSource<'_>) -> Result<Vec<u8>> {
    let mut writer = Writer::new();
    writer.u8(TAG_GRAYSCALE);
    write_grayscale_stream(&mut writer, source)?;
    Ok(writer.into_vec())
}

/// Encode with tag `0x02`; the returned bytes include the tag.
pub fn encode_split(pixels: &[u8], total_pixels: u32) -> Result<Vec<u8>> {
    check_mask(pixels, total_pixels)?;
    require_pixels(pixels)?;
    encode_split_source(RunSource::Pixels(pixels))
}

/// Tag `0x02` for a source already known to hold at least one pixel.
fn encode_split_source(source: RunSource<'_>) -> Result<Vec<u8>> {
    let mut writer = Writer::new();
    writer.u8(TAG_SPLIT);
    write_split_stream(&mut writer, source)?;
    Ok(writer.into_vec())
}

/// Encode with tag `0x03`; the returned bytes include the tag.
pub fn encode_attached(pixels: &[u8], total_pixels: u32) -> Result<Vec<u8>> {
    check_mask(pixels, total_pixels)?;
    require_pixels(pixels)?;
    encode_attached_source(RunSource::Pixels(pixels))
}

/// Tag `0x03` for a source already known to hold at least one pixel.
fn encode_attached_source(source: RunSource<'_>) -> Result<Vec<u8>> {
    let mut writer = Writer::new();
    writer.u8(TAG_ATTACHED);
    write_attached_stream(&mut writer, source)?;
    Ok(writer.into_vec())
}

/// Check a stream against the canonical rules and report the bytes it used.
///
/// `data` is the same one-byte tag plus stream that [`decode`] takes - the
/// canonical rules of section 5.7 depend on the tag - and no mask is built: the
/// walk reads the same bytes under the same rules with a sink that keeps
/// nothing, which is what takes a 16K layer's validation from the 94 MB a slice
/// decodes to down to the stream itself. The returned length is the stream's
/// exact extent, so a caller holding the layer's stored range can reject padding
/// after it.
pub fn validate_stream(data: &[u8], total_pixels: u32, strict: bool) -> Result<usize> {
    let (tag, mut reader) = tag_and_stream(data)?;
    read(tag, Sink::None, &mut reader, total_pixels, strict)?;
    Ok(1 + reader.pos())
}

/// Walk the pixels a slice exposes, as `[start, end)` ranges.
///
/// A slice exposes every pixel its mask decodes to something other than `0x00`,
/// which is what the sector partition rule ([`spec/13-sectors.md`] section 7.3)
/// compares between the sectors of one layer. The ranges come from the stream's
/// structure, so the rule costs no mask: a split stream reports its thresholded
/// core's runs and then the overlay it carries, whose pixels a strict reader has
/// already required to be neither `0x00` nor `0xFF`, and a caller that wants the
/// exposed pixels keeps their union.
pub(crate) fn exposed_ranges(
    data: &[u8],
    total_pixels: u32,
    report: impl FnMut(u64, u64) -> Result<()>,
) -> Result<()> {
    let (tag, mut reader) = tag_and_stream(data)?;
    let mut report = report;
    read(
        tag,
        Sink::Exposed(&mut report),
        &mut reader,
        total_pixels,
        true,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The 64 x 48 pixel masks of `test-vectors/valid/binary-basic.lumen`, one
    /// per tag, exactly as the corpus stores them.
    ///
    /// Each length array is four plane lengths followed by the planes, so the
    /// binary stream's `02 01 00 00 64 c8 01` is plane 0 holding `64 c8` and
    /// plane 1 holding `01`: the lengths 100 and 200.
    const LAYER_BINARY: &str = "0000030201000064c801";
    const LAYER_GRAYSCALE: &str = "0105008000ff000400000064146464";
    const LAYER_SPLIT: &str = "02000504000000641e14321e1e000000640101010101010101010101010101010101010101010101010101010101c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8";
    /// `HEAD.display_width_px * HEAD.display_height_px` for that file.
    const TOTAL: u32 = 64 * 48;

    /// Expand `(value, length)` runs into a mask.
    fn mask(runs: &[(u8, usize)]) -> Vec<u8> {
        let mut pixels = Vec::new();
        for (value, length) in runs {
            pixels.extend(std::iter::repeat_n(*value, *length));
        }
        pixels
    }

    /// The `(value, length)` runs of a mask.
    fn runs(pixels: &[u8]) -> Vec<(u8, usize)> {
        let mut runs: Vec<(u8, usize)> = Vec::new();
        for &pixel in pixels {
            if let Some(last) = runs.last_mut() {
                if last.0 == pixel {
                    last.1 += 1;
                    continue;
                }
            }
            runs.push((pixel, 1));
        }
        runs
    }

    fn bytes(hex: &str) -> Vec<u8> {
        hex::decode(hex).unwrap()
    }

    /// The canonical `Run` list of a mask.
    fn runs_of(pixels: &[u8]) -> Vec<Run> {
        runs(pixels)
            .into_iter()
            .map(|(value, length)| Run::new(length as u32, value))
            .collect()
    }

    /// The `Run` list of `(value, length)` pairs.
    fn run_list(spec: &[(u8, usize)]) -> Vec<Run> {
        spec.iter()
            .map(|(value, length)| Run::new(*length as u32, *value))
            .collect()
    }

    /// Every encoding, so a mismatch in any of them is caught.
    const MODES: [EncodeMode; 5] = [
        EncodeMode::Auto,
        EncodeMode::Binary,
        EncodeMode::Grayscale,
        EncodeMode::Split,
        EncodeMode::Attached,
    ];

    /// One corpus stream: the hex it is stored as, its mask as `(value, length)`
    /// pairs, the tag it carries, and the mode that selects that tag.
    type CorpusCase = (&'static str, Vec<(u8, usize)>, u8, EncodeMode);

    /// The corpus masks as runs, with the tag each one is stored under and the
    /// mode that selects that tag. The split mask is stored as split by the
    /// corpus' own preference, not because it is the smaller stream.
    fn corpus_cases() -> [CorpusCase; 3] {
        [
            (
                LAYER_BINARY,
                vec![(0, 100), (255, 200), (0, 2772)],
                TAG_BINARY,
                EncodeMode::Binary,
            ),
            (
                LAYER_GRAYSCALE,
                vec![(0, 100), (128, 20), (0, 100), (255, 100), (0, 2752)],
                TAG_GRAYSCALE,
                EncodeMode::Grayscale,
            ),
            (
                LAYER_SPLIT,
                vec![(0, 100), (200, 30), (0, 20), (255, 50), (0, 2872)],
                TAG_SPLIT,
                EncodeMode::Split,
            ),
        ]
    }

    /// The run path must return the pixel path's bytes for a mask, or fail the
    /// same named check when the mode cannot represent it.
    fn assert_run_path_matches(pixels: &[u8], runs: &[Run], total: u32, mode: EncodeMode) {
        match (encode(pixels, total, mode), encode_runs(runs, total, mode)) {
            (Ok(pixel_path), Ok(run_path)) => assert_eq!(pixel_path, run_path, "mode {mode:?}"),
            (Err(pixel_path), Err(run_path)) => {
                assert_eq!(pixel_path.check(), run_path.check(), "mode {mode:?}")
            }
            (pixel_path, run_path) => {
                panic!("{mode:?}: pixel path {pixel_path:?}, run path {run_path:?}")
            }
        }
    }

    fn check_of(data: &[u8], total: u32, strict: bool) -> Check {
        decode(data, total, strict).unwrap_err().check()
    }

    #[test]
    fn spec_varint_examples() {
        // Section 5.2's table and its three worked examples.
        assert_eq!(crate::varint::to_vec(0), vec![0x00]);
        assert_eq!(crate::varint::to_vec(128), vec![0x80, 0x01]);
        assert_eq!(crate::varint::encoded_len(127), 1);
        assert_eq!(crate::varint::encoded_len(128), 2);
        assert_eq!(crate::varint::encoded_len(16_383), 2);
        assert_eq!(crate::varint::encoded_len(16_384), 3);
        assert_eq!(crate::varint::encoded_len(2_097_151), 3);
        assert_eq!(crate::varint::encoded_len(268_435_455), 4);
        assert_eq!(
            crate::varint::to_vec(1920 * 1080),
            vec![0x80, 0xC8, 0x7E],
            "2 073 600 is 3 bytes"
        );
        assert_eq!(crate::varint::encoded_len(11_520 * 6_480), 4);
        let twelve_k = crate::varint::to_vec(11_520 * 6_480);
        let mut reader = Reader::new(&twelve_k);
        assert_eq!(reader.varint().unwrap(), 11_520 * 6_480);
        assert!(reader.is_empty());
    }

    #[test]
    fn binary_layer_of_the_corpus_round_trips() {
        let data = bytes(LAYER_BINARY);
        let expected = mask(&[(0, 100), (255, 200), (0, 2772)]);
        for strict in [false, true] {
            let layer = decode(&data, TOTAL, strict).unwrap();
            assert_eq!(layer.tag, Some(TAG_BINARY));
            assert_eq!(layer.pixels, expected);
            assert!(layer.is_binary());
        }
        assert_eq!(encode_binary(&expected, TOTAL).unwrap(), data);
        assert_eq!(
            encode(&expected, TOTAL, EncodeMode::Auto).unwrap(),
            Some((TAG_BINARY, data))
        );
    }

    #[test]
    fn grayscale_layer_of_the_corpus_round_trips() {
        let data = bytes(LAYER_GRAYSCALE);
        let expected = mask(&[(0, 100), (128, 20), (0, 100), (255, 100), (0, 2752)]);
        for strict in [false, true] {
            let layer = decode(&data, TOTAL, strict).unwrap();
            assert_eq!(layer.tag, Some(TAG_GRAYSCALE));
            assert_eq!(layer.pixels, expected);
        }
        assert_eq!(encode_grayscale(&expected, TOTAL).unwrap(), data);
        // Grayscale is 15 bytes here; the split stream is far larger.
        assert_eq!(
            encode(&expected, TOTAL, EncodeMode::Auto).unwrap(),
            Some((TAG_GRAYSCALE, data))
        );
    }

    #[test]
    fn split_layer_of_the_corpus_round_trips() {
        let data = bytes(LAYER_SPLIT);
        assert_eq!(data.len(), 76, "the corpus split stream is 76 bytes");
        // A binary core with thirty 200-valued edge pixels at 100..130.
        let expected = mask(&[(0, 100), (200, 30), (0, 20), (255, 50), (0, 2872)]);
        for strict in [false, true] {
            let layer = decode(&data, TOTAL, strict).unwrap();
            assert_eq!(layer.tag, Some(TAG_SPLIT));
            assert_eq!(layer.pixels, expected);
        }
        // Byte equality pins the delta encoding: the first position is absolute
        // (0x64 = 100), the twenty-nine that follow are 1 apart, and exactly
        // thirty value bytes close the stream. The positions are one plane, so
        // they start after its four length varints.
        assert_eq!(data[16], 0x64, "the first position is 100");
        assert!(data[17..46].iter().all(|b| *b == 0x01));
        assert!(data[46..].iter().all(|b| *b == 0xC8));
        assert_eq!(encode_split(&expected, TOTAL).unwrap(), data);
        assert_eq!(
            encode(&expected, TOTAL, EncodeMode::Split).unwrap(),
            Some((TAG_SPLIT, data))
        );
    }

    #[test]
    fn all_black_is_the_empty_layer_form() {
        assert_eq!(encode(&[0u8; 16], 16, EncodeMode::Auto).unwrap(), None);
        assert_eq!(encode(&[0u8; 16], 16, EncodeMode::Binary).unwrap(), None);
        assert_eq!(encode(&[0u8; 16], 16, EncodeMode::Split).unwrap(), None);
        assert!(DecodedLayer::empty(16).is_empty());
        // A zero-pixel layer is the empty-layer form too, and the per-tag
        // encoders refuse to invent a stream for it.
        assert_eq!(encode(&[], 0, EncodeMode::Auto).unwrap(), None);
        assert_eq!(
            encode_binary(&[], 0).unwrap_err().check(),
            Check::ReeDataSize
        );
        assert_eq!(
            encode_grayscale(&[], 0).unwrap_err().check(),
            Check::ReeDataSize
        );
        assert_eq!(
            encode_split(&[], 0).unwrap_err().check(),
            Check::ReeDataSize
        );
    }

    #[test]
    fn all_white_is_one_run() {
        let (tag, data) = encode(&[255u8; 16], 16, EncodeMode::Auto).unwrap().unwrap();
        assert_eq!(tag, TAG_BINARY);
        // tag, first_value 0xFF, run_count 1, then four zero plane lengths: the
        // header is written even when no length is stored.
        assert_eq!(data, vec![TAG_BINARY, 0xFF, 0x01, 0x00, 0x00, 0x00, 0x00]);
        assert_eq!(decode(&data, 16, true).unwrap().pixels, vec![255u8; 16]);
    }

    #[test]
    fn auto_picks_the_smaller_stream_and_breaks_ties_towards_grayscale() {
        // A six-pixel mask whose two streams are both 17 bytes: grayscale pays a
        // value byte per run, split a byte per edge pixel.
        let tie = [0xFF, 0x00, 0x01, 0x00, 0x01, 0x00];
        assert_eq!(encode_grayscale(&tie, 6).unwrap().len(), 17);
        assert_eq!(encode_split(&tie, 6).unwrap().len(), 17);
        assert_eq!(
            encode(&tie, 6, EncodeMode::Auto).unwrap().unwrap().0,
            TAG_GRAYSCALE
        );

        // Alternating black and edge pixels: the thresholded mask collapses to a
        // single run, so the split core is seven bytes against grayscale's two
        // hundred runs.
        let alternating: Vec<u8> = (0..200).map(|i| if i % 2 == 0 { 0 } else { 10 }).collect();
        let grayscale = encode_grayscale(&alternating, 200).unwrap();
        let split = encode_split(&alternating, 200).unwrap();
        assert!(split.len() < grayscale.len(), "{split:?} {grayscale:?}");
        let (tag, data) = encode(&alternating, 200, EncodeMode::Auto)
            .unwrap()
            .unwrap();
        assert_eq!(tag, TAG_SPLIT);
        assert_eq!(data, split);
        assert_eq!(decode(&data, 200, false).unwrap().pixels, alternating);

        // A five-pixel ramp is not all-binary, and grayscale is the smaller of
        // the two streams here: the split overlay pays a byte per edge pixel on
        // top of its core.
        let ramp = [0u8, 64, 128, 192, 255];
        let grayscale = encode_grayscale(&ramp, 5).unwrap();
        assert!(grayscale.len() < encode_split(&ramp, 5).unwrap().len());
        let (tag, data) = encode(&ramp, 5, EncodeMode::Auto).unwrap().unwrap();
        assert_eq!(tag, TAG_GRAYSCALE);
        assert_eq!(decode(&data, 5, false).unwrap().pixels, ramp);
    }

    #[test]
    fn binary_stripes_round_trip_all_modes() {
        let pixels = mask(&[(0, 3), (255, 2), (0, 4), (255, 1)]);
        let data = encode_binary(&pixels, 10).unwrap();
        // first_value 0, run_count 4, then four plane lengths and the one plane
        // holding the three stored lengths.
        assert_eq!(
            data,
            vec![TAG_BINARY, 0x00, 0x04, 0x03, 0x00, 0x00, 0x00, 3, 2, 4]
        );
        for strict in [false, true] {
            assert_eq!(decode(&data, 10, strict).unwrap().pixels, pixels);
        }
        assert_eq!(runs(&pixels).len(), 4);
    }

    #[test]
    fn encode_rejects_a_mask_of_the_wrong_size() {
        assert_eq!(
            encode(&[0u8; 4], 5, EncodeMode::Auto).unwrap_err().check(),
            Check::ReeDataSize
        );
        assert_eq!(
            encode_binary(&[0u8; 4], 5).unwrap_err().check(),
            Check::ReeDataSize
        );
        assert_eq!(
            encode_grayscale(&[0u8; 4], 5).unwrap_err().check(),
            Check::ReeDataSize
        );
        assert_eq!(
            encode_split(&[0u8; 4], 5).unwrap_err().check(),
            Check::ReeDataSize
        );
    }

    #[test]
    fn binary_mode_refuses_a_non_binary_mask() {
        let pixels = [0u8, 7, 255, 0];
        assert_eq!(
            encode(&pixels, 4, EncodeMode::Binary).unwrap_err().check(),
            Check::ReeFirstValue
        );
        assert_eq!(
            encode_binary(&pixels, 4).unwrap_err().check(),
            Check::ReeFirstValue
        );
        // A non-binary first pixel is the same rule.
        assert_eq!(
            encode_binary(&[7u8, 0], 2).unwrap_err().check(),
            Check::ReeFirstValue
        );
    }

    /// A mask whose overlay pixels sit in all three places an attached stream can
    /// put one: the first pixel of a core run, the last pixel of one, and a pixel
    /// strictly inside a longer run, which only an escape can describe.
    fn attached_mask() -> Vec<u8> {
        mask(&[
            (0x00, 2), // core run 0: black, no overlay
            (0x80, 1), // core run 1 starts here: the run's first bit
            (0xFF, 2),
            (0x40, 1), // core run 2 is this one pixel: its first bit, not its last
            (0xFF, 2), //             (0x70, 1),   //  | core run 3: an escape inside it
            (0x90, 1), //  | and its last pixel
            (0x00, 2),
            (0x10, 1), // core run 4 ends on its last pixel
            (0x00, 1),
        ])
    }

    #[test]
    fn attached_round_trips_every_placement() {
        let pixels = attached_mask();
        let total = pixels.len() as u32;
        let (tag, data) = encode(&pixels, total, EncodeMode::Attached)
            .unwrap()
            .expect("a mask with overlay pixels has a stream");
        assert_eq!(tag, TAG_ATTACHED);
        assert_eq!(decode(&data, total, true).unwrap().pixels, pixels);
        assert_eq!(
            validate_stream(&data, total, true),
            Ok(data.len()),
            "the stream must use exactly its bytes"
        );
        // The run path is the same stream without ever building the mask.
        assert_eq!(
            encode_runs(&runs_of(&pixels), total, EncodeMode::Attached),
            Ok(Some((TAG_ATTACHED, data)))
        );
    }

    #[test]
    fn attached_pins_the_smallest_overlay_stream() {
        // [0x00, 0x80, 0x40, 0xFF]: four core runs of one pixel each, so the two
        // overlay pixels are each their run's first pixel; the stored lengths are
        // the first three runs, split by parity, with run 2's entry a difference
        // from run 0's.
        let data: Vec<u8> = vec![
            TAG_ATTACHED,
            0x00, // first_value
            0x04, // run_count
            0x02,
            0x00,
            0x00,
            0x00,
            0x01,
            0x00, // even lengths PLANES(2) = [1, 0]
            0x01,
            0x00,
            0x00,
            0x00,
            0x01, // odd lengths PLANES(1) = [1]
            0x02, // aa_pixel_count
            0x14, // attachment bits: run 1's first pixel, run 2's first pixel
            0x00, // escape_count
            0x00,
            0x00,
            0x00,
            0x00, // escapes PLANES(0)
            0x02,
            0x01,
            0x00,
            0x00,
            0x80,
            0x7F,
            0x01, // values PLANES(2)
        ];
        let pixels = vec![0x00, 0x80, 0x40, 0xFF];
        assert_eq!(decode(&data, 4, true).unwrap().pixels, pixels);
        assert_eq!(
            encode(&pixels, 4, EncodeMode::Attached).unwrap(),
            Some((TAG_ATTACHED, data.clone()))
        );
        assert_eq!(validate_stream(&data, 4, true), Ok(data.len()));
    }

    #[test]
    fn attached_accepts_an_all_binary_layer() {
        // No overlay pixels at all: the form degenerates to the parity-split,
        // self-delta coded core, and section 5.7 allows it for a binary layer.
        let pixels = mask(&[(0x00, 5), (0xFF, 7), (0x00, 3)]);
        let (tag, data) = encode(&pixels, 15, EncodeMode::Attached).unwrap().unwrap();
        assert_eq!(tag, TAG_ATTACHED);
        assert_eq!(
            decode(&data, 15, true).unwrap().pixels,
            pixels,
            "strict mode accepts it: unlike split, an empty overlay is not a defect here"
        );
        // And it is smaller than the plain binary stream once it is compressed is
        // not something this test can ask, but it must at least be decodable.
        assert_eq!(
            encode(&pixels, 15, EncodeMode::Binary).unwrap().unwrap().0,
            TAG_BINARY
        );
    }

    #[test]
    fn attached_rejects_broken_overlays() {
        // The smallest form above, with one field broken at a time.
        let base: Vec<u8> = vec![
            TAG_ATTACHED,
            0x00,
            0x04,
            0x02,
            0x00,
            0x00,
            0x00,
            0x01,
            0x00,
            0x01,
            0x00,
            0x00,
            0x00,
            0x01,
            0x02,
            0x14,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x02,
            0x01,
            0x00,
            0x00,
            0x80,
            0x7F,
            0x01,
        ];
        assert_eq!(
            decode(&base, 4, true).unwrap().pixels,
            vec![0, 0x80, 0x40, 0xFF]
        );

        // A run of one pixel that claims both of its ends: run 1 is one pixel, so
        // its two bits name the same pixel and the count carries it twice. Strict
        // refuses the shape; a loose read places the pixel twice and balances.
        let both_ends: Vec<u8> = vec![
            TAG_ATTACHED,
            0x00,
            0x04,
            0x02,
            0x00,
            0x00,
            0x00,
            0x01,
            0x00,
            0x01,
            0x00,
            0x00,
            0x00,
            0x01,
            0x03, // aa_pixel_count: run 1's two bits are two entries
            0x1c, // attachment bits: run 1's first and last pixel, run 2's first
            0x00,
            0x00,
            0x00,
            0x00,
            0x00, // no escapes
            0x03,
            0x01,
            0x00,
            0x00,
            0x80,
            0x7F,
            0x00, // three values
            0x01,
        ];
        assert_eq!(check_of(&both_ends, 4, true), Check::ReeAttachBits);
        assert_eq!(
            decode(&both_ends, 4, false).unwrap().pixels,
            vec![0x00, 0x40, 0x40, 0xFF],
            "the second bit's value is the one the pixel ends up with"
        );

        // An overlay value that is a binary value: the core would no longer be the
        // mask's thresholded form.
        let mut binary_value = base.clone();
        // Both stored values, because the second is a delta from the first.
        binary_value[25] = 0x00;
        binary_value[26] = 0x00;
        assert_eq!(check_of(&binary_value, 4, true), Check::ReeAttachThreshold);
        assert!(decode(&binary_value, 4, false).is_ok());

        // An overlay value on the wrong side of the threshold.
        let mut wrong_side = base.clone();
        wrong_side[25] = 0x40;
        assert_eq!(check_of(&wrong_side, 4, true), Check::ReeAttachThreshold);

        // An escape that sits on the first pixel of its run: a bit describes that
        // pixel, so it is not strictly inside the run.
        let mut not_inside = vec![
            TAG_ATTACHED,
            0x00,
            0x04,
            0x02,
            0x00,
            0x00,
            0x00,
            0x01,
            0x00,
            0x01,
            0x00,
            0x00,
            0x00,
            0x01,
            0x02,
            0x14,
            0x01, // one escape
            0x01,
            0x00,
            0x00,
            0x00,
            0x01, // at position 1, run 1's first pixel
            0x02,
            0x01,
            0x00,
            0x00,
            0x80,
            0x7F,
            0x01,
        ];
        assert_eq!(check_of(&not_inside, 4, false), Check::ReeAttachPositions);
        assert_eq!(check_of(&not_inside, 4, true), Check::ReeAttachPositions);

        // The same escape moved to a position past the layer is the other half of
        // the rule.
        not_inside[21] = 0x09; // 9, past total_pixels 4
        assert_eq!(check_of(&not_inside, 4, false), Check::ReeAttachPositions);

        // A count that disagrees with the bits and escapes: one more pixel than
        // the stream stores values for.
        let mut short_values = base.clone();
        short_values[14] = 0x03;
        assert_eq!(check_of(&short_values, 4, false), Check::ReeAttachCount);

        // One fewer: a value the walk never spends.
        let mut long_values = base.clone();
        long_values[14] = 0x01;
        assert_eq!(check_of(&long_values, 4, false), Check::ReeAttachCount);
    }

    #[test]
    fn attached_ignores_a_bit_on_an_empty_run() {
        // run_count 2 with one stored length of 3: run 1 is the implicit final run
        // and covers nothing, and its first bit claims a pixel that is not there.
        // A loose read steps into that run - a stored length of 0 is legal until a
        // strict reader refuses it - and reading its end must not be reading the
        // mask's last pixel plus one.
        let data: Vec<u8> = vec![
            TAG_ATTACHED,
            0x00,
            0x02, // first_value, run_count
            0x01,
            0x00,
            0x00,
            0x00,
            0x03, // even lengths PLANES(1) = [3]
            0x00,
            0x00,
            0x00,
            0x00, // odd lengths PLANES(0)
            0x01, // aa_pixel_count
            0x04, // run 1's first bit
            0x00, // escape_count
            0x00,
            0x00,
            0x00,
            0x00, // escapes PLANES(0)
            0x01,
            0x00,
            0x00,
            0x00,
            0x40, // values PLANES(1) = [0x40]
        ];
        // The bit places nothing, so the pixels the bits describe no longer match
        // the stream's own count - in either mode, because the count is checked
        // before the canonical rules that would refuse the empty run.
        assert_eq!(check_of(&data, 3, false), Check::ReeAttachCount);
        assert_eq!(check_of(&data, 3, true), Check::ReeAttachCount);
    }

    #[test]
    fn attached_padding_bits_are_strict_only() {
        // A one-run core: the attachment bits are one byte, and only its first two
        // bits address a run.
        let pixels = mask(&[(0xFF, 4)]);
        let (_, data) = encode(&pixels, 4, EncodeMode::Attached).unwrap().unwrap();
        let mut padded = data.clone();
        let last = padded.len() - 1 - 4 - 4 - 1; // the bits byte sits before escape_count
        padded[last] = 0x04;
        assert_eq!(check_of(&padded, 4, true), Check::ReeAttachBits);
        assert!(decode(&padded, 4, false).is_ok());
    }

    #[test]
    fn attached_run_count_zero_is_loose_only() {
        // first_value 0x00, run_count 0, no overlay: one black run over the whole
        // layer, as tag 0x00's non-canonical form reads. The fixed fields still
        // follow - two empty length arrays, a count, no bits, no escapes, no
        // values - because a stream's layout does not depend on its counts.
        let data: Vec<u8> = vec![
            TAG_ATTACHED,
            0x00,
            0x00, // first_value, run_count
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00, // both length arrays
            0x00, // aa_pixel_count
            0x00, // escape_count
            0x00,
            0x00,
            0x00,
            0x00, // escapes PLANES(0)
            0x00,
            0x00,
            0x00,
            0x00, // values PLANES(0)
        ];
        assert_eq!(decode(&data, 4, false).unwrap().pixels, vec![0u8; 4]);
        assert_eq!(check_of(&data, 4, true), Check::ReeNoRunCountZero);
    }

    #[test]
    fn unknown_or_missing_tags_are_rejected() {
        assert_eq!(check_of(&[], 4, false), Check::ReeTag);
        assert_eq!(check_of(&[0x04, 0x00], 4, false), Check::ReeTag);
        assert_eq!(check_of(&[0xFF, 0x00], 4, true), Check::ReeTag);
        assert_eq!(check_of(&[TAG_BINARY], 4, false), Check::ReeVarint);
        assert_eq!(check_of(&[TAG_GRAYSCALE], 4, false), Check::ReeVarint);
        assert_eq!(check_of(&[TAG_ATTACHED], 4, false), Check::ReeVarint);
        assert_eq!(
            check_of(&[TAG_SPLIT, TAG_BINARY, 0x01], 4, false),
            Check::ReeVarint
        );
    }

    #[test]
    fn binary_first_value_must_be_black_or_white() {
        assert_eq!(
            check_of(&[TAG_BINARY, 0x7F, 0x01], 4, false),
            Check::ReeFirstValue
        );
        assert_eq!(
            check_of(&[TAG_BINARY, 0x01, 0x01], 4, true),
            Check::ReeFirstValue
        );
    }

    #[test]
    fn run_count_zero_is_loose_only() {
        // Binary: first_value 0x00, run_count 0.
        let binary = [TAG_BINARY, 0x00, 0x00];
        assert_eq!(decode(&binary, 4, false).unwrap().pixels, vec![0u8; 4]);
        assert_eq!(check_of(&binary, 4, true), Check::ReeNoRunCountZero);
        // Accepted, and reported as using exactly the three bytes it holds.
        assert_eq!(validate_stream(&binary, 4, false), Ok(binary.len()));
        assert_eq!(
            validate_stream(&binary, 4, true).unwrap_err().check(),
            Check::ReeNoRunCountZero
        );

        // Grayscale: run_count 0.
        let grayscale = [TAG_GRAYSCALE, 0x00];
        assert_eq!(decode(&grayscale, 4, false).unwrap().pixels, vec![0u8; 4]);
        assert_eq!(check_of(&grayscale, 4, true), Check::ReeNoRunCountZero);

        // Encoders never emit it: an all-black layer has no stream at all.
        assert_eq!(encode(&[0u8; 4], 4, EncodeMode::Binary).unwrap(), None);
    }

    #[test]
    fn binary_run_lengths_split_loose_from_strict() {
        // first_value 0x00, run_count 3, stored lengths 0 and 2: the first run
        // is empty but still toggles the value.
        let empty_first = [TAG_BINARY, 0x00, 0x03, 0x02, 0x00, 0x00, 0x00, 0x00, 0x02];
        assert_eq!(
            decode(&empty_first, 4, false).unwrap().pixels,
            vec![255, 255, 0, 0]
        );
        assert_eq!(check_of(&empty_first, 4, true), Check::ReeRunLengths);

        // run_count 2 with one stored length of 4: the implicit final run is
        // empty, which loose accepts.
        let implicit_empty = [TAG_BINARY, 0x00, 0x02, 0x01, 0x00, 0x00, 0x00, 0x04];
        assert_eq!(
            decode(&implicit_empty, 4, false).unwrap().pixels,
            vec![0, 0, 0, 0]
        );
        assert_eq!(check_of(&implicit_empty, 4, true), Check::ReeRunLengths);

        // The stored lengths overshoot total_pixels, so the implicit final run
        // would be negative: both modes reject it.
        let overshoot = [TAG_BINARY, 0x00, 0x02, 0x01, 0x00, 0x00, 0x00, 0x05];
        assert_eq!(check_of(&overshoot, 4, false), Check::ReeEndPositions);
        assert_eq!(check_of(&overshoot, 4, true), Check::ReeEndPositions);

        // run_count above total_pixels + 1 is refused before anything is sized.
        let too_many = [TAG_BINARY, 0x00, 0x06];
        assert_eq!(check_of(&too_many, 4, false), Check::ReeRunLengths);
        assert_eq!(
            check_of(&[TAG_GRAYSCALE, 0x06], 4, false),
            Check::ReeRunLengths
        );

        // The canonical form is accepted by both modes.
        let canonical = [TAG_BINARY, 0x00, 0x02, 0x01, 0x00, 0x00, 0x00, 0x02];
        for strict in [false, true] {
            assert_eq!(
                decode(&canonical, 4, strict).unwrap().pixels,
                vec![0, 0, 255, 255]
            );
        }
    }

    #[test]
    fn grayscale_run_rules_split_loose_from_strict() {
        // Two adjacent runs with the same value. run_count 2, values 0x00 0x00,
        // one stored length of 2.
        let repeated = [
            TAG_GRAYSCALE,
            0x02,
            0x00,
            0x00,
            0x01,
            0x00,
            0x00,
            0x00,
            0x02,
        ];
        assert_eq!(
            decode(&repeated, 4, false).unwrap().pixels,
            vec![0, 0, 0, 0]
        );
        assert_eq!(check_of(&repeated, 4, true), Check::ReeGrayscaleRuns);

        // A zero-length first run: run_count 2, values 0x00 0x05, stored length
        // 0. Loose fills the second run over the whole layer.
        let empty_run = [
            TAG_GRAYSCALE,
            0x02,
            0x00,
            0x05,
            0x01,
            0x00,
            0x00,
            0x00,
            0x00,
        ];
        assert_eq!(
            decode(&empty_run, 4, false).unwrap().pixels,
            vec![5, 5, 5, 5]
        );
        assert_eq!(check_of(&empty_run, 4, true), Check::ReeGrayscaleRuns);

        // An implicit final run of zero length: the stored length is the whole
        // layer, so the last run would cover nothing.
        let implicit_empty = [
            TAG_GRAYSCALE,
            0x02,
            0x00,
            0x05,
            0x01,
            0x00,
            0x00,
            0x00,
            0x04,
        ];
        assert_eq!(
            decode(&implicit_empty, 4, false).unwrap().pixels,
            vec![0, 0, 0, 0]
        );
        assert_eq!(check_of(&implicit_empty, 4, true), Check::ReeGrayscaleRuns);

        // The stored lengths overshoot total_pixels, in both modes.
        let past = [
            TAG_GRAYSCALE,
            0x02,
            0x00,
            0x05,
            0x01,
            0x00,
            0x00,
            0x00,
            0x05,
        ];
        assert_eq!(check_of(&past, 4, false), Check::ReeEndPositions);
        assert_eq!(check_of(&past, 4, true), Check::ReeEndPositions);

        // Only 0x00/0xFF pixels: such a layer must use tag 0x00.
        let binary_values = [
            TAG_GRAYSCALE,
            0x02,
            0x00,
            0xFF,
            0x01,
            0x00,
            0x00,
            0x00,
            0x02,
        ];
        assert_eq!(
            decode(&binary_values, 4, false).unwrap().pixels,
            vec![0, 0, 255, 255]
        );
        assert_eq!(
            check_of(&binary_values, 4, true),
            Check::ReeGrayscaleAllBinary
        );

        // One run of black is a whole layer of 0x00, which is the tag 0x00
        // layer's business too.
        let one_run = [TAG_GRAYSCALE, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00];
        assert_eq!(decode(&one_run, 4, false).unwrap().pixels, vec![0u8; 4]);
        assert_eq!(check_of(&one_run, 4, true), Check::ReeGrayscaleAllBinary);

        // The corpus grayscale stream is canonical for both modes.
        assert_eq!(
            validate_stream(&bytes(LAYER_GRAYSCALE), TOTAL, true),
            Ok(LAYER_GRAYSCALE.len() / 2)
        );
    }

    /// A canonical split stream: binary 0x0000, 0xFF00, AA 200 at 4 and 5.
    const SPLIT_TOTAL: u32 = 8;
    const SPLIT_CANONICAL: [u8; 18] = [
        TAG_SPLIT, 0x00, 0x03, 0x02, 0x00, 0x00, 0x00, 0x04, 0x02, // core
        0x02, // aa_count
        0x02, 0x00, 0x00, 0x00, 0x04, 0x01, // positions
        0xC8, 0xC8, // values
    ];

    #[test]
    fn split_overlay_positions_are_delta_encoded() {
        let expected = [0, 0, 0, 0, 200, 200, 0, 0];
        for strict in [false, true] {
            assert_eq!(
                decode(&SPLIT_CANONICAL, SPLIT_TOTAL, strict)
                    .unwrap()
                    .pixels,
                expected
            );
        }
        assert_eq!(
            encode_split(&expected, SPLIT_TOTAL).unwrap(),
            SPLIT_CANONICAL
        );
        // The first position is absolute (4), the second a delta of 1.
        assert_eq!(&SPLIT_CANONICAL[14..16], &[0x04, 0x01]);
    }

    #[test]
    fn split_overlay_rules_are_enforced() {
        // A repeated position (delta 0) and a position at total_pixels are both
        // refused, in loose mode too.
        let repeated = [
            TAG_SPLIT, 0x00, 0x03, 0x02, 0x00, 0x00, 0x00, 0x04, 0x02, 0x02, 0x02, 0x00, 0x00,
            0x00, 0x04, 0x00, 0xC8, 0xC8,
        ];
        assert_eq!(
            check_of(&repeated, SPLIT_TOTAL, false),
            Check::ReeSplitPositions
        );
        assert_eq!(
            check_of(&repeated, SPLIT_TOTAL, true),
            Check::ReeSplitPositions
        );

        let out_of_range = [
            TAG_SPLIT, 0x00, 0x03, 0x02, 0x00, 0x00, 0x00, 0x04, 0x02, 0x02, 0x02, 0x00, 0x00,
            0x00, 0x08, 0x01, 0xC8, 0xC8,
        ];
        assert_eq!(
            check_of(&out_of_range, SPLIT_TOTAL, false),
            Check::ReeSplitPositions
        );

        // An overlay count above total_pixels + 1 is refused before allocating.
        // The core is one run, so it carries the four zero plane lengths.
        let too_many = [TAG_SPLIT, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x06];
        assert_eq!(check_of(&too_many, 4, false), Check::ReeSplitPositions);

        // A truncated value array: one position, no value byte.
        let short_values = [
            TAG_SPLIT, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x00, 0x04,
        ];
        assert_eq!(
            check_of(&short_values, SPLIT_TOTAL, false),
            Check::ReeVarint
        );

        // The overlay must hold exactly the pixels that are neither 0x00 nor
        // 0xFF, and must threshold to the binary component.
        let wrong_threshold = [
            TAG_SPLIT, 0x00, 0x03, 0x02, 0x00, 0x00, 0x00, 0x04, 0x02, 0x02, 0x02, 0x00, 0x00,
            0x00, 0x04, 0x01, 0x64, 0xC8,
        ];
        assert!(decode(&wrong_threshold, SPLIT_TOTAL, false).is_ok());
        assert_eq!(
            check_of(&wrong_threshold, SPLIT_TOTAL, true),
            Check::ReeSplitThreshold
        );

        let white_overlay = [
            TAG_SPLIT, 0x00, 0x03, 0x02, 0x00, 0x00, 0x00, 0x04, 0x02, 0x02, 0x02, 0x00, 0x00,
            0x00, 0x04, 0x01, 0xFF, 0xC8,
        ];
        assert_eq!(
            check_of(&white_overlay, SPLIT_TOTAL, true),
            Check::ReeSplitThreshold
        );

        // An empty overlay over a thresholded core: the slice is all-0x00/0xFF,
        // so section 5.7 requires tag 0x00 and a strict read refuses the split
        // form. A loose read accepts it, and it still round-trips: the encoder
        // writes what the caller asked for, as it does for a grayscale stream
        // over a binary mask.
        let no_overlay = [
            TAG_SPLIT, 0x00, 0x02, 0x01, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00,
        ];
        let expected = mask(&[(0, 4), (255, 4)]);
        assert_eq!(
            decode(&no_overlay, SPLIT_TOTAL, false).unwrap().pixels,
            expected
        );
        assert_eq!(
            check_of(&no_overlay, SPLIT_TOTAL, true),
            Check::ReeSplitAllBinary
        );
        assert_eq!(encode_split(&expected, SPLIT_TOTAL).unwrap(), no_overlay);

        // The binary component's own rules still apply.
        let non_canonical_core = [TAG_SPLIT, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00];
        assert_eq!(
            check_of(&non_canonical_core, SPLIT_TOTAL, true),
            Check::ReeNoRunCountZero
        );
        assert!(decode(&non_canonical_core, SPLIT_TOTAL, false).is_ok());
    }

    /// The planes of a length array, in significance order: the four plane
    /// lengths, then the plane bytes.
    fn planes(sizes: [u8; PLANES], bytes: &[u8]) -> Vec<u8> {
        let mut out = sizes.to_vec();
        out.extend_from_slice(bytes);
        out
    }

    #[test]
    fn varint_bytes_are_laid_out_in_significance_planes() {
        // Lengths 100 and 300: 300 is two bytes, so plane 0 holds both low bytes
        // and plane 1 the single high byte. Interleaved they would be
        // `64 00 01 01`-ish; grouped, the noisy plane stays on its own.
        let pixels = mask(&[(0, 100), (255, 300), (0, 3)]);
        let data = encode_binary(&pixels, 403).unwrap();
        let mut expected = vec![TAG_BINARY, 0x00, 0x03];
        expected.extend(planes([2, 1, 0, 0], &[100, 0xAC, 0x02]));
        assert_eq!(data, expected);
        assert_eq!(decode(&data, 403, true).unwrap().pixels, pixels);

        // A varint whose high byte is zero in a later plane is the same value:
        // 128 is `80 01`, so plane 0 holds `80` and plane 1 `01`.
        let wide = mask(&[(0, 128), (255, 128)]);
        let data = encode_binary(&wide, 256).unwrap();
        let mut expected = vec![TAG_BINARY, 0x00, 0x02];
        expected.extend(planes([1, 1, 0, 0], &[0x80, 0x01]));
        assert_eq!(data, expected);
        assert_eq!(decode(&data, 256, true).unwrap().pixels, wide);
    }

    #[test]
    fn planes_must_be_prefix_closed_and_exactly_used() {
        // Prefix-closure: plane 3 holds a byte while planes 0..2 are empty. A
        // single-run stream stores no lengths, so nothing is read from them.
        let not_prefix_closed = [TAG_BINARY, 0x00, 0x01, 0x00, 0x00, 0x00, 0x02, 0x80, 0x01];
        assert!(decode(&not_prefix_closed, 4, false).is_ok());
        assert_eq!(
            check_of(&not_prefix_closed, 4, true),
            Check::ReePlanes,
            "a non-empty plane may not follow an empty one"
        );

        // Leftover plane bytes: two runs store one length, so plane 0's second
        // byte describes no varint.
        let leftover = [TAG_BINARY, 0x00, 0x02, 0x02, 0x00, 0x00, 0x00, 0x02, 0x02];
        assert_eq!(
            decode(&leftover, 4, false).unwrap().pixels,
            vec![0, 0, 255, 255]
        );
        assert_eq!(check_of(&leftover, 4, true), Check::ReePlanes);

        // A varint that continues past plane 3 has nowhere to go.
        let too_many_planes = [
            TAG_BINARY, 0x00, 0x02, 0x01, 0x01, 0x01, 0x01, 0x80, 0x80, 0x80, 0x80,
        ];
        assert_eq!(check_of(&too_many_planes, 4, false), Check::ReeVarint);

        // A varint crossing planes must still be minimally encoded: `80 00` is
        // the overlong form of 0.
        let overlong = [TAG_BINARY, 0x00, 0x02, 0x01, 0x01, 0x00, 0x00, 0x80, 0x00];
        assert_eq!(check_of(&overlong, 4, false), Check::ReeVarint);

        // Fewer varints than the count needs: two runs want one length, but the
        // planes hold none.
        let short = [TAG_BINARY, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00];
        assert_eq!(check_of(&short, 4, false), Check::ReeVarint);

        // A plane length that claims more bytes than the stream holds is a
        // truncated stream.
        let truncated = [TAG_BINARY, 0x00, 0x02, 0x04, 0x00, 0x00, 0x00];
        assert_eq!(check_of(&truncated, 4, false), Check::ReeVarint);
    }

    #[test]
    fn a_length_needing_a_fifth_plane_is_refused() {
        // 2^28 is the first length whose varint is five bytes, and the format has
        // four planes: the encoder reports it rather than writing a varint whose
        // top byte is missing. The run list never materializes the mask.
        let total = (1u64 << 28) + 1;
        let runs = [Run::new(1 << 28, 0), Run::new(1, 255)];
        assert_eq!(
            encode_runs(&runs, total as u32, EncodeMode::Binary)
                .unwrap_err()
                .check(),
            Check::ReePlanes
        );
        assert_eq!(
            encode_runs(&runs, total as u32, EncodeMode::Grayscale)
                .unwrap_err()
                .check(),
            Check::ReePlanes
        );

        // One below the boundary is a four-byte varint: plane 3 holds its top
        // byte and the stream round-trips without building the mask.
        let fits = [Run::new((1 << 28) - 1, 255), Run::new(1, 0)];
        let (_, data) = encode_runs(&fits, 1 << 28, EncodeMode::Binary)
            .unwrap()
            .unwrap();
        assert_eq!(data.len(), 2 + 1 + 4 + 4, "four plane bytes, one per plane");
        assert_eq!(&data[7..11], &[0xFF, 0xFF, 0xFF, 0x7F]);
    }

    #[test]
    fn a_single_run_stream_carries_the_four_plane_lengths() {
        // A run_count == 1 stream stores no length, and carries the header anyway:
        // a reader that returned before reading it would leave four bytes behind
        // and `ree.no_trailing_bytes` would fire on a canonical stream.
        let one_run = [TAG_BINARY, 0xFF, 0x01, 0x00, 0x00, 0x00, 0x00];
        assert_eq!(validate_stream(&one_run, 7, true), Ok(one_run.len()));
        for strict in [false, true] {
            assert_eq!(decode(&one_run, 7, strict).unwrap().pixels, vec![255u8; 7]);
        }

        // The same stream without the header is short of its structure, not a run
        // of seven pixels: the four lengths are not optional.
        let headerless = [TAG_BINARY, 0xFF, 0x01];
        assert_eq!(check_of(&headerless, 7, false), Check::ReeVarint);

        // Grayscale reads its values first, then the header: one run of 0x80.
        let grayscale = [TAG_GRAYSCALE, 0x01, 0x80, 0x00, 0x00, 0x00, 0x00];
        assert_eq!(validate_stream(&grayscale, 7, true), Ok(grayscale.len()));
        assert_eq!(decode(&grayscale, 7, true).unwrap().pixels, vec![0x80u8; 7]);
        assert_eq!(
            check_of(&[TAG_GRAYSCALE, 0x01, 0x80], 7, false),
            Check::ReeVarint
        );

        // A split whose core is a single run and whose overlay is not empty: the
        // core's header is what lines the overlay count up behind it, and the
        // whole stream is consumed in strict mode too.
        let split = [
            TAG_SPLIT, 0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, // core: one run of 0xFF
            0x07, // aa_count
            0x07, 0x00, 0x00, 0x00, // positions: plane 0 holds seven bytes
            0x00, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, // deltas
            0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, // values
        ];
        assert_eq!(validate_stream(&split, 7, true), Ok(split.len()));
        assert_eq!(decode(&split, 7, true).unwrap().pixels, vec![0x80u8; 7]);

        // The same core with an empty overlay is the shape a strict read refuses
        // (section 5.7's tag choice), but a loose read still consumes both four
        // zero plane headers rather than leaving them behind.
        let split = [
            TAG_SPLIT, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        ];
        assert_eq!(validate_stream(&split, 7, false), Ok(split.len()));
        assert_eq!(decode(&split, 7, false).unwrap().pixels, vec![0u8; 7]);
        assert_eq!(check_of(&split, 7, true), Check::ReeSplitAllBinary);
    }

    #[test]
    fn a_split_over_an_all_binary_mask_is_strict_only() {
        // Section 5.7's tag choice, enforced for tag 0x02 as it is for tag 0x01:
        // an all-0x00/0xFF slice has no anti-aliasing to overlay, so a strict
        // read refuses the split form and a loose read accepts it. The stream is
        // the canonical shape of an empty overlay: PLANES(0) for its positions.
        let empty_overlay = [
            TAG_SPLIT, 0x00, 0x02, 0x01, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00,
        ];
        let expected = mask(&[(0, 4), (255, 4)]);
        assert_eq!(
            decode(&empty_overlay, SPLIT_TOTAL, false).unwrap().pixels,
            expected
        );
        assert_eq!(
            check_of(&empty_overlay, SPLIT_TOTAL, true),
            Check::ReeSplitAllBinary
        );
        assert_eq!(
            validate_stream(&empty_overlay, SPLIT_TOTAL, true)
                .unwrap_err()
                .check(),
            Check::ReeSplitAllBinary
        );

        // The same layer under tag 0x00 is what the rule asks for, and it is
        // accepted by both modes.
        let binary = encode_binary(&expected, SPLIT_TOTAL).unwrap();
        assert_eq!(
            validate_stream(&binary, SPLIT_TOTAL, true),
            Ok(binary.len())
        );

        // A grayscale stream over the same mask reports its own check, so the two
        // rules stay distinguishable.
        let grayscale = encode_grayscale(&expected, SPLIT_TOTAL).unwrap();
        assert_eq!(
            check_of(&grayscale, SPLIT_TOTAL, true),
            Check::ReeGrayscaleAllBinary
        );

        // The rule is about the decoded pixels, so an overlay that changes
        // nothing does not evade it: this one writes 0x00 over a 0xFF core, which
        // the threshold rule refuses first.
        let zero_overlay = [
            TAG_SPLIT, 0x00, 0x02, 0x01, 0x00, 0x00, 0x00,
            0x04, // core, one stored length of 4
            0x01, // aa_count
            0x01, 0x00, 0x00, 0x00, 0x04, // one position: 4
            0x00, // the value it carries
        ];
        assert_eq!(
            check_of(&zero_overlay, SPLIT_TOTAL, true),
            Check::ReeSplitThreshold
        );
    }

    #[test]
    fn validate_stream_matches_decode() {
        assert_eq!(
            validate_stream(&bytes(LAYER_BINARY), TOTAL, true),
            Ok(LAYER_BINARY.len() / 2)
        );
        assert_eq!(
            validate_stream(&bytes(LAYER_SPLIT), TOTAL, true),
            Ok(LAYER_SPLIT.len() / 2)
        );
        assert_eq!(
            validate_stream(&[], TOTAL, false),
            Err(Error::new(
                Check::ReeTag,
                "layer mask data is empty: the empty-layer form carries no bytes"
            ))
        );
    }

    /// Which pixels a set of ranges covers.
    fn covered(ranges: &[(u64, u64)], total: usize) -> Vec<bool> {
        let mut pixels = vec![false; total];
        for &(start, end) in ranges {
            for pixel in &mut pixels[start as usize..end as usize] {
                *pixel = true;
            }
        }
        pixels
    }

    /// Every mask of `total` pixels over an alphabet that spans the threshold,
    /// the two binary ends and a pair that merges under it.
    fn every_small_mask(total: usize, mut f: impl FnMut(&[u8])) {
        const ALPHABET: [u8; 5] = [0x00, 0x01, 0x7F, 0x80, 0xFF];
        let mut pixels = vec![0u8; total];
        for index in 0..ALPHABET.len().pow(total as u32) {
            let mut rest = index;
            for pixel in pixels.iter_mut() {
                *pixel = ALPHABET[rest % ALPHABET.len()];
                rest /= ALPHABET.len();
            }
            f(&pixels);
        }
    }

    #[test]
    fn the_exposed_walk_matches_the_mask_it_decodes_to() {
        let mut compared = 0usize;
        for total in 1usize..=5 {
            every_small_mask(total, |pixels| {
                for mode in MODES {
                    let Ok(Some((_, data))) = encode(pixels, total as u32, mode) else {
                        continue;
                    };
                    // The tag a caller asks for is not always the canonical one
                    // for the mask - a grayscale stream over a binary mask is
                    // legal, and a strict read refuses it - so the walk and the
                    // decoder are compared either way, and the pixels are
                    // compared where either of them has pixels to show.
                    let decoded = decode(&data, total as u32, true);
                    let mut ranges: Vec<(u64, u64)> = Vec::new();
                    let walked = exposed_ranges(&data, total as u32, |start, end| {
                        ranges.push((start, end));
                        Ok(())
                    });
                    match (decoded, walked) {
                        (Ok(mask), Ok(())) => {
                            // A split stream reports its core's runs and then its
                            // overlay, so the ranges are a union and not a
                            // partition.
                            assert_eq!(
                                covered(&ranges, total),
                                mask.pixels.iter().map(|p| *p != 0).collect::<Vec<_>>(),
                                "{pixels:?} as {mode:?}"
                            );
                        }
                        (Err(decoded), Err(walked)) => {
                            assert_eq!(decoded.check(), walked.check(), "{pixels:?} as {mode:?}")
                        }
                        (decoded, walked) => {
                            panic!("{pixels:?} as {mode:?}: {decoded:?} but {walked:?}")
                        }
                    }
                    compared += 1;
                }
            });
        }

        // The walk is only ever asked about a slice a strict read has already
        // passed, and its verdicts are that read's: a stream it refuses is one
        // `decode` refuses, and the other way round.
        for hex in [LAYER_BINARY, LAYER_GRAYSCALE, LAYER_SPLIT] {
            let data = bytes(hex);
            for at in 0..data.len() {
                for byte in [0x00, 0x01, 0x7F, 0x80, 0xFF, 0x02] {
                    for stream in [data[..at].to_vec(), {
                        let mut changed = data.clone();
                        changed[at] = byte;
                        changed
                    }] {
                        let decoded = decode(&stream, TOTAL, true).is_ok();
                        let walked = exposed_ranges(&stream, TOTAL, |_, _| Ok(())).is_ok();
                        assert_eq!(
                            decoded, walked,
                            "{hex} with byte {at} set to 0x{byte:02X}: decoded {decoded}, \
                             walked {walked}"
                        );
                        compared += 1;
                    }
                }
            }
        }
        println!("{compared} streams compared");
    }

    #[test]
    fn run_path_encodes_the_corpus_masks_byte_for_byte() {
        for (hex, spec, tag, chosen) in corpus_cases() {
            let pixels = mask(&spec);
            let runs = run_list(&spec);
            assert_eq!(
                encode_runs(&runs, TOTAL, chosen).unwrap(),
                Some((tag, bytes(hex))),
                "the corpus stream is what the run path must produce"
            );
            for mode in MODES {
                assert_run_path_matches(&pixels, &runs, TOTAL, mode);
            }
        }
    }

    /// A 1920 x 1080 mask whose white block carries a 64-pixel anti-aliased ramp
    /// on each side: a rasterizer's output, with the split overlay at its busiest.
    fn large_mask() -> Vec<u8> {
        const W: usize = 1920;
        const H: usize = 1080;
        const MARGIN: usize = 480;
        const RAMP: usize = 64;
        let mut pixels = vec![0u8; W * H];
        for row in 0..H {
            let line = &mut pixels[row * W..(row + 1) * W];
            for offset in 0..RAMP {
                line[MARGIN + offset] = (offset * 4) as u8;
                line[W - MARGIN - RAMP + offset] = 255 - (offset * 4) as u8;
            }
            line[MARGIN + RAMP..W - MARGIN - RAMP].fill(255);
        }
        pixels
    }

    #[test]
    fn run_path_matches_the_pixel_path_on_a_large_anti_aliased_mask() {
        let pixels = large_mask();
        let runs = runs_of(&pixels);
        let total = pixels.len() as u32;
        assert_eq!(total, 1920 * 1080);
        assert!(
            pixels.iter().any(|pixel| *pixel != 0x00 && *pixel != 0xFF),
            "the mask must exercise the split overlay"
        );
        for mode in MODES {
            assert_run_path_matches(&pixels, &runs, total, mode);
        }
    }

    #[test]
    fn run_path_matches_the_pixel_path_over_every_small_mask() {
        // Every five-pixel mask over an alphabet that spans both sides of the
        // 128 threshold, the two binary values, and a pair that merges under it.
        // Small enough to exhaust, and dense enough that the odd cases -
        // anti-aliasing at position 0, a single run, an all-black layer, a tie
        // between split and grayscale - all appear.
        const ALPHABET: [u8; 5] = [0x00, 0x01, 0x7F, 0x80, 0xFF];
        let mut pixels = [0u8; 5];
        let mut counter = 0usize;
        while counter < ALPHABET.len().pow(pixels.len() as u32) {
            let mut rest = counter;
            for pixel in &mut pixels {
                *pixel = ALPHABET[rest % ALPHABET.len()];
                rest /= ALPHABET.len();
            }
            counter += 1;
            let runs = runs_of(&pixels);
            for mode in MODES {
                assert_run_path_matches(&pixels, &runs, 5, mode);
            }
        }
    }

    #[test]
    fn split_core_merges_runs_that_threshold_alike() {
        // Adjacent runs of 90 and 100 both threshold to 0x00, so the binary core
        // holds one run for the three pixels and the overlay keeps each pixel's
        // own value - which is what the pixel path does.
        let pixels = [90u8, 100, 90, 255, 255];
        let runs = runs_of(&pixels);
        assert_eq!(runs.len(), 4, "the mask's own runs do not merge");
        assert_eq!(runs[0], Run::new(1, 90));
        assert_eq!(runs[1], Run::new(1, 100));
        assert_run_path_matches(&pixels, &runs, 5, EncodeMode::Split);
        // The core is `first_value 0x00`, two runs, and one stored length of 3
        // in plane 0 behind the four plane lengths.
        let (tag, data) = encode_runs(&runs, 5, EncodeMode::Split).unwrap().unwrap();
        assert_eq!(tag, TAG_SPLIT);
        assert_eq!(
            &data[..9],
            &[TAG_SPLIT, 0x00, 0x02, 0x01, 0x00, 0x00, 0x00, 0x03, 0x03]
        );
        assert_eq!(decode(&data, 5, true).unwrap().pixels, pixels);
    }

    #[test]
    fn run_path_rejects_non_canonical_runs() {
        // A run of length 0, at either end: a run covers at least one pixel.
        assert_eq!(
            encode_runs(&[Run::new(0, 0), Run::new(4, 255)], 4, EncodeMode::Auto)
                .unwrap_err()
                .check(),
            Check::ReeRunLengths
        );
        assert_eq!(
            encode_runs(
                &[Run::new(4, 255), Run::new(0, 0)],
                4,
                EncodeMode::Grayscale
            )
            .unwrap_err()
            .check(),
            Check::ReeRunLengths
        );

        // Adjacent runs carrying the same value are one run, in every mode.
        for mode in MODES {
            assert_eq!(
                encode_runs(&[Run::new(2, 0), Run::new(2, 0)], 4, mode)
                    .unwrap_err()
                    .check(),
                Check::ReeGrayscaleRuns,
                "mode {mode:?}"
            );
        }
        assert_eq!(
            encode_runs(
                &[Run::new(1, 200), Run::new(1, 200), Run::new(2, 0)],
                4,
                EncodeMode::Split
            )
            .unwrap_err()
            .check(),
            Check::ReeGrayscaleRuns
        );

        // A cover of the wrong size, in either direction, and no cover at all.
        for runs in [
            vec![Run::new(2, 0), Run::new(1, 255)],
            vec![Run::new(5, 255)],
            vec![],
        ] {
            assert_eq!(
                encode_runs(&runs, 4, EncodeMode::Auto).unwrap_err().check(),
                Check::ReeDataSize
            );
        }

        // A layer with no pixels, and an all-black cover, are both the
        // empty-layer form rather than an error.
        assert_eq!(encode_runs(&[], 0, EncodeMode::Auto).unwrap(), None);
        assert_eq!(
            encode_runs(&[Run::new(4, 0)], 4, EncodeMode::Auto).unwrap(),
            None
        );
        assert_eq!(
            encode_runs(&[Run::new(1, 0), Run::new(3, 0)], 4, EncodeMode::Auto)
                .unwrap_err()
                .check(),
            Check::ReeGrayscaleRuns
        );

        // Binary REE still refuses a value that is neither black nor white.
        assert_eq!(
            encode_runs(&[Run::new(1, 0), Run::new(3, 7)], 4, EncodeMode::Binary)
                .unwrap_err()
                .check(),
            Check::ReeFirstValue
        );
        assert_eq!(
            encode_runs(&[Run::new(4, 7)], 4, EncodeMode::Binary)
                .unwrap_err()
                .check(),
            Check::ReeFirstValue
        );
    }
}
