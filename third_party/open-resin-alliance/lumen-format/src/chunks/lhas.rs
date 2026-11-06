//! The `LHAS` chunk: per-layer leaf hashes and a Merkle root
//! ([`spec/09-layer-data.md`] section 4.10).
//!
//! The tree is RFC 6962 style and domain separated: leaves hash `0x00 || data`,
//! internal nodes hash `0x01 || left || right`, and an odd node at any level is
//! promoted rather than duplicated.

use crate::check::Check;
use crate::error::{Error, Result};
use crate::io::{Reader, Writer};
use sha2::{Digest, Sha256};

/// The `LHAS` header: algorithm, hash size, layer count and root.
pub const LHAS_HEADER_LEN: usize = 38;
/// `hash_algorithm` for SHA-256.
pub const HASH_ALGORITHM_SHA256: u8 = 0x01;
/// `hash_size` for SHA-256.
pub const HASH_SIZE_SHA256: u8 = 32;

/// The `LHAS` chunk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LayerHashes {
    /// Hash algorithm. `0x01` is SHA-256.
    pub hash_algorithm: u8,
    /// Digest length. `32` for SHA-256.
    pub hash_size: u8,
    /// Layer count, which must equal `HEAD.total_layers`.
    pub layer_count: u32,
    /// Root of the Merkle tree over `layer_hashes`.
    pub merkle_root: [u8; 32],
    /// Leaf hashes, one per layer.
    pub layer_hashes: Vec<[u8; 32]>,
}

impl LayerHashes {
    /// Parse the chunk payload.
    pub fn parse(payload: &[u8]) -> Result<LayerHashes> {
        let mut r = Reader::checked(payload, Check::LhasFrame);
        let hash_algorithm = r.u8()?;
        let hash_size = r.u8()?;
        let layer_count = r.u32()?;
        let merkle_root = r.array::<32>()?;
        if hash_algorithm != HASH_ALGORITHM_SHA256 || hash_size != HASH_SIZE_SHA256 {
            return Err(Error::new(
                Check::LhasHashAlgorithm,
                format!(
                    "hash_algorithm {hash_algorithm:#04x} with hash_size {hash_size} is not SHA-256"
                ),
            ));
        }
        let table_len = (layer_count as usize)
            .checked_mul(HASH_SIZE_SHA256 as usize)
            .ok_or_else(|| Error::new(Check::LhasFrame, "the leaf table length overflows"))?;
        if table_len > r.remaining() {
            return Err(Error::new(
                Check::LhasFrame,
                format!(
                    "{layer_count} leaf hashes need {table_len} bytes, {} remain",
                    r.remaining()
                ),
            ));
        }
        let mut layer_hashes = Vec::with_capacity(layer_count as usize);
        for _ in 0..layer_count {
            layer_hashes.push(r.array::<32>()?);
        }
        Ok(LayerHashes {
            hash_algorithm,
            hash_size,
            layer_count,
            merkle_root,
            layer_hashes,
        })
    }

    /// Serialize the chunk payload.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut w = Writer::with_capacity(LHAS_HEADER_LEN + self.layer_hashes.len() * 32);
        w.u8(self.hash_algorithm);
        w.u8(self.hash_size);
        w.u32(self.layer_count);
        w.bytes(&self.merkle_root);
        for leaf in &self.layer_hashes {
            w.bytes(leaf);
        }
        w.into_vec()
    }
}

/// The leaf hash of one layer: `SHA-256(0x00 || data)`.
///
/// An empty layer hashes the single `0x00` prefix byte.
pub fn leaf_hash(data: &[u8]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update([0x00u8]);
    hasher.update(data);
    hasher.finalize().into()
}

/// An internal node: `SHA-256(0x01 || left || right)`.
fn internal_hash(left: &[u8; 32], right: &[u8; 32]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update([0x01u8]);
    hasher.update(left);
    hasher.update(right);
    hasher.finalize().into()
}

/// The empty internal-node hash, `SHA-256(0x01)`.
///
/// A conforming file always has `total_layers > 0`, so the zero-leaf root is
/// never stored; this value is chosen because it cannot be mistaken for the
/// digest of a real node's contents.
fn empty_internal_hash() -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update([0x01u8]);
    hasher.finalize().into()
}

