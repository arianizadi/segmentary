"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { Activity, ChevronLeft, ChevronRight, HelpCircle, X, AlertTriangle } from "lucide-react";
import MaskCanvas from "./MaskCanvas";
import DiffCanvas from "./DiffCanvas";
import ClassLegend from "./ClassLegend";
import HoverTooltip from "./HoverTooltip";
import DiffTooltip from "./DiffTooltip";
import type { ViewMode, ModelOption } from "./ModelSelector";
import type { ArtifactProvenance, SegmentationConfig } from "../lib/data";
import type { ModelStats } from "../lib/stats";

interface ViewerModel {
  name: string;
  filename: string;
  provenance?: ArtifactProvenance;
}

interface SceneInfo {
  id: string;
  title?: string;
  inputImage: string;
  groundTruth: string;
  models: ViewerModel[];
  provenance?: ArtifactProvenance;
}

interface ViewerProps {
  scenes: SceneInfo[];
  config: SegmentationConfig;
  setupError?: string;
}

interface ModelStatsError {
  modelName: string;
  message: string;
}

export default function Viewer({ scenes, config, setupError }: ViewerProps) {
  const ignoredClasses = useMemo(() => config.labels.flatMap((l, i) => l.evaluate ? [] : [i]), [config.labels]);
  const [sceneIndex, setSceneIndex] = useState(0);
  const [mode, setMode] = useState<ViewMode>("single");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [leftIndex, setLeftIndex] = useState(0);
  const [rightIndex, setRightIndex] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [opacity, setOpacity] = useState(0.65);
  const [hiddenClasses, setHiddenClasses] = useState<Set<number>>(new Set());

  // Lazy stats
  const [sceneStats, setSceneStats] = useState<Map<string, ModelStats[]>>(new Map());
  const [sceneStatsErrors, setSceneStatsErrors] = useState<Map<string, ModelStatsError[]>>(new Map());
  const [statsRequestErrors, setStatsRequestErrors] = useState<Map<string, string>>(new Map());
  const [statsRetryNonce, setStatsRetryNonce] = useState(0);
  const fetchedRef = useRef<Set<string>>(new Set());

  const [showHelp, setShowHelp] = useState(false);
  const [showLegend, setShowLegend] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (showHelp) dialogRef.current?.showModal(); }, [showHelp]);

  // Hover state
  const [hoverClassIndex, setHoverClassIndex] = useState<number | null>(null);
  const [hoverX, setHoverX] = useState(0);
  const [hoverY, setHoverY] = useState(0);
  const [hoverVisible, setHoverVisible] = useState(false);

  // Diff hover state
  const [diffHoverInfo, setDiffHoverInfo] = useState<{ classA: number | null; classB: number | null; classGT: number | null } | null>(null);
  const [diffHoverX, setDiffHoverX] = useState(0);
  const [diffHoverY, setDiffHoverY] = useState(0);
  const [diffHoverVisible, setDiffHoverVisible] = useState(false);

  const scene = scenes[sceneIndex];

  // Fetch stats lazily when scene changes
  useEffect(() => {
    if (!scene) return;
    if (fetchedRef.current.has(scene.id)) return;
    fetchedRef.current.add(scene.id);

    fetch(`/api/stats?sceneId=${encodeURIComponent(scene.id)}`)
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `Stats request failed (${res.status})`);
        return data as { stats: ModelStats[]; errors?: ModelStatsError[] };
      })
      .then((data) => {
        setSceneStats((prev) => {
          const next = new Map(prev);
          next.set(scene.id, data.stats);
          return next;
        });
        setSceneStatsErrors((prev) => {
          const next = new Map(prev);
          next.set(scene.id, data.errors ?? []);
          return next;
        });
      })
      .catch((error) => {
        fetchedRef.current.delete(scene.id);
        setStatsRequestErrors((prev) => {
          const next = new Map(prev);
          next.set(scene.id, error instanceof Error ? error.message : String(error));
          return next;
        });
      });
  }, [scene, statsRetryNonce]);

  const handleHover = useCallback(
    (classIndex: number | null, x: number, y: number) => {
      if (classIndex === null) {
        setHoverVisible(false);
      } else {
        setHoverClassIndex(classIndex);
        setHoverX(x);
        setHoverY(y);
        setHoverVisible(true);
      }
    },
    []
  );

  const handleDiffHover = useCallback(
    (info: { classA: number | null; classB: number | null; classGT: number | null } | null, x: number, y: number) => {
      if (!info) {
        setDiffHoverVisible(false);
      } else {
        setDiffHoverInfo(info);
        setDiffHoverX(x);
        setDiffHoverY(y);
        setDiffHoverVisible(true);
      }
    },
    []
  );

  const toggleClass = useCallback((classIndex: number) => {
    setHiddenClasses((prev) => {
      const next = new Set(prev);
      if (next.has(classIndex)) next.delete(classIndex);
      else next.add(classIndex);
      return next;
    });
  }, []);

  if (!scene) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-8">
        <div className="glass-panel p-10 rounded-3xl max-w-2xl border-dashed border-2 border-white/10">
          {setupError ? (
            <AlertTriangle className="text-red-400 mx-auto mb-6" size={64} />
          ) : (
            <Activity className="text-blue-400 mx-auto mb-6 opacity-50" size={64} />
          )}
          <h2 className="text-2xl font-bold text-white mb-4">
            {setupError ? "Inference Data Is Invalid" : "No Inference Data Found"}
          </h2>
          {setupError && (
            <p className="text-left text-red-200 bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 font-mono text-sm break-words">
              {setupError}
            </p>
          )}
          <p className="text-gray-400 mb-6 leading-relaxed">
            Add a validated config and scene directories under:
            <code className="bg-white/5 px-2 py-1 rounded text-blue-300 select-all block mt-3 font-mono text-sm">
              public/inference_comparison/
            </code>
          </p>
          <div className="text-left bg-black/40 p-5 rounded-xl border border-white/5 text-sm">
            <p className="text-gray-300 font-semibold mb-2">Minimal artifact layout:</p>
            <pre className="text-gray-500 font-mono leading-tight overflow-x-auto">
              public/inference_comparison/<br />
              ├── config.json<br />
              └── scene_id/<br />
                  ├── input.jpg<br />
                  ├── gt.png<br />
                  └── model.png
            </pre>
            <p className="text-gray-500 mt-4">
              See README.md for the mask encoding, config schema, validation rules, and optional provenance metadata.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const artifactSrc = (filename: string) =>
    `/api/artifact?sceneId=${encodeURIComponent(scene.id)}&filename=${encodeURIComponent(filename)}`;
  const inputSrc = artifactSrc(scene.inputImage);
  const allModels: (ModelOption & { provenance?: ArtifactProvenance })[] = [
    { name: "Ground Truth", filename: scene.groundTruth, isGroundTruth: true },
    ...scene.models.map((model) => ({
      name: model.name,
      filename: model.filename,
      provenance: model.provenance,
    })),
  ];
  const clampModelIndex = (index: number) =>
    Math.min(Math.max(index, 0), allModels.length - 1);
  const safeSelectedIndex = clampModelIndex(selectedIndex);
  const safeLeftIndex = clampModelIndex(leftIndex);
  const safeRightIndex = clampModelIndex(rightIndex);
  const getMaskSrc = (index: number) =>
    artifactSrc(allModels[clampModelIndex(index)].filename);
  const currentSceneStats = sceneStats.get(scene.id);
  const currentModel = allModels[mode === "single" ? safeSelectedIndex : safeRightIndex];
  const currentStats = !currentModel.isGroundTruth
    ? currentSceneStats?.find((stats) => stats.modelName === currentModel.name)
    : undefined;
  const statsLoading =
    !currentSceneStats && !statsRequestErrors.has(scene.id);
  const statsErrors = sceneStatsErrors.get(scene.id) ?? [];
  const statsRequestError = statsRequestErrors.get(scene.id);
  const provenanceEntries = Object.entries({
    ...scene.provenance,
    ...currentModel.provenance,
  }).filter((entry): entry is [string, string] => typeof entry[1] === "string");

  const goToScene = (idx: number) => {
    if (idx >= 0 && idx < scenes.length) {
      setSceneIndex(idx);
    }
  };

  const retryStats = () => {
    fetchedRef.current.delete(scene.id);
    setStatsRequestErrors((prev) => {
      const next = new Map(prev);
      next.delete(scene.id);
      return next;
    });
    setStatsRetryNonce((value) => value + 1);
  };

  const modelSelect = (label: string, value: number, change: (value: number) => void) => (
    <label className="model-field"><span>{label}</span><select aria-label={`${label} model`} value={value} onChange={e => change(Number(e.target.value))}>
      {allModels.map((model, i) => <option key={model.filename} value={i}>{model.name}</option>)}
    </select></label>
  );
  const maskPane = (index: number, badge: string) => <section className="image-pane" key={badge} aria-label={badge}>
    <div className="pane-heading"><span className="pane-badge">{badge}</span><span title={allModels[index].name}>{allModels[index].name}</span></div>
    <MaskCanvas zoom={zoom} ignoreIndex={config.ignoreIndex} inputImageSrc={inputSrc} maskSrc={getMaskSrc(index)} labels={config.labels} hiddenClasses={hiddenClasses} opacity={opacity} onHover={handleHover} />
  </section>;
  const percent = (value?: number) => value === undefined ? "—" : `${value.toFixed(2)}%`;

  return (
    <div className="inspection-app">
      <header className="app-header">
        <div className="app-brand"><Activity size={20}/><span>Inference checker</span><span className="local-badge">LOCAL</span></div>
        <span className="dataset-title" title={config.title}>{config.title || config.dataset || "Segmentation review"}</span>
        <button className="icon-button" aria-label="Help and provenance" onClick={() => setShowHelp(true)}><HelpCircle size={18}/></button>
      </header>
      <div className="scene-bar">
        <span className="eyebrow">SCENE</span>
        <button className="icon-button" aria-label="Previous scene" disabled={sceneIndex === 0} onClick={() => goToScene(sceneIndex - 1)}><ChevronLeft size={18}/></button>
        <select aria-label="Scene" value={sceneIndex} onChange={e => goToScene(Number(e.target.value))}>{scenes.map((s,i) => <option key={s.id} value={i}>{s.title || s.id}</option>)}</select>
        <button className="icon-button" aria-label="Next scene" disabled={sceneIndex === scenes.length - 1} onClick={() => goToScene(sceneIndex + 1)}><ChevronRight size={18}/></button>
        <span className="scene-count">{sceneIndex + 1} / {scenes.length}</span>
      </div>
      <div className="view-bar">
        <div className="mode-switch" aria-label="View mode">{([['single','Single'],['sideBySide','Compare'],['diff','Diff']] as const).map(([value,label]) => <button key={value} aria-pressed={mode === value} onClick={() => setMode(value)}>{label}</button>)}</div>
        <div className="model-fields">{mode === "single" ? modelSelect("View", safeSelectedIndex, setSelectedIndex) : <>{modelSelect("Left", safeLeftIndex, setLeftIndex)}{modelSelect("Right", safeRightIndex, setRightIndex)}</>}</div>
      </div>
      <div className="adjustment-bar">
        <label>Overlay <input aria-label="Overlay opacity" type="range" min="0" max="1" step="0.01" value={opacity} onChange={e => setOpacity(Number(e.target.value))}/><output>{Math.round(opacity*100)}%</output></label>
        <label>Zoom <input aria-label="Image zoom" type="range" min="1" max="4" step="0.25" value={zoom} onChange={e => setZoom(Number(e.target.value))}/><output>{zoom}×</output></label>
        <button onClick={() => {setZoom(1); setOpacity(0.65); setHiddenClasses(new Set());}}>Reset view</button>
        <button className="legend-toggle" aria-expanded={showLegend} onClick={() => setShowLegend(!showLegend)}>Classes ({config.labels.length})</button>
      </div>
      {(statsRequestError || statsErrors.length > 0) && <div className="error-strip" role="alert">{statsRequestError}{statsErrors.map(e => <p key={e.modelName}>{e.modelName}: {e.message}</p>)}<button onClick={retryStats}>Retry metrics</button></div>}
      <div className="inspection-workspace">
        <div className={`image-workspace ${mode === "sideBySide" ? "compare-workspace" : ""}`}>
          {mode === "single" && maskPane(safeSelectedIndex, currentModel.isGroundTruth ? "REFERENCE" : "PREDICTION")}
          {mode === "sideBySide" && <>{maskPane(safeLeftIndex, "LEFT")}{maskPane(safeRightIndex, "RIGHT")}</>}
          {mode === "diff" && <section className="image-pane"><div className="pane-heading diff-key"><span><i style={{background:'#00c850'}}/>Agree + correct</span><span><i style={{background:'#ffa500'}}/>Agree + wrong</span><span><i style={{background:'#dc2828'}}/>Disagree</span></div>
            <DiffCanvas zoom={zoom} ignoreIndex={config.ignoreIndex} ignoredClasses={ignoredClasses} inputImageSrc={inputSrc} maskSrcA={getMaskSrc(safeLeftIndex)} maskSrcB={getMaskSrc(safeRightIndex)} gtMaskSrc={artifactSrc(scene.groundTruth)} numClasses={config.labels.length} hiddenClasses={hiddenClasses} opacity={opacity} onHover={handleDiffHover}/>
          </section>}
        </div>
        <aside className={`inspector-sidebar ${showLegend ? "is-open" : ""}`} aria-label="Class inspector">
          <div className="inspector-heading"><h2>Classes <span>{config.labels.length}</span></h2><button className="legend-close icon-button" aria-label="Close classes" onClick={() => setShowLegend(false)}><X size={16}/></button></div>
          <label className="focus-field"><span>Isolate a class</span><select aria-label="Focus class" value={hiddenClasses.size === config.labels.length-1 ? config.labels.findIndex((_,i) => !hiddenClasses.has(i)) : ""} onChange={e => setHiddenClasses(e.target.value === "" ? new Set() : new Set(config.labels.map((_,i) => i).filter(i => i !== Number(e.target.value))))}><option value="">All classes</option>{config.labels.map((label,i) => <option key={label.name} value={i}>{label.readable}</option>)}</select></label>
          <ClassLegend labels={config.labels} hiddenClasses={hiddenClasses} onToggleClass={toggleClass} classIoUs={currentStats?.classIoUs}/>
          <p className="inspector-note">Click a class to toggle its overlay. Filters do not change metrics.</p>
        </aside>
      </div>
      <footer className="metrics-bar" aria-label="Scene metrics">
        <span className="metrics-source" title={currentModel.name}>{statsLoading ? "Loading metrics…" : currentModel.isGroundTruth ? "Ground truth · no model metrics" : `${mode === "single" ? "" : "Right · "}${currentModel.name}`}</span>
        <span title="Mean IoU over evaluated classes present in this scene’s ground truth">GT-present mIoU <strong>{percent(currentStats?.mIoU)}</strong></span>
        <span>Pixel accuracy <strong>{percent(currentStats?.pixelAccuracy)}</strong></span>
        <span title="Mean IoU includes prediction-only classes">Union mIoU <strong>{percent(currentStats?.unionMIoU)}</strong></span>
        {currentStats && currentStats.predictionOnlyClasses.length > 0 && <span title={currentStats.predictionOnlyClasses.map(c => `${c.readable}: ${c.predPixels} px`).join(", ")}>{currentStats.predictionOnlyClasses.length} prediction-only classes</span>}
      </footer>
      <HoverTooltip classIndex={hoverClassIndex} labels={config.labels} x={hoverX} y={hoverY} visible={hoverVisible && mode !== "diff"}/>
      <DiffTooltip info={diffHoverInfo} labels={config.labels} leftName={allModels[safeLeftIndex].name} rightName={allModels[safeRightIndex].name} x={diffHoverX} y={diffHoverY} visible={diffHoverVisible && mode === "diff"}/>
      {showHelp && <dialog ref={dialogRef} className="help-dialog" onClose={() => setShowHelp(false)} aria-labelledby="help-title">
        <div className="inspector-heading"><h2 id="help-title">Inspection guide</h2><button className="icon-button" aria-label="Close help" onClick={() => dialogRef.current?.close()}><X size={18}/></button></div>
        <div className="help-content"><p>Compare saved predictions with ground truth. Hover an image to read its class; isolate a class to inspect small regions. Zoom above 1× and scroll inside the image to pan.</p><p>Diff colors show whether the selected pair agrees and whether that agreement matches ground truth. Ignored ground-truth pixels are excluded.</p><p>Metrics describe this scene, not the full dataset. GT-present mIoU excludes classes absent from ground truth; Union mIoU includes prediction-only classes. Class recall is the fraction of ground-truth pixels recovered.</p><h3>Open another bundle</h3><code>./scripts/inspect.sh /path/to/bundle</code><p>Standalone usage and bundle preparation are documented in docs/guides/inference-checker.md. Input masks use 8-bit grayscale class IDs at the original image resolution.</p><h3>Scene / selected model provenance</h3>{provenanceEntries.length ? <dl>{provenanceEntries.map(([key,value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl> : <p>No additional provenance supplied.</p>}</div>
      </dialog>}
    </div>
  );
}
