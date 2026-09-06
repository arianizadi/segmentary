"use client";

import { memo, useState } from "react";

interface ClassLegendProps {
  labels: { color: [number, number, number]; name: string; readable: string }[];
  hiddenClasses: Set<number>;
  onToggleClass: (classIndex: number) => void;
  classIoUs?: { classIndex: number; iou: number; intersection?: number; gtPixels?: number }[];
}

function ClassLegend({ labels, hiddenClasses, onToggleClass, classIoUs }: ClassLegendProps) {
  const [query, setQuery] = useState("");
  const statsMap = new Map(classIoUs?.map(stats => [stats.classIndex, stats]));
  const matches = labels.map((label, index) => ({label, index})).filter(({label}) => `${label.name} ${label.readable}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="class-legend">
    <input className="class-search" aria-label="Search classes" type="search" placeholder="Search classes…" value={query} onChange={e => setQuery(e.target.value)}/>
    <div className="class-columns"><span>CLASS / VISIBILITY</span><span>IoU</span><span>Recall</span></div>
    <div className="class-list" tabIndex={0} aria-label="Class list">
      {matches.map(({label,index}) => {
        const stats = statsMap.get(index);
        const recall = stats?.gtPixels && stats.intersection !== undefined ? stats.intersection / stats.gtPixels * 100 : undefined;
        return <button type="button" key={label.name} className="class-row" aria-pressed={!hiddenClasses.has(index)} onClick={() => onToggleClass(index)} title={`${label.readable} · class ${index} · ${hiddenClasses.has(index) ? "hidden" : "visible"}`}>
          <span className="class-name"><i style={{backgroundColor: `rgb(${label.color.join(",")})`}}/><span>{label.readable}</span></span>
          <span>{stats ? `${stats.iou.toFixed(1)}%` : "—"}</span><span>{recall === undefined ? "—" : `${recall.toFixed(1)}%`}</span>
        </button>;
      })}
      {!matches.length && <p className="inspector-note">No matching classes.</p>}
    </div>
  </div>;
}
export default memo(ClassLegend);
