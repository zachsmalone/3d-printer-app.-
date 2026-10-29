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

/* FDM Back clears the bed after a confirm. It does not publish and does not open Showcase.
   A next URL is only the tab the person already chose. Done lists destinations and stays. */
export const FDM_DONE = ["cad", "device", "account", "showcase"];

export function fdmLeavePlan(state) {
  const confirmed = !!(state && state.confirmed);
  const next = state && state.nextUrl ? String(state.nextUrl) : "";
  return {
    action: "exit",
    section: "slicer",
    publish: false,
    clear: confirmed,
    save: true,
    ask: !confirmed,
    navigate: confirmed && !!next,
    url: confirmed && next ? next : null,
  };
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