/// The Merkle root over `leaves`, promoting odd nodes at each level.
pub fn merkle_root(leaves: &[[u8; 32]]) -> [u8; 32] {
    if leaves.is_empty() {
        return empty_internal_hash();
    }
    let mut level = leaves.to_vec();
    while level.len() > 1 {
        let mut next = Vec::with_capacity(level.len().div_ceil(2));
        let mut i = 0;
        while i + 1 < level.len() {
            next.push(internal_hash(&level[i], &level[i + 1]));
            i += 2;
        }
        if i < level.len() {
            // An odd node is promoted unchanged, never duplicated.
            next.push(level[i]);
        }
        level = next;
    }
    level.into_iter().next().unwrap_or_else(empty_internal_hash)
}

/// Whether level `n` leaves with `index` carries a sibling, mirroring the level
/// walk of [`merkle_path`].
fn sibling_flags(mut n: usize, mut index: usize) -> Vec<bool> {
    let mut flags = Vec::new();
    while n > 1 {
        flags.push(index % 2 == 1 || index + 1 < n);
        index >>= 1;
        n = n.div_ceil(2);
    }
    flags
}

/// The number of siblings on the path, without materializing the flags.
fn sibling_count(mut n: usize, mut index: usize) -> usize {
    let mut count = 0;
    while n > 1 {
        if index % 2 == 1 || index + 1 < n {
            count += 1;
        }
        index >>= 1;
        n = n.div_ceil(2);
    }
    count
}

/// Fold `leaf` along `flags`, consuming one sibling per set flag.
fn fold_flags(
    leaf: &[u8; 32],
    path: &[[u8; 32]],
    mut index: usize,
    flags: &[bool],
) -> Option<[u8; 32]> {
    let mut acc = *leaf;
    let mut used = 0;
    for &has_sibling in flags {
        if has_sibling {
            let sibling = path.get(used)?;
            acc = if index & 1 == 1 {
                internal_hash(sibling, &acc)
            } else {
                internal_hash(&acc, sibling)
            };
            used += 1;
        }
        index >>= 1;
    }
    Some(acc)
}

/// The sibling hashes on the path from `index` to the root.
///
/// At most `ceil(log2(layer_count))` of them, every one recoverable from the
/// leaf table, which is what makes single-layer verification bounded.
pub fn merkle_path(leaves: &[[u8; 32]], index: usize) -> Vec<[u8; 32]> {
    let mut path = Vec::new();
    if index >= leaves.len() {
        return path;
    }
    let mut level = leaves.to_vec();
    let mut i = index;
    while level.len() > 1 {
        if i % 2 == 1 {
            if let Some(left) = level.get(i - 1) {
                path.push(*left);
            }
        } else if let Some(right) = level.get(i + 1) {
            path.push(*right);
        }
        let mut next = Vec::with_capacity(level.len().div_ceil(2));
        let mut k = 0;
        while k + 1 < level.len() {
            next.push(internal_hash(&level[k], &level[k + 1]));
            k += 2;
        }
        if k < level.len() {
            next.push(level[k]);
        }
        level = next;
        i >>= 1;
    }
    path
}

