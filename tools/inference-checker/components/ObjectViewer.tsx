"use client";

import { useEffect, useMemo, useRef, useState, type UIEvent } from "react";
import type { SceneData, SegmentationConfig } from "../lib/data";
import { diagnose, visibleObjects, type Diagnostic, type ObjectScene, type ReviewObject } from "../lib/objects";

function objectColor(id: number): string { return `hsl(${(id * 137.508) % 360} 75% 63%)`; }
function ObjectCanvas({ imageSrc, data, objects, zoom, opacity, boundaries, ids, selected, onSelect, labels }: {
  imageSrc: string; data: ObjectScene; objects: ReviewObject[]; zoom: number; opacity: number;
  boundaries: boolean; ids: boolean; selected: number | null; onSelect: (id: number | null) => void;
  labels: SegmentationConfig["labels"];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [image, setImage] = useState<{src: string; value: HTMLImageElement} | null>(null);
  const [error, setError] = useState<{src: string; text: string} | null>(null);
  useEffect(() => {
    let cancelled = false;
    const image = new Image();
    image.onload = () => { if (!cancelled) setImage({src: imageSrc, value: image}); };
    image.onerror = () => { if (!cancelled) setError({src: imageSrc, text: `Could not load ${imageSrc}`}); };
    image.src = imageSrc;
    return () => { cancelled = true; };
  }, [imageSrc]);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = data.width; canvas.height = data.height;
    const ctx = canvas.getContext("2d");
    if (!ctx || image?.src !== imageSrc) return;
    ctx.drawImage(image.value, 0, 0, data.width, data.height);
    const layer = document.createElement("canvas"); layer.width = data.width; layer.height = data.height;
    const overlay = layer.getContext("2d")!;
    const pixels = new Uint8Array(data.width * data.height);
    for (const object of objects) {
      if (selected !== null && object.id !== selected) continue;
      pixels.fill(0);
      for (const [start, length] of object.runs) pixels.fill(1, start, start + length);
      overlay.clearRect(0, 0, data.width, data.height);
      overlay.fillStyle = objectColor(object.id);
      for (const [start, length] of object.runs) {
        for (let p = start; p < start + length;) {
          const row = Math.floor(p / data.width), x = p % data.width;
          const n = Math.min(data.width - x, start + length - p);
          overlay.fillRect(x, row, n, 1); p += n;
        }
      }
      ctx.globalAlpha = opacity; ctx.drawImage(layer, 0, 0); ctx.globalAlpha = 1;
      if (boundaries) {
        ctx.fillStyle = objectColor(object.id);
        for (const [start, length] of object.runs) for (let p = start; p < start + length; p++) {
          const x = p % data.width, y = Math.floor(p / data.width);
          if (x === 0 || x === data.width - 1 || y === 0 || y === data.height - 1 ||
              !pixels[p - 1] || !pixels[p + 1] || !pixels[p - data.width] || !pixels[p + data.width]) ctx.fillRect(x, y, 1, 1);
        }
      }
      if (ids) {
        const point = object.runs[0][0], x = point % data.width, y = Math.floor(point / data.width);
        const text = `#${object.id} ${labels[object.classId].readable}${object.score === null ? "" : ` ${(100 * object.score).toFixed(0)}%`}`;
        const font = Math.max(14, Math.round(data.width / 55));
        ctx.font = `600 ${font}px Arial`; const width = ctx.measureText(text).width + 8;
        const tx = Math.max(0, Math.min(x, data.width - width)); const ty = Math.max(font + 4, y);
        ctx.fillStyle = "#101419e8"; ctx.fillRect(tx, ty - font - 3, width, font + 7);
        ctx.fillStyle = objectColor(object.id); ctx.fillText(text, tx + 4, ty);
      }
    }
  }, [data, image, imageSrc, objects, opacity, boundaries, ids, selected, labels]);
  return <div className="canvas-scroll"><div className="object-canvas-stage" style={{width: `${zoom * 100}%`, height: `${zoom * 100}%`}}>
    <canvas ref={canvasRef} aria-label="Object segmentation overlay; select objects in the list for exact isolation" onClick={event => {
      const rect = event.currentTarget.getBoundingClientRect();
      const scale = Math.min(rect.width / data.width, rect.height / data.height);
      const x = Math.floor((event.clientX - rect.left - (rect.width - data.width * scale) / 2) / scale);
      const y = Math.floor((event.clientY - rect.top - (rect.height - data.height * scale) / 2) / scale);
      if (x < 0 || x >= data.width || y < 0 || y >= data.height) { onSelect(null); return; }
      const point = y * data.width + x;
      const hit = [...objects].reverse().find(o => o.runs.some(([start, n]) => point >= start && point < start + n));
      onSelect(hit?.id ?? null);
    }} />
    {error?.src === imageSrc && <p role="alert" className="error-strip">{error.text}</p>}
  </div></div>;
}

