"""Identify a printer file by the bytes the engine wrote. This does not encode one.

GOO's 8-byte tag is the tag in Elegoo's published container and in mslicer's
`MAGIC_TAG` (`07 00 00 00 44 4C 50 00`), sitting immediately after the 4-byte
version. CTB v4 starts with little-endian `0x12FD0106` and mslicer's v5 with
`0x12FD0107`. Layer count for GOO is the big-endian u32 at offset 195310, the
same offset the MIT Elegoo plugin records as `GOO_LAYER_COUNT_OFFSET`.
"""
from __future__ import annotations

import struct

GOO_TAG = bytes([0x07, 0x00, 0x00, 0x00, 0x44, 0x4C, 0x50, 0x00])
GOO_LAYER_COUNT_OFFSET = 195_310
CTB_V4 = 0x12FD0106
CTB_V5 = 0x12FD0107


class FileIdError(ValueError):
    pass


def identify(data: bytes, fmt: str) -> dict:
    if fmt == "goo":
        if len(data) < GOO_LAYER_COUNT_OFFSET + 4 or data[4:12] != GOO_TAG:
            raise FileIdError("The file does not start like an Elegoo GOO container.")
        layers = struct.unpack_from(">I", data, GOO_LAYER_COUNT_OFFSET)[0]
        return {"magic": "GOO", "layers_in_file": int(layers)}
    if fmt == "ctb":
        if len(data) < 8:
            raise FileIdError("The CTB file is too small.")
        magic = struct.unpack_from("<I", data, 0)[0]
        if magic == CTB_V4:
            name = "CTB-v4"
        elif magic == CTB_V5:
            name = "CTB-v5"
        else:
            raise FileIdError(f"The file magic is 0x{magic:08X}, not a CTB v4 or v5 header.")
        return {"magic": name, "layers_in_file": None}
    if fmt == "nanodlp":
        # mslicer writes NanoDLP as a zip of layer PNGs. A .goo or .ctb that is a zip is still rejected above.
        if data[:2] != b"PK":
            raise FileIdError("mslicer's NanoDLP file is a zip of layer images. This file is not one.")
        return {"magic": "NanoDLP-zip", "layers_in_file": None}
    if data[:2] == b"PK":
        raise FileIdError("The slicer wrote a zip. That is not a .goo or .ctb printer file.")
    raise FileIdError(f"No identifier for .{fmt}.")
