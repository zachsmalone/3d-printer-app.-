//! The `LTBL` chunk: the layer table
//! ([`spec/09-layer-data.md`] section 4.7).
//!
//! One 28-byte entry per (layer, sector), grouped by layer and ascending
//! `sector_id` within a layer, a layer's first entry being sector 0's. An entry
//! carries everything needed to reach one sector's mask without walking the
//! table: the `LAYR` chunk that holds the layer's run for that sector, the
//! offset and size of the layer's slice inside that chunk's decompressed output,
//! the `LROV` chunk holding the (layer, sector)'s overrides or `0`, and how many
//! further entries the same layer has.

use crate::check::Check;
use crate::error::{Error, Result};
use crate::io::{Reader, Writer};

/// The `LTBL` chunk header: `table_version`, `layer_count`, `entry_size`,
/// `entry_count`.
pub const LTBL_HEADER_LEN: usize = 16;
/// Bytes per entry in a v1 table.
pub const LTBL_ENTRY_SIZE_V1: u32 = 28;

/// One (layer, sector) of the layer table.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct LayerEntry {
    /// Bytes of this layer's data for this sector; `0` means none.
    pub data_size: u32,
    /// Directory index of this (layer, sector)'s `LROV` chunk; `0` means no
    /// overrides. Index 0 is `HEAD`, so `0` is a safe null.
    pub first_lrov: u32,
    /// Directory index of the `LAYR` chunk holding this sector's run.
    pub first_layr: u32,
    /// Further entries for this layer, ascending `sector_id`; non-zero only on
    /// the layer's first entry.
    pub additional_sector_count: u32,
    /// Offset of this layer's slice inside `first_layr`'s decompressed output.
    pub data_offset: u64,
    /// This entry's sector. `0` is the primary sector.
    pub sector_id: u32,
}

impl LayerEntry {
    /// Whether this (layer, sector) carries no data.
    pub fn is_empty(&self) -> bool {
        self.data_size == 0
    }
}

/// The `LTBL` chunk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LayerTable {
    /// Layout version. `1` for this specification.
    pub table_version: u32,
    /// Layers the table describes, which must equal `HEAD.total_layers`.
    pub layer_count: u32,
    /// Bytes per entry; readers stride by this and skip unknown trailing fields.
    pub entry_size: u32,
    /// Entries in the table.
    pub entry_count: u32,
    /// Every entry, in table order.
    pub entries: Vec<LayerEntry>,
    /// Index of each layer's first entry, derived from `entries`.
    first: Vec<u32>,
}

impl LayerTable {
    /// Parse the chunk payload.
    pub fn parse(payload: &[u8]) -> Result<LayerTable> {
        let mut r = Reader::checked(payload, Check::LtblEntrySize);
        let table_version = r.u32()?;
        if table_version != 1 {
            return Err(Error::new(
                Check::LtblVersion,
                format!("unsupported table_version {table_version}"),
            ));
        }
        let layer_count = r.u32()?;
        let entry_size = r.u32()?;
        let entry_count = r.u32()?;
        if entry_size < LTBL_ENTRY_SIZE_V1 {
            return Err(Error::new(
                Check::LtblEntrySize,
                format!("entry_size {entry_size} is below the {LTBL_ENTRY_SIZE_V1} byte v1 layout"),
            ));
        }
        let table_len = (entry_count as usize)
            .checked_mul(entry_size as usize)
            .ok_or_else(|| Error::new(Check::LtblEntryCount, "the layer table length overflows"))?;
        // The declared count is what the chunk must hold and end at, so a payload
        // that is shorter or longer than `entry_count` entries is the count's
        // failure, not the entry layout's: `ltbl.entry_size` owns an entry_size
        // below the v1 layout, and nothing else.
        if table_len != r.remaining() {
            return Err(Error::new(
                Check::LtblEntryCount,
                format!(
                    "entry_count {entry_count} of {entry_size} bytes needs {table_len} bytes, {} remain",
                    r.remaining()
                ),
            ));
        }
        let mut entries = Vec::with_capacity(entry_count as usize);
        for _ in 0..entry_count {
            entries.push(LayerEntry {
                data_size: r.u32()?,
                first_lrov: r.u32()?,
                first_layr: r.u32()?,
                additional_sector_count: r.u32()?,
                data_offset: r.u64()?,
                sector_id: r.u32()?,
            });
            // Future versions may append fields; stride past them.
            r.skip(entry_size as usize - LTBL_ENTRY_SIZE_V1 as usize)?;
        }
        let first = layer_index(&entries, layer_count)?;
        Ok(LayerTable {
            table_version,
            layer_count,
            entry_size,
            entry_count,
            entries,
            first,
        })
    }

