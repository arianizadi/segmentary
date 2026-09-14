"""Plot separate cohorts from captured benchmark and validated campaign data."""
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
official = json.loads((ROOT / "official-scores.json").read_text())["scores"]
local = list(csv.DictReader((ROOT.parent / "performance-continuation-20260914/results.csv").open()))
assert len(local) == 27 and all(r["status"] == "completed" and r["final_cases"] == "42" for r in local)
local.sort(key=lambda r: float(r["final_mass_dice"]), reverse=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
fig, axes = plt.subplots(2, 1, figsize=(11, 12), gridspec_kw={"height_ratios": [1, 4]})
fig.subplots_adjust(left=.25, right=.94, top=.90, bottom=.08, hspace=.35)
fig.suptitle("Pancreatic mass segmentation: current results and reference context", x=.08, ha="left", fontsize=16, weight="bold")
fig.text(.08, .935, "Different cohorts and recipes. These panels do not establish a head-to-head performance gap.", fontsize=10)
names = ["CancerVerse (2025)", "Universal Model (2023)", "Swin_UNETR (2021)", "Isensee (2019)"]
for ax, labels, values, color, title in [
    (axes[0], names, [r["mass_l2_dice_mean"]*100 for r in official], "#BD692E", "Official hidden test: 139 examinations; four selected submissions"),
    (axes[1], [r["model"] for r in local], [float(r["final_mass_dice"])*100 for r in local], "#217B91", "Our validation: 42 examinations; scratch seed 0; 10,000 updates"),
]:
    ax.barh(labels, values, height=.65, color=color)
    ax.invert_yaxis()
    ax.set_xlim(0, 80)
    ax.set_title(title, loc="left", pad=12, weight="bold", fontsize=11)
    ax.set_xlabel("Mean mass Dice (%)")
    ax.set_axisbelow(True)
    ax.grid(axis="x", alpha=.15)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    for i, value in enumerate(values):
        ax.text(value+.65, i, f"{value:.2f}", va="center", fontsize=9)
fig.text(.08, .025, "Selected validation checkpoints. Ongoing nnU-Net ResEnc L has no final native score and is excluded.\nSource: official evaluation downloads and validated Segmentary campaign records; captured 2026-09-14.", fontsize=9, color="#454545")
fig.savefig(ROOT / "mass-dice-context.png", dpi=160)
fig.savefig(ROOT / "mass-dice-context.svg")
