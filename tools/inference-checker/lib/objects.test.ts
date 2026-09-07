import { describe, expect, test } from "bun:test";
import { diagnose, intersection, validateObjectScene, visibleObjects, type ReviewObject } from "./objects";
const object = (id: number, runs: [number,number][], extras: Partial<ReviewObject> = {}): ReviewObject => ({id, runs, classId:0, categoryId:3, isthing:true, crowd:false, score:null, ...extras});
describe("object review", () => {
  test("interval intersections retain overlapping objects and match by IoU rather than IDs", () => {
    const a = object(7, [[0,3],[10,4]]), b = object(1, [[1,3],[12,4]]);
    expect(intersection(a,b)).toBe(4);
    const result = diagnose([a], [object(8,a.runs), object(7,[[20,4]])]);
    expect(result.matches).toEqual([{gt:7,pred:8,iou:1}]);
    expect([...result.extra]).toEqual([7]);
  });
  test("merge and split candidates expose both affected layers", () => {
    const gt = [object(1,[[0,4]]),object(2,[[4,4]])];
    const merged = [object(3,[[0,8]])];
    const d = diagnose(gt,merged);
    expect([...d.merged]).toEqual([3]); expect([...d.mergedGT]).toEqual([1,2]);
    expect(visibleObjects(gt,"gt","merged",d)).toHaveLength(2);
    const split = diagnose(merged,gt);
    expect([...split.split]).toEqual([3]); expect([...split.splitPred]).toEqual([1,2]);
  });
  test("same class required; stuff and crowd excluded; deterministic one-to-one matching", () => {
    const gt = [object(3,[[0,4]]),object(2,[[0,4]]),object(5,[[8,2]],{crowd:true}),object(6,[[10,2]],{isthing:false})];
    const d = diagnose(gt,[object(7,[[0,4]]),object(8,[[20,2]],{classId:1})]);
    expect(d.matches).toEqual([{gt:2,pred:7,iou:1}]);
    expect([...d.missed]).toEqual([3]); expect([...d.extra]).toEqual([8]);
    expect(visibleObjects(gt,"gt","extra",d)).toEqual([]);
  });
  test("empty predictions expose missed objects, not stuff", () => {
    expect([...diagnose([object(1,[[0,1]])],[]).missed]).toEqual([1]);
  });
  test("reject corrupt runs, duplicate IDs, excessive dimensions and unknown class", () => {
    const scene = (objects: ReviewObject[]) => ({version:1,task:"instance",width:4,height:4,layers:[{name:"GT",objects},{name:"Prediction",objects:[]}]});
    expect(validateObjectScene(scene([object(1,[[0,2]])]),1).width).toBe(4);
    for (const objects of [[object(1,[[15,2]])], [object(1,[[0,3],[2,2]])], [object(1,[[0,1]]),object(1,[[3,1]])], [object(1,[[0,2]],{classId:1})]]) expect(() => validateObjectScene(scene(objects),1)).toThrow();
    expect(() => validateObjectScene({...scene([]),width:100000000},1)).toThrow();
  });
});
