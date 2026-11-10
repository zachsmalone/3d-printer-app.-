/* Binary STL view sample for the FDM slicer.

The sample is only for the on-screen mesh. The file the page uploads is not modified, and
Slice uses that file. The pick order matches app/services/editproj.py iter_binary_stl_preview:
chunks of max(step, floor(n / 8)), then every `step` triangle inside the chunk, then cut
to maxFaces. BIG_FACES matches app/core/fdmlean.py FDM_MAX_FACES (files at or under that
stay on the normal import). MAX_STORE_FACES matches app/core/meshedit.py MAX_FACES.
*/
export const PREVIEW_FACES = 150000;
export const BIG_FACES = 400000;
export const MAX_STORE_FACES = 3000000;

export function previewPickIndices(n, maxFaces) {
  const step = n <= maxFaces ? 1 : Math.ceil(n / maxFaces);
  const chunk = Math.max(step, Math.floor(n / 8));
  const ids = [];
  let done = 0;
  while (done < n && ids.length < maxFaces) {
    const nxt = Math.min(n, done + chunk);
    for (let i = done; i < nxt && ids.length < maxFaces; i += step) ids.push(i);
    done = nxt;
  }
  return ids;
}

function headerCount(size, bytes) {
  if (size < 84 || bytes.byteLength < 84) return 0;
  const n = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(80, true);
  if (n <= 0 || size !== 84 + 50 * n) return 0;
  return n;
}

/* Read a big binary STL. Returns null when the file is not an exact binary STL in the
   large-file range (the caller then uses the normal upload). Progress `done` is source
   triangles visited, never a guess. The returned positions are a sample; `triangles` is
   the count stored in the file header. */
export async function sampleBinaryStl(file, opts = {}) {
  const maxFaces = opts.maxFaces || PREVIEW_FACES;
  const minFaces = opts.minFaces == null ? BIG_FACES : opts.minFaces;
  const scale = opts.scale || 1;
  const signal = opts.signal;
  const onProgress = opts.onProgress;
  if (signal?.aborted) throw new DOMException("aborted", "AbortError");
  const headBuf = await file.slice(0, 84).arrayBuffer();
  const n = headerCount(file.size, new Uint8Array(headBuf));
  if (!n || n <= minFaces || n > MAX_STORE_FACES) return null;
  const ids = previewPickIndices(n, maxFaces);
  const step = n <= maxFaces ? 1 : Math.ceil(n / maxFaces);
  const chunk = Math.max(step, Math.floor(n / 8));
  const positions = new Float32Array(ids.length * 9);
  let kept = 0;
  let nextId = 0;
  const lo = [Infinity, Infinity, Infinity];
  const hi = [-Infinity, -Infinity, -Infinity];
  let done = 0;
  while (done < n) {
    if (signal?.aborted) throw new DOMException("aborted", "AbortError");
    const nxt = Math.min(n, done + chunk);
    const buf = await file.slice(84 + done * 50, 84 + nxt * 50).arrayBuffer();
    const dv = new DataView(buf);
    for (let i = done; i < nxt; i++) {
      const base = (i - done) * 50 + 12;
      const x0 = dv.getFloat32(base, true), y0 = dv.getFloat32(base + 4, true), z0 = dv.getFloat32(base + 8, true);
      const x1 = dv.getFloat32(base + 12, true), y1 = dv.getFloat32(base + 16, true), z1 = dv.getFloat32(base + 20, true);
      const x2 = dv.getFloat32(base + 24, true), y2 = dv.getFloat32(base + 28, true), z2 = dv.getFloat32(base + 32, true);
      if (x0 < lo[0]) lo[0] = x0;
      if (y0 < lo[1]) lo[1] = y0;
      if (z0 < lo[2]) lo[2] = z0;
      if (x1 < lo[0]) lo[0] = x1;
      if (y1 < lo[1]) lo[1] = y1;
      if (z1 < lo[2]) lo[2] = z1;
      if (x2 < lo[0]) lo[0] = x2;
      if (y2 < lo[1]) lo[1] = y2;
      if (z2 < lo[2]) lo[2] = z2;
      if (x0 > hi[0]) hi[0] = x0;
      if (y0 > hi[1]) hi[1] = y0;
      if (z0 > hi[2]) hi[2] = z0;
      if (x1 > hi[0]) hi[0] = x1;
      if (y1 > hi[1]) hi[1] = y1;
      if (z1 > hi[2]) hi[2] = z1;
      if (x2 > hi[0]) hi[0] = x2;
      if (y2 > hi[1]) hi[1] = y2;
      if (z2 > hi[2]) hi[2] = z2;
      if (nextId < ids.length && ids[nextId] === i) {
        const dst = kept * 9;
        positions[dst] = x0; positions[dst + 1] = y0; positions[dst + 2] = z0;
        positions[dst + 3] = x1; positions[dst + 4] = y1; positions[dst + 5] = z1;
        positions[dst + 6] = x2; positions[dst + 7] = y2; positions[dst + 8] = z2;
        kept++;
        nextId++;
      }
    }
    done = nxt;
    if (onProgress) onProgress(done, n);
  }
  const used = positions.subarray(0, kept * 9);
  const out = new Float32Array(used);
  if (scale !== 1) {
    for (let i = 0; i < out.length; i++) out[i] *= scale;
  }
  const size_mm = [0, 1, 2].map(k => Math.round((hi[k] - lo[k]) * scale * 1000) / 1000);
  return { triangles: n, kept, positions: out, decimated: step !== 1, size_mm };
}
