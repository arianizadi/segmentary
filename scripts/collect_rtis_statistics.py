"""Collect deterministic per-image RTIS evidence; never read the test split."""

from __future__ import annotations

import argparse
import csv
import gc
import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_rtis_campaign as runtime

from segmentary.config import load_experiment
from segmentary.data.loaders import aug_from_spec
from segmentary.data.transforms import build_eval_transform
from segmentary.engine.ema import ema_evaluation_safe
from segmentary.engine.inference import InferenceConfig, inference, prediction_from_inference
from segmentary.engine.metrics import ConfusionMatrix
from segmentary.eval import load_configured_checkpoint
from segmentary.models.factory import build_model
from segmentary.taxonomy import load_space
from segmentary.utils.seed import seed_everything


def matrix_metrics(matrix, names):
    metric = ConfusionMatrix(len(names), 255, device="cpu")
    metric.mat.copy_(torch.from_numpy(matrix))
    result = metric.compute().as_dict(names)
    result["confusion"] = matrix.tolist()
    return result


def mud_counts(matrix, mud):
    tp = int(matrix[mud, mud])
    support = int(matrix[mud].sum())
    predicted = int(matrix[:, mud].sum())
    total = int(matrix.sum())
    fp = predicted - tp
    fn = support - tp
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": total - tp - fp - fn,
        "support": support,
        "predicted_pixels": predicted,
        "iou": tp / (tp + fp + fn) if tp + fp + fn else None,
        "precision": tp / predicted if predicted else None,
        "recall": tp / support if support else None,
    }


def score_curve(positive, negative):
    tp = np.cumsum(positive[::-1])[::-1]
    fp = np.cumsum(negative[::-1])[::-1]
    support = int(positive.sum())
    return [
        {
            "threshold": k / 1000,
            "tp": int(tp[k]),
            "fp": int(fp[k]),
            "fn": int(support - tp[k]),
            "precision": float(tp[k] / (tp[k] + fp[k])) if tp[k] + fp[k] else None,
            "recall": float(tp[k] / support) if support else None,
        }
        for k in range(0, 1001, 10)
    ]


