# lumen-format

A reference implementation of the **LUMEN print file format**, version 1.0, in
Rust: encoder, decoder, and validator.

LUMEN is the Open Resin Alliance's resin (MSLA) print format. Its normative
specification lives beside this crate in the
[LumenFormat repository](https://github.com/Open-Resin-Alliance/LumenFormat),
under [`spec/`](https://github.com/Open-Resin-Alliance/LumenFormat/tree/main/spec),
with the conformance corpus under
[`test-vectors/`](https://github.com/Open-Resin-Alliance/LumenFormat/tree/main/test-vectors).

```toml
[dependencies]
lumen-format = "1.0"
```

The package is `lumen-format` and the library target is `lumen`, so code reads
`use lumen::…`.

## Why this crate exists

LUMEN has more than one consumer - the **DragonFruit** slicer writes it, the
**Odyssey** firmware prints it - and every divergence between their
implementations is a compatibility bug that only shows up on a printer. Three
readings of a specification are three chances to disagree about REE
canonicalization, dictionary-ID agreement, or the per-block AAD that binds a
sealed frame to its chunk and index. So the format has one implementation, and
each consumer is an adapter over it:

- DragonFruit maps its own settings into `META`/`PROF` and hands this crate
  layer masks.
- Odyssey implements its `PrintFile` trait over [`LumenFile`], whose
  [`layer`](reader::LumenFile::layer) is already the "give me layer *i*" call
  that trait wants.

What stays in the consumer is what is genuinely theirs: the mapping from their
own model into `META`, and hardware-side concerns the specification deliberately
excludes (calibration, firmware-side mirroring, §1.1).

## Reading

```no_run
use lumen::{reader::LumenFile, validate::Level};

let bytes = std::fs::read("print.lumen")?;
let file = LumenFile::open(&bytes, Level::Loose)?;

println!("{} layers of {}x{}", file.layer_count(),
         file.head().display_width_px, file.head().display_height_px);
let meta = file.meta();
println!("normal exposure {} ms", meta.timing.normal_exposure_ms.unwrap_or(0));

let layer = file.layer(0)?;            // decompresses one block, not the file
println!("{:?} {}", layer.tag, layer.pixels.len());

// Timing, with the bottom/transition blend and LROV overrides already applied.
let timing = file.timing_for(0, 0)?;
println!("layer 0: {} ms at PWM {}", timing.exposure_ms, timing.light_pwm);
# Ok::<(), lumen::Error>(())
```

`layer` decompresses only the block that holds the layer it was asked for, so a
firmware reader streams a 2,000-layer print through a bounded buffer instead of
materializing it. See [`LumenFile::block`] for the block-level interface and
[`LumenFile::verify_layer`] for bounded integrity verification.

**On size.** [`LumenFile`] borrows the container's bytes. Opening validates, which
walks the layer data once - one block at a time, per section 4.10's design note for
memory-constrained readers - and after that each [`LumenFile::layer`] call touches
only the block that holds it. The peak is therefore one block rather than the file.
Measured on a 7.3 MB print of eight 1 MB blocks (`tests/memory.rs`, which asserts
the bound because it is easy to lose and invisible in a small test): decompressing
one block peaks at 2.1 MB and a full validation at 2.2 MB, against 8.3 MB of
decompressed layer stream.

For a print too large to keep resident, memory-map it and hand over the slice:
because the directory sits at the end and `LTBL` carries per-layer ranges, only the
blocks a caller asks for are faulted in, and the pages the validation pass already
walked are evictable. Reading from an arbitrary `Read + Seek` source would need a
different API here; the format already permits it, so in that case the interface is
the limitation rather than the container.

Encrypted files are opened with a key, a password, or a recipient private key:

```no_run
# use lumen::reader::LumenFile;
# use lumen::validate::Level;
# let bytes: Vec<u8> = Vec::new();
let file = LumenFile::open_with_password(&bytes, Level::Loose, "hunter2")?;
# Ok::<(), lumen::Error>(())
```

## Writing

```no_run
use lumen::chunks::head::Head;
use lumen::json::Meta;
use lumen::writer::Encoder;
# let (head, meta): (Head, Meta) = todo!();
# let layers: Vec<Vec<u8>> = Vec::new();

let mut encoder = Encoder::new(head, meta);
encoder.set_layers_per_chunk(64);
encoder.set_zstd_level(6);
for mask in &layers {
    encoder.push_layer(mask)?;
}
let bytes = encoder.finish()?;
# Ok::<(), lumen::Error>(())
```

A layer's tag is the encoder's choice (§5.7). By default the writer encodes
each layer group both ways - with the tag `EncodeMode::Auto` picks and with
`EncodeMode::Attached` (tag `0x03`) - compresses both exactly as the file will
frame them, and keeps the smaller; `Encoder::set_tag_probe(false)` turns that
off, and `Encoder::push_layer_with_mode` states a tag instead of choosing one.
The comparison is what makes the attached encoding safe to have on by default:
on a print whose layers barely change its raw bytes are the smaller ones and its
compressed bytes are 23% larger, so an encoder that picked by byte count would
write the bigger file. A layer that arrives already encoded
(`push_encoded_layer`) carries one encoding, so it is stored as it is.

The encoder is deterministic: identical input and settings produce identical
bytes, which is what makes re-slicing a scene produce the same file and the same
`LHAS` hashes (§5.7). Framing each `LAYR` chunk and hashing each layer are
per-item passes, so `finish` runs them on worker threads - one per core unless
`Encoder::set_worker_threads` says otherwise - and that count is not one of the
settings: it moves the wall clock and not a byte. Encrypted output is of course
not deterministic - it draws a fresh session key, salts and nonces from the OS
CSPRNG, as §9.4 requires.

## Validating

```no_run
use lumen::validate::{validate, Level};

# let bytes: Vec<u8> = Vec::new();
validate(&bytes, Level::Strict)?;      // first failure, or Ok
# Ok::<(), lumen::Error>(())
```

A failure carries the check that failed, named exactly as the corpus names it:

```no_run
# use lumen::validate::{validate, Level};
# let bytes: Vec<u8> = Vec::new();
if let Err(error) = validate(&bytes, Level::Strict) {
    eprintln!("{}: {}", error.check_name(), error.detail());  // e.g. "ree.run_lengths: ..."
}
```

`Level::Loose` is for printing: structurally valid files are accepted, unknown
chunks and fields are skipped, and non-canonical encodings are tolerated.
`Level::Strict` is for verification tools: every check in §11 runs, including the
strict-only ones, and a loop count or host could be pinned by them. Validation
returns the **first** failure in the specification's own order, which is what the
corpus's `expected_failure` contract asserts.

## Conformance

The corpus in
[`test-vectors/`](https://github.com/Open-Resin-Alliance/LumenFormat/tree/main/test-vectors)
is the contract this crate is written against, and `tests/conformance.rs` checks
three separate claims:

1. **Validator agreement.** Every valid vector passes at both levels; every
   invalid vector fails the check its manifest entry names, *and fails it first*;
   the eight `strict_only` vectors pass a loose read and fail a strict one.
2. **Decoder agreement.** The golden values in `manifest.json` - chunk layout,
   the layer table, each `LAYR` chunk's frame and version, per-layer decompressed
   bytes, leaf hashes and Merkle root - are recomputed from this crate's own parse
   of the same files.
3. **Pipeline agreement.** The settings a conforming reader must resolve for a sample
   of `(layer, sector)` points - base values, the bottom and transition blend, the
   absent-field defaults, the `LROV` overrides that §4.5 requires a reader to apply -
   are compared against the manifest's `resolved_timing` for every valid vector. This
   crate did not write those expectations, so agreeing with them is evidence about the
   pipeline rather than a restatement of it.

The corpus itself is generated by `make_vectors` (in `rust/corpus-gen`) and checked
by `verify_vectors` (in `rust/corpus`), which share no code with each other and
depend on neither this crate nor one another - and `cross_check` points that second
one at files *this crate* wrote. Agreement between all three is evidence about the
specification, not self-consistency, and CI runs all of it on every change: the
generator reproducing the committed corpus byte for byte, the corpus under the
specification's own reader, this crate's output under that reader, this crate's suite
over the corpus, plus formatting, lints, the declared minimum Rust version, the
`wasm32` target and the packaging path a release takes.

`tests/roundtrip.rs` covers the other direction: files this crate writes
validate, decode back to the exact pixels that went in, verify their own
integrity tree, and round trip through password and machine-binding encryption.
`tests/memory.rs` measures what validating a file actually allocates, since
"one block at a time" is a claim that a small test cannot show.

The `make_test_file` example writes four sample files - a full-featured
single-sector print, the same without the optional integrity tree, the same sealed
with a password, and a two-resin print with per-layer settings. Appendix A of the
specification documents what is in each of them, with the numbers the command just
printed.

```sh
cargo test                                   # unit, conformance and round trip
cargo test --test conformance                # the corpus only
```

The conformance tests read the corpus from beside the specification, so they run
from a checkout of the repository. Unpacking the published `.crate` on its own and
running `cargo test` fails with that explanation rather than passing without
having checked anything — conformance is not a property a crate can assert about
itself in isolation.

## Scope

Implemented: the container (§3), every chunk type (§4), binary, grayscale and
split REE (§5), the zstd block and dictionary strategy (§6), the sector model
(§7), the layer timing pipeline (§8), authenticated encryption with Argon2id
password wrapping and X25519 machine binding (§9), and the checks of §11.

Deliberately not implemented, with reasons:

- **VOXL parsing.** A `VOXL` payload is opaque to LUMEN (§4.11) and is carried
  through byte for byte. A strict read checks only that it is recognizably VOXL.
- **Extension payloads.** `EXTD` is vendor-defined and copied through, never
  interpreted (§4.12). No extension is implemented, so any extension claiming
  `critical` is refused, as the specification requires.
- **Signatures.** `EXTD`/`SIGN` is optional in v1 and not part of this crate.

## Specification revision

Written against **LUMEN v1.0**, the published revision tagged
[`v1.0`](https://github.com/Open-Resin-Alliance/LumenFormat/releases/tag/v1.0) in the
[LumenFormat repository](https://github.com/Open-Resin-Alliance/LumenFormat), which is where
the text of that revision is fixed. A published revision is immutable (§10.3): a correction
ships as a new revision with its own number, and it is this crate's conformance test that
reports the difference, since the crate names a revision rather than tracking the working
tree. That is why the crate's version is the revision it was written against, 1.0.

The corpus is the shared contract. A file this crate writes is checked against the
specification's own encoder by its own validator, in both directions, and that agreement is
what "conforming" means here rather than any claim about this crate's internals.

## Requirements

Rust 1.85 or later, edition 2021. The floor is set by a transitive dependency of
the RustCrypto stack (`zeroize_derive`, which uses edition 2024) rather than by
anything this crate does, and CI runs the whole suite on 1.85 with the committed
lock to keep the claim honest.

Hosted targets build with no extra tooling. A `wasm32-unknown-unknown` build -
the DragonFruit webview target - needs `clang` on the build host, because the
zstd dependency compiles C; without it the failure is
`cc-rs: failed to find tool "clang"`, which is a toolchain gap rather than a
crate one. The `getrandom` `js` backend is selected for wasm32, since that
target has no other entropy source.

There is no `no_std` support: a print file is a bulk data format and the
block/dictionary machinery wants an allocator.

## License

MIT OR Apache-2.0, matching the specification's MIT license while remaining
usable by GPL-3.0 consumers such as Odyssey. See [LICENSE-MIT](LICENSE-MIT) and
[LICENSE-APACHE](LICENSE-APACHE).
