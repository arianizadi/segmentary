import csv
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent.parent
out = root / "convergence-review-20260914"
records = [
    json.loads(p.read_text())
    for p in sorted((root / "recipe-ablation-20260914/records").glob("*.json"))
]
fig, axs = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
summary = []
for r in records:
    name = r["id"].removeprefix("dynunet-").removesuffix("-seed0")
    cs = r["curves"]
    vs = [x for x in cs if x.get("mass_dice") is not None]
    b = max(vs, key=lambda x: x["mass_dice"])
    x = [v["step"] for v in cs]
    sm = [statistics.mean(v["loss"] for v in cs[max(0, i - 4) : i + 1]) for i in range(len(cs))]
    axs[0, 0].plot(x, sm, label=name)
    axs[0, 1].plot([v["step"] for v in vs], [100 * v["mass_dice"] for v in vs], ".-", label=name)
    axs[1, 0].plot(
        [v["step"] for v in vs], [100 * v["pancreas_dice"] for v in vs], ".-", label=name
    )
    rows = [
        v
        for v in csv.DictReader((root / "recipe-ablation-20260914/validation-cases.csv").open())
        if v["run_id"] == r["id"] and int(v["step"]) == b["step"]
    ]
    ds = [float(v["mass_dice"]) for v in rows]
    summary.append(
        {
            "arm": name,
            "best_step": b["step"],
            "best_mass_dice": b["mass_dice"],
            "last_mass_dice": vs[-1]["mass_dice"],
            "best_pancreas_dice": b["pancreas_dice"],
            "loss_6001_8000": statistics.mean(v["loss"] for v in cs[60:80]),
            "loss_8001_10000": statistics.mean(v["loss"] for v in cs[80:]),
            "zero_overlap_cases": sum(v == 0 for v in ds),
            "below_01_cases": sum(v < 0.1 for v in ds),
        }
    )
axs[1, 1].plot(x, [v["learning_rate"] for v in records[0]["curves"]], color="black")
for ax, title, y in zip(
    axs.flat,
    [
        "Training loss: trailing 5-epoch mean",
        "Validation mass Dice: all 42 scans",
        "Validation pancreas-union Dice",
        "Shared learning-rate schedule",
    ],
    ["CE + foreground Dice loss", "Dice (%)", "Dice (%)", "Learning rate"], strict=False,
):
    ax.set(title=title, xlabel="Optimizer updates", ylabel=y)
    ax.grid(alpha=0.2)
axs[0, 1].legend(ncol=2, fontsize=9)
fig.suptitle(
    "DynUNet recipe screen: no early stopping; all arms reached 10,000 updates", fontsize=14
)
fig.savefig(out / "curves.png", dpi=160)
(out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
