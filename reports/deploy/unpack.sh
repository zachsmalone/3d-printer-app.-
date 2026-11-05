#!/usr/bin/env bash
# Put a release tarball onto a deploy directory.
# tar extract over an existing folder keeps files the new release deleted, so static/ is
# replaced. .env on the server is kept. Other release files are copied over.
#
# Usage: unpack.sh <release.tar> [deploy_dir]
#   deploy_dir defaults to $DEPLOY_DIR or /opt/zeim
set -euo pipefail

ARCHIVE="${1:-}"
DEST="${2:-${DEPLOY_DIR:-/opt/zeim}}"
[ -n "$ARCHIVE" ] && [ -f "$ARCHIVE" ] || { echo "usage: $0 <release.tar> [deploy_dir]" >&2; exit 2; }
[ -d "$DEST" ] || { echo "no such deploy dir: $DEST" >&2; exit 1; }
case "$DEST" in
  /|"") echo "refusing to unpack onto $DEST" >&2; exit 1 ;;
esac

# Reject members that would write outside the stage directory.
tar -tf "$ARCHIVE" | while IFS= read -r name; do
  case "$name" in
    /*|..|../*|*/..|*/../*) echo "refusing unsafe path: $name" >&2; exit 1 ;;
  esac
done

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
tar -xf "$ARCHIVE" -C "$STAGE"

SRC="$STAGE"
if [ ! -d "$SRC/static" ]; then
  tops=()
  for d in "$SRC"/*/; do
    [ -d "$d" ] && tops+=("$d")
  done
  if [ "${#tops[@]}" -eq 1 ] && [ -d "${tops[0]}static" ]; then
    SRC="${tops[0]}"
  fi
fi
[ -d "$SRC/static" ] || { echo "archive has no static/ directory; live static/ was left as it is" >&2; exit 1; }

# Swap in the release static tree, then drop the old one. A failed copy does not empty the live tree.
rm -rf "$DEST/static.new"
cp -a "$SRC/static" "$DEST/static.new"
rm -rf "$DEST/static"
mv "$DEST/static.new" "$DEST/static"

shopt -s dotglob nullglob
for item in "$SRC"/*; do
  base="$(basename "$item")"
  case "$base" in
    static|.env) continue ;;
  esac
  cp -a "$item" "$DEST/"
done