    /// Build a table over `entries`, which must account for `layer_count`
    /// layers exactly as [`LayerTable::parse`] requires of a file.
    pub fn new(entries: Vec<LayerEntry>, layer_count: u32) -> Result<LayerTable> {
        let first = layer_index(&entries, layer_count)?;
        Ok(LayerTable {
            table_version: 1,
            layer_count,
            entry_size: LTBL_ENTRY_SIZE_V1,
            entry_count: entries.len() as u32,
            entries,
            first,
        })
    }

    /// Serialize the chunk payload at the v1 entry size.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut w = Writer::with_capacity(
            LTBL_HEADER_LEN + self.entries.len() * LTBL_ENTRY_SIZE_V1 as usize,
        );
        w.u32(self.table_version);
        w.u32(self.layer_count);
        w.u32(LTBL_ENTRY_SIZE_V1);
        w.u32(self.entries.len() as u32);
        for entry in &self.entries {
            w.u32(entry.data_size);
            w.u32(entry.first_lrov);
            w.u32(entry.first_layr);
            w.u32(entry.additional_sector_count);
            w.u64(entry.data_offset);
            w.u32(entry.sector_id);
        }
        w.into_vec()
    }

    /// The entries of layer `layer`, its first entry included.
    ///
    /// Empty when the table describes no such layer.
    pub fn layer_entries(&self, layer: u32) -> &[LayerEntry] {
        let Some(&start) = self.first.get(layer as usize) else {
            return &[];
        };
        let start = start as usize;
        // The count was proven to fit the table when the index was built.
        let count = 1 + self.entries[start].additional_sector_count as usize;
        &self.entries[start..start + count]
    }

    /// The first entry of layer `layer`, which is sector 0's.
    pub fn first_entry(&self, layer: u32) -> Option<&LayerEntry> {
        self.layer_entries(layer).first()
    }

    /// The entry for `(layer, sector_id)`.
    pub fn entry(&self, layer: u32, sector_id: u32) -> Option<&LayerEntry> {
        self.layer_entries(layer)
            .iter()
            .find(|entry| entry.sector_id == sector_id)
    }

    /// Whether some layer carries more than one sector with data.
    ///
    /// A layer carries a sector when its entry for it holds bytes, so an entry
    /// that exists only to point at an `LROV` chunk does not make a file
    /// multi-sector. This is what the `MULTI_SECTOR` header flag asserts.
    pub fn is_multi_sector(&self) -> bool {
        (0..self.layer_count).any(|layer| {
            self.layer_entries(layer)
                .iter()
                .filter(|entry| !entry.is_empty())
                .count()
                > 1
        })
    }
}

