#!/bin/bash
# Build the unmodified DragonFruit CLI at the commit the resin bench measured.
# The source is cloned here and is not copied into ZEIM. ZEIM does not patch it.
set -euo pipefail

COMMIT=97596a55882cb139bbcf96bb98b211f82ae4c5f0
DEST=${1:-/tmp/zeim-dragonfruit}

if ! command -v git >/dev/null || ! command -v node >/dev/null || ! command -v cargo >/dev/null; then
  echo "git, node, and cargo are required" >&2
  exit 1
fi

mkdir -p "$DEST"
if [[ ! -d "$DEST/.git" ]]; then
  git init "$DEST"
  git -C "$DEST" remote add origin https://github.com/Open-Resin-Alliance/DragonFruit.git
fi
git -C "$DEST" fetch --depth 1 origin "$COMMIT"
git -C "$DEST" checkout --detach FETCH_HEAD
git -C "$DEST" submodule update --init --depth 1 --recursive
got=$(git -C "$DEST" rev-parse HEAD)
if [[ "$got" != "$COMMIT" ]]; then
  echo "DragonFruit HEAD is $got, expected $COMMIT" >&2
  exit 1
fi
node "$DEST/scripts/generate-plugin-registry.mjs"
cargo build --release --manifest-path "$DEST/rust/dragonfruit-cli/Cargo.toml" --bin dragonfruit-cli
echo "$DEST/rust/dragonfruit-cli/target/release/dragonfruit-cli"