export default function ObjectViewer({ scenes, config }: {scenes: SceneData[]; config: SegmentationConfig}) {
  const [sceneIndex, setSceneIndex] = useState(0), [modelIndex, setModelIndex] = useState(1);
  const [loaded, setLoaded] = useState<{id: string; data: ObjectScene} | null>(null);
  const [error, setError] = useState<{id: string; text: string} | null>(null);
  const [mode, setMode] = useState<Diagnostic>("all");
  const [zoom, setZoom] = useState(1), [opacity, setOpacity] = useState(0.5);
  const [boundaries, setBoundaries] = useState(true), [ids, setIds] = useState(true);
  const [search, setSearch] = useState(""), [confidence, setConfidence] = useState(0);
  const [selection, setSelection] = useState<{layer: number; id: number} | null>(null);
  const [showObjects, setShowObjects] = useState(false);
  const workspace = useRef<HTMLDivElement>(null), synchronizing = useRef(false);
  const scene = scenes[sceneIndex];
  const data = loaded?.id === scene?.id ? loaded.data : null;
  const selected = data?.layers[modelIndex] ? modelIndex : 1;
  useEffect(() => {
    if (!scene) return;
    const controller = new AbortController();
    fetch(`/api/objects?sceneId=${encodeURIComponent(scene.id)}`, {signal: controller.signal}).then(async response => {
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Object scene request failed");
      setLoaded({id: scene.id, data: result});
    }).catch(e => { if (!controller.signal.aborted) setError({id: scene.id, text: String(e.message)}); });
    return () => controller.abort();
  }, [scene]);
  const gt = useMemo(() => data?.layers[0].objects ?? [], [data]);
  const pred = useMemo(() => (data?.layers[selected]?.objects ?? []).filter(o => o.score === null || o.score >= confidence), [data, selected, confidence]);
  const diagnostics = useMemo(() => diagnose(gt, pred), [gt, pred]);
  const left = useMemo(() => visibleObjects(gt, "gt", mode, diagnostics), [gt, mode, diagnostics]);
  const right = useMemo(() => visibleObjects(pred, "pred", mode, diagnostics), [pred, mode, diagnostics]);
  function syncScroll(event: UIEvent<HTMLDivElement>) {
    const source = event.target as HTMLElement;
    if (!source.classList.contains("canvas-scroll") || synchronizing.current) return;
    synchronizing.current = true;
    const x = source.scrollLeft / Math.max(1, source.scrollWidth - source.clientWidth);
    const y = source.scrollTop / Math.max(1, source.scrollHeight - source.clientHeight);
    workspace.current?.querySelectorAll<HTMLElement>(".canvas-scroll").forEach(other => {
      if (other !== source) { other.scrollLeft = x * (other.scrollWidth - other.clientWidth); other.scrollTop = y * (other.scrollHeight - other.clientHeight); }
    });
    requestAnimationFrame(() => { synchronizing.current = false; });
  }
  const imageSrc = scene ? `/api/artifact?sceneId=${encodeURIComponent(scene.id)}&filename=${encodeURIComponent(scene.inputImage)}` : "";
  return <div className="inspection-app">
    <header className="app-header"><h1>Inference checker</h1><span className="local-badge">{config.task?.toUpperCase()}</span><span className="dataset-title">{config.title ?? "Object identity and error review"}</span></header>
    <div className="scene-bar"><label htmlFor="object-scene">Scene</label><select id="object-scene" value={sceneIndex} onChange={e => {setSceneIndex(Number(e.target.value)); setSelection(null);}}>{scenes.map((s,i) => <option key={s.id} value={i}>{s.title ?? s.id}</option>)}</select><span className="scene-count">{scenes.length ? sceneIndex + 1 : 0}/{scenes.length}</span></div>
    <div className="view-bar object-view-bar"><label className="model-field">Prediction <select aria-label="Prediction" value={selected} onChange={e => {setModelIndex(Number(e.target.value)); setSelection(null);}}>{data?.layers.slice(1).map((l,i) => <option key={i} value={i+1}>{l.name}</option>)}</select></label>
      <label className="model-field">Review <select aria-label="Review" value={mode} onChange={e => {setMode(e.target.value as Diagnostic); setSelection(null);}}><option value="all">All segments</option><option value="missed">Missed things ({diagnostics.missed.size})</option><option value="extra">Extra things ({diagnostics.extra.size})</option><option value="merged">Merge candidates ({diagnostics.merged.size})</option><option value="split">Split candidates ({diagnostics.split.size})</option></select></label></div>
    <div className="adjustment-bar"><label>Overlay <input aria-label="Overlay" type="range" min="0" max="1" step="0.05" value={opacity} onChange={e => setOpacity(Number(e.target.value))}/></label><label>Zoom <input aria-label="Zoom" type="range" min="1" max="5" step="0.25" value={zoom} onChange={e => setZoom(Number(e.target.value))}/><output>{zoom}×</output></label><label><input type="checkbox" checked={boundaries} onChange={e => setBoundaries(e.target.checked)}/>Boundaries</label><label><input type="checkbox" checked={ids} onChange={e => setIds(e.target.checked)}/>IDs</label><label>Min confidence <input aria-label="Minimum confidence" type="range" min="0" max="1" step="0.05" value={confidence} onChange={e => {setConfidence(Number(e.target.value)); setSelection(null);}}/><output>{confidence.toFixed(2)}</output></label><button onClick={() => {setZoom(1); setSelection(null); workspace.current?.querySelectorAll(".canvas-scroll").forEach(el => el.scrollTo(0,0));}}>Reset view</button><button className="legend-toggle" onClick={() => setShowObjects(!showObjects)}>Objects</button></div>
    {error?.id === scene?.id && <p role="alert" className="error-strip">{error?.text}</p>}
    <div className="inspection-workspace">
      <div className="image-workspace compare-workspace" ref={workspace} onScrollCapture={syncScroll}>
      {data ? [left, right].map((objects,i) => <section className="image-pane" key={i}><h2 className="pane-heading">{i === 0 ? "Ground truth" : data.layers[selected].name}<span>{objects.length} segments</span></h2><ObjectCanvas imageSrc={imageSrc} data={data} objects={objects} zoom={zoom} opacity={opacity} boundaries={boundaries} ids={ids} labels={config.labels} selected={selection?.layer === i ? selection.id : null} onSelect={id => setSelection(id === null ? null : {layer:i,id})}/></section>) : <p role="status">{scene ? "Loading object masks…" : "No scenes in bundle"}</p>}
      </div>
      <aside className={`inspector-sidebar ${showObjects ? "is-open" : ""}`}><div className="inspector-heading"><h2>Objects</h2><button onClick={() => {setSelection(null); setShowObjects(false);}}>Clear / close</button></div><input className="class-search" type="search" aria-label="Search objects" placeholder="Class or object ID…" value={search} onChange={e => setSearch(e.target.value)}/><div className="class-list">
        {[left,right].map((objects,i) => <div key={i}><h3 className="pane-heading">{i === 0 ? "Ground truth" : "Prediction"}</h3>{objects.filter(o => `${o.id} ${config.labels[o.classId].readable}`.toLowerCase().includes(search.toLowerCase())).map(o => <button key={o.id} className="object-row" aria-pressed={selection?.layer === i && selection.id === o.id} onClick={() => setSelection(selection?.layer === i && selection.id === o.id ? null : {layer:i,id:o.id})}><i style={{background:objectColor(o.id)}}/><span>#{o.id} {config.labels[o.classId].readable}<small>{o.isthing ? "thing" : "stuff"}{o.crowd ? " · crowd (excluded)" : ""} · {o.score === null ? "confidence unavailable" : `${(o.score*100).toFixed(1)}% confidence`}</small></span></button>)}</div>)}
      </div><p className="inspector-note">IDs are local to each image and layer; equal IDs do not imply a match. Click an object to isolate its exact mask. Overlapping masks retain independent identities.</p></aside>
    </div>
    <details className="object-method"><summary>Review matching rules · {diagnostics.matches.length} matched things · heuristic, not AP/PQ</summary><p>Missed / extra: unmatched things after greedy same-class matching at mask IoU ≥ 0.50, highest IoU first; ties use IDs. Crowd and stuff are excluded from object diagnostics. Predictions below the selected confidence are excluded. Crowd overlap is not COCO crowd handling. Merge / split candidates: one mask overlaps at least two same-class masks by ≥ 50% of the smaller mask’s area. These are review flags, not confirmed annotation/model errors. Stuff is visible in “All segments”. Colors distinguish local segment IDs, not semantic classes. Instance masks are drawn in annotation order; later masks cover earlier fills visually, without changing the stored masks. Isolate an object to inspect overlaps.</p><p>Prediction checkpoint SHA-256: <code>{data?.layers[selected]?.checkpoint ?? "unavailable"}</code></p></details>
  </div>;
}
