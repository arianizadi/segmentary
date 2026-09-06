"""Inference-only RTIS validation diagnostic from existing source checkpoints.

Uses the repository's exact checkpoint loader, transforms and tiled inference.
Source class predictions are retained intact. A separate coarse diagnostic
combines vegetation/terrain into natural-surroundings and evaluates shared
classes only; it is NOT a 21-class RTIS benchmark or an anomaly detector score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from segmentary.config import load_experiment
from segmentary.data.loaders import aug_from_spec, input_normalization
from segmentary.data.transforms import build_eval_transform
from segmentary.engine.inference import InferenceConfig, inference, prediction_from_inference
from segmentary.eval import load_configured_checkpoint
from segmentary.models.factory import build_model
from segmentary.taxonomy import load_space

COMMON = [
    "road",
    "sidewalk",
    "construction",
    "fence",
    "pole",
    "traffic-light",
    "traffic-sign",
    "natural-surroundings",
    "sky",
    "person",
    "car",
    "truck",
    "on-rails",
]
COARSE = {
    "building": "construction",
    "wall": "construction",
    "human": "person",
    "rider": "person",
    "bus": "truck",
    "train": "on-rails",
    "vegetation": "natural-surroundings",
    "terrain": "natural-surroundings",
    "vegetation-overgrowth": "natural-surroundings",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def coarse_lut(classes: list[dict]) -> np.ndarray:
    lut = np.full(256, len(COMMON), np.uint8)
    for c in classes:
        name = COARSE.get(c["name"], c["name"])
        if name in COMMON:
            lut[c["id"]] = COMMON.index(name)
    return lut


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--checkpoints", type=Path, required=True)
    ap.add_argument("--taxonomy", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--device", default="cuda:0")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    schema = json.loads((args.dataset / "classes.json").read_text())
    targets = coarse_lut(schema["classes"])
    samples = [
        r
        for r in json.loads((args.dataset / "audit/samples.json").read_text())
        if r["split"] == "val"
    ]
    checkpoints = json.loads(args.checkpoints.read_text())
    cfg_infer = InferenceConfig(sliding_window=True, window=(1024, 1024), stride=(768, 768))
    summary = []
    torch.set_num_threads(4)
    for source in checkpoints:
        print(f"START {source['name']}", flush=True)
        output = args.out / source["name"]
        output.mkdir()
        ckpt = Path(source["checkpoint"])
        checksum = sha(ckpt)
        if source.get("recorded_sha256") and checksum != source["recorded_sha256"]:
            raise ValueError(f"Checkpoint hash differs from campaign: {ckpt}")
        cfg = load_experiment(
            [Path(source["config"])], overrides={"taxonomy_root": str(args.taxonomy)}
        )
        space = load_space(args.taxonomy, cfg.space)
        model = load_configured_checkpoint(
            build_model(cfg.model, space.num_classes), cfg, ckpt, False
        )
        model = model.to(args.device).eval()
        transform = build_eval_transform(aug_from_spec(cfg.aug, model))
        classes = [{"id": c.id, "name": c.name, "color": list(c.color)} for c in space.classes]
        pred_lut = coarse_lut(classes)
        palette = np.zeros((256, 3), np.uint8)
        for c in classes:
            palette[c["id"]] = c["color"]
        (output / "prediction-classes.json").write_text(json.dumps(classes, indent=2) + "\n")
        cm = np.zeros((len(COMMON) + 1, len(COMMON) + 1), np.int64)
        frame_records = []
        for row in samples:
            key = row["key"]
            image_path = args.dataset / "images/val" / (key + row["image_extension"])
            with Image.open(image_path) as im:
                rgb = np.asarray(im.convert("RGB"))
            with Image.open(args.dataset / "masks/val" / (key + ".png")) as im:
                gt = np.asarray(im)
            item = transform(image=rgb, mask=gt)
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                scores = inference(
                    model, item["image"].unsqueeze(0).to(args.device), space.num_classes, cfg_infer
                )
                prediction = (
                    prediction_from_inference(scores.float(), cfg_infer)[0]
                    .cpu()
                    .numpy()
                    .astype(np.uint8)
                )
            assert prediction.shape == gt.shape and int(prediction.max()) < space.num_classes
            dest = output / "predictions" / (key + ".png")
            dest.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(prediction).save(dest)
            preview = output / "previews" / (key + ".jpg")
            preview.parent.mkdir(parents=True, exist_ok=True)
            blended = (0.55 * rgb + 0.45 * palette[prediction]).astype(np.uint8)
            im = Image.fromarray(blended)
            im.thumbnail((960, 540))
            im.save(preview, quality=88)
            truth, pred = targets[gt], pred_lut[prediction]
            valid = truth < len(COMMON)
            n = len(COMMON) + 1
            cm += np.bincount(
                (truth[valid].astype(np.int64) * n + pred[valid]).ravel(), minlength=n * n
            ).reshape(n, n)
            frame_records.append(
                {
                    "key": key,
                    "input_sha256": sha(image_path),
                    "prediction_sha256": sha(dest),
                    "shared_pixels": int(valid.sum()),
                    "excluded_pixels": int((~valid).sum()),
                }
            )
        intersection = np.diag(cm)[: len(COMMON)]
        union = cm.sum(0)[: len(COMMON)] + cm.sum(1)[: len(COMMON)] - intersection
        support = cm.sum(1)[: len(COMMON)]
        iou = np.divide(intersection, union, out=np.zeros(len(COMMON), float), where=union > 0)
        result = {
            **source,
            "checkpoint_sha256": checksum,
            "config_sha256": sha(Path(source["config"])),
            "weights": "raw",
            "source_space": space.name,
            "target_dataset": "paul-test-rtis",
            "target_split": "val",
            "target_split_sha256": sha(args.dataset / "splits.json"),
            "inference": vars(cfg_infer),
            "normalization": input_normalization(model),
            "autocast": "bf16",
            "frames": frame_records,
            "shared_coarse_miou_on_supported_classes": float(iou[support > 0].mean()),
            "shared_coarse_pixel_accuracy": float(intersection.sum() / cm.sum()),
            "classes": [
                {
                    "name": name,
                    "target_pixels": int(support[i]),
                    "iou": float(iou[i]) if support[i] > 0 else None,
                }
                for i, name in enumerate(COMMON)
            ],
            "caveat": "Validation diagnostic only. Natural surroundings merges terrain/vegetation/overgrowth; mud, water, rail-specific targets and void excluded. Source recording overlap unverified. Not RTIS anomaly accuracy.",
            "confusion": cm.tolist(),
        }
        (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
        summary.append({k: v for k, v in result.items() if k not in ("confusion", "frames")})
        (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(
            f"DONE {source['name']} shared-coarse mIoU={result['shared_coarse_miou_on_supported_classes']:.4f}",
            flush=True,
        )
        del model
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
