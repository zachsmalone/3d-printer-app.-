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
        "commit": "",
        "version": "v0.10.1",
        "license": "GPL-3.0",
        "used": False,
        "role": "Resin slicer for .ctb, .goo, .nanodlp and .svg. Not linked or shipped. GPL-3.0 was not approved for ZEIM the way unmodified PrusaSlicer was.",
        "outputs": [".ctb", ".goo", ".nanodlp", ".svg"],
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
    "The layer file is .lumen from the Open Resin Alliance reference encoder. "
    "Elegoo plate sizes come from that alliance's MIT plugin and are not .goo or .ctb files. "
    "mslicer (GPL-3.0) is not included. REA 6.8.0 is a reverse-engineering tool, not a resin slicer, "
    "and it is not pointed at a proprietary slicer."
)


def public_sources() -> list[dict]:
    return [dict(row) for row in SOURCES]
