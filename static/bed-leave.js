/* Four-way leave for FDM, CAD, and TorchC0. Stay is the safe default. */
export const BED_LEAVE_MESSAGE = "Stay keeps this workspace open. Save & leave stores the draft, then leaves. Reset bed takes the model off this bed so you can import a fresh one. You stay here, and work already on Account stays. Abandon work discards unsaved changes and leaves without saving. That cannot be undone.";

const CHOICES = [
  { id: "stay", label: "Stay", danger: false },
  { id: "save", label: "Save & leave", danger: false },
  { id: "reset", label: "Reset bed", danger: false },
  { id: "abandon", label: "Abandon work", danger: true },
];

export function askBedLeave({ title, message } = {}) {
  return new Promise(resolve => {
    let dlg = document.getElementById("dlgBedLeave");
    if (!dlg) {
      dlg = document.createElement("dialog");
      dlg.id = "dlgBedLeave";
      dlg.setAttribute("aria-labelledby", "bedLeaveTitle");
      dlg.innerHTML = `<div class="dlg"><div class="dh"><h3 id="bedLeaveTitle"></h3></div><div class="body"><p id="bedLeaveMsg"></p></div><div class="df" id="bedLeaveActs"></div></div>`;
      const acts = dlg.querySelector("#bedLeaveActs");
      CHOICES.forEach(choice => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = choice.danger ? "btn danger" : "btn";
        btn.dataset.leave = choice.id;
        btn.textContent = choice.label;
        acts.appendChild(btn);
      });
      document.body.appendChild(dlg);
    }
    dlg.querySelector("#bedLeaveTitle").textContent = title || "Leave this workspace?";
    dlg.querySelector("#bedLeaveMsg").textContent = message || BED_LEAVE_MESSAGE;
    let settled = false;
    const done = (choice) => {
      if (settled) return;
      settled = true;
      if (dlg.open) dlg.close();
      resolve(choice);
    };
    dlg.querySelectorAll("[data-leave]").forEach(btn => {
      btn.onclick = () => done(btn.dataset.leave || "stay");
    });
    dlg.addEventListener("close", () => done("stay"), { once: true });
    dlg.showModal();
    dlg.querySelector("[data-leave=stay]")?.focus();
  });
}
