"""'Pause at this layer' for the G-code preview (written for ZEIM, no third-party code).

Layers are counted exactly like static/gcode-parse.js: a new layer starts on the first EXTRUDING move (E grows and X/Y
change) at a new Z, so the layer number the maker picked in the preview is the layer the pause lands on. The pause is
put at the START of that layer: before PrusaSlicer's ;LAYER_CHANGE block if there is one, else before the move that
lifted Z, else just before the first extrusion. The original file is never changed: a new file is written next to it."""
from __future__ import annotations

import re
from pathlib import Path

# command -> label shown to the maker. Only these can be inserted (no free text goes into G-code).
COMMANDS = {
    "M600": "M600 (Marlin filament change: unloads, waits for new filament)",
    "M601": "M601 (pause print: Prusa firmware and newer Marlin)",
    "M0": "M0 (Marlin stop and wait for a button press)",
    "PAUSE": "PAUSE (Klipper macro)",
    "M400 U1": "M400 U1 (Bambu Lab pause)",
}
_KLIPPER = ("creality_k1", "creality_k2", "creality_hi", "creality_ender3_v3_ke", "creality_ender3_v3_plus", "creality_cr10_se",
            "elegoo_neptune4", "voron_", "sovol_sv08", "qidi_", "artillery_sidewinder_x4", "flashforge_ad5x", "flashforge_adventurer_5m",
            "anycubic_kobra3", "anycubic_kobra_s1")
_MARLIN = ("creality_ender3_v3_se", "creality_ender5_s1", "sovol_sv06", "ankermake_m5", "snapmaker_")


def firmware_for(printer_id: str | None) -> dict:
    """Best guess from the printer id. 'unknown' means the maker must pick the command."""
    pid = (printer_id or "").lower()
    if pid == "creality_ender3_v3":
        pid = "creality_ender3_v3_ke"           # the CoreXZ V3 runs Klipper like the KE; the SE runs Marlin (exact match first)
    if pid.startswith(_KLIPPER) and not pid.startswith("creality_ender3_v3_se"):
        fw, cmd = "klipper", "PAUSE"
    elif pid.startswith("prusa_"):
        fw, cmd = "prusa", "M601"
    elif pid.startswith("bambu_"):
        fw, cmd = "bambu", "M400 U1"
    elif pid.startswith(_MARLIN):
        fw, cmd = "marlin", "M600"
    else:
        fw, cmd = "unknown", None
    return {"firmware": fw, "command": cmd, "commands": COMMANDS,
            "note": ("We couldn't tell which firmware this printer runs. Pick the pause command it understands." if cmd is None else
                     "Best guess from the printer model. Check your printer's manual if the pause doesn't trigger.")}


_NUM = re.compile(r"([A-Za-z])\s*([-+]?(?:\d+\.?\d*|\.\d+))")


class _Layers:
    """Same state machine as gcode-parse.js (G90/G91, M82/M83, G92, G20/21). feed(line) -> True when it starts a layer."""
    def __init__(self):
        self.x = self.y = self.z = self.e = 0.0; self.abs = True; self.absE = True; self.unit = 1.0; self.lz = None

    def feed(self, raw: str) -> bool:
        line = raw.split(";", 1)[0].strip()
        if not line:
            return False
        if line[0] in "Nn":
            line = re.sub(r"^[Nn]\d+\s*", "", line)
        line = line.split("*", 1)[0]
        m = re.match(r"([GgMm])(\d+)", line)
        if not m:
            return False
        code = m.group(1).upper() + str(int(m.group(2)))
        if code == "M82": self.absE = True; return False
        if code == "M83": self.absE = False; return False
        if code == "G90": self.abs = self.absE = True; return False
        if code == "G91": self.abs = self.absE = False; return False
        if code == "G20": self.unit = 25.4; return False
        if code == "G21": self.unit = 1.0; return False
        if code not in ("G0", "G1", "G2", "G3", "G92"):
            return False
        w = {k.upper(): float(v) for k, v in _NUM.findall(line[m.end():])}
        u = self.unit
        if code == "G92":
            if "E" in w: self.e = w["E"]
            for k in "XYZ":
                if k in w: setattr(self, k.lower(), w[k] * u)
            if not any(k in w for k in "XYZE"): self.x = self.y = self.z = self.e = 0.0
            return False
        nx = self.x if "X" not in w else (w["X"] * u if self.abs else self.x + w["X"] * u)
        ny = self.y if "Y" not in w else (w["Y"] * u if self.abs else self.y + w["Y"] * u)
        nz = self.z if "Z" not in w else (w["Z"] * u if self.abs else self.z + w["Z"] * u)
        de = 0.0
        if "E" in w:
            if self.absE: de = w["E"] - self.e; self.e = w["E"]
            else: de = w["E"]; self.e += w["E"]
        new = False
        if de > 1e-9 and (nx != self.x or ny != self.y) and (self.lz is None or abs(nz - self.lz) > 1e-4):
            self.lz = nz; new = True
        self.z_changed = nz != self.z
        self.extruded = de > 1e-9 and (nx != self.x or ny != self.y)
        self.x, self.y, self.z = nx, ny, nz
        return new


def pause_block(cmd: str, layer: int, z: float) -> str:
    return f"; ZEIM: pause inserted at the start of layer {layer} (Z {z:.2f} mm) with {cmd}\n{cmd}\n"


def insert_pauses(src: Path, dst: Path, layers: list[int], cmd: str) -> list[dict]:
    """Copy src to dst with `cmd` at the start of each 1-based layer in `layers`. Returns where each pause went."""
    if cmd not in COMMANDS:
        raise ValueError("unknown pause command")
    want = set(int(n) for n in layers if int(n) >= 1)
    st, n, done = _Layers(), 0, []
    held: list[str] = []          # lines since the previous layer started (candidates for the insertion point)
    mark = zmove = None           # index in `held` of the last ;LAYER_CHANGE / Z move
    with open(src, "r", encoding="utf-8", errors="surrogateescape", newline="") as f, \
         open(dst, "w", encoding="utf-8", errors="surrogateescape", newline="") as out:
        for line in f:
            if line.lstrip().startswith(";LAYER_CHANGE"):
                mark = len(held)
            started = st.feed(line)
            if started:
                n += 1
                if n in want:
                    at = mark if mark is not None else zmove if zmove is not None else len(held)
                    held.insert(at, pause_block(cmd, n, st.z)); done.append({"layer": n, "z": round(st.z, 3)})
                out.writelines(held); held = []; mark = zmove = None
                out.write(line)
                continue
            if getattr(st, "extruded", False):
                zmove = None if mark is None else zmove; st.extruded = False   # a Z hop inside the layer is not the layer start
            if getattr(st, "z_changed", False):
                if zmove is None:
                    zmove = len(held)
                st.z_changed = False
            held.append(line)
            if len(held) > 200_000:   # pathological layer: never hold more than this in memory
                out.writelines(held); held = []; mark = zmove = None
        out.writelines(held)
    return done
