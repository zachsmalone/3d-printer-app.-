import {
  showcaseFile, showSlice, showOpenCad, sliceDestination, rememberRemixFor,
  licenceChoice, shareAlikeIds, cadPageHref,
} from "../static/showcase-open.js";

const stl = { name: "cup.stl", url: "/api/showcase/x/files/cup.stl" };
const obj = { name: "cup.obj", url: "/api/showcase/x/files/cup.obj" };
const item = (over) => Object.assign({
  example: false, no_model: false, download_blocked: false, view_only: false,
  owned: false, can_remix: false, original: false, files: [stl],
}, over);

const fails = [];
const check = (name, cond) => { if (!cond) fails.push(name); };

const viewOnly = item({ view_only: true, download_blocked: true, can_remix: true, files: [{ name: "cup.stl", url: null }] });
check("view-only hides Slice", showSlice(viewOnly) === false);
check("view-only hides Open in CAD", showOpenCad(viewOnly) === false);

const nd = item({ can_remix: false });
check("ND shows Slice", showSlice(nd) === true);
check("ND hides Open in CAD", showOpenCad(nd) === false);

const priv = item({ can_remix: false });
check("private-use shows Slice", showSlice(priv) === true);
check("private-use hides Open in CAD", showOpenCad(priv) === false);

const ccby = item({ can_remix: true });
check("CC BY shows Slice", showSlice(ccby) === true);
check("CC BY shows Open in CAD", showOpenCad(ccby) === true);
check("CC BY non-owner remembers remix for CAD", rememberRemixFor("cad", ccby) === true);
check("CC BY Slice does not remember remix", rememberRemixFor("slice", ccby) === false);

const off = item({ can_remix: false, allow_remixes: false });
check("remixes-off shows Slice", showSlice(off) === true);
check("remixes-off hides Open in CAD", showOpenCad(off) === false);

const owner = item({ owned: true, can_remix: false, view_only: true });
check("owner shows Slice", showSlice(owner) === true);
check("owner shows Open in CAD", showOpenCad(owner) === true);
check("owner CAD does not remember remix", rememberRemixFor("cad", owner) === false);

const example = item({ example: true, can_remix: true, owned: true });
check("example hides Slice", showSlice(example) === false);
check("example hides Open in CAD", showOpenCad(example) === false);

const none = item({ no_model: true, files: [], can_remix: true });
check("no-model hides Slice", showSlice(none) === false);
check("no-model hides Open in CAD", showOpenCad(none) === false);

const original = item({ original: true, owned: false, can_remix: true });
check("ZEIM Original shows Slice", showSlice(original) === true);
check("remixable Original shows Open in CAD", showOpenCad(original) === true);

check("prefers stl over an earlier file", showcaseFile(item({ files: [obj, stl] })).name === "cup.stl");
check("a non-stl file still counts", showSlice(item({ files: [obj] })) === true);
check("download_blocked hides Slice even with a url", showSlice(item({ download_blocked: true })) === false);

check("FDM goes to the slicer", sliceDestination("fdm") === "slicer");
check("unset printer type goes to the slicer", sliceDestination(undefined) === "slicer");
check("resin goes to TorchC0", sliceDestination("resin") === "torchc0");

check("default licence is private-use", licenceChoice("private-use", "cc-by-4.0") === "private-use");
check("empty source stays private-use", licenceChoice("private-use", "") === "private-use");
check("ND source stays private-use", licenceChoice("private-use", "cc-by-nd-4.0") === "private-use");
check("CC BY-SA selects the same licence", licenceChoice("private-use", "cc-by-sa-4.0") === "cc-by-sa-4.0");
check("CC BY-NC-SA selects the same licence", licenceChoice("", "cc-by-nc-sa-4.0") === "cc-by-nc-sa-4.0");

const href = cadPageHref("abc");
check("CAD href carries the build id", href.includes("bid=abc"));
check("CAD href names Showcase", href.includes("from=Showcase"));
check("CAD href encodes the showcase return", href.includes("back=" + encodeURIComponent("/#showcase")));

if (shareAlikeIds().join(",") !== "cc-by-sa-4.0,cc-by-nc-sa-4.0") fails.push("share-alike ids");

if (fails.length) {
  console.error(fails.join("\n"));
  process.exit(1);
}
console.log("ok");
