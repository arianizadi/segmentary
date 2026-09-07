import fs from "fs";
import { NextRequest, NextResponse } from "next/server";
import { getBundleIndex, getSceneImagePath } from "../../../lib/data";
import { validateObjectScene } from "../../../lib/objects";

export async function GET(request: NextRequest) {
  try {
    const bundle = getBundleIndex();
    const scene = bundle.scenesById.get(new URL(request.url).searchParams.get("sceneId") ?? "");
    if (!scene || !bundle.config.task) return NextResponse.json({error: "Object scene not found"}, {status: 404});
    const file = getSceneImagePath(scene.id, "objects.json", bundle.root);
    if (fs.statSync(file).size > 64 * 1024 * 1024) throw new Error("Object scene exceeds 64 MiB limit");
    const data = validateObjectScene(JSON.parse(fs.readFileSync(file, "utf8")), bundle.config.labels.length);
    if (data.task !== bundle.config.task) throw new Error("Object task differs from bundle configuration");
    return NextResponse.json(data, {headers: {"Cache-Control": "no-store"}});
  } catch (error) {
    return NextResponse.json({error: error instanceof Error ? error.message : String(error)}, {status: 422});
  }
}
