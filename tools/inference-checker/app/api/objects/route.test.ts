import { afterEach, expect, test } from "bun:test";
import fs from "fs";
import os from "os";
import path from "path";
import { NextRequest } from "next/server";
import { GET } from "./route";
import { GET as statsGET } from "../stats/route";
import { clearBundleIndexCache, BUNDLE_ROOT_ENV } from "../../../lib/data";
const previous = process.env[BUNDLE_ROOT_ENV];
const roots: string[] = [];
afterEach(() => {
  if (previous === undefined) delete process.env[BUNDLE_ROOT_ENV]; else process.env[BUNDLE_ROOT_ENV] = previous;
  clearBundleIndexCache(); for (const root of roots.splice(0)) fs.rmSync(root,{recursive:true,force:true});
});
function bundle() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(),"object-review-")); roots.push(root);
  fs.writeFileSync(path.join(root,"config.json"),JSON.stringify({version:1,task:"instance",labels:[{name:"car",readable:"Car",color:[1,2,3],evaluate:true}]}));
  fs.mkdirSync(path.join(root,"scene-1"));
  for (const name of ["input.png","gt.png","model.png"]) fs.writeFileSync(path.join(root,"scene-1",name),"");
  const object = {id:1,classId:0,categoryId:3,isthing:true,crowd:false,score:null,runs:[[0,1]]};
  fs.writeFileSync(path.join(root,"scene-1","objects.json"),JSON.stringify({version:1,task:"instance",width:1,height:1,layers:[{name:"GT",objects:[object]},{name:"model",objects:[object]}]}));
  process.env[BUNDLE_ROOT_ENV] = root;
  return root;
}
test("serves validated object masks while refusing semantic metrics on flattened previews", async () => {
  bundle();
  const response = await GET(new NextRequest("http://localhost/api/objects?sceneId=scene-1"));
  expect(response.status).toBe(200); expect((await response.json()).layers).toHaveLength(2);
  expect(statsGET(new NextRequest("http://localhost/api/stats?sceneId=scene-1")).status).toBe(422);
  expect((await GET(new NextRequest("http://localhost/api/objects?sceneId=unknown"))).status).toBe(404);
});
test("rejects malformed JSON and symlinked artifacts", async () => {
  const root = bundle(), file = path.join(root,"scene-1","objects.json");
  fs.writeFileSync(file,"{}");
  expect((await GET(new NextRequest("http://localhost/api/objects?sceneId=scene-1"))).status).toBe(422);
  fs.rmSync(file); fs.symlinkSync(path.join(root,"config.json"),file);
  expect((await GET(new NextRequest("http://localhost/api/objects?sceneId=scene-1"))).status).toBe(422);
});
