// Minimal ZIP reader (stored + deflate) using the browser's DecompressionStream, and SHA-256 via
// WebCrypto. Used to show and independently re-verify an export's manifest in the browser.

const td = new TextDecoder();

export function webCryptoAvailable() {
  return typeof crypto !== 'undefined' && !!crypto.subtle && typeof DecompressionStream !== 'undefined';
}

export async function sha256Hex(data) {
  const buf = data instanceof ArrayBuffer ? data : data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
  const d = await crypto.subtle.digest('SHA-256', buf);
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function inflateRaw(u8) {
  const stream = new Blob([u8]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Returns [{name, size, compressedSize, read(): Promise<Uint8Array>}] */
export function readZip(buffer) {
  const dv = new DataView(buffer);
  const u8 = new Uint8Array(buffer);
  let eocd = -1;
  for (let i = buffer.byteLength - 22; i >= Math.max(0, buffer.byteLength - 22 - 65535); i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('not a zip archive');
  const count = dv.getUint16(eocd + 10, true);
  let p = dv.getUint32(eocd + 16, true);
  const entries = [];
  for (let n = 0; n < count; n++) {
    if (dv.getUint32(p, true) !== 0x02014b50) throw new Error('corrupt zip central directory');
    const method = dv.getUint16(p + 10, true);
    const csize = dv.getUint32(p + 20, true);
    const size = dv.getUint32(p + 24, true);
    const nlen = dv.getUint16(p + 28, true);
    const elen = dv.getUint16(p + 30, true);
    const clen = dv.getUint16(p + 32, true);
    const loff = dv.getUint32(p + 42, true);
    const name = td.decode(u8.subarray(p + 46, p + 46 + nlen));
    p += 46 + nlen + elen + clen;
    const start = loff + 30 + dv.getUint16(loff + 26, true) + dv.getUint16(loff + 28, true);
    const raw = u8.subarray(start, start + csize);
    entries.push({
      name, size, compressedSize: csize,
      read: async () => {
        if (method === 0) return raw.slice();
        if (method === 8) return inflateRaw(raw);
        throw new Error(`unsupported zip compression method ${method}`);
      },
    });
  }
  return entries;
}

export const decodeText = (u8) => td.decode(u8);
