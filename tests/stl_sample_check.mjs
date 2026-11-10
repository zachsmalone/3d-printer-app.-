/* Checks the browser STL sample and the line splitter. Run by tests/test_fdm_client_view.py. */
import fs from "fs";
import { sampleBinaryStl, previewPickIndices } from "../static/stl-sample.js";
import { createLineParser } from "../static/ndjson-lines.js";

const cmd = process.argv[2];

if (cmd === "sample") {
  const data = fs.readFileSync(process.argv[3]);
  const maxFaces = Number(process.argv[4]);
  const file = new File([data], "t.stl");
  const sample = await sampleBinaryStl(file, { maxFaces, minFaces: 0 });
  if (!sample) {
    console.error("sample returned null");
    process.exit(2);
  }
  const ids = [];
  for (let i = 0; i < sample.positions.length; i += 9) ids.push(sample.positions[i]);
  const picks = previewPickIndices(sample.triangles, maxFaces);
  if (ids.length !== picks.length || ids.some((id, i) => id !== picks[i])) {
    console.error("picked triangles do not follow previewPickIndices");
    process.exit(2);
  }
  process.stdout.write(JSON.stringify({
    triangles: sample.triangles,
    kept: sample.kept,
    ids,
    size_mm: sample.size_mm,
    decimated: sample.decimated,
  }));
} else if (cmd === "lines") {
  const lines = [];
  const check = createLineParser(line => lines.push(line));
  check.push('{"a":');
  check.push('1}\n{"b":2}\n');
  check.flush();
  if (lines.join("|") !== '{"a":1}|{"b":2}') {
    console.error(lines);
    process.exit(3);
  }
  const payload = "a".repeat(8 * 1024 * 1024);
  const parser = createLineParser(() => {});
  const t = process.hrtime.bigint();
  for (let i = 0; i < payload.length; i += 512) parser.push(payload.slice(i, i + 512));
  parser.push("\n");
  parser.flush();
  const ms = Number(process.hrtime.bigint() - t) / 1e6;
  process.stdout.write(JSON.stringify({ ms: Math.round(ms) }));
  if (ms > 3000) process.exit(4);
} else {
  console.error("usage: sample <file> <maxFaces> | lines");
  process.exit(1);
}
