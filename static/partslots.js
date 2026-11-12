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

/* Saved add-on on this printer. No unit_id means the catalog default (a listed unit, or none). */
export function choiceFor(printer, pref) {
  const units = printer?.multi_material_units || [];
  const explicit = pref && Object.prototype.hasOwnProperty.call(pref, "unit_id");
  const saved = explicit ? pref.unit_id : undefined;
  let unit = null;
  if (saved === "none" || saved === "") unit = null;
  else if (saved) unit = units.find(u => u.id === saved) || null;
  else unit = units.find(u => u.default) || null;
  if (!unit) return { unit: null, count: 1, slots: 1, systems: [] };
  const max = +unit.max_units || 1;
  const count = Math.min(max, Math.max(1, +pref?.unit_count || 1));
  return { unit, count, slots: Math.min(16, (+unit.slots_per_unit || 1) * count), systems: [unit.name] };
}

/* Catalog row with filament_slots and multi_color_system set from the saved add-on. */
export function effectivePrinter(printer, pref) {
  if (!printer || !(printer.multi_material_units || []).length) return printer;
  const choice = choiceFor(printer, pref && pref.printer_id && pref.printer_id !== printer.id ? {} : pref);
  return {
    ...printer,
    filament_slots: choice.slots,
    multi_color_system: choice.systems,
    unit_id: choice.unit ? choice.unit.id : "none",
    unit_count: choice.count,
  };
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
  if (printer.unit_id != null && !fd.has("unit_id")) fd.append("unit_id", printer.unit_id);
  if (printer.unit_count != null && !fd.has("unit_count")) fd.append("unit_count", String(printer.unit_count));
}

export async function printerForImport() {
  let cat = null, pref = null;
  try { cat = await (await fetch("/api/printers/catalog")).json(); } catch { /* keep the default */ }
  try {
    const me = await (await fetch("/api/me/printer")).json();
    if (me && me.signed_up && me.saved && me.printer_id) {
      pref = { printer_id: me.printer_id, nozzle: me.nozzle };
      if (me.unit_id != null) { pref.unit_id = me.unit_id; pref.unit_count = me.unit_count || 1; }
    }
  } catch { /* unsigned */ }
  if (!pref) {
    try { pref = JSON.parse(localStorage.getItem("zeim.printer") || "null"); } catch { pref = null; }
  }
  const id = pref?.printer_id || cat?.default?.printer_id || "creality_k1";
  const row = (cat?.printers || []).find(p => p.id === id) || { id, filament_slots: 1, multi_color_system: [] };
  return effectivePrinter(row, pref && pref.printer_id === id ? pref : {}) || row;
}
