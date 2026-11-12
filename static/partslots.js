/* Filament colours shared by the slicer slots and the part colour editor.
   The sentences match app/core/partslots.py. */
export const DEFAULT_COLOURS = ["#FFFFFF", "#FF0000", "#00AA00", "#0066FF", "#FFD000", "#FF00AA", "#00DDDD", "#222222"];
export const UNIT_NOTE = "Multi-color needs a multi-material unit. Every part uses slot 1.";
export const PRINT_NOTE = "This print uses one colour until per-part printing ships.";
export const SINGLE_NOTE = "Single slot is on, and these parts use more than one slot. The slot choices stay as they are.";
const KEY = "zeim.slotColours";

function norm(value) {
  if (typeof value !== "string") return "";
  const h = value.trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(h)) return "";
  return h.toUpperCase();
}

export function readSavedColours() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "[]");
    if (!Array.isArray(raw)) return [];
    return raw.map(norm);
  } catch {
    return [];
  }
}

export function writeSavedColours(list) {
  const clean = (list || []).map(c => norm(c) || "");
  try { localStorage.setItem(KEY, JSON.stringify(clean)); } catch { /* private mode */ }
}

export function slotCount(printer) {
  const systems = printer?.multi_color_system || [];
  const n = +printer?.filament_slots || 1;
  if (n <= 1 || !systems.length) return 1;
  return n;
}

export function coloursForPrinter(printer) {
  const n = slotCount(printer);
  const saved = readSavedColours();
  const out = [];
  for (let i = 0; i < n; i++) out.push(saved[i] || DEFAULT_COLOURS[i % DEFAULT_COLOURS.length]);
  return out;
}

export function ink(hex) {
  const h = norm(hex) || "#FFFFFF";
  const n = parseInt(h.slice(1), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return (r * 0.299 + g * 0.587 + b * 0.114) > 150 ? "#1a1a1a" : "#f4f4f4";
}

export function appendSlotFields(fd, printer) {
  if (!fd || !printer) return;
  const id = printer.id || printer.printer_id || "";
  if (id && !fd.has("printer_id")) fd.append("printer_id", id);
  if (!fd.has("slot_colours")) fd.append("slot_colours", JSON.stringify(coloursForPrinter(printer)));
}

export async function printerForImport() {
  let cat = null, pref = null;
  try { cat = await (await fetch("/api/printers/catalog")).json(); } catch { /* keep the default */ }
  try {
    const me = await (await fetch("/api/me/printer")).json();
    if (me && me.signed_up && me.saved && me.printer_id) pref = { printer_id: me.printer_id };
  } catch { /* unsigned */ }
  if (!pref) {
    try { pref = JSON.parse(localStorage.getItem("zeim.printer") || "null"); } catch { pref = null; }
  }
  const id = pref?.printer_id || cat?.default?.printer_id || "creality_k1";
  return (cat?.printers || []).find(p => p.id === id) || { id, filament_slots: 1, multi_color_system: [] };
}
