/* Exit, Done, New build, and Return to Account outside CAD.
   Showcase publishing is never a side effect of these actions.
   The library URL is Account (studio-library.js). #showcase is the app home, not a publish. */
import { LIBRARY_URL } from "./studio-library.js";

export { LIBRARY_URL };
export const SHOWCASE_BROWSE = "#showcase";

const ACTIONS = ["exit", "done", "return-studio"];

export function isPublishUrl(url) {
  return /(?:^|[?&#])publish(?:=|&|#|$)/.test(String(url || ""));
}

export function leavePlan(action, state) {
  const fromStudio = !!(state && state.fromStudio);
  const libraryUrl = (state && state.libraryUrl) || LIBRARY_URL;
  const save = true;
  const publish = false;
  const clear = false;
  switch (action) {
    case "exit":
      return { action, publish, clear, save, navigate: true, url: fromStudio ? libraryUrl : SHOWCASE_BROWSE };
    case "done":
      return { action, publish, clear, save, navigate: fromStudio, url: fromStudio ? libraryUrl : null };
    case "return-studio":
      return { action, publish, clear, save, navigate: true, url: libraryUrl };
    default: {
      const unknown = action;
      return { action: unknown, publish: false, clear: false, save: false, navigate: false, url: null };
    }
  }
}

/* New build stays on the workspace. A stored draft can clear. Unsaved or not-yet-stored work asks first. */
export function newBuildPlan(state) {
  const dirty = !!(state && state.dirty);
  const saveOk = !!(state && state.saveOk);
  const unstored = !!(state && state.unstored);
  const confirmed = !!(state && state.confirmed);
  const base = { action: "new-build", publish: false, navigate: false, url: null, save: dirty };
  if (dirty && !saveOk && !confirmed) return { ...base, clear: false, ask: true, reason: "unsaved" };
  if (unstored && !confirmed) return { ...base, clear: false, ask: true, reason: "unstored" };
  return { ...base, clear: true, ask: false, reason: "ready" };
}

/* Back on FDM, CAD, and TorchC0.
   An empty bed leaves with no save and no clear.
   Dirty work asks: stay, save and leave, reset the bed, or abandon.
   None of these publish. A next URL is only the tab the person already chose. */
export const FDM_DONE = ["cad", "device", "account", "showcase"];
export const BED_LEAVE = ["stay", "save", "reset", "abandon"];
const BED_SECTIONS = ["slicer", "cad", "torchc0"];

function safeLeaveUrl(url) {
  const s = url ? String(url) : "";
  if (!s || isPublishUrl(s)) return "";
  return s;
}

function inertLeave(section) {
  return {
    action: "exit",
    section: section || "",
    publish: false,
    ask: false,
    choice: "",
    save: false,
    clear: false,
    reset: false,
    navigate: false,
    url: null,
    options: BED_LEAVE.slice(),
  };
}

export function bedLeavePlan(state) {
  const section = state && state.section ? String(state.section) : "";
  if (!BED_SECTIONS.includes(section)) return inertLeave(section);
  const dirty = !!(state && state.dirty);
  const choice = state && state.choice ? String(state.choice) : "";
  const dest = safeLeaveUrl(state && state.nextUrl) || safeLeaveUrl(state && state.fallbackUrl);
  const base = { action: "exit", section, publish: false, options: BED_LEAVE.slice() };
  if (!dirty) {
    return { ...base, ask: false, choice: "leave", save: false, clear: false, reset: false, navigate: !!dest, url: dest || null };
  }
  switch (choice) {
    case "stay":
      return { ...base, ask: false, choice, save: false, clear: false, reset: false, navigate: false, url: null };
    case "save":
      return { ...base, ask: false, choice, save: true, clear: true, reset: false, navigate: !!dest, url: dest || null };
    case "reset":
      return { ...base, ask: false, choice, save: false, clear: true, reset: true, navigate: false, url: null };
    case "abandon":
      return { ...base, ask: false, choice, save: false, clear: true, reset: false, navigate: !!dest, url: dest || null };
    default: {
      const unknown = choice;
      return { ...base, ask: true, choice: unknown, save: false, clear: false, reset: false, navigate: false, url: null };
    }
  }
}

export function fdmDonePlan() {
  return {
    action: "done",
    section: "slicer",
    publish: false,
    clear: false,
    save: false,
    navigate: false,
    url: null,
    sheet: true,
    destinations: FDM_DONE.slice(),
  };
}

export function plansNeverPublish(action, state) {
  if (ACTIONS.includes(action)) {
    const plan = leavePlan(action, state);
    return plan.publish === false && !isPublishUrl(plan.url);
  }
  if (action === "new-build") {
    const plan = newBuildPlan(state);
    return plan.publish === false && plan.navigate === false && !isPublishUrl(plan.url);
  }
  return false;
}
