import fs from "node:fs";
import { PNG } from "pngjs";
import { readMaskIndices } from "./stats";

const MAX_BYTES = 16 * 1024 * 1024;
const MAX_ENTRIES = 16;
const cache = new Map<string, { signature: string; bytes: Buffer }>();
let cacheBytes = 0;

// Canvas reads display RGB bytes, not original grayscale samples. Strip color
// profiles/gamma from masks so browser color management cannot change class IDs.
export function displayMask(filePath: string): Buffer {
  const stat = fs.statSync(filePath, { bigint: true });
  const signature = `${stat.ino}:${stat.size}:${stat.mtimeNs}:${stat.ctimeNs}`;
  const hit = cache.get(filePath);
  if (hit) {
    cache.delete(filePath);
    if (hit.signature === signature) {
      cache.set(filePath, hit);
      return hit.bytes;
    }
    cacheBytes -= hit.bytes.length;
  }
  const { indices, width, height } = readMaskIndices(filePath);
  const data = Buffer.alloc(indices.length * 4);
  for (let i = 0; i < indices.length; i++) {
    data[i * 4] = data[i * 4 + 1] = data[i * 4 + 2] = indices[i];
    data[i * 4 + 3] = 255;
  }
  const bytes = PNG.sync.write({ width, height, data } as PNG);
  if (bytes.length <= MAX_BYTES) {
    while (cache.size >= MAX_ENTRIES || cacheBytes + bytes.length > MAX_BYTES) {
      const key = cache.keys().next().value!;
      cacheBytes -= cache.get(key)!.bytes.length;
      cache.delete(key);
    }
    cache.set(filePath, {signature, bytes});
    cacheBytes += bytes.length;
  }
  return bytes;
}