/// The index of every layer's first entry, checking the accounting rules.
///
/// A layer's entries are `1 + additional_sector_count`, `additional_sector_count`
/// is non-zero only on a layer's first entry, and the walk must land exactly on
/// the end of the table.
fn layer_index(entries: &[LayerEntry], layer_count: u32) -> Result<Vec<u32>> {
    // Section 11 orders these rules, and the order decides which name a file
    // that breaks several of them is reported under: the accounting first, then
    // the walk over the layers, and only then the per-layer sector rules. So the
    // walk is completed before any layer's contents are judged.
    let mut first = Vec::with_capacity(layer_count as usize);
    let mut cursor = 0usize;
    for layer in 0..layer_count {
        if cursor >= entries.len() {
            return Err(Error::new(
                Check::LtblLayerIndexRange,
                format!(
                    "layer {layer} has no first entry: {} of the {layer_count} layers account \
                     for every one of the {} entries",
                    first.len(),
                    entries.len()
                ),
            ));
        }
        let count = 1 + entries[cursor].additional_sector_count as usize;
        if entries.len() - cursor < count {
            return Err(Error::new(
                Check::LtblEntryCount,
                format!(
                    "layer {layer} declares {count} entries, but only {} remain after {}",
                    entries.len() - cursor,
                    cursor
                ),
            ));
        }
        for (k, entry) in entries[cursor..cursor + count].iter().enumerate().skip(1) {
            if entry.additional_sector_count != 0 {
                return Err(Error::new(
                    Check::LtblEntryCount,
                    format!(
                        "layer {layer}'s entry {k} carries additional_sector_count {}, which only \
                         a layer's first entry may",
                        entry.additional_sector_count
                    ),
                ));
            }
        }
        first.push(cursor as u32);
        cursor += count;
    }
    if cursor != entries.len() {
        return Err(Error::new(
            Check::LtblEntryCount,
            format!(
                "{layer_count} layers account for {cursor} entries, but the table declares {}",
                entries.len()
            ),
        ));
    }

    // Within a layer, the sectors ascend and none repeats.
    for layer in 0..layer_count {
        let start = first[layer as usize] as usize;
        let count = 1 + entries[start].additional_sector_count as usize;
        for pair in entries[start..start + count].windows(2) {
            if pair[1].sector_id == pair[0].sector_id {
                return Err(Error::new(
                    Check::LtblSectorIdUnique,
                    format!("layer {layer} names sector {} twice", pair[1].sector_id),
                ));
            }
            if pair[1].sector_id < pair[0].sector_id {
                return Err(Error::new(
                    Check::LtblSectorIdsAscending,
                    format!(
                        "layer {layer} names sector {} after sector {}",
                        pair[1].sector_id, pair[0].sector_id
                    ),
                ));
            }
        }
    }

    // A layer's first entry is sector 0's.
    for layer in 0..layer_count {
        let start = first[layer as usize] as usize;
        if entries[start].sector_id != 0 {
            return Err(Error::new(
                Check::LtblFirstEntryIsSectorZero,
                format!(
                    "layer {layer}'s first entry names sector {}, not the primary sector 0",
                    entries[start].sector_id
                ),
            ));
        }
    }
    Ok(first)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The v1 decision for a (layer, sector): which chunk, which slice, which
    /// overrides, and how many further entries the layer has.
    fn entry(
        sector_id: u32,
        first_layr: u32,
        data_offset: u64,
        data_size: u32,
        additional: u32,
        first_lrov: u32,
    ) -> LayerEntry {
        LayerEntry {
            data_size,
            first_lrov,
            first_layr,
            additional_sector_count: additional,
            data_offset,
            sector_id,
        }
    }

    /// Two layers: layer 0 with two sectors, layer 1 with sector 0 only.
    fn table() -> LayerTable {
        LayerTable::new(
            vec![
                entry(0, 3, 0, 5, 1, 0),
                entry(1, 4, 0, 7, 0, 6),
                entry(0, 3, 5, 0, 0, 0),
            ],
            2,
        )
        .unwrap()
    }

    #[test]
    fn a_table_round_trips_and_indexes_its_layers() {
        let table = table();
        assert_eq!(table.table_version, 1);
        assert_eq!(table.layer_count, 2);
        assert_eq!(table.entry_size, 28);
        assert_eq!(table.entry_count, 3);
        assert_eq!(table.layer_entries(0).len(), 2);
        assert_eq!(table.layer_entries(1).len(), 1);
        assert_eq!(table.layer_entries(2).len(), 0, "no such layer");
        assert_eq!(table.first_entry(1).unwrap().data_size, 0);
        assert_eq!(table.entry(0, 1).unwrap().first_lrov, 6);
        assert_eq!(table.entry(0, 2), None);
        assert!(table.is_multi_sector(), "layer 0 carries two sectors");

        let bytes = table.to_bytes();
        assert_eq!(bytes.len(), LTBL_HEADER_LEN + 3 * 28);
        let parsed = LayerTable::parse(&bytes).unwrap();
        assert_eq!(parsed, table);
    }

    #[test]
    fn a_single_sector_file_is_not_multi_sector() {
        let table =
            LayerTable::new(vec![entry(0, 3, 0, 5, 0, 0), entry(0, 3, 5, 0, 0, 0)], 2).unwrap();
        assert!(!table.is_multi_sector());

        // A second entry that carries no data is not a second sector.
        let table =
            LayerTable::new(vec![entry(0, 3, 0, 5, 1, 0), entry(4, 4, 0, 0, 0, 7)], 1).unwrap();
        assert!(!table.is_multi_sector(), "sector 4 holds no bytes");
    }

    #[test]
    fn the_entry_accounting_is_enforced() {
        let rejects = |entries: Vec<LayerEntry>, layers: u32, check: Check| {
            assert_eq!(LayerTable::new(entries, layers).unwrap_err().check(), check);
        };

        // A layer that declares more entries than the table holds.
        rejects(vec![entry(0, 3, 0, 5, 1, 0)], 1, Check::LtblEntryCount);
        // A non-first entry carrying a count of its own.
        rejects(
            vec![entry(0, 3, 0, 5, 1, 0), entry(1, 4, 0, 7, 1, 0)],
            1,
            Check::LtblEntryCount,
        );
        // A table holding entries no layer accounts for.
        rejects(
            vec![entry(0, 3, 0, 5, 0, 0), entry(0, 3, 5, 1, 0, 0)],
            1,
            Check::LtblEntryCount,
        );
        // A layer with no entry at all: the walk runs out of table before it has
        // described every layer the header declares.
        rejects(vec![entry(0, 3, 0, 5, 0, 0)], 2, Check::LtblLayerIndexRange);
        // A layer whose first entry is not sector 0's.
        rejects(
            vec![entry(3, 3, 0, 5, 0, 0)],
            1,
            Check::LtblFirstEntryIsSectorZero,
        );
        // Sector ids that do not ascend within a layer.
        rejects(
            vec![
                entry(0, 3, 0, 5, 2, 0),
                entry(2, 3, 5, 1, 0, 0),
                entry(1, 3, 6, 1, 0, 0),
            ],
            1,
            Check::LtblSectorIdsAscending,
        );
        // The same sector named twice on one layer.
        rejects(
            vec![
                entry(0, 3, 0, 5, 2, 0),
                entry(1, 3, 5, 1, 0, 0),
                entry(1, 3, 6, 1, 0, 0),
            ],
            1,
            Check::LtblSectorIdUnique,
        );
    }

    #[test]
    fn a_table_whose_bytes_disagree_with_its_header_is_rejected() {
        let bytes = table().to_bytes();

        // Three entries declared, room for three, but the accounting then runs
        // out of table before the second layer's entry.
        let mut short = bytes.clone();
        short[12..16].copy_from_slice(&2u32.to_le_bytes());
        assert_eq!(
            LayerTable::parse(&short).unwrap_err().check(),
            Check::LtblEntryCount
        );

        // Nine entries declared: the payload does not hold them, which is the
        // declared count's failure rather than the entry layout's.
        let mut over = bytes.clone();
        over[12..16].copy_from_slice(&9u32.to_le_bytes());
        assert_eq!(
            LayerTable::parse(&over).unwrap_err().check(),
            Check::LtblEntryCount
        );

        // The table declares three entries; layer 0's first entry claims nine,
        // so the walk runs past the end.
        let mut long = bytes.clone();
        long[16 + 12..16 + 16].copy_from_slice(&9u32.to_le_bytes());
        assert_eq!(
            LayerTable::parse(&long).unwrap_err().check(),
            Check::LtblEntryCount
        );
    }

    #[test]
    fn a_bad_version_entry_size_or_stride_is_rejected() {
        let mut bytes = table().to_bytes();

        let mut version = bytes.clone();
        version[0..4].copy_from_slice(&2u32.to_le_bytes());
        assert_eq!(
            LayerTable::parse(&version).unwrap_err().check(),
            Check::LtblVersion
        );

        let mut small = bytes.clone();
        small[8..12].copy_from_slice(&27u32.to_le_bytes());
        assert_eq!(
            LayerTable::parse(&small).unwrap_err().check(),
            Check::LtblEntrySize
        );

        // entry_size is fine, but the chunk does not hold the declared entries.
        bytes[12..16].copy_from_slice(&9u32.to_le_bytes());
        assert_eq!(
            LayerTable::parse(&bytes).unwrap_err().check(),
            Check::LtblEntryCount
        );
    }

    #[test]
    fn a_wider_entry_strides_past_unknown_fields() {
        // Three 32-byte entries: the v1 28-byte layout plus four unknown bytes.
        let mut w = Writer::new();
        w.u32(1);
        w.u32(1);
        w.u32(32);
        w.u32(2);
        for (sector, offset, size, additional) in [(0u32, 0u64, 5u32, 1u32), (2, 5, 7, 0)] {
            w.u32(size);
            w.u32(0);
            w.u32(3);
            w.u32(additional);
            w.u64(offset);
            w.u32(sector);
            w.u32(0xDEAD_BEEF); // an unknown trailing field
        }
        let parsed = LayerTable::parse(&w.into_vec()).unwrap();
        assert_eq!(parsed.entry_size, 32);
        assert_eq!(parsed.layer_entries(0).len(), 2);
        assert_eq!(parsed.entry(0, 2).unwrap().data_offset, 5);
    }
}
