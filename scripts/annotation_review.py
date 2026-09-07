"""Portable, read-only human review queue for annotation audits."""

from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path


def write_review(out: Path, report: dict, class_schema: dict, focus_class: str | None) -> dict:
    classes = {str(c["id"]): c["name"] for c in class_schema["classes"]}
    matches = [k for k, name in classes.items() if focus_class in (k, name)]
    if focus_class is not None and len(matches) != 1:
        raise ValueError(f"Unknown or ambiguous focus class: {focus_class}")
    focus = matches[0] if matches else None
    background = {k for k, name in classes.items() if name in {"sky", "terrain", "trackbed"}}
    rows = []
    for sample in report["samples"]:
        flags = sample.get("flags", [])
        notices = [f for f in flags if f == "source_annotation_packaging_hash_unavailable"]
        integrity = [
            f
            for f in flags
            if f not in notices
            and not f.startswith(
                ("object_class_coverage_lost:", "dominant_class:", "empty_object:")
            )
        ]
        pixels = sample.get("pixels", 0)
        source = sample.get("class_source_pixels", {}).get(focus, 0) if focus else 0
        final = sample.get("class_pixels", {}).get(focus, 0) if focus else 0
        source_fraction = source / pixels if pixels else 0
        final_fraction = final / pixels if pixels else 0
        reasons = []
        if focus and source_fraction >= 0.98:
            reasons.append("Focus class covers at least 98% of the original image")
        if focus and final_fraction >= 0.5:
            reasons.append("Focus class covers at least 50% of the training image")
        losses = []
        other_loss = False
        for obj in sample.get("objects", []):
            if (obj.get("lost_fraction") or 0) < 0.5:
                continue
            cid = str(obj["class_id"])
            other_loss |= cid not in background
            if cid != focus:
                continue
            recipients = [
                {
                    "class": classes.get(str(e["to_class"]), str(e["to_class"])),
                    "pixels": e["pixels"],
                }
                for e in sample.get("overwrite_events", [])
                if e["from_object"] == obj["id"]
            ]
            losses.append(
                {
                    "object_id": obj["id"],
                    "source_pixels": obj["source_pixels"],
                    "lost_pixels": obj["cross_class_lost_pixels"],
                    "lost_fraction": obj["lost_fraction"],
                    "recipients": recipients,
                }
            )
        if losses:
            reasons.append("Focus object loses at least 50% of its original class coverage")
        if focus and source > 0 and final == 0:
            reasons.append("Focus class present in source but absent in training mask")
        priority = (
            "integrity"
            if integrity
            else "focus"
            if reasons
            else "other"
            if other_loss or any(f.startswith("empty_object:") for f in flags)
            else "context"
            if len(flags) > len(notices)
            else "notices"
            if notices
            else "clear"
        )
        preview = sample.get("preview", "")
        if preview and (
            Path(preview).is_absolute()
            or ".." in Path(preview).parts
            or ":" in preview
            or "\\" in preview
        ):
            raise ValueError("Review preview must be a safe relative path")
        rows.append(
            {
                "key": sample["key"],
                "split": sample["split"],
                "priority": priority,
                "reasons": reasons,
                "flags": flags,
                "notices": notices,
                "integrity": integrity,
                "source_fraction": source_fraction,
                "final_fraction": final_fraction,
                "losses": losses,
                "preview": preview,
                "mask_sha256": sample.get("mask_file_sha256"),
                "annotation_sha256": sample.get("annotation_sha256"),
            }
        )
    order = {
        p: i for i, p in enumerate(["integrity", "focus", "other", "context", "notices", "clear"])
    }
    rows.sort(key=lambda r: (order[r["priority"]], -r["source_fraction"], r["key"]))
    fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    summary = {
        "focus_class": classes.get(focus) if focus is not None else None,
        "images": len(rows),
        "priority_counts": {p: sum(r["priority"] == p for r in rows) for p in order},
        "source_full_frame_candidates": sum(r["source_fraction"] >= 0.98 for r in rows),
        "final_broad_coverage_candidates": sum(r["final_fraction"] >= 0.5 for r in rows),
        "fingerprint": fingerprint,
    }
    with (out / "review-ranked.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            lineterminator="\n",
            fieldnames=[
                "key",
                "split",
                "priority",
                "source_fraction",
                "final_fraction",
                "reasons",
                "flags",
                "mask_sha256",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: "; ".join(row[k]) if isinstance(row[k], list) else row[k]
                    for k in writer.fieldnames
                }
            )
    payload = (
        json.dumps({"rows": rows, "summary": summary}, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    page = _PAGE.replace("__DATA__", payload).replace(
        "__TITLE__", html.escape(classes[focus] if focus is not None else "All classes")
    )
    (out / "index.html").write_text(page)
    (out / "review-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


_PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Annotation review</title><link rel="icon" href="data:,">
<style>*{box-sizing:border-box}body{margin:0;font:14px system-ui;background:#11191f;color:#e3ecee;height:100dvh;display:flex;flex-direction:column}header{padding:16px;border-bottom:1px solid #39464c}h1{font-size:20px;margin:0 0 8px}p{margin:5px 0;color:#b4c8cc}main{display:grid;grid-template-columns:310px 1fr;min-height:0;flex:1}aside{padding:12px;overflow:auto;border-right:1px solid #39464c}section{padding:16px;overflow:auto;min-width:0}input,select,button,textarea{font:inherit;padding:9px;background:#203039;color:inherit;border:1px solid #60717a;border-radius:5px}input,select,textarea{width:100%;margin-bottom:8px}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #96d9c6}#queue button{display:block;width:100%;text-align:left;margin:6px 0;overflow-wrap:anywhere}#queue button[aria-current=true]{border-color:#96d9c6;background:#29453f}small{display:block;color:#bdd0d5}img{width:100%;height:auto;max-height:58vh;object-fit:contain;background:#05090b}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px system-ui}#summary{font-size:12px;overflow-wrap:anywhere}h2{overflow-wrap:anywhere}label{display:block;margin:8px 0 4px}@media(max-width:700px){main{grid-template-columns:1fr;grid-template-rows:30% 70%}aside{border-bottom:1px solid #39464c}header{padding:8px}img{max-height:40vh}}</style>
<header><h1>Annotation review · __TITLE__</h1><p>Review candidates are not confirmed annotation errors. No labels are changed.</p><div id="summary"></div><button id="export">Export review decisions</button></header>
<main><aside><label for="search">Search image or reason</label><input id="search" type="search"><label for="filter">Queue</label><select id="filter"><option value="all">All images</option><option value="integrity">Integrity failures</option><option value="focus">Focus class candidates</option><option value="other">Other object loss</option><option value="context">Background / coverage context</option><option value="notices">Provenance notices only</option><option value="clear">No current flags</option></select><div id="queue"></div></aside><section id="detail"></section></main>
<script id="data" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent),rows=data.rows,key='annotation-review:'+data.summary.fingerprint;let decisions={},selected=null;try{decisions=JSON.parse(localStorage.getItem(key)||'{}')}catch{};
const el=id=>document.getElementById(id), node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
el('summary').textContent=rows.length+' images · '+Object.entries(data.summary.priority_counts).map(([name,count])=>count+' '+({integrity:'integrity failures',focus:'focus candidates',other:'other object loss',context:'background / coverage',notices:'provenance notices',clear:'without flags'}[name])).join(' · ');
function renderQueue(){const q=el('search').value.toLowerCase(),filter=el('filter').value;el('queue').replaceChildren();for(const r of rows.filter(r=>(filter==='all'||r.priority===filter)&&JSON.stringify([r.key,r.reasons,r.flags]).toLowerCase().includes(q))){const b=node('button',r.key);b.append(node('small',r.split+' · '+r.priority+(decisions[r.key]?' · '+decisions[r.key].verdict:'')));b.setAttribute('aria-current',String(selected===r.key));b.onclick=()=>show(r);el('queue').append(b)}}
function show(r){selected=r.key;const d=el('detail');d.replaceChildren(node('h2',r.key),node('p',r.split+' · '+r.priority));if(data.summary.focus_class)d.append(node('p','Focus coverage: original union '+(100*r.source_fraction).toFixed(2)+'% · training '+(100*r.final_fraction).toFixed(2)+'%'));for(const reason of r.reasons)d.append(node('p',reason));if(r.preview){const img=node('img');img.src=r.preview;img.alt='Labeled annotation comparison for '+r.key;d.append(img);const a=node('a','Open full-size comparison');a.href=r.preview;a.target='_blank';a.rel='noopener';a.style.color='#96d9c6';d.append(a)}const details=node('details');details.append(node('summary','Full evidence and original flags'),node('pre',JSON.stringify({flags:r.flags,notices:r.notices,losses:r.losses,mask_sha256:r.mask_sha256},null,2)));d.append(details);const label=node('label','Human review verdict'),select=node('select');select.id='verdict';label.htmlFor=select.id;for(const [v,t] of [['unreviewed','Unreviewed'],['expected','Expected annotation / occlusion'],['needs_definition','Needs class-definition review'],['correction_needed','Correction needed'],['uncertain','Uncertain']]){const o=node('option',t);o.value=v;select.append(o)}select.value=decisions[r.key]?.verdict||'unreviewed';const noteLabel=node('label','Review notes'),notes=node('textarea');notes.id='notes';noteLabel.htmlFor='notes';notes.value=decisions[r.key]?.notes||'';const save=node('button','Save review locally'),status=node('p');save.onclick=()=>{decisions[r.key]={key:r.key,split:r.split,mask_sha256:r.mask_sha256,annotation_sha256:r.annotation_sha256,verdict:select.value,notes:notes.value,evidence:{priority:r.priority,reasons:r.reasons,source_fraction:r.source_fraction,final_fraction:r.final_fraction,losses:r.losses},reviewed_at:new Date().toISOString()};try{localStorage.setItem(key,JSON.stringify(decisions));status.textContent='Saved in this browser. Export decisions to keep a portable copy.'}catch{status.textContent='Browser storage unavailable. Export decisions now to preserve them.'}renderQueue()};d.append(label,select,noteLabel,notes,save,status);renderQueue()}
el('search').oninput=renderQueue;el('filter').onchange=renderQueue;el('export').onclick=()=>{const blob=new Blob([JSON.stringify({schema_version:1,audit_fingerprint:data.summary.fingerprint,decisions:Object.values(decisions)},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='annotation-review-decisions.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};renderQueue();if(rows.length)show(rows[0]);
</script></html>"""