/// Fold `leaf` up `path` and report whether the result is `root`.
pub fn verify_leaf(leaf: &[u8; 32], path: &[[u8; 32]], index: usize, root: &[u8; 32]) -> bool {
    // The common case: no level promoted this node, so every path element is a
    // sibling and the node's side is the running index's low bit.
    let mut acc = *leaf;
    let mut i = index;
    for sibling in path {
        acc = if i & 1 == 1 {
            internal_hash(sibling, &acc)
        } else {
            internal_hash(&acc, sibling)
        };
        i >>= 1;
    }
    if &acc == root {
        return true;
    }

    // A promotion leaves a hole in the path, so the fast fold cannot align it.
    // A promoted node was the last of an odd-sized level, which caps the tree at
    // `2*index + 2` leaves; the path length is monotone in the leaf count, so
    // find the smallest count that produces this path and fold with its levels.
    let target = path.len();
    let mut lo = index.saturating_add(1);
    let mut hi = index.saturating_mul(2).saturating_add(2);
    if sibling_count(lo, index) > target {
        return false;
    }
    while lo < hi {
        let mid = lo + (hi - lo) / 2;
        if sibling_count(mid, index) < target {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    if sibling_count(lo, index) != target {
        return false;
    }
    fold_flags(leaf, path, index, &sibling_flags(lo, index)) == Some(*root)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// SHA-256 of the concatenation of `parts`, spelled out so the expected
    /// roots do not go through the code under test.
    fn sha(parts: &[&[u8]]) -> [u8; 32] {
        let mut hasher = Sha256::new();
        for part in parts {
            hasher.update(part);
        }
        hasher.finalize().into()
    }

    fn leaves(n: usize) -> Vec<[u8; 32]> {
        (0..n).map(|i| leaf_hash(&[i as u8; 4])).collect()
    }

    #[test]
    fn leaf_hash_prefixes_the_data_with_zero() {
        assert_eq!(leaf_hash(b"abc"), sha(&[&[0x00], b"abc"]));
        assert_eq!(leaf_hash(b""), sha(&[&[0x00]]));
        assert_ne!(leaf_hash(b"abc"), sha(&[b"abc"]));
    }

    #[test]
    fn merkle_root_handles_one_two_three_and_five_leaves() {
        let l = leaves(5);
        let node = |left: &[u8; 32], right: &[u8; 32]| sha(&[&[0x01], left, right]);

        assert_eq!(merkle_root(&l[..1]), l[0]);
        assert_eq!(merkle_root(&l[..2]), node(&l[0], &l[1]));

        // Three leaves: the third is promoted, never duplicated.
        let promoted = node(&l[0], &l[1]);
        assert_eq!(merkle_root(&l[..3]), node(&promoted, &l[2]));
        let duplicated = node(&promoted, &node(&l[2], &l[2]));
        assert_ne!(merkle_root(&l[..3]), duplicated);

        // Five leaves: 5 -> 3 -> 2 -> 1, promoting the third then the fifth.
        let top = node(&node(&l[0], &l[1]), &node(&l[2], &l[3]));
        assert_eq!(merkle_root(&l[..5]), node(&top, &l[4]));
    }

    #[test]
    fn merkle_path_verifies_every_leaf_including_promoted_ones() {
        let l = leaves(5);
        let root = merkle_root(&l);
        for (i, leaf) in l.iter().enumerate() {
            let path = merkle_path(&l, i);
            assert!(verify_leaf(leaf, &path, i, &root), "leaf {i} should verify");
            let mut flipped = *leaf;
            flipped[0] ^= 0x01;
            assert!(
                !verify_leaf(&flipped, &path, i, &root),
                "flipped leaf {i} must not verify"
            );
        }

        // A three-leaf tree promotes index 2.
        let l3 = leaves(3);
        let root3 = merkle_root(&l3);
        let path = merkle_path(&l3, 2);
        assert!(verify_leaf(&l3[2], &path, 2, &root3));
        assert!(merkle_path(&l3, 3).is_empty());
    }

    #[test]
    fn lhas_round_trips_and_rejects_bad_payloads() {
        let hashes = LayerHashes {
            hash_algorithm: HASH_ALGORITHM_SHA256,
            hash_size: HASH_SIZE_SHA256,
            layer_count: 3,
            merkle_root: [7u8; 32],
            layer_hashes: vec![[1u8; 32], [2u8; 32], [3u8; 32]],
        };
        let bytes = hashes.to_bytes();
        assert_eq!(bytes.len(), LHAS_HEADER_LEN + 3 * 32);
        assert_eq!(LayerHashes::parse(&bytes).unwrap(), hashes);

        assert_eq!(
            LayerHashes::parse(&bytes[..LHAS_HEADER_LEN - 1])
                .unwrap_err()
                .check(),
            Check::LhasFrame
        );

        let mut wrong_algorithm = bytes.clone();
        wrong_algorithm[0] = 2;
        assert_eq!(
            LayerHashes::parse(&wrong_algorithm).unwrap_err().check(),
            Check::LhasHashAlgorithm
        );

        let mut short = bytes.clone();
        short[2..6].copy_from_slice(&9u32.to_le_bytes());
        assert_eq!(
            LayerHashes::parse(&short).unwrap_err().check(),
            Check::LhasFrame
        );
    }
}
