/** Object review uses independent foreground intervals, preserving overlapping instances. */
export interface ReviewObject {
  id: number; classId: number; categoryId: number; isthing: boolean;
  crowd: boolean; score: number | null; runs: [number, number][];
}
export interface ObjectLayer { name: string; checkpoint?: string; objects: ReviewObject[] }
export interface ObjectScene { version: 1; task: "instance" | "panoptic"; width: number; height: number; layers: ObjectLayer[] }
export type Diagnostic = "all" | "missed" | "extra" | "merged" | "split";
export function validateObjectScene(value: unknown, classCount: number): ObjectScene {
  if (!value || typeof value !== "object") throw new Error("Invalid object scene");
  const scene = value as ObjectScene;
  if (scene.version !== 1 || !["instance", "panoptic"].includes(scene.task) ||
      !Number.isSafeInteger(scene.width) || !Number.isSafeInteger(scene.height) ||
      scene.width < 1 || scene.height < 1 || scene.width * scene.height > 40_000_000 ||
      !Array.isArray(scene.layers) || scene.layers.length < 2 || scene.layers.length > 32) {
    throw new Error("Invalid object scene dimensions, version, task, or layers");
  }
  let totalRuns = 0;
  for (const layer of scene.layers) {
    if (typeof layer.name !== "string" || !Array.isArray(layer.objects) || layer.objects.length > 5000 ||
        (layer.checkpoint !== undefined && layer.checkpoint !== null && typeof layer.checkpoint !== "string")) throw new Error("Invalid object layer");
    const ids = new Set<number>();
    for (const object of layer.objects) {
      if (!object || !Number.isSafeInteger(object.id) || object.id < 0 || ids.has(object.id) ||
          !Number.isInteger(object.classId) || object.classId < 0 || object.classId >= classCount ||
          !Number.isSafeInteger(object.categoryId) || object.categoryId < 0 ||
          typeof object.isthing !== "boolean" || typeof object.crowd !== "boolean" ||
          (object.score !== null && (typeof object.score !== "number" || !Number.isFinite(object.score) || object.score < 0 || object.score > 1)) ||
          !Array.isArray(object.runs) || !object.runs.length) throw new Error("Invalid object metadata");
      ids.add(object.id);
      let end = 0;
      for (const run of object.runs) {
        if (!Array.isArray(run) || run.length !== 2 || !Number.isSafeInteger(run[0]) ||
            !Number.isSafeInteger(run[1]) || run[0] < end || run[1] < 1 || run[0] + run[1] > scene.width * scene.height) throw new Error("Invalid foreground interval");
        end = run[0] + run[1];
      }
      totalRuns += object.runs.length;
      if (totalRuns > 4_000_000) throw new Error("Object scene exceeds interval budget");
    }
  }
  const gt = scene.layers[0].objects.filter(o => o.isthing && !o.crowd);
  for (const layer of scene.layers.slice(1)) {
    const pred = layer.objects.filter(o => o.isthing && !o.crowd);
    const estimate = gt.reduce((sum, o) => sum + o.runs.length, 0) * pred.length +
      pred.reduce((sum, o) => sum + o.runs.length, 0) * gt.length;
    if (estimate > 100_000_000) throw new Error("Object matching exceeds the 100 million interval-work budget; prepare a smaller scene");
  }
  return scene;
}
export function area(object: ReviewObject): number { return object.runs.reduce((sum, [, n]) => sum + n, 0); }
export function intersection(a: ReviewObject, b: ReviewObject): number {
  let i = 0, j = 0, count = 0;
  while (i < a.runs.length && j < b.runs.length) {
    const [x, n] = a.runs[i], [y, m] = b.runs[j];
    count += Math.max(0, Math.min(x + n, y + m) - Math.max(x, y));
    if (x + n <= y + m) i++; else j++;
  }
  return count;
}
export interface Diagnostics {
  missed: Set<number>; extra: Set<number>; mergedGT: Set<number>; merged: Set<number>;
  split: Set<number>; splitPred: Set<number>; matches: {gt: number; pred: number; iou: number}[];
}
/** Review heuristic, NOT COCO AP/PQ: greedy largest-IoU same-class matching.
 * Crowd excluded. Merge/split candidates use intersection / smaller area >= overlap.
 * Only things are counted as objects; stuff remains visible in the all view. */
export function diagnose(gt: ReviewObject[], predictions: ReviewObject[], threshold = 0.5, overlap = 0.5): Diagnostics {
  const truth = gt.filter(o => o.isthing && !o.crowd);
  const pred = predictions.filter(o => o.isthing && !o.crowd);
  const result: Diagnostics = {missed: new Set(truth.map(o => o.id)), extra: new Set(pred.map(o => o.id)), mergedGT: new Set(), merged: new Set(), split: new Set(), splitPred: new Set(), matches: []};
  const pairs: {gt: number; pred: number; iou: number}[] = [];
  const linksGT = new Map<number, number[]>(), linksPred = new Map<number, number[]>();
  const areas = new Map<ReviewObject, number>([...truth, ...pred].map(o => [o, area(o)]));
  for (const g of truth) for (const p of pred) {
    if (g.classId !== p.classId) continue;
    const shared = intersection(g, p), ga = areas.get(g)!, pa = areas.get(p)!;
    const iou = shared / (ga + pa - shared);
    if (iou >= threshold) pairs.push({gt: g.id, pred: p.id, iou});
    if (shared > 0 && shared / Math.min(ga, pa) >= overlap) {
      linksGT.set(g.id, [...(linksGT.get(g.id) ?? []), p.id]);
      linksPred.set(p.id, [...(linksPred.get(p.id) ?? []), g.id]);
    }
  }
  pairs.sort((a,b) => b.iou - a.iou || a.gt - b.gt || a.pred - b.pred);
  for (const pair of pairs) if (result.missed.has(pair.gt) && result.extra.has(pair.pred)) {
    result.matches.push(pair); result.missed.delete(pair.gt); result.extra.delete(pair.pred);
  }
  for (const [id, links] of linksGT) if (links.length > 1) { result.split.add(id); links.forEach(p => result.splitPred.add(p)); }
  for (const [id, links] of linksPred) if (links.length > 1) { result.merged.add(id); links.forEach(g => result.mergedGT.add(g)); }
  return result;
}
export function visibleObjects(objects: ReviewObject[], side: "gt" | "pred", mode: Diagnostic, d: Diagnostics): ReviewObject[] {
  if (mode === "all") return objects;
  const ids = mode === "missed" ? (side === "gt" ? d.missed : new Set<number>()) :
    mode === "extra" ? (side === "pred" ? d.extra : new Set<number>()) :
    mode === "merged" ? (side === "gt" ? d.mergedGT : d.merged) : (side === "gt" ? d.split : d.splitPred);
  return objects.filter(o => ids.has(o.id));
}
