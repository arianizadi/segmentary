import { test, expect } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { PNG } from "pngjs";
import { displayMask } from "./display-mask";

test("display mask preserves every class byte while stripping gamma", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "display-mask-"));
  try {
    const data = Buffer.alloc(256 * 4);
    for (let i = 0; i < 256; i++) {
      data[i * 4] = data[i * 4 + 1] = data[i * 4 + 2] = i;
      data[i * 4 + 3] = 255;
    }
    const file = path.join(root, "mask.png");
    fs.writeFileSync(file, PNG.sync.write({width: 256, height: 1, data, gamma: 0.2} as PNG, {colorType: 0}));
    const first = displayMask(file);
    expect(displayMask(file)).toBe(first);
    const result = PNG.sync.read(first);
    expect(result.gamma).toBe(0);
    expect(result.data).toEqual(data);
    data[0] = data[1] = data[2] = 13;
    fs.writeFileSync(file, PNG.sync.write({width: 256, height: 1, data} as PNG, {colorType: 0}));
    expect(PNG.sync.read(displayMask(file)).data[0]).toBe(13);
  } finally { fs.rmSync(root, {recursive: true, force: true}); }
});
