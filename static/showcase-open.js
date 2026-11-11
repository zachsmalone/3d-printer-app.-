/* Showcase item → Slice / Open in CAD, and the publish licence default.
   showSlice / showOpenCad read the item payload. They do not grant remix permission.
   can_remix is the server's answer (licence and the maker's switch). A missing flag stays off. */

export function showcaseFile(item) {
  const files = Array.isArray(item?.files) ? item.files : [];
  return files.find(f => f && f.url && /\.stl$/i.test(String(f.name || ""))) || files.find(f => f && f.url) || null;
}

/** A file this viewer can actually fetch: not an example, not an empty project, not view-only for someone else. */
export function canDownloadModel(item) {
  if (!item || item.example || item.no_model) return false;
  if (item.download_blocked) return false;
  if (item.view_only && !item.owned) return false;
  return !!showcaseFile(item);
}

export function showSlice(item) {
  return canDownloadModel(item);
}

/** Owners may open their own downloadable file. Everyone else needs can_remix as well. */
export function showOpenCad(item) {
  if (!canDownloadModel(item)) return false;
  if (item.owned) return true;
  return item.can_remix === true;
}

/** Matches the My printer switch: resin prepares in TorchC0, anything else in the FDM Slicer. */
export function sliceDestination(printKind) {
  return printKind === "resin" ? "torchc0" : "slicer";
}

/** Send to Showcase keeps a credit chain only for Open in CAD by someone who does not own the project. */
export function rememberRemixFor(action, item) {
  return action === "cad" && !!item && item.owned !== true && item.can_remix === true;
}

const SHARE_ALIKE = ["cc-by-sa-4.0", "cc-by-nc-sa-4.0"];

export function shareAlikeIds() {
  return SHARE_ALIKE.slice();
}

export function shareAlikeLicence(licenseId) {
  return SHARE_ALIKE.includes(licenseId) ? licenseId : "";
}

/** Private use unless the remix source is share-alike, which asks for the same licence. */
export function licenceChoice(menuDefault, sourceLicenseId) {
  const same = shareAlikeLicence(sourceLicenseId);
  if (same) return same;
  return menuDefault || "private-use";
}

export function cadPageHref(buildId) {
  return `/static/cad.html?bid=${encodeURIComponent(buildId)}&from=${encodeURIComponent("Showcase")}&back=${encodeURIComponent("/#showcase")}`;
}
