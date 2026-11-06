//! A reference implementation of the LUMEN print file format, version 1.0.
//!
//! LUMEN is the Open Resin Alliance's resin (MSLA) print format; the normative
//! specification lives beside this crate, in `spec/`. This crate is a consumer
//! of that text, not a substitute for it: where the specification and this code
//! disagree, the specification wins, and the conformance corpus under
//! `test-vectors/` is what settles the argument.
//!
//! # Shape
//!
//! - [`container`] - the file header, chunk directory and trailer.
//! - [`chunks`] - one codec per chunk type.
//! - [`json`] - the typed `META`, `PROF` and `LROV` models.
//! - [`ree`] - run-end encoded layer masks: binary, grayscale and split.
//! - [`timing`] - the per-layer settings pipeline of section 8.
//! - [`crypto`] - `AUTH`, the AEAD units, Argon2id and X25519 key wrapping.
//! - [`validate`] - the checks of section 11, named as the corpus names them.
//! - [`reader`] - [`reader::LumenFile`], including random access to one layer.
//! - [`writer`] - [`writer::Encoder`], which produces a conforming file.
//!
//! # Reading
//!
//! ```no_run
//! use lumen::{reader::LumenFile, validate::Level};
//!
//! let bytes = std::fs::read("print.lumen").unwrap();
//! let file = LumenFile::open(&bytes, Level::Loose).unwrap();
//! println!("{} layers", file.layer_count());
//! let layer = file.layer(0).unwrap();
//! println!("{:?}", layer.tag);
//! ```
//!
//! # Two tiers
//!
//! [`reader::LumenFile`] decodes what a caller asks for and nothing else: a
//! layer is fetched by index, which decompresses only the `LAYR` chunk that
//! holds it. A firmware reader can open the file, read `META` and the layer
//! table, and stream layers through a fixed-size buffer without ever
//! materializing the whole file. A slicer can instead use [`writer::Encoder`],
//! which trains the zstd dictionary, frames the chunks and assembles the
//! directory.

#![forbid(unsafe_code)]
#![warn(missing_docs)]

pub mod check;
mod chunkio;
pub mod chunks;
pub mod container;
pub mod crypto;
pub mod error;
pub mod io;
pub mod json;
pub mod reader;
pub mod ree;
pub mod timing;
pub mod validate;
pub mod varint;
pub mod writer;

pub use check::Check;
pub use container::{ChunkDescriptor, ChunkType, Directory, FileHeader};
pub use error::{Error, Result};
pub use json::{Material, Meta, Profile, Sector, Timing};
pub use reader::LumenFile;
pub use ree::{DecodedLayer, EncodeMode};
pub use validate::{Level, Validator};
pub use writer::Encoder;
