//! ZEIMCad - a Rust translation of SolveSpace, the parametric 2D/3D CAD.
//!
//! Provenance: this crate is a source-assisted translation of SolveSpace
//! (https://github.com/solvespace/solvespace), Copyright 2008-2013 Jonathan Westhues
//! and SolveSpace contributors, distributed under GPL-3.0-or-later. This translation
//! is therefore GPL-3.0-or-later. The ZEIM web application itself is not derived from
//! this code and is unaffected by this license.
//!
//! Translation notes:
//! - Naming follows the original (Vector::Plus, Quaternion::RotationU, ...) so that
//!   every function can be audited against its C++ counterpart.
//! - SolveSpace's `List<T>` / `IdList<T, H>` become `Vec<T>` / `BTreeMap`-backed
//!   stores in later modules; the templated memory management has no Rust equivalent.
//! - The hParam / SK-dependent constructors (Vector::From(hParam,...)) wait for the
//!   sketch/solver modules.

pub mod defs;
pub mod dsc;
pub mod util;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
