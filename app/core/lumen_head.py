"""Independent reader for the fixed LUMEN v1 header and HEAD chunk.

This does not use the lumen-format crate. It follows the layout in LumenFormat
spec parts 02 and 04 (32-byte file header, 32-byte directory entries, uncompressed
HEAD). It checks the magic and the fields a slicer must get right: plate size,
layer size and layer count. It does not decode layer masks.
"""
from __future__ import annotations

import struct


class LumenHeadError(ValueError):
    pass


def read_head(data: bytes) -> dict:
    if len(data) < 40 or data[:4] != b"LUMN":
        raise LumenHeadError("Not a LUMEN file: missing LUMN.")
    if data[-8:-4] != b"LEND":
        raise LumenHeadError("Not a LUMEN file: missing LEND.")
    if data[:2] == b"PK":
        raise LumenHeadError("This is a zip, not a LUMEN file.")
    version, dir_off, count, flags, _total = struct.unpack_from("<IQIIQ", data, 4)
    if version != 1:
        raise LumenHeadError(f"Unsupported LUMEN container version {version}.")
    if count < 1 or dir_off + count * 32 > len(data) - 8:
        raise LumenHeadError("LUMEN directory does not fit in the file.")
    head = None
    for i in range(count):
        at = dir_off + i * 32
        tag = data[at:at + 4]
        offset, size_u, size_c, _cflags = struct.unpack_from("<QQQI", data, at + 4)
        if tag != b"HEAD":
            continue
        stored = size_u if size_c == 0 else size_c
        if offset + stored > len(data):
            raise LumenHeadError("HEAD chunk extends past the file.")
        head = data[offset:offset + size_u if size_c == 0 else offset + stored]
        break
    if head is None:
        raise LumenHeadError("LUMEN file has no HEAD chunk.")
    if len(head) < 8:
        raise LumenHeadError("HEAD chunk is too short.")
    head_version, name_len = struct.unpack_from("<II", head, 0)
    if head_version != 1:
        raise LumenHeadError(f"Unsupported HEAD version {head_version}.")
    if 8 + name_len + 36 > len(head):
        raise LumenHeadError("HEAD name does not fit.")
    name = head[8:8 + name_len].decode("utf-8", "replace")
    rest = 8 + name_len
    created, width, height, bw, bd, bh, layer_um, layers = struct.unpack_from("<QIIIIIII", head, rest)
    return {
        "magic": "LUMN",
        "trailer": "LEND",
        "container_version": version,
        "flags": flags,
        "encrypted": bool(flags & (1 << 3)),
        "encoder_name": name,
        "created_unix_sec": created,
        "width": width,
        "height": height,
        "build_width_um": bw,
        "build_depth_um": bd,
        "build_height_um": bh,
        "layer_height_um": layer_um,
        "layers": layers,
    }