def collect(model, cfg, samples, split, directory, names):
    assert split in ("train", "val")
    directory.mkdir(parents=True, exist_ok=True)
    dataset = Path(cfg.stages[0].data[0].root)
    # Train images include narrow, non-stride-aligned frames never seen by the
    # standalone validation loader. Pad RGB before normalization and crop all
    # predictions back; no added pixels enter any diagnostic denominator.
    transform = build_eval_transform(
        aug_from_spec(cfg.aug, model), pad_to_multiple=32 if split == "train" else None
    )
    infer_cfg = InferenceConfig(
        sliding_window=cfg.eval.sliding_window,
        window=tuple(cfg.eval.window),
        stride=tuple(cfg.eval.stride),
        scales=(1.0,),
        flip=False,
    )
    n = len(names)
    mud = names.index("mud-pumping")
    matrices = {}
    group_matrices = {}
    rows = []
    total = np.zeros((n, n), np.int64)
    positive = np.zeros(1001, np.int64)
    negative = positive.copy()
    for sample in [s for s in samples if s["split"] == split]:
        key = sample["key"]
        group = key.split("/")[0]
        image_path = dataset / "images" / split / (key + sample["image_extension"])
        mask_path = dataset / "masks" / split / (key + ".png")
        rgb = np.array(Image.open(image_path).convert("RGB"))
        target = np.array(Image.open(mask_path))
        if (
            runtime.digest(image_path) != sample["image_sha256"]
            or hashlib.sha256(target.tobytes()).hexdigest() != sample["mask_sha256"]
        ):
            raise RuntimeError(f"Dataset content changed: {key}")
        item = transform(image=rgb, mask=target)
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            logits = inference(model, item["image"].unsqueeze(0).cuda(), n, infer_cfg)
            pred = (
                prediction_from_inference(logits.float(), infer_cfg)[0]
                .cpu()
                .numpy()
                .astype(np.uint8)
            )
            # Diagnostic normalized scores, not calibrated defect probabilities.
            scores = logits.float().softmax(1)[0, mud].cpu().numpy()
        if split == "train":
            height, width = target.shape
            pred = pred[:height, :width]
            scores = scores[:height, :width]
        if pred.shape != target.shape:
            raise RuntimeError(f"Prediction shape mismatch: {key}")
        valid = target != 255
        matrix = np.bincount(
            (target[valid].astype(np.int64) * n + pred[valid]).ravel(), minlength=n * n
        ).reshape(n, n)
        total += matrix
        matrices[key] = matrix.tolist()
        group_matrices.setdefault(group, np.zeros((n, n), np.int64))
        group_matrices[group] += matrix
        row = {"key": key, "group": group, "split": split, **mud_counts(matrix, mud)}
        per_class = matrix_metrics(matrix, names)["per_class_iou"]
        row.update({f"iou:{k}": v for k, v in per_class.items()})
        rows.append(row)
        if not np.isfinite(scores[valid]).all():
            raise RuntimeError(f"Nonfinite prediction scores: {key}")
        indices = np.clip((scores[valid] * 1000).astype(np.int64), 0, 1000)
        truth = target[valid] == mud
        positive += np.bincount(indices[truth], minlength=1001)
        negative += np.bincount(indices[~truth], minlength=1001)
        destination = directory / "predictions" / (key + ".png")
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(pred).save(destination)
        row.update(
            image_sha256=sample["image_sha256"],
            mask_decoded_sha256=sample["mask_sha256"],
            prediction_sha256=runtime.digest(destination),
        )
    with (directory / "per-image.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    groups = {
        key: {"metrics": matrix_metrics(value, names), "mud": mud_counts(value, mud)}
        for key, value in group_matrices.items()
    }
    runtime.write(directory / "per-image-confusion.json", matrices)
    (directory / "per-image-confusion.json.gz").write_bytes(
        gzip.compress(json.dumps(matrices, separators=(",", ":")).encode(), mtime=0)
    )
    runtime.write(directory / "groups.json", groups)
    runtime.write(
        directory / "mud-score-curves.json",
        {
            "score": "softmax of merged inference scores; uncalibrated; independent thresholding is not the argmax segmentation rule",
            "positive_bins": positive.tolist(),
            "negative_bins": negative.tolist(),
            "curve": score_curve(positive, negative),
        },
    )
    metrics = matrix_metrics(total, names)
    runtime.write(directory / "metrics.json", metrics)
    positive_rows = sorted([r for r in rows if r["support"]], key=lambda r: (r["iou"], r["key"]))
    negatives = sorted([r for r in rows if not r["support"]], key=lambda r: (-r["fp"], r["key"]))
    selected = {r["key"]: r for r in positive_rows[:2] + positive_rows[-2:] + negatives[:2]}
    if selected:
        sheet = Image.new("RGB", (1200, 270 * len(selected)), "white")
        draw = ImageDraw.Draw(sheet)
        lookup = {s["key"]: s for s in samples if s["split"] == split}
        for index, (key, row) in enumerate(selected.items()):
            rgb = np.array(
                Image.open(
                    dataset / "images" / split / (key + lookup[key]["image_extension"])
                ).convert("RGB")
            )
            target = np.array(Image.open(dataset / "masks" / split / (key + ".png")))
            prediction = np.array(Image.open(directory / "predictions" / (key + ".png")))
            gt = rgb.copy()
            gt[target == mud] = (gt[target == mud] * 0.4 + np.array([255, 0, 180]) * 0.6).astype(
                np.uint8
            )
            error = rgb.copy()
            for region, color in [
                ((target == mud) & (prediction == mud), [0, 220, 0]),
                ((target != mud) & (target != 255) & (prediction == mud), [255, 0, 0]),
                ((target == mud) & (prediction != mud), [255, 220, 0]),
            ]:
                error[region] = (error[region] * 0.4 + np.array(color) * 0.6).astype(np.uint8)
            for j, array in enumerate([rgb, gt, error]):
                im = Image.fromarray(array)
                im.thumbnail((395, 230))
                sheet.paste(im, (400 * j, index * 270 + 30))
            draw.text(
                (5, index * 270 + 5),
                f"{key} | mud IoU {row['iou']} | original / GT magenta / TP green, FP red, FN yellow",
                fill="black",
            )
        sheet.save(directory / "examples.jpg", quality=88)
    return {
        "split": split,
        "images": len(rows),
        "metrics": metrics,
        "mud": mud_counts(total, mud),
        "group_names": list(groups),
        "artifacts": {
            name: str(directory / name)
            for name in [
                "per-image.csv",
                "per-image-confusion.json.gz",
                "groups.json",
                "mud-score-curves.json",
                "examples.jpg",
            ]
        },
        "prediction_directory": str(directory / "predictions"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument("--job", required=True)
    ap.add_argument("--limit-per-split", type=int)
    args = ap.parse_args()
    root = args.campaign
    state = runtime.read(root / "state" / (args.job + ".json"))
    job = next(j for j in runtime.read(root / "plan.json")["jobs"] if j["name"] == args.job)
    cfg = load_experiment([Path(job["config"])])
    space = load_space(cfg.taxonomy_root, cfg.space)
    names = list(space.names)
    samples = runtime.read(Path(cfg.stages[0].data[0].root) / "audit/samples.json")
    if args.limit_per_split is not None:
        if args.limit_per_split < 1:
            raise ValueError("Limit must be positive")
        samples = [
            s
            for split in ("train", "val")
            for s in [x for x in samples if x["split"] == split][: args.limit_per_split]
        ]
    out = Path(state["checkpoints"]["best"]["path"]).parent / "diagnostics"
    results = {}
    torch.set_num_threads(4)
    for anchor, mode, splits in [
        ("best", "auto", ["train", "val"]),
        ("best", "alternate", ["val"]),
        ("final", "auto", ["val"]),
    ]:
        seed_everything(cfg.train.seed)
        model = build_model(cfg.model, space.num_classes)
        auto_ema = ema_evaluation_safe(model)
        use_ema = auto_ema if mode == "auto" else not auto_ema
        checkpoint = state["checkpoints"][anchor]
        if runtime.digest(checkpoint["path"]) != checkpoint["sha256"]:
            raise RuntimeError("Checkpoint hash changed")
        model = (
            load_configured_checkpoint(model, cfg, Path(checkpoint["path"]), use_ema).cuda().eval()
        )
        for split in splits:
            key = f"{anchor}-{mode}-{split}"
            results[key] = {
                "checkpoint_sha256": checkpoint["sha256"],
                "weights": "ema" if use_ema else "raw",
                "ema_with_uncalibrated_batchnorm": use_ema and not auto_ema,
                **collect(model, cfg, samples, split, out / key, names),
            }
        del model
        gc.collect()
        torch.cuda.empty_cache()
    selected = results["best-auto-val"]["metrics"]
    reference = state["evaluation"]["metrics"]
    if args.limit_per_split is None and not np.allclose(
        selected["confusion"], reference["confusion"], rtol=0, atol=0
    ):
        raise RuntimeError("Detailed validation does not reproduce standalone confusion matrix")
    if args.limit_per_split is None and (
        results["best-auto-train"]["images"] != 220 or results["best-auto-val"]["images"] != 37
    ):
        raise RuntimeError("Unexpected split coverage")
    runtime.write(
        out / "summary.json",
        {
            "contract": "rtis-full-statistics-v1",
            "test_evaluated": False,
            "results": results,
            "standalone_confusion_exact_match": args.limit_per_split is None,
            "smoke_limit": args.limit_per_split,
        },
    )
    print("Complete per-image, per-group, raw/EMA and final-checkpoint evidence", flush=True)


if __name__ == "__main__":
    main()
