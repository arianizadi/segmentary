"""Offline, evidence-bound review of medical predictions without editing annotations.

Blinding is a display aid, not an access-control boundary: the portable report includes
model identities and scores. Decisions are observations by reviewers, never new labels.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

VERDICTS = (
    "acceptable",
    "model_failure",
    "annotation_uncertain",
    "technical_issue",
    "needs_radiologist",
    "uncertain",
)
CATEGORIES = (
    "localization_miss",
    "boundary_error",
    "false_positive",
    "small_lesion",
    "low_contrast",
    "crop_exclusion",
    "annotation_ambiguity",
    "geometry",
    "other",
)
CONFIDENCES = ("low", "medium", "high")
PLANES = ("axial", "coronal", "sagittal")
_DECISION_FIELDS = {
    "case_key",
    "model_id",
    "evidence_sha256",
    "reviewer_id",
    "verdict",
    "categories",
    "confidence",
    "notes",
    "reviewed_at",
    "is_blinded",
    "revision",
}
_EXPORT_FIELDS = {
    "schema_version",
    "kind",
    "report_id",
    "report_evidence_sha256",
    "decisions",
    "summary",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any, name: str, limit: int = 256, *, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(f"Invalid {name}")
    if any(ord(c) < 32 and c not in "\n\t\r" for c in value):
        raise ValueError(f"Invalid control character in {name}")
    return value


def _image_path(value: Any) -> str:
    """Allow plain local PNG references only, without URL decoding ambiguities."""
    if not isinstance(value, str) or not value:
        raise ValueError("Panel path must be a safe relative PNG path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(c in value for c in ":\\%?#\"'<>\n\r\t")
        or any(ord(c) < 32 for c in value)
        or path.suffix.lower() != ".png"
    ):
        raise ValueError("Panel path must be a safe relative PNG path")
    return value


def _payload(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ValueError("Report must be an object")
    if (
        type(report.get("schema_version")) is not int
        or report.get("schema_version") != 1
        or report.get("kind") != "medical_failure_analysis"
    ):
        raise ValueError("Unsupported medical failure report")
    if report.get("partition") not in {"train", "val"}:
        raise ValueError("Review supports declared train or val partitions only")
    _text(report.get("report_id"), "report_id")
    models = report.get("models")
    cases = report.get("cases")
    if not isinstance(models, list) or not isinstance(cases, list):
        raise ValueError("Report models and cases must be lists")
    model_ids = []
    for model in models:
        if not isinstance(model, dict):
            raise ValueError("Invalid report model")
        model_ids.append(_text(model.get("id"), "model id"))
    if len(set(model_ids)) != len(model_ids):
        raise ValueError("Duplicate report model")
    seen = set()
    evidence = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Invalid case")
        key = _text(case.get("case_key"), "case key")
        if key in seen:
            raise ValueError("Duplicate case key")
        seen.add(key)
        results = case.get("models")
        if not isinstance(results, dict) or set(results) - set(model_ids):
            raise ValueError("Case references unknown models")
        counts: dict[str, set[int]] = {plane: set() for plane in PLANES}
        for result in results.values():
            if not isinstance(result, dict):
                raise ValueError("Invalid model result")
            panels = result.get("panels", {})
            if not isinstance(panels, dict) or set(panels) - set(PLANES):
                raise ValueError("Invalid panel planes")
            for plane, paths in panels.items():
                if not isinstance(paths, list):
                    raise ValueError("Panel references must be lists")
                for value in paths:
                    _image_path(value)
                if paths:
                    counts[plane].add(len(paths))
        if any(len(lengths) > 1 for lengths in counts.values()):
            raise ValueError("Synchronized review requires matching panel counts for each plane")
        evidence[key] = _digest(case)
    return {
        "report": report,
        "report_evidence_sha256": _digest(report),
        "case_evidence": evidence,
        "verdicts": VERDICTS,
        "categories": CATEGORIES,
        "confidences": CONFIDENCES,
        "decision_fields": sorted(_DECISION_FIELDS),
        "export_fields": sorted(_EXPORT_FIELDS),
    }


def _summary(records: list[dict[str, Any]], cases: int) -> dict[str, Any]:
    latest: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    for record in records:
        latest[(record["reviewer_id"], record["case_key"], record["model_id"])] = record
    effective = list(latest.values())
    return {
        "cases_available": cases,
        "cases_reviewed": len({row["case_key"] for row in effective}),
        "reviewers": len({row["reviewer_id"] for row in effective}),
        "effective_decisions": len(effective),
        "history_records": len(records),
        "verdict_counts": {v: sum(row["verdict"] == v for row in effective) for v in VERDICTS},
        "category_counts": {
            c: sum(c in row["categories"] for row in effective) for c in CATEGORIES
        },
        "blinded_decisions": sum(row["is_blinded"] for row in effective),
    }


def validate_decisions(report: dict[str, Any], decisions: Any) -> dict[str, Any]:
    """Validate a portable review export, preserving every ordered revision.

    Unknown fields, edited evidence, unknown cases/models, duplicate revisions and
    mismatching supplied summary counts fail closed. This does not certify the
    truth of a reviewer's clinical assessment or provide identity authentication.
    """
    payload = _payload(report)
    if not isinstance(decisions, dict):
        raise ValueError("Decisions export must be an object")
    if set(decisions) - _EXPORT_FIELDS or _EXPORT_FIELDS - {"summary"} - set(decisions):
        raise ValueError("Invalid export fields")
    if (
        type(decisions["schema_version"]) is not int
        or decisions["schema_version"] != 1
        or decisions["kind"] != "medical_failure_review_decisions"
        or decisions["report_id"] != report["report_id"]
        or decisions["report_evidence_sha256"] != payload["report_evidence_sha256"]
    ):
        raise ValueError("Decisions belong to different report evidence")
    records = decisions["decisions"]
    if not isinstance(records, list):
        raise ValueError("Decision records must be a list")
    known = {case["case_key"]: set(case["models"]) for case in report["cases"]}
    revisions: Counter[tuple[str, str, str | None]] = Counter()
    times: dict[tuple[str, str, str | None], datetime] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != _DECISION_FIELDS:
            raise ValueError("Invalid decision fields")
        case_key = _text(record["case_key"], "case_key")
        if case_key not in known:
            raise ValueError("Unknown case key")
        if record["evidence_sha256"] != payload["case_evidence"][case_key]:
            raise ValueError("Case evidence mismatch")
        model = record["model_id"]
        if model is not None and (not isinstance(model, str) or model not in known[case_key]):
            raise ValueError("Unknown model for case")
        reviewer = _text(record["reviewer_id"], "reviewer_id", 100)
        if record["verdict"] not in VERDICTS or record["confidence"] not in CONFIDENCES:
            raise ValueError("Invalid verdict or confidence")
        categories = record["categories"]
        if (
            not isinstance(categories, list)
            or any(not isinstance(c, str) or c not in CATEGORIES for c in categories)
            or len(set(categories)) != len(categories)
        ):
            raise ValueError("Invalid review categories")
        _text(record["notes"], "notes", 10000, empty=True)
        if type(record["is_blinded"]) is not bool:
            raise ValueError("is_blinded must be boolean")
        timestamp = _text(record["reviewed_at"], "reviewed_at", 64)
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", timestamp
        ):
            raise ValueError("reviewed_at must be an ISO timestamp with timezone")
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise ValueError("Invalid reviewed_at timestamp") from exc
        key = (reviewer, case_key, model)
        if type(record["revision"]) is not int or record["revision"] != revisions[key] + 1:
            raise ValueError("Duplicate or nonconsecutive decision revision")
        if key in times and parsed < times[key]:
            raise ValueError("Decision history timestamps are out of order")
        revisions[key] += 1
        times[key] = parsed
    summary = _summary(records, len(known))
    if "summary" in decisions and decisions["summary"] != summary:
        raise ValueError("Decision summary mismatch")
    return json.loads(_canonical({**decisions, "summary": summary}))


def decision_summary(report: dict[str, Any], decisions: Any) -> dict[str, Any]:
    """Return aggregate counts for latest reviewer/case/model decisions only."""
    return validate_decisions(report, decisions)["summary"]


def write_failure_review(
    output_dir: Path, report: dict[str, Any], *, filename: str = "review.html"
) -> dict[str, Any]:
    """Write one offline HTML document next to report-relative PNG evidence.

    Output must be new. PNG symlinks outside the report directory and missing
    files are rejected so the portable review cannot expose unrelated images.
    """
    payload = _payload(report)
    if Path(filename).name != filename or not filename.endswith(".html"):
        raise ValueError("Review filename must be a simple HTML filename")
    output_dir = Path(output_dir)
    root = output_dir.resolve()
    for case in report["cases"]:
        for result in case["models"].values():
            for paths in result.get("panels", {}).values():
                for value in paths:
                    image = (root / value).resolve()
                    if not image.is_relative_to(root) or not image.is_file():
                        raise ValueError(f"Missing or outside report panel: {value}")
    encoded = (
        json.dumps(payload, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / filename).open("x", encoding="utf-8") as stream:
        stream.write(_PAGE.replace("__PAYLOAD__", encoded))
    return {
        "report_id": report["report_id"],
        "report_evidence_sha256": payload["report_evidence_sha256"],
        "cases": len(report["cases"]),
        "models": len(report["models"]),
        "path": filename,
        "blinded_by_default": True,
    }


_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'">
<title>Medical failure review</title><link rel="icon" href="data:,">
<style>
*{box-sizing:border-box}body{margin:0;font:15px system-ui,sans-serif;background:#101820;color:#e4edf3}header{padding:20px;border-bottom:1px solid #38505e}h1{font-size:23px;margin:0 0 8px}h2{font-size:20px}h3{font-size:16px;margin:4px 0 10px}p{line-height:1.5}small,.muted{color:#afc1cd}button,input,select,textarea{font:inherit;background:#1d303e;border:1px solid #6f8998;color:inherit;border-radius:6px;padding:9px}button{cursor:pointer}button:hover{background:#2b4556}button:disabled{cursor:default;opacity:.5}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #94e1cc;outline-offset:2px}label{display:block;margin:10px 0 5px}input:not([type=checkbox]):not([type=range]),select,textarea{width:100%}textarea{min-height:95px}input[type=checkbox]{margin-right:8px}main{display:grid;grid-template-columns:280px minmax(0,1fr)}aside{border-right:1px solid #38505e;padding:16px;max-height:calc(100vh - 180px);overflow:auto;position:sticky;top:0}section{padding:20px;min-width:0}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.toolbar label{margin:0}.toolbar input[type=file]{max-width:260px}.queue-button{width:100%;text-align:left;margin:5px 0;overflow-wrap:anywhere}.queue-button[aria-current=true]{border-color:#94e1cc;background:#24483f}.queue-button small{display:block;margin-top:5px}.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:14px;margin:18px 0}.panel{padding:12px;background:#182631;border:1px solid #38505e;border-radius:8px;min-width:0}.panel img{display:block;width:100%;height:auto;background:#000}.panel a{color:#94e1cc}.panel pre,pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px ui-monospace,monospace}.review{border-top:1px solid #38505e;padding-top:14px;max-width:1000px}.formgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.checks{display:flex;flex-wrap:wrap;gap:8px 20px}.checks label{margin:5px 0}.notice{color:#ffe0a1}.status{min-height:1.5em}#caseTitle{overflow-wrap:anywhere}#slice{flex:1;min-width:160px}details{margin:14px 0}#summary{margin:10px 0}.visually-hidden{position:absolute;left:-10000px}@media(max-width:760px){main{display:block}aside{position:static;max-height:280px;border-bottom:1px solid #38505e}header,section{padding:14px}.formgrid{grid-template-columns:1fr}h1{font-size:20px}}
</style></head><body>
<header><h1>Medical segmentation · failure review</h1><p>Compare the same selected CT slices across models. Reference annotations are evidence to review, not unquestionable ground truth. This tool never changes labels.</p>
<div class="toolbar"><button id="reveal">Reveal model identities and scores</button><button id="export">Export review JSON</button><label for="import">Import review JSON</label><input id="import" type="file" accept="application/json,.json"></div>
<p class="muted">Offline and local only. Blinding hides labels on screen; identities remain inside this file. Use a reviewer code and avoid patient names in notes. Export a copy to preserve work across browsers.</p><div id="summary"></div><div id="globalStatus" class="status" role="status" aria-live="polite"></div></header>
<main><aside><label for="search">Search case or failure flag</label><input id="search" type="search"><label for="filter">Review queue</label><select id="filter"><option value="all">All cases</option><option value="unreviewed">Unreviewed by this reviewer</option><option value="reviewed">Reviewed by this reviewer</option><option value="flagged">Has automated flags</option><option value="panels">Has image panels</option><option value="unavailable">Missing or failed prediction</option></select><label for="flag">Specific automated flag</label><select id="flag"><option value="all">All flags</option></select><label for="reviewer">Reviewer code</label><input id="reviewer" maxlength="100" autocomplete="off" placeholder="e.g. reviewer-01"><p id="queueCount" class="muted"></p><div id="queue"></div></aside>
<section><h2 id="caseTitle">Select a case</h2><p id="caseInfo" class="muted"></p><div id="modelSelection" class="checks"></div><div class="toolbar"><label for="plane">Plane</label><select id="plane" style="width:auto"><option value="axial">Axial</option><option value="coronal">Coronal</option><option value="sagittal">Sagittal</option></select><button id="previousSlice" aria-label="Previous review slice">←</button><input id="slice" type="range" min="0" max="0" value="0" aria-label="Synchronized review slice"><button id="nextSlice" aria-label="Next review slice">→</button><span id="sliceLabel"></span></div><p class="muted">The slider selects synchronized review slices, not a complete volume. A normal-looking panel does not rule out an error elsewhere. Use the original volume viewer for full clinical review.</p><div id="panels" class="panels"></div><details><summary>Case features and protocol</summary><pre id="features"></pre></details>
<div id="reviewForm" class="review"><h3>Record an assessment</h3><div class="formgrid"><div><label for="scope">Assessment scope</label><select id="scope"></select></div><div><label for="verdict">Verdict</label><select id="verdict"></select></div><div><label for="confidence">Confidence</label><select id="confidence"></select></div></div><label>Error categories (select all that apply)</label><div id="categories" class="checks"></div><label for="notes">Evidence and notes</label><textarea id="notes" maxlength="10000" placeholder="Describe the finding and relevant review slice; avoid patient identifiers."></textarea><div class="toolbar"><button id="save">Save assessment locally</button><button id="nextCase">Next unreviewed case</button></div><p id="saveStatus" class="status" role="status" aria-live="polite"></p><details><summary>Assessment revision history</summary><pre id="history"></pre></details></div></section></main>
<script id="reviewData" type="application/json">__PAYLOAD__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('reviewData').textContent),report=data.report,cases=report.cases,models=report.models;
const el=id=>document.getElementById(id),node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
const display=value=>String(value).replaceAll('_',' '),storeKey='segmentary-medical-review:'+data.report_evidence_sha256;
const byCase=new Map(cases.map(c=>[c.case_key,c])),modelLabels=new Map(models.map((m,i)=>[m.id,'Model '+(i+1)]));
let records=[],selected=cases.find(hasPanels)?.case_key||cases[0]?.case_key||null,blinded=true,selectedModels=new Set(models.map(m=>m.id)),dirty=false,everRevealed=false,loadedReviewer='',loadedScope='';
const tuple=r=>JSON.stringify([r.reviewer_id,r.case_key,r.model_id]),label=id=>blinded?modelLabels.get(id):id;
function latest(){const result=new Map();for(const r of records)result.set(tuple(r),r);return [...result.values()]}
function counts(rows){const effective=new Map();for(const r of rows)effective.set(tuple(r),r);const values=[...effective.values()];return {cases_available:cases.length,cases_reviewed:new Set(values.map(r=>r.case_key)).size,reviewers:new Set(values.map(r=>r.reviewer_id)).size,effective_decisions:values.length,history_records:rows.length,verdict_counts:Object.fromEntries(data.verdicts.map(v=>[v,values.filter(r=>r.verdict===v).length])),category_counts:Object.fromEntries(data.categories.map(c=>[c,values.filter(r=>r.categories.includes(c)).length])),blinded_decisions:values.filter(r=>r.is_blinded).length}}
function exportObject(rows=records){return {schema_version:1,kind:'medical_failure_review_decisions',report_id:report.report_id,report_evidence_sha256:data.report_evidence_sha256,decisions:rows,summary:counts(rows)}}
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v),equal=(a,b)=>JSON.stringify(stable(a))===JSON.stringify(stable(b));
function stable(v){if(Array.isArray(v))return v.map(stable);if(object(v))return Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])]));return v}
function text(v,n,max=256,empty=false){if(typeof v!=='string'||v.length>max||(!empty&&!v.trim())||/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(v))throw Error('Invalid '+n)}
function validTimestamp(value){if(typeof value!=='string')return false;const m=value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|[+-](\d{2}):(\d{2}))$/);if(!m)return false;const y=Number(m[1]),month=Number(m[2]),day=Number(m[3]),maxDay=[31,(y%4===0&&(y%100!==0||y%400===0))?29:28,31,30,31,30,31,31,30,31,30,31][month-1];return y>0&&month>=1&&month<=12&&day>=1&&day<=maxDay&&Number(m[4])<=23&&Number(m[5])<=59&&Number(m[6])<=59&&(m[7]==='Z'||(Number(m[8])<=23&&Number(m[9])<=59))&&Number.isFinite(Date.parse(value))}
function validate(value){if(!object(value)||Object.keys(value).some(k=>!data.export_fields.includes(k))||data.export_fields.filter(k=>k!=='summary').some(k=>!(k in value)))throw Error('Invalid export fields');if(value.schema_version!==1||value.kind!=='medical_failure_review_decisions'||value.report_id!==report.report_id||value.report_evidence_sha256!==data.report_evidence_sha256)throw Error('This review belongs to different report evidence');if(!Array.isArray(value.decisions))throw Error('Decisions must be a list');const versions=new Map(),times=new Map();for(const r of value.decisions){if(!object(r)||!equal(Object.keys(r).sort(),data.decision_fields))throw Error('Invalid decision fields');text(r.case_key,'case key');const c=byCase.get(r.case_key);if(!c)throw Error('Unknown case');if(r.evidence_sha256!==data.case_evidence[r.case_key])throw Error('Case evidence mismatch');if(r.model_id!==null&&(typeof r.model_id!=='string'||!Object.hasOwn(c.models,r.model_id)))throw Error('Unknown model for case');text(r.reviewer_id,'reviewer code',100);if(!data.verdicts.includes(r.verdict)||!data.confidences.includes(r.confidence))throw Error('Invalid verdict or confidence');if(!Array.isArray(r.categories)||r.categories.some(x=>!data.categories.includes(x))||new Set(r.categories).size!==r.categories.length)throw Error('Invalid categories');text(r.notes,'notes',10000,true);if(typeof r.is_blinded!=='boolean')throw Error('Invalid blinding value');if(!validTimestamp(r.reviewed_at))throw Error('Invalid timestamp');const key=tuple(r),version=versions.get(key)||0,time=Date.parse(r.reviewed_at);if(!Number.isInteger(r.revision)||r.revision!==version+1)throw Error('Duplicate or nonconsecutive revision');if(times.has(key)&&time<times.get(key))throw Error('History timestamps out of order');versions.set(key,r.revision);times.set(key,time)}if('summary'in value&&!equal(value.summary,counts(value.decisions)))throw Error('Summary mismatch');return value.decisions}
function status(message){el('globalStatus').textContent=message}
function persist(){try{localStorage.setItem(storeKey,JSON.stringify(exportObject()));localStorage.setItem(storeKey+':reviewer',el('reviewer').value);status('Saved in this browser. Export JSON for a portable copy.')}catch{status('Browser storage is unavailable. Export JSON now to preserve this session.')}}
function currentReviews(c){return latest().filter(r=>r.case_key===c.case_key&&r.reviewer_id===el('reviewer').value.trim())}
function hasPanels(c){return Object.values(c.models).some(r=>Object.values(r.panels||{}).some(paths=>paths.length>0))}
function flags(c){return [...new Set(Object.values(c.models).flatMap(r=>r.flags||[]))]}
function filtered(){const q=el('search').value.toLowerCase(),f=el('filter').value,g=el('flag').value;return cases.filter(c=>{const reviewed=currentReviews(c).length>0,fs=flags(c),unavailable=models.some(m=>!c.models[m.id]||!['completed','ok','success'].includes(c.models[m.id].status));return(f==='all'||(f==='reviewed'&&reviewed)||(f==='unreviewed'&&!reviewed)||(f==='flagged'&&fs.length)||(f==='panels'&&hasPanels(c))||(f==='unavailable'&&unavailable))&&(g==='all'||fs.includes(g))&&JSON.stringify([c.case_key,fs]).toLowerCase().includes(q)})}
function renderQueue(){el('queue').replaceChildren();const visible=filtered();el('queueCount').textContent=visible.length+' / '+cases.length+' cases';for(const c of visible){const b=node('button',c.case_key);b.className='queue-button';b.setAttribute('aria-current',String(selected===c.case_key));b.append(node('small',(currentReviews(c).length?'Reviewed':'Unreviewed')+' · '+flags(c).length+' automated flags'));b.onclick=()=>changeCase(c.case_key);el('queue').append(b)}const s=counts(records);el('summary').textContent=report.partition+' partition · '+s.cases_reviewed+'/'+s.cases_available+' cases reviewed · '+s.effective_decisions+' current assessments · '+s.history_records+' history records'}
function confirmDiscard(){return !dirty||window.confirm('Discard unsaved assessment edits? Saved revision history is retained.')}
function changeCase(key){if(!confirmDiscard())return;selected=key;dirty=false;el('slice').value='0';renderCase();renderQueue()}
function renderModels(){el('modelSelection').replaceChildren();for(const m of models){const l=node('label'),check=node('input');check.type='checkbox';check.checked=selectedModels.has(m.id);check.onchange=()=>{check.checked?selectedModels.add(m.id):selectedModels.delete(m.id);renderPanels()};l.append(check,document.createTextNode(label(m.id)));el('modelSelection').append(l)}}
function renderPanels(){const c=byCase.get(selected),container=el('panels');container.replaceChildren();if(!c)return;const plane=el('plane').value,n=Math.max(0,...Object.values(c.models).map(r=>r.panels?.[plane]?.length||0));el('slice').max=String(Math.max(0,n-1));el('slice').value=String(Math.min(Number(el('slice').value),Math.max(0,n-1)));const index=Number(el('slice').value);el('sliceLabel').textContent=n?'Review slice '+(index+1)+' / '+n:'No panels for this plane';el('slice').disabled=n<2;el('previousSlice').disabled=index===0;el('nextSlice').disabled=index>=n-1;for(const m of models){if(!selectedModels.has(m.id))continue;const r=c.models[m.id],card=node('div');card.className='panel';card.append(node('h3',label(m.id)));const path=r?.panels?.[plane]?.[index];if(path){const img=node('img');img.src=path;img.alt=plane+' CT, reference and prediction comparison for '+label(m.id)+', review slice '+(index+1);img.loading='lazy';img.onerror=()=>{img.remove();card.append(node('p','Panel image unavailable. Do not infer an absence of errors.'))};card.append(img);const link=node('a','Open full-size panel');link.href=path;link.target='_blank';link.rel='noopener';card.append(link)}else card.append(node('p','No rendered panel available for this model and slice.'));if(!blinded&&r){card.append(node('pre',JSON.stringify({status:r.status,mass_dice:r.mass_dice,pancreas_dice:r.pancreas_dice,hd95_mm:r.hd95_mm,missed_lesions:r.missed_lesions,false_positive_lesions:r.false_positive_lesions,flags:r.flags},null,2)))}container.append(card)}}
function fillOptions(element,values){element.replaceChildren();for(const v of values){const option=node('option',display(v));option.value=v;element.append(option)}}
function loadForm(){loadedReviewer=el('reviewer').value;loadedScope=el('scope').value;dirty=false;el('saveStatus').textContent='';const scope=el('scope').value||null,reviewer=el('reviewer').value.trim(),mine=records.filter(r=>r.case_key===selected&&r.model_id===scope&&r.reviewer_id===reviewer),last=mine.at(-1);el('verdict').value=last?.verdict||'uncertain';el('confidence').value=last?.confidence||'low';el('notes').value=last?.notes||'';for(const input of el('categories').querySelectorAll('input'))input.checked=last?.categories.includes(input.value)||false;el('history').textContent=mine.length?JSON.stringify(mine.map(r=>({...r,model_id:r.model_id===null?null:label(r.model_id)})),null,2):'No saved assessment in this scope.'}
function renderCase(){const c=byCase.get(selected);el('reviewForm').hidden=!c;if(!c){el('caseTitle').textContent='No cases in this report';return}el('caseTitle').textContent=c.case_key;el('caseInfo').textContent=report.partition+' · '+c.status+' · reference = annotation; prediction = model output';el('features').textContent=JSON.stringify({features:c.features,protocol:blinded?'Hidden while blinded. Reveal identities and scores to view protocol.':report.protocol},null,2);renderModels();renderPanels();const previous=el('scope').value;el('scope').replaceChildren();const all=node('option','Case / annotation overall');all.value='';el('scope').append(all);for(const m of models){if(!Object.hasOwn(c.models,m.id))continue;const option=node('option',label(m.id));option.value=m.id;el('scope').append(option)}if([...el('scope').options].some(o=>o.value===previous))el('scope').value=previous;loadForm()}
function save(){const c=byCase.get(selected);if(!c)return;const reviewer=el('reviewer').value.trim(),scope=el('scope').value||null,mine=records.filter(r=>r.reviewer_id===reviewer&&r.case_key===selected&&r.model_id===scope),r={case_key:selected,model_id:scope,evidence_sha256:data.case_evidence[selected],reviewer_id:reviewer,verdict:el('verdict').value,categories:[...el('categories').querySelectorAll('input:checked')].map(i=>i.value),confidence:el('confidence').value,notes:el('notes').value,reviewed_at:new Date().toISOString(),is_blinded:blinded&&!everRevealed,revision:mine.length+1};try{records=validate(exportObject([...records,r]));dirty=false;persist();loadForm();el('saveStatus').textContent='Assessment revision '+r.revision+' saved. No annotations changed.';renderQueue()}catch(e){el('saveStatus').textContent=e.message}}
function mergeImport(incoming){const merged=[...records],known=new Map(records.map(r=>[tuple(r)+':'+r.revision,r]));for(const r of incoming){const key=tuple(r)+':'+r.revision;if(known.has(key)){if(!equal(known.get(key),r))throw Error('Conflicting revision: keep both exports and reconcile explicitly; nothing imported.')}else{merged.push(r);known.set(key,r)}}merged.sort((a,b)=>tuple(a).localeCompare(tuple(b))||a.revision-b.revision);return validate(exportObject(merged))}
fillOptions(el('verdict'),data.verdicts);fillOptions(el('confidence'),data.confidences);for(const category of data.categories){const l=node('label'),input=node('input');input.type='checkbox';input.value=category;l.append(input,document.createTextNode(display(category)));el('categories').append(l)}for(const f of [...new Set(cases.flatMap(flags))].sort()){const option=node('option',display(f));option.value=f;el('flag').append(option)}
try{const saved=localStorage.getItem(storeKey);if(saved)records=validate(JSON.parse(saved));el('reviewer').value=localStorage.getItem(storeKey+':reviewer')||'';everRevealed=localStorage.getItem(storeKey+':revealed')==='true'}catch(e){status('Local reviews were not loaded: '+e.message+'. Existing browser data has not been overwritten.')}
el('search').oninput=renderQueue;el('filter').onchange=renderQueue;el('flag').onchange=renderQueue;el('reviewer').onchange=()=>{if(!confirmDiscard()){el('reviewer').value=loadedReviewer;return;}loadForm();renderQueue()};el('scope').onchange=()=>{if(!confirmDiscard()){el('scope').value=loadedScope;return;}loadForm()};el('plane').onchange=()=>{el('slice').value='0';renderPanels()};el('slice').oninput=renderPanels;el('previousSlice').onclick=()=>{el('slice').value=String(Math.max(0,Number(el('slice').value)-1));renderPanels()};el('nextSlice').onclick=()=>{el('slice').value=String(Math.min(Number(el('slice').max),Number(el('slice').value)+1));renderPanels()};el('reveal').onclick=()=>{if(!confirmDiscard())return;blinded=!blinded;if(!blinded){everRevealed=true;try{localStorage.setItem(storeKey+':revealed','true')}catch{}}el('reveal').textContent=blinded?'Reveal model identities and scores':'Hide model identities and scores';renderCase();if(everRevealed)status('Identities have been revealed in this browser. Subsequent assessments are recorded as unblinded.')};el('save').onclick=save;el('nextCase').onclick=()=>{const pending=filtered().filter(c=>!currentReviews(c).length),next=pending.find(c=>c.case_key!==selected);if(next)changeCase(next.case_key);else status('No other unreviewed case in the current filter.')};for(const id of ['verdict','confidence','notes','categories'])el(id).addEventListener('input',()=>dirty=true);
el('export').onclick=()=>{if(dirty&&!window.confirm('Export saved assessments only? Unsaved form edits will not be included.'))return;try{const output=exportObject();validate(output);const blob=new Blob([JSON.stringify(output,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='medical-review-'+data.report_evidence_sha256.slice(0,12)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status('Exported '+records.length+' revision records. Keep this file with the report evidence.')}catch(e){status('Export failed: '+e.message)}};
el('import').onchange=async()=>{const file=el('import').files[0];if(!file)return;try{if(file.size>20000000)throw Error('Review file exceeds 20 MB');if(!confirmDiscard())return;const incoming=validate(JSON.parse(await file.text())),merged=mergeImport(incoming);records=merged;dirty=false;persist();renderCase();renderQueue();status('Imported and validated review history; matching revisions deduplicated.')}catch(e){status('Import rejected: '+e.message)}finally{el('import').value=''}};
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue=''}});renderCase();renderQueue();
</script></body></html>
"""
