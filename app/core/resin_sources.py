"""Where TorchC0's resin layer file comes from, and what was left out.

Inspected 2026-11-06. This is a record of the three requested sources. It is not
legal advice and it is not a claim that the slice matches another slicer.
"""
from __future__ import annotations

# Pinned from the commits and package metadata actually read for this change.
SOURCES = (
    {
        "id": "lumen-format",
        "project": "Open-Resin-Alliance/LumenFormat",
        "url": "https://github.com/Open-Resin-Alliance/LumenFormat",
        "commit": "4f25f7bcf77c487447e28b8918eb8017e986cc78",
        "version": "1.0.0",
        "license": "MIT OR Apache-2.0",
        "used": True,
        "role": "Writes and reads the .lumen v1 container. Vendored unmodified.",
        "outputs": [".lumen"],
    },
    {
        "id": "df-plugin-elegoo",
        "project": "Open-Resin-Alliance/df-plugin-elegoo",
        "url": "https://github.com/Open-Resin-Alliance/df-plugin-elegoo",
        "commit": "be59b1597ac5f5551ddbdae97145f584f05be056",
        "version": "",
        "license": "MIT",
        "used": True,
        "role": "Plate width, height, pixel pitch and Z only. The GOO/CTB encoder in that plugin is not compiled.",
        "outputs": [],
    },
    {
        "id": "mslicer",
        "project": "connorslade/mslicer",
        "url": "https://github.com/connorslade/mslicer",
        "commit": "2d639519eedf4269a341fb6d5508901e06d99d48",
        "version": "v0.10.1",
        "license": "GPL-3.0",
        "used": True,
        "role": (
            "Separate GPL-3.0 program. Source is vendored at third_party/mslicer (v0.10.1 plus the "
            "--ctb flag and the slab-sample fix in ZEIM-CHANGES.md). ZEIM execs the slicer binary and "
            "does not copy that code into app/. Shipping the binary is not a claim that process "
            "separation removes GPL-3.0 obligations for that program. Corresponding source is the vendored tree."
        ),
        "outputs": [".goo", ".ctb", ".nanodlp"],
    },
    {
        "id": "dragonfruit",
        "project": "Open-Resin-Alliance/DragonFruit",
        "url": "https://github.com/Open-Resin-Alliance/DragonFruit",
        "commit": "",
        "version": "",
        "license": "AGPL-3.0-or-later",
        "used": False,
        "role": "Resin slicer and support tools. The slicing engine is not linked. Plugins under plugins/ are MIT and were reviewed separately.",
        "outputs": [],
    },
    {
        "id": "rea",
        "project": "morluto/rea",
        "url": "https://github.com/morluto/rea",
        "commit": "a7574d4274728fcb0a13414d6ae43f1597864d94",
        "version": "6.8.0",
        "license": "MIT",
        "used": False,
        "role": (
            "Reverse-engineering CLI and MCP (npm rea-agents). It inspects binaries, JavaScript, Android, "
            "firmware and other artifacts. It does not rasterise a mesh or write a resin layer file. "
            "rea inspect-artifact on a .lumen file returns unsupported binary format. "
            "It is not run on Lychee, CHITUBOX, or other proprietary slicers. Its own disclaimer refuses "
            "DRM circumvention and copying protected code and assets. Optional engines it can call "
            "(GDB GPL-3.0, Unicorn GPL-2.0, Frida LGPL-2.0) are not bundled."
        ),
        "outputs": [],
    },
)

SOURCES_NOTE = (
    "Open Resin .lumen uses the MIT/Apache reference encoder. "
    ".ctb and .nanodlp are written by the separate unmodified DragonFruit program (AGPL-3.0-or-later). "
    ".goo is written by the separate mslicer program (GPL-3.0), whose source is shipped beside it. "
    "A plate's stock extension has to match the file. CTB v2 is not written. "
    "REA is a reverse-engineering tool, not a resin slicer, and it is not pointed at a proprietary program."
)


def public_sources() -> list[dict]:
    return [dict(row) for row in SOURCES]
