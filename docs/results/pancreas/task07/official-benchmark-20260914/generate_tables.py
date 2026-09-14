"""Render tables from captured official metrics and validated campaign records."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
official = json.loads((ROOT / "official-scores.json").read_text())
local_path = ROOT.parent / "performance-continuation-20260914/results.csv"
local = list(csv.DictReader(local_path.open()))
assert len(local) == 27
assert all(r["status"] == "completed" and r["final_cases"] == "42" for r in local)
lines = ["# Exact official test scores", "", "All values are percentages; these are four selected submissions on 139 official test examinations.", "", "| Submission | Mean mass Dice | Median mass Dice | Mass Dice IQR | Pancreas L1 Dice | Mass NSD | Zero mass Dice |", "| --- | ---: | ---: | --- | ---: | ---: | ---: |"]
for r in official["scores"]:
    url = "https://decathlon-10.grand-challenge.org/evaluation/" + r["evaluation_id"] + "/"
    lines.append(f"| [{r['name']}]({url}) | {r['mass_l2_dice_mean']*100:.2f} | {r['mass_l2_dice_median']*100:.2f} | {r['mass_l2_dice_q25']*100:.2f}-{r['mass_l2_dice_q75']*100:.2f} | {r['pancreas_l1_dice_mean']*100:.2f} | {r['mass_l2_nsd_mean']*100:.2f} | {r['mass_l2_dice_zero_cases']}/139 |")
lines += ["", "# Our completed 10,000-update screening runs", "", "These use 197 training and 42 validation examinations, one scratch seed, and a selected validation checkpoint. Pancreas here means labels 1 OR 2. Do not rank this table together with the official test table. Our ongoing official-backend ResEnc L run has no final native score yet.", "", "| Model | Mass Dice | Pancreas union Dice |", "| --- | ---: | ---: |"]
for r in local:
    lines.append(f"| [{r['model']}](../performance-continuation-20260914/models/{r['id']}.md) | {float(r['final_mass_dice'])*100:.2f} | {float(r['final_pancreas_dice'])*100:.2f} |")
lines += ["", "Source CSV SHA256: `" + hashlib.sha256(local_path.read_bytes()).hexdigest() + "`.", "", "The local table is generated from the campaign's validated final-evaluation records, not patch-level training estimates. See [interpretation and limitations](README.md).", ""]
(ROOT / "tables.md").write_text("\n".join(lines))
