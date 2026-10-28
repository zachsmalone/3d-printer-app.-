/* Beads and rings drawn over the model. Dragging calls the host's existing step. */
import {
  commitFor, dragAmount, handleName, keyAmount, layoutHandles, overlapsChrome, readout, ringSamples,
} from "/static/gizmo-math.js";

const CHROME = ".wsbar, .objdock, .proc-sheet, .zws-p, .cw-top, .cw-chips, .cw-cubewrap, .cw-bl, .cw-panel, .cw-section, .cw-hint, .cw-lesson, .cw-ctx, .vtools, #editVtools";

function shown(el) {
  if (!el || el.hidden || el.closest("[hidden]")) return false;
  const s = getComputedStyle(el);
  return s.display !== "none" && s.visibility !== "hidden" && el.getClientRects().length > 0;
}

export function chromeRects() {
  return [...document.querySelectorAll(CHROME)].filter(shown).map(el => el.getBoundingClientRect());
}

export function createGizmo(host, hooks) {
  const root = document.createElement("div");
  root.className = "zg";
  root.dataset.owner = hooks.owner || "";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("aria-hidden", "true");
  root.append(svg);
  const read = document.createElement("div");
  read.className = "zg-read";
  read.setAttribute("role", "status");
  read.hidden = true;
  root.append(read);
  host.append(root);

  let raf = 0, alive = true, drag = null, buttons = [];

  function localOf(ev) {
    const r = host.getBoundingClientRect();
    return { x: ev.clientX - r.left, y: ev.clientY - r.top };
  }
  function blocked(x, y) {
    const r = host.getBoundingClientRect();
    return overlapsChrome(x + r.left, y + r.top, hooks.chromeRects ? hooks.chromeRects() : chromeRects(), 8);
  }
  function hideRead() { read.hidden = true; read.textContent = ""; }

  function paint() {
    const frame = hooks.frame ? hooks.frame() : null;
    root.hidden = !frame;
    if (!frame) { hideRead(); return; }
    const handles = layoutHandles(frame);
    const w = host.clientWidth || 1, h = host.clientHeight || 1;
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    const sig = frame.surface + ":" + frame.mode + ":" + handles.map(h => h.axis).join(",");
    if (!drag && root.dataset.sig !== sig) { root.dataset.sig = sig; build(frame, handles); }
    const center = hooks.project(frame.center);
    const parts = [];
    buttons.forEach(btn => {
      const handle = handles.find(h => h.axis === btn.dataset.axis);
      if (!handle) return;
      btn._at = handle.at; btn._dir = handle.dir; btn._reach = handle.reach;
      const p = hooks.project(handle.at);
      const off = !p || p.behind || blocked(p.x, p.y);
      btn.hidden = drag ? btn !== drag.btn : off;
      if (off || !p) return;
      btn.style.left = p.x + "px";
      btn.style.top = p.y + "px";
      if (drag) return;
      if (frame.mode === "rotate" && handle.axis === handles[0].axis) {
        const ring = ringSamples(frame.center, handle.dir, handle.reach).map(hooks.project).filter(q => q && !q.behind);
        if (ring.length > 8) parts.push(poly(ring));
      } else if (frame.mode !== "rotate" && handle.axis !== "u" && center && !center.behind) {
        parts.push(line(center, p));
      }
    });
    svg.innerHTML = parts.join("");
  }

  function line(a, b) {
    const at = `x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"`;
    return `<line class="zg-halo" ${at} /><line ${at} />`;
  }
  function poly(pts) {
    const d = pts.map(p => p.x + "," + p.y).join(" ") + " " + pts[0].x + "," + pts[0].y;
    return `<polyline class="zg-halo" points="${d}" /><polyline points="${d}" />`;
  }

  function build(frame, handles) {
    buttons.forEach(b => b.remove());
    buttons = handles.map(handle => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "zg-handle" + (frame.mode === "rotate" ? " zg-turn" : frame.mode === "scale" ? (handle.axis === "u" ? " zg-all" : " zg-size") : "");
      btn.dataset.axis = handle.axis;
      btn.textContent = handle.axis === "u" ? "All" : handle.axis.toUpperCase();
      btn.setAttribute("aria-label", handleName(frame.mode, handle.axis));
      btn.addEventListener("pointerdown", ev => onDown(ev, btn));
      btn.addEventListener("pointermove", onMove);
      btn.addEventListener("pointerup", onUp);
      btn.addEventListener("pointercancel", onUp);
      btn.addEventListener("keydown", onKey);
      root.append(btn);
      return btn;
    });
  }

  function liveAmount(ev) {
    const here = localOf(ev);
    const start = drag.local;
    if (drag.mode === "rotate") {
      const c = hooks.project(drag.center);
      const ang = c ? (Math.atan2(here.y - c.y, here.x - c.x) - Math.atan2(start.y - c.y, start.x - c.x)) * 180 / Math.PI : 0;
      let d = ang;
      while (d > 180) d -= 360;
      while (d < -180) d += 360;
      return dragAmount(drag.frame, drag.handle, 0, 0, drag.basis, ev.altKey, d, drag.screenPerDeg);
    }
    return dragAmount(drag.frame, drag.handle, here.x - start.x, here.y - start.y, drag.basis, ev.altKey, 0, 1);
  }

  function showRead(frame, axis, amount, x, y) {
    read.hidden = false;
    read.textContent = readout(frame.surface, frame.mode, axis, amount, frame.box);
    let left = x + 28, top = y - 28;
    if (blocked(left, top)) { left = x - 72; }
    if (blocked(left, top)) { top = y + 24; }
    read.style.left = left + "px";
    read.style.top = top + "px";
  }

  function onDown(ev, btn) {
    if (ev.button != null && ev.button > 0) return;
    const frame = hooks.frame();
    if (!frame) return;
    ev.preventDefault();
    ev.stopPropagation();
    try { btn.setPointerCapture(ev.pointerId); } catch { /* already captured */ }
    hooks.freeze?.();
    const handle = { dir: btn._dir, reach: btn._reach, at: btn._at, axis: btn.dataset.axis };
    const basis = hooks.basis(frame.center);
    let screenPerDeg = 1;
    if (frame.mode === "rotate") {
      const spun = ringSamples(frame.center, handle.dir, handle.reach, 360);
      const step = spun[1];
      const c = hooks.project(frame.center), s0 = hooks.project(handle.at), s1 = hooks.project(step);
      if (c && s0 && s1) {
        const a0 = Math.atan2(s0.y - c.y, s0.x - c.x) * 180 / Math.PI;
        const a1 = Math.atan2(s1.y - c.y, s1.x - c.x) * 180 / Math.PI;
        let d = a1 - a0;
        while (d > 180) d -= 360;
        while (d < -180) d += 360;
        screenPerDeg = d;
      }
    }
    drag = { id: ev.pointerId, btn, frame, handle, basis, screenPerDeg, local: localOf(ev), center: frame.center.slice(), mode: frame.mode };
    root.classList.add("zg-drag");
    btn.classList.add("zg-on");
  }

  function onMove(ev) {
    if (!drag || ev.pointerId !== drag.id) return;
    const amount = liveAmount(ev);
    hooks.preview?.(drag.frame, drag.handle.axis, amount);
    const here = localOf(ev);
    showRead(drag.frame, drag.handle.axis, amount, here.x, here.y);
  }

  function onUp(ev) {
    if (!drag || (ev && ev.pointerId != null && ev.pointerId !== drag.id)) return;
    const amount = ev ? liveAmount(ev) : 0;
    const spec = commitFor(drag.frame, drag.handle.axis, amount, !!(ev && ev.altKey));
    const finish = drag;
    drag = null;
    root.classList.remove("zg-drag");
    finish.btn.classList.remove("zg-on");
    hideRead();
    hooks.thaw?.();
    if (spec) hooks.apply?.(spec);
    else hooks.clearPreview?.();
    buttons.forEach(b => { b.hidden = false; });
  }

  function onKey(ev) {
    const frame = hooks.frame();
    if (!frame) return;
    const raw = keyAmount(frame.mode, ev.key, ev.shiftKey, ev.altKey);
    if (raw == null) return;
    ev.preventDefault();
    ev.stopPropagation();
    const spec = commitFor(frame, ev.currentTarget.dataset.axis, raw, ev.altKey);
    if (spec) hooks.apply?.(spec);
  }

  function loop() {
    if (!alive) return;
    raf = requestAnimationFrame(loop);
    try { paint(); } catch { /* a disposed viewer can throw for one frame */ }
  }
  raf = requestAnimationFrame(loop);

  return {
    destroy() {
      alive = false;
      cancelAnimationFrame(raf);
      if (drag) { hooks.thaw?.(); hooks.clearPreview?.(); drag = null; }
      root.remove();
    },
  };
}
