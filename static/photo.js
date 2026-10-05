/* Photo picker shared by Studio and Edit: Take a photo / Choose a photo / Use a sample image, all inline (no popups).
   - phones/tablets: "Take a photo" is a file input with capture=environment (works over plain http)
   - desktops with a camera: live preview in the page (getUserMedia, only after the tap), Capture / Retake / Use photo
   - no camera, blocked, or insecure page: a calm message under the buttons; the Choose button is right there
   The photo is NOT uploaded or stored until the person builds; the server also strips EXIF/GPS from everything it receives. */

const $ = (s, r = document) => r.querySelector(s);
export const CAMERA_MSG = "ZEIM can't use the camera. You can choose a photo instead.";
export const isPhone = () =>
  matchMedia("(pointer:coarse)").matches || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent) ||
  (navigator.maxTouchPoints > 1 && /Macintosh/.test(navigator.userAgent));

export function photoBlock(p, { sample = true } = {}) {
  return `<div class="pp" id="${p}Pick">
  <div class="pp-actions">
    <button type="button" class="btn big" id="${p}Take" hidden><span aria-hidden="true">📷</span> Take a photo</button>
    <button type="button" class="btn big primary" id="${p}Choose"><span aria-hidden="true">🖼</span> Choose a photo</button>
  </div>
  ${sample ? `<div class="pp-sample"><button type="button" class="btn" id="${p}Sample"><span aria-hidden="true">✨</span> Use a sample image</button></div>` : ""}
  <p class="pp-msg" id="${p}Msg" role="status" aria-live="polite" hidden></p>
  <div class="pp-cam" id="${p}CamPanel" hidden>
    <video id="${p}Video" playsinline muted autoplay aria-label="Camera preview"></video>
    <canvas id="${p}Canvas" hidden></canvas>
    <div class="pp-actions">
      <button type="button" class="btn big primary" id="${p}Snap">Capture</button>
      <button type="button" class="btn big" id="${p}Retake" hidden>Retake</button>
      <button type="button" class="btn big primary" id="${p}Use" hidden>Use photo</button>
      <button type="button" class="btn big ghost" id="${p}CamCancel">Cancel</button>
    </div>
  </div>
  <input type="file" id="${p}File" accept="image/*,.heic,.heif" class="sr-only" tabindex="-1" aria-hidden="true">
  <input type="file" id="${p}Cam" accept="image/*" capture="environment" class="sr-only" tabindex="-1" aria-hidden="true">
  <label class="inl pp-ack"><input type="checkbox" id="${p}Ack"> <span>This is my photo or drawing, or I have permission from everyone in it. No addresses, school names or license plates.</span></label>
  <p class="pp-note">Photos stay private to you unless you choose to share.<br>Use your own photo or drawing, or ask first. No addresses, school names or plates.</p>
</div>`;
}

export function mountPhoto(p, onFile) {
  const el = id => $("#" + p + id);
  const msg = (t) => { const m = el("Msg"); m.textContent = t || ""; m.hidden = !t; };
  let stream = null;
  const stop = () => { stream?.getTracks().forEach(t => t.stop()); stream = null; };
  // CR-5: an uploaded photo needs the permission box ticked first (never pre-ticked; the sample image is exempt and does not come through here)
  const ackBox = el("Ack");
  const allowed = f => {
    if (!f) return false;
    if (ackBox.checked) return true;
    msg("Please tick the box below that says this is your photo (or you have permission), then choose the photo again.");
    ackBox.focus(); return false;
  };
  ackBox.addEventListener("change", () => { if (ackBox.checked) msg(""); });
  const give = f => { if (!allowed(f)) return; msg(""); onFile(f); };

  el("Choose").onclick = () => el("File").click();
  el("File").onchange = e => { give(e.target.files[0]); e.target.value = ""; };
  el("Cam").onchange = e => { give(e.target.files[0]); e.target.value = ""; };

  // "Take a photo": phones use the capture input; desktops only show it when a camera can exist.
  const take = el("Take");
  const hasMD = !!navigator.mediaDevices?.getUserMedia;
  const showTake = async () => {
    if (isPhone()) return true;
    if (!navigator.mediaDevices) return true;                       // insecure page: show, then explain on tap
    if (!hasMD || !navigator.mediaDevices.enumerateDevices) return false;
    try { return (await navigator.mediaDevices.enumerateDevices()).some(d => d.kind === "videoinput"); } catch { return false; }
  };
  showTake().then(ok => { take.hidden = !ok; });

  async function openCamera() {
    msg("");
    if (isPhone() && !hasMD) { el("Cam").click(); return; }
    if (isPhone()) { el("Cam").click(); return; }
    if (!window.isSecureContext || !hasMD) { msg(CAMERA_MSG); return; }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
    } catch (e) { stop(); msg(CAMERA_MSG); return; }               // NotAllowedError, NotFoundError, NotReadableError, ...
    const v = el("Video"); v.srcObject = stream; v.hidden = false; el("Canvas").hidden = true;
    el("Snap").hidden = false; el("Retake").hidden = true; el("Use").hidden = true;
    el("CamPanel").hidden = false; v.play?.().catch(() => { });
  }
  take.onclick = openCamera;
  el("Snap").onclick = () => {
    const v = el("Video"), c = el("Canvas");
    if (!v.videoWidth) { msg(CAMERA_MSG); return; }
    c.width = v.videoWidth; c.height = v.videoHeight; c.getContext("2d").drawImage(v, 0, 0);   // pixels only: no EXIF/GPS from a canvas
    stop(); v.hidden = true; c.hidden = false;                       // camera light goes off right after the capture
    el("Snap").hidden = true; el("Retake").hidden = false; el("Use").hidden = false;
  };
  el("Retake").onclick = () => { el("CamPanel").hidden = true; openCamera(); };
  el("Use").onclick = () => {
    el("Canvas").toBlob(b => { el("CamPanel").hidden = true; if (b) give(new File([b], "camera.jpg", { type: "image/jpeg" })); else msg(CAMERA_MSG); }, "image/jpeg", 0.92);
  };
  el("CamCancel").onclick = () => { stop(); el("CamPanel").hidden = true; };
  addEventListener("pagehide", stop);
  return { msg, el, stop, allowed, acked: () => ackBox.checked };
}
