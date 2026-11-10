/* Split a growing response into lines without copying the unfinished line on every chunk.

A multi-megabyte JSON line (the mesh preview) used to be appended with `buf += chunk`
and then split. Each chunk copied the whole line again, so a 1 KB delivery of a ~10 MB
line froze the page for tens of seconds. Chunks are kept until a newline, then joined once.
*/
export function createLineParser(onLine) {
  const chunks = [];
  const emit = (line) => {
    if (line.trim()) onLine(line);
  };
  return {
    push(text) {
      let start = 0;
      for (let i = 0; i < text.length; i++) {
        if (text.charCodeAt(i) !== 10) continue;
        chunks.push(text.slice(start, i));
        const line = chunks.join("");
        chunks.length = 0;
        start = i + 1;
        emit(line);
      }
      if (start < text.length) chunks.push(text.slice(start));
    },
    flush() {
      if (!chunks.length) return;
      const line = chunks.join("");
      chunks.length = 0;
      emit(line);
    },
  };
}
