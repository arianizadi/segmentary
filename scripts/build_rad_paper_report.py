"""Build a hash-verified, three-seed RAD paper report from completed test evidence."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image, ImageOps

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
from scripts.rad_paper_metrics import paper_metrics, seed_summary
from scripts.run_rad_test import digest, result_complete, validate_request, write
from scripts.run_rad_test_profiles import result_complete as profile_complete

LIMITATIONS = [
    "Seeds measure RAD adaptation variation conditional on the frozen source training runs and these test images. Sample SD uses ddof=1. Seed labels do not establish paired data orders.",
    "The held-out test set was historically exposed. Scene blocks are visually inferred, with original recording provenance unconfirmed. Seed SD does not estimate test sampling uncertainty.",
    "Every prespecified initialization recipe and seed is retained. The headline uses the common recipe frozen before test evaluation. Rankings describe the observed means.",
    "Auto weights use EMA where running-stat BatchNorm permits it and raw weights otherwise. EMA retains a long history within the 4000-step budget. The initialization recipes also retain their prescribed learning-rate differences.",
    "Recipe initialization includes architecture-specific public supervision. EoMT's COCO-panoptic checkpoint and ImageNet-initialized encoders carry different upstream supervision and compute. The comparison describes complete initialization recipes.",
    "Model-only FPS measures batch-one BF16 1024-square dense-logit forwards. Native-pipeline timing includes the independently recorded full-image inference contract. Allocator peak, process memory and resident parameter bytes have separate denominators.",
    "Per-block and leave-one-block-out results are descriptive. Each block has its own class support. Four scene blocks provide limited evidence about new recordings.",
]


def verified_json(path: Path, expected: str) -> dict:
    if digest(path) != expected:
        raise ValueError(f"Artifact SHA-256 changed: {path}")
    return json.loads(path.read_text())


def nullable_summary(values: dict[int, float | None]) -> dict:
    if all(value is None for value in values.values()):
        return {
            "seeds": {str(seed): None for seed in values},
            "mean": None,
            "sample_sd": None,
            "n": 0,
        }
    if any(value is None for value in values.values()):
        raise ValueError("A metric has inconsistent support across the three seeds")
    return seed_summary(values)


def class_split_support(samples: list[dict], names: list[str]) -> dict:
    """Count label support on both sides from the hashed, mask-derived sample audit."""
    totals = {}
    classes = {name: {} for name in names}
    for split in ("train", "test"):
        selected = [sample for sample in samples if sample["split"] == split]
        pixels = np.zeros(len(names), dtype=np.int64)
        positives = np.zeros(len(names), dtype=np.int64)
        for sample in selected:
            counts = np.zeros(len(names), dtype=np.int64)
            if "class_pixels" not in sample:
                raise ValueError("Class support requires mask-derived audited class_pixels")
            for label, count in sample["class_pixels"].items():
                label = int(label)
                if type(count) is not int or count < 0 or label not in {*range(len(names)), 255}:
                    raise ValueError("Audited class support contains invalid labels or counts")
                if label != 255:
                    counts[label] += count
            pixels += counts
            positives += counts > 0
        missing = [name for name, count in zip(names, positives, strict=True) if count == 0]
        if missing:
            raise ValueError(f"Every class requires positive {split} support; missing {missing}")
        valid_pixels = int(pixels.sum())
        totals[split] = {"images": len(selected), "valid_pixels": valid_pixels}
        for index, name in enumerate(names):
            classes[name][split] = {
                "positive_images": int(positives[index]),
                "positive_image_fraction": int(positives[index]) / len(selected),
                "pixels": int(pixels[index]),
                "valid_pixel_fraction": int(pixels[index]) / valid_pixels,
            }
    return {"totals": totals, "classes": classes}


def aggregate(runs: list[dict], names: list[str]) -> list[dict]:
    groups = {}
    for run in runs:
        key = run["model"], run["protocol"]
        if run["seed"] in groups.setdefault(key, {}):
            raise ValueError("Duplicate model/recipe/seed result")
        groups[key][run["seed"]] = run
    result = []
    for (model, protocol), seeds in groups.items():
        if sorted(seeds) != [0, 1, 2]:
            raise ValueError(f"Incomplete three-seed recipe: {model}/{protocol}")

        def summary(getter, current=seeds):
            return nullable_summary({seed: getter(run) for seed, run in current.items()})

        classes = {}
        for name in names:
            support = [
                run["metrics"]["pixel_pooled"]["per_class"][name]["pixels"]
                for run in seeds.values()
            ]
            positive = [
                run["metrics"]["class_positive_images"]["per_class"][name]["positive_images"]
                for run in seeds.values()
            ]
            if (
                len(set(support)) != 1
                or len(set(positive)) != 1
                or min(support) <= 0
                or min(positive) <= 0
            ):
                raise ValueError(
                    f"All 21 classes require matching nonzero ground-truth support: {name}"
                )
            classes[name] = {
                "pixels": support[0],
                "positive_images": positive[0],
                **{
                    metric: summary(
                        lambda run, field=metric, label=name: run["metrics"]["pixel_pooled"][
                            "per_class"
                        ][label][field]
                    )
                    for metric in ("iou", "precision", "recall", "dice")
                },
                "negative_image_false_alarm_rate": summary(
                    lambda run, label=name: run["metrics"]["negative_images"][label][
                        "image_false_alarm_rate_any_pixel"
                    ]
                ),
                "positive_image_iou": summary(
                    lambda run, label=name: run["metrics"]["class_positive_images"]["per_class"][
                        label
                    ]["mean_image_iou"]
                ),
                "negative_image_false_alarm_rate_area": summary(
                    lambda run, label=name: run["metrics"]["negative_images"][label][
                        "image_false_alarm_rate_0_1_percent_area"
                    ]
                ),
            }
        result.append(
            {
                "model": model,
                "protocol": protocol,
                "pixel_pooled_miou": summary(lambda run: run["metrics"]["pixel_pooled"]["miou"]),
                "class_positive_image_miou": summary(
                    lambda run: run["metrics"]["class_positive_images"]["miou"]
                ),
                "model_only_fps": summary(
                    lambda run: run["performance"]["measurements"]["latency"]["fps"]
                ),
                "native_pipeline_fps": summary(
                    lambda run: run["performance"]["native_pipeline"]["measurements"]["latency"][
                        "fps"
                    ]
                ),
                "allocator_peak_bytes": summary(
                    lambda run: run["performance"]["measurements"]["peak_reserved_bytes"]
                ),
                "process_total_bytes": summary(
                    lambda run: run["performance"]["measurements"]["process_total_bytes"]
                ),
                "native_allocator_peak_bytes": summary(
                    lambda run: run["performance"]["native_pipeline"]["measurements"][
                        "peak_reserved_bytes"
                    ]
                ),
                "parameter_count": summary(
                    lambda run: run["performance"]["model"]["parameter_count"]
                ),
                "resident_parameter_bytes": summary(
                    lambda run: run["performance"]["model"]["resident_parameter_bytes"]
                ),
                "training_peak_bytes": summary(
                    lambda run: max(
                        run["training"].get("peak_vram_bytes", {}).values(), default=None
                    )
                ),
                "training_hours": summary(
                    lambda run: (
                        run["training_resources"]
                        .get("phase_wall_seconds_including_failed_attempts", {})
                        .get("training", None)
                        / 3600
                        if run["training_resources"]
                        .get("phase_wall_seconds_including_failed_attempts", {})
                        .get("training")
                        is not None
                        else None
                    )
                ),
                "training_hours_is_lower_bound": any(
                    run["training_resources"]
                    .get("phase_wall_seconds_are_lower_bounds", {})
                    .get("training", False)
                    for run in seeds.values()
                ),
                "per_class": classes,
            }
        )
    return result


def load_source_stage_report(request: dict) -> dict:
    from scripts.evaluate_rad_source_stages import load_verified_report

    pointer = request["research_protocol"]["source_stage_reports"]
    spec_path = Path(pointer["spec"])
    spec = verified_json(spec_path, pointer["spec_sha256"])
    artifact = request["source_stage_reports"]
    expected_path = Path(spec["output_root"]) / "source-stage-reports.json"
    if Path(artifact["path"]).resolve() != expected_path.resolve():
        raise ValueError("Source-stage report path differs from its frozen request")
    recorded = verified_json(expected_path, artifact["sha256"])
    if recorded != load_verified_report(spec_path, REPO):
        raise ValueError("Source-stage report differs from its verified native-stage artifacts")
    if {value["model"] for value in recorded["models"]} != set(
        request["research_protocol"]["models"]
    ):
        raise ValueError("Source-stage report lacks the complete prespecified model set")
    for model in recorded["models"]:
        if [stage["stage"] for stage in model["stages"]] != [
            "cityscapes",
            "cityscapes_to_railsem19",
        ]:
            raise ValueError("Each model requires both verified native source stages")
    return recorded


def load_report(request_path: Path) -> dict:
    request, policy, request_sha = validate_request(request_path)
    if request["schema_version"] != 2:
        raise ValueError("The paper report requires a complete-run-set schema-2 request")
    protocol = request["research_protocol"]
    if protocol["primary_metric"] != "pixel_pooled_miou" or protocol["qualitative_seed"] != 0:
        raise ValueError("The report requires pooled primary mIoU and frozen qualitative seed 0")
    source_stages = load_source_stage_report(request)
    root = Path(request["dataset_root"])
    samples = verified_json(root / "audit/samples.json", request["samples_sha256"])
    classes = sorted(
        verified_json(root / "classes.json", request["classes_sha256"])["classes"],
        key=lambda value: value["id"],
    )
    names = request["class_names"]
    if [value["name"] for value in classes] != names:
        raise ValueError("Report palette differs from the frozen class order")
    splits = verified_json(root / "splits.json", request["split_sha256"])
    if len({sample["key"] for sample in samples}) != len(samples):
        raise ValueError("Sample audit contains duplicate image keys")
    for split in ("train", "val", "test"):
        if {sample["key"] for sample in samples if sample["split"] == split} != set(splits[split]):
            raise ValueError("Sample audit membership differs from the frozen split")
    split_support = class_split_support(samples, names)
    test_samples = {sample["key"]: sample for sample in samples if sample["split"] == "test"}
    if not set(protocol["qualitative_keys"]) <= set(test_samples):
        raise ValueError("Qualitative keys differ from frozen test membership")
    output = Path(request["output_root"])
    deployment = output.parent / "deployment-performance"
    expected_gpu = next(
        entry["uuid"] for entry in policy["allowed"] if entry["index"] == request["benchmark_gpu"]
    )
    runs = []
    for job in request["jobs"]:
        if not result_complete(output, job, request_sha, names):
            raise ValueError(f"Incomplete test result: {job['name']}")
        if not profile_complete(deployment, job, request_sha, names):
            raise ValueError(f"Incomplete deployment profile: {job['name']}")
        directory = output / job["name"]
        source = json.loads((directory / "result.json").read_text())
        if any(
            source.get(field) != job[field]
            for field in ("name", "model", "protocol", "seed", "config_sha256")
        ):
            raise ValueError("Test result identity differs from the prespecified run")
        profile = json.loads((deployment / job["name"] / "result.json").read_text())
        performance = profile["performance"]
        if performance["source"]["source_test_result_sha256"] != digest(directory / "result.json"):
            raise ValueError("Deployment profile is bound to a different test result")
        if performance["hardware"]["gpu_uuid"] != expected_gpu:
            raise ValueError("Deployment profiles must use the frozen common benchmark GPU")
        native = performance.get("native_pipeline", {})
        latency = native.get("measurements", {}).get("latency", {})
        timings = native.get("per_image", native.get("measurements", {}).get("per_image", []))
        if {row["key"] for row in timings} != set(test_samples) or len(timings) != len(
            test_samples
        ):
            raise ValueError("Native-pipeline timing lacks complete test-image coverage")
        if not math.isfinite(latency.get("fps", 0)) or latency.get("fps", 0) <= 0:
            raise ValueError("Native-pipeline timing requires positive finite FPS")
        artifact = source["artifacts"].get("paper-metrics.json")
        if not artifact:
            raise ValueError("Missing recomputable paper-metrics.json artifact")
        metrics = verified_json(Path(artifact["path"]), artifact["sha256"])
        confusion_artifact = source["artifacts"]["per-image-confusion.json.gz"]
        matrices = json.loads(gzip.decompress(Path(confusion_artifact["path"]).read_bytes()))
        if set(matrices) != set(test_samples):
            raise ValueError("Per-image confusion evidence differs from the complete test set")
        matrices = {key: np.asarray(value, dtype=np.int64) for key, value in matrices.items()}
        expected = paper_metrics(
            matrices, names, {key: sample["group"] for key, sample in test_samples.items()}
        )
        if metrics != expected:
            raise ValueError("Paper metrics differ from the per-image confusion evidence")
        runs.append(
            {
                **{
                    key: job[key]
                    for key in (
                        "name",
                        "model",
                        "protocol",
                        "seed",
                        "config_sha256",
                        "final_checkpoint_sha256",
                        "state_sha256",
                    )
                },
                "weights": source["weights"],
                "source_checkpoint": job.get("source_checkpoint"),
                "training": json.loads(Path(job["state_path"]).read_text()).get("training", {}),
                "training_resources": json.loads(Path(job["state_path"]).read_text())
                .get("collection", {})
                .get("resources", {}),
                "metrics": metrics,
                "performance": performance,
                "provenance": {
                    "test_result": str(directory / "result.json"),
                    "test_result_sha256": digest(directory / "result.json"),
                    "deployment_result": str(deployment / job["name"] / "result.json"),
                    "deployment_result_sha256": digest(deployment / job["name"] / "result.json"),
                    "paper_metrics": artifact,
                    "source_state": job["state_path"],
                },
            }
        )
    aggregates = aggregate(runs, names)
    headline = sorted(
        [row for row in aggregates if row["protocol"] == protocol["headline_protocol"]],
        key=lambda row: (-row["pixel_pooled_miou"]["mean"], row["model"]),
    )
    if {row["model"] for row in headline} != set(protocol["models"]):
        raise ValueError("Headline recipe lacks all prespecified models")
    coverage = {
        name: {key: headline[0]["per_class"][name][key] for key in ("pixels", "positive_images")}
        for name in names
    }
    if any(
        {name: {key: row["per_class"][name][key] for key in coverage[name]} for name in names}
        != coverage
        for row in aggregates
    ):
        raise ValueError("Test class support differs across models or initialization recipes")
    if any(
        coverage[name]
        != {
            field: split_support["classes"][name]["test"][field]
            for field in ("positive_images", "pixels")
        }
        for name in names
    ):
        raise ValueError("Test class support differs between sample audit and confusion evidence")
    missing = []
    for run in runs:
        if not run["training"].get("env", {}).get("model_origins"):
            missing.append(
                run["name"] + " public checkpoint origins and revisions must be collected"
            )
        if not run["training"].get("config", {}).get("optim"):
            missing.append(run["name"] + " optimizer recipe must be collected")
    for entry in aggregates:
        for field in ("training_peak_bytes", "training_hours"):
            if entry[field]["mean"] is None:
                missing.append(
                    entry["model"] + "/" + entry["protocol"] + " " + field + " must be collected"
                )
    return {
        "schema_version": 1,
        "request": str(request_path.resolve()),
        "request_sha256": request_sha,
        "training_plan_sha256": request["training_plan_sha256"],
        "training_campaign_sha256": request["training_campaign_sha256"],
        "training_code_sha": request["training_code_sha"],
        "split_sha256": request["split_sha256"],
        "samples_sha256": request["samples_sha256"],
        "research_protocol": protocol,
        "class_names": names,
        "class_coverage": coverage,
        "class_split_support": split_support["classes"],
        "split_totals": split_support["totals"],
        "test_images": len(test_samples),
        "runs": runs,
        "aggregates": aggregates,
        "headline_order": [row["model"] for row in headline],
        "limitations": LIMITATIONS,
        "missing_provenance": missing,
        "source_stage_reports": source_stages,
        "qualitative": {
            "seed": protocol["qualitative_seed"],
            "keys": protocol["qualitative_keys"],
            "selection": "prespecified from ground truth before final-fit training",
        },
    }


def format_summary(value: dict, scale: float = 100) -> str:
    if value["mean"] is None:
        return "N/A"
    return f"{scale * value['mean']:.2f}\nSD {scale * value['sample_sd']:.2f}"


def write_csv(path: Path, report: dict) -> None:
    rows = []
    for entry in report["aggregates"]:
        row = {"model": entry["model"], "protocol": entry["protocol"], "seeds": "0,1,2"}
        for metric in (
            "pixel_pooled_miou",
            "class_positive_image_miou",
            "model_only_fps",
            "native_pipeline_fps",
            "allocator_peak_bytes",
            "process_total_bytes",
            "resident_parameter_bytes",
        ):
            for statistic in ("mean", "sample_sd", "minimum", "maximum"):
                row[f"{metric}:{statistic}"] = entry[metric].get(statistic)
            for seed, value in entry[metric]["seeds"].items():
                row[f"{metric}:seed_{seed}"] = value
        for name, metrics in entry["per_class"].items():
            row[f"positive_images:{name}"] = metrics["positive_images"]
            row[f"pixels:{name}"] = metrics["pixels"]
            for metric in ("iou", "precision", "recall", "dice", "negative_image_false_alarm_rate"):
                for statistic in ("mean", "sample_sd"):
                    row[f"{metric}:{name}:{statistic}"] = metrics[metric][statistic]
        rows.append(row)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def semantic_panel(
    request: dict, job: dict, key: str, classes: list[dict], sample: dict
) -> io.BytesIO:
    root = Path(request["dataset_root"])
    source = root / "images/test" / (key + sample["image_extension"])
    if digest(source) != sample["image_sha256"]:
        raise ValueError("Qualitative RGB image differs from the frozen sample audit")
    rgb = np.asarray(Image.open(source).convert("RGB"))
    target = np.asarray(Image.open(root / "masks/test" / (key + ".png")))
    if hashlib.sha256(target.tobytes()).hexdigest() != sample["mask_sha256"]:
        raise ValueError("Qualitative ground truth differs from the frozen sample audit")
    directory = Path(request["output_root"]) / job["name"]
    prediction_path = directory / "predictions" / (key + ".png")
    with (directory / "per-image.csv").open() as stream:
        rows = {row["key"]: row for row in csv.DictReader(stream)}
    if digest(prediction_path) != rows[key]["prediction_sha256"]:
        raise ValueError("Qualitative prediction differs from its inference artifact")
    prediction = np.asarray(Image.open(prediction_path))
    palette = np.asarray([value["color"] for value in classes], dtype=np.uint8)
    if target.shape != prediction.shape or rgb.shape[:2] != target.shape:
        raise ValueError("Qualitative image/mask/prediction dimensions differ")
    images = [Image.fromarray(rgb)]
    for mask in (target, prediction):
        if set(np.unique(mask)) - set(range(21)) - {255}:
            raise ValueError("Qualitative labels fall outside the 21-class taxonomy")
        overlay = rgb.copy()
        valid = mask != 255
        overlay[valid] = (0.48 * rgb[valid] + 0.52 * palette[mask[valid]]).astype(np.uint8)
        images.append(Image.fromarray(overlay))
    panel = Image.new("RGB", (1500, 300), "white")
    for column, image in enumerate(images):
        rendered = ImageOps.contain(image, (490, 280))
        panel.paste(
            rendered,
            (column * 500 + (500 - rendered.width) // 2, 10 + (280 - rendered.height) // 2),
        )
    stream = io.BytesIO()
    panel.save(stream, format="PNG")
    stream.seek(0)
    return stream


def build_pdf(path: Path, report: dict) -> None:
    from reportlab.graphics.shapes import Drawing, Rect
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Image as PdfImage
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    width = A4[0] - 72
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="PaperTitle",
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#142D46"),
            spaceAfter=12,
        )
    )
    styles.add(ParagraphStyle(name="PaperBody", fontSize=8.5, leading=11.5, spaceAfter=7))
    styles.add(ParagraphStyle(name="PaperSmall", fontSize=6.8, leading=8.8, spaceAfter=5))
    styles.add(ParagraphStyle(name="PaperCell", fontSize=6.5, leading=8))
    story = []

    def paragraph(value, style="PaperBody"):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    def table(rows, fractions=None, winners=()):
        rendered = [[paragraph(value, "PaperCell") for value in row] for row in rows]
        widths = (
            [width * fraction for fraction in fractions]
            if fractions
            else [width / len(rows[0])] * len(rows[0])
        )
        item = Table(rendered, colWidths=widths, repeatRows=1)
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DBE5ED")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F8")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        commands.extend(
            ("BACKGROUND", (column, row), (column, row), colors.HexColor("#D6F2DF"))
            for column, row in winners
        )
        item.setStyle(TableStyle(commands))
        story.extend([item, Spacer(1, 8)])

    def title(value):
        story.append(paragraph(value, "PaperTitle"))

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#586979"))
        canvas.drawString(
            36, 22, "RAD semantic segmentation | request " + report["request_sha256"][:12]
        )
        canvas.drawRightString(A4[0] - 36, 22, str(canvas.getPageNumber()))
        canvas.restoreState()

    def metric(value, scale=100):
        return "N/A" if value is None else f"{scale * value:.2f}"

    def class_table(entries, field):
        if len(entries) == 1:
            entry = entries[0]
            rows = [["Class", "Images", "GT pixels", "IoU mean (%)", "SD"]]
            for name in report["class_names"]:
                values = entry["per_class"][name]
                rows.append(
                    [
                        name,
                        values["positive_images"],
                        f"{values['pixels']:,}",
                        metric(values[field]["mean"]),
                        metric(values[field]["sample_sd"]),
                    ]
                )
            table(rows, [0.36, 0.1, 0.18, 0.21, 0.15])
            return
        rows = [["Class", "Images"] + [entry["protocol"] + "\nMean / SD" for entry in entries]]
        winners = []
        for row_index, name in enumerate(report["class_names"], 1):
            values = [entry["per_class"][name][field] for entry in entries]
            rows.append(
                [
                    name,
                    report["class_coverage"][name]["positive_images"],
                    *[format_summary(value) for value in values],
                ]
            )
            best = max(round(value["mean"] * 100, 2) for value in values)
            winners.extend(
                (column + 2, row_index)
                for column, value in enumerate(values)
                if round(value["mean"] * 100, 2) == best
            )
        table(rows, [0.29, 0.07] + [0.64 / len(entries)] * len(entries), winners)

    def legend(classes):
        cells = []
        for value in classes:
            swatch = Drawing(9, 9)
            swatch.add(
                Rect(
                    0,
                    0,
                    9,
                    9,
                    fillColor=colors.Color(*[channel / 255 for channel in value["color"]]),
                    strokeColor=None,
                )
            )
            cells.append(
                Table(
                    [[swatch, paragraph(value["name"], "PaperCell")]],
                    colWidths=[13, width / 3 - 17],
                )
            )
        rows = [cells[index : index + 3] for index in range(0, len(cells), 3)]
        item = Table(rows, colWidths=[width / 3] * 3)
        item.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(item)

    def source_stage_pages(model):
        source_model = next(
            value for value in report["source_stage_reports"]["models"] if value["model"] == model
        )
        for stage in source_model["stages"]:
            story.append(PageBreak())
            title(model.replace("_", " ") + "\n" + stage["stage"].replace("_", " "))
            record = stage["metrics"]
            metrics = record["metrics"]
            performance = stage["performance"]
            training = stage["training"]
            duration = training.get("wall_clock_s")
            story.append(
                paragraph(
                    f"Dataset {stage['dataset']} | split {stage['split']} | label space {stage['taxonomy']} | original source seed {stage['source_seed']} | fresh auto-weight evaluation",
                    "PaperSmall",
                )
            )
            table(
                [
                    [
                        "Native validation mIoU (%)",
                        "Model-only FPS",
                        "Training hours",
                        "Parameters M",
                        "Weights MiB",
                    ],
                    [
                        metric(metrics.get("miou")),
                        metric(performance["measurements"]["latency"]["fps"], 1),
                        metric(duration / 3600 if duration is not None else None, 1),
                        metric(performance["model"]["parameter_count"], 1 / 1e6),
                        metric(performance["model"]["resident_parameter_bytes"], 1 / 2**20),
                    ],
                ]
            )
            rows = [["Class", "GT pixels", "IoU (%)", "Precision (%)", "Recall (%)", "Dice (%)"]]
            for name in stage["class_names"]:
                rows.append(
                    [
                        name,
                        f"{metrics['support'][name]:,}",
                        *[
                            metric(metrics.get(field, {}).get(name))
                            for field in (
                                "per_class_iou",
                                "per_class_precision",
                                "per_class_recall",
                                "per_class_dice",
                            )
                        ],
                    ]
                )
            table(rows, [0.31, 0.17, 0.13, 0.13, 0.13, 0.13])
            story.append(
                paragraph(
                    "Source evaluations use the native dataset and label space of this stage. Cityscapes validation, RailSem19 validation and RAD test each describe their own samples and taxonomy. Source training runs are reused across all three RAD adaptation seeds.",
                    "PaperSmall",
                )
            )
            cfg = training.get("config", {})
            provenance = {
                "public_pretraining": stage.get("public_pretraining"),
                "optimizer": cfg.get("optim"),
                "effective_stage_optimizer": training.get("env", {}).get("stage_optimizer"),
                "model": cfg.get("model"),
                "training_duration_seconds": duration,
            }
            story.append(
                paragraph(
                    "Public supervision and training recipe\n"
                    + json.dumps(provenance, sort_keys=True),
                    "PaperSmall",
                )
            )
            for label in (
                "checkpoint",
                "config",
                "evaluation_receipt",
                "performance_receipt",
                "training_receipt",
            ):
                story.append(
                    paragraph(
                        label.replace("_", " ") + "\n" + json.dumps(stage[label], sort_keys=True),
                        "PaperSmall",
                    )
                )
            if duration is None or not stage.get("public_pretraining"):
                story.append(
                    paragraph(
                        "Missing source duration or public-pretraining provenance must be collected. Public pretraining compute remains unavailable unless its published source explicitly records it.",
                        "PaperSmall",
                    )
                )

    protocol = report["research_protocol"]
    aggregates = report["aggregates"]
    headline = [
        next(
            row
            for row in aggregates
            if row["model"] == model and row["protocol"] == protocol["headline_protocol"]
        )
        for model in report["headline_order"]
    ]
    request = json.loads(Path(report["request"]).read_text())
    root = Path(request["dataset_root"])
    classes = sorted(
        json.loads((root / "classes.json").read_text())["classes"], key=lambda value: value["id"]
    )
    samples = {
        sample["key"]: sample for sample in json.loads((root / "audit/samples.json").read_text())
    }
    title("RAD semantic segmentation\nThree-seed final-checkpoint study")
    story.append(
        paragraph(
            f"{len(report['runs'])} completed RAD runs | {len(headline)} models | 21 classes | {report['test_images']} test images"
        )
    )
    story.append(
        paragraph(
            "The primary ranking uses dataset-pooled 21-class mIoU under the common initialization recipe frozen before test evaluation. Mean and sample SD summarize adaptation seeds 0, 1 and 2. All individual values remain in the CSV and JSON."
        )
    )
    story.append(paragraph("Common recipe " + protocol["headline_protocol"]))
    rows = [
        [
            "Rank",
            "Model",
            "mIoU mean (%)",
            "SD",
            "Model FPS\nMean / SD",
            "Native FPS\nMean / SD",
            "Mud IoU (%)\nMean / SD",
        ]
    ]
    for index, entry in enumerate(headline, 1):
        rows.append(
            [
                index,
                entry["model"],
                metric(entry["pixel_pooled_miou"]["mean"]),
                metric(entry["pixel_pooled_miou"]["sample_sd"]),
                format_summary(entry["model_only_fps"], 1),
                format_summary(entry["native_pipeline_fps"], 1),
                format_summary(entry["per_class"]["mud-pumping"]["iou"]),
            ]
        )
    winners = []
    for column, getter, scale in (
        (2, lambda row: row["pixel_pooled_miou"]["mean"], 100),
        (4, lambda row: row["model_only_fps"]["mean"], 1),
        (5, lambda row: row["native_pipeline_fps"]["mean"], 1),
        (6, lambda row: row["per_class"]["mud-pumping"]["iou"]["mean"], 100),
    ):
        best = max(round(getter(row) * scale, 2) for row in headline)
        winners.extend(
            (column, index)
            for index, row in enumerate(headline, 1)
            if round(getter(row) * scale, 2) == best
        )
    table(rows, [0.05, 0.25, 0.13, 0.08, 0.16, 0.16, 0.17], winners)
    story.append(
        paragraph(
            "Green cells mark the highest displayed means within comparable columns or class rows, including displayed ties. Qualitative figures use the same fixed images and seed 0 for every model.",
            "PaperSmall",
        )
    )
    for limitation in report["limitations"]:
        story.append(paragraph(limitation, "PaperSmall"))
    if report["missing_provenance"]:
        story.append(paragraph("Evidence requiring collection", "Heading2"))
        for missing in sorted(set(report["missing_provenance"]))[:8]:
            story.append(paragraph(missing, "PaperSmall"))
        story.append(
            paragraph(
                "The complete missing-evidence list is retained in rad-paper.json.", "PaperSmall"
            )
        )
    story.append(PageBreak())
    title("Complete study summary")
    table(
        [["Split", "Images", "Valid ground-truth pixels"]]
        + [
            [
                split.capitalize(),
                report["split_totals"][split]["images"],
                f"{report['split_totals'][split]['valid_pixels']:,}",
            ]
            for split in ("train", "test")
        ],
        [0.3, 0.2, 0.5],
    )
    table(
        [["Class", "Positive train images", "Train pixels", "Positive test images", "Test pixels"]]
        + [
            [
                name,
                f"{report['class_split_support'][name]['train']['positive_images']}\n{100 * report['class_split_support'][name]['train']['positive_image_fraction']:.2f}%",
                f"{report['class_split_support'][name]['train']['pixels']:,}\n{100 * report['class_split_support'][name]['train']['valid_pixel_fraction']:.4f}%",
                f"{report['class_split_support'][name]['test']['positive_images']}\n{100 * report['class_split_support'][name]['test']['positive_image_fraction']:.2f}%",
                f"{report['class_split_support'][name]['test']['pixels']:,}\n{100 * report['class_split_support'][name]['test']['valid_pixel_fraction']:.4f}%",
            ]
            for name in report["class_names"]
        ],
        [0.3, 0.175, 0.175, 0.175, 0.175],
    )
    story.append(
        paragraph(
            "Image percentages divide class-positive images by all images in the named split. Pixel percentages divide ground-truth class pixels by valid labeled pixels in that split. Void pixels are excluded from pixel denominators. One image can contain several classes.",
            "PaperSmall",
        )
    )
    mud = report["class_split_support"]["mud-pumping"]
    story.append(
        paragraph(
            f"Mud-pumping training support is {mud['train']['positive_images']} positive images and {mud['train']['pixels']:,} pixels ({100 * mud['train']['valid_pixel_fraction']:.4f}% of valid training pixels). Test support is {mud['test']['positive_images']} positive images and {mud['test']['pixels']:,} pixels ({100 * mud['test']['valid_pixel_fraction']:.4f}% of valid test pixels).",
            "PaperSmall",
        )
    )
    if len(aggregates) > len(headline):
        story.append(paragraph("All prespecified initialization recipes", "Heading2"))
        table(
            [
                [
                    "Model",
                    "Recipe",
                    "Pooled mIoU (%)\nMean / SD",
                    "Positive-image mIoU (%)\nMean / SD",
                ]
            ]
            + [
                [
                    entry["model"],
                    entry["protocol"],
                    format_summary(entry["pixel_pooled_miou"]),
                    format_summary(entry["class_positive_image_miou"]),
                ]
                for entry in aggregates
            ],
            [0.27, 0.29, 0.22, 0.22],
        )
    for model in report["headline_order"]:
        entries = [entry for entry in aggregates if entry["model"] == model]
        source_stage_pages(model)
        story.append(PageBreak())
        title(model.replace("_", " ") + "\nRAD test pooled IoU")
        story.append(
            paragraph(
                "Each class pools every test-image confusion matrix before computing TP / (TP + FP + FN). All 21 classes have ground-truth support.",
                "PaperSmall",
            )
        )
        class_table(entries, "iou")
        story.append(paragraph("Deployment and RAD training resources", "Heading2"))
        table(
            [
                [
                    "Recipe",
                    "Model FPS\nMean / SD",
                    "Native FPS\nMean / SD",
                    "Train peak GiB\nMean / SD",
                    "Train hours\nMean / SD",
                    "Parameters M",
                    "Weights MiB",
                ]
            ]
            + [
                [
                    entry["protocol"],
                    format_summary(entry["model_only_fps"], 1),
                    format_summary(entry["native_pipeline_fps"], 1),
                    format_summary(entry["training_peak_bytes"], 1 / 2**30),
                    (
                        f">= {entry['training_hours']['mean']:.2f}\nSD unknown"
                        if entry["training_hours_is_lower_bound"]
                        else format_summary(entry["training_hours"], 1)
                    ),
                    format_summary(entry["parameter_count"], 1 / 1e6),
                    format_summary(entry["resident_parameter_bytes"], 1 / 2**20),
                ]
                for entry in entries
            ],
            [0.22, 0.13, 0.13, 0.13, 0.13, 0.13, 0.13],
        )
        table(
            [
                [
                    "Recipe",
                    "Inference allocator peak GiB",
                    "Inference process GiB",
                    "Native allocator peak GiB",
                ]
            ]
            + [
                [
                    entry["protocol"],
                    format_summary(entry["allocator_peak_bytes"], 1 / 2**30),
                    format_summary(entry["process_total_bytes"], 1 / 2**30),
                    format_summary(entry["native_allocator_peak_bytes"], 1 / 2**30),
                ]
                for entry in entries
            ],
            [0.28, 0.24, 0.24, 0.24],
        )
        story.append(
            paragraph(
                "Training hours include recorded failed attempts. Incomplete-tail hours are explicit lower bounds with unknown SD. Train peak is the successful final invocation's allocator peak. Weight size counts resident parameters. Process memory is the recorded post-loop sample. Native timing uses its recorded preprocessing, tiling and prediction contract.",
                "PaperSmall",
            )
        )
        story.append(PageBreak())
        title(model.replace("_", " ") + "\nClass-positive-image IoU")
        story.append(
            paragraph(
                "For each class, image IoU is averaged over test images containing that class. False alarms on entirely class-negative images have separate statistics in the full JSON.",
                "PaperSmall",
            )
        )
        class_table(entries, "positive_image_iou")
        model_runs = [run for run in report["runs"] if run["model"] == model]
        observations = [
            {
                "seed": run["seed"],
                "protocol": run["protocol"],
                **run["training"]["env"]["training_observations"],
            }
            for run in model_runs
            if run["training"].get("env", {}).get("training_observations")
        ]
        if observations:
            story.append(
                paragraph(
                    "Recorded training observations by invocation\n"
                    + json.dumps(observations, sort_keys=True),
                    "PaperSmall",
                )
            )
        for run in model_runs:
            if run["seed"]:
                continue
            training = run["training"]
            cfg = training.get("config", {})
            origins = training.get("env", {}).get("model_origins", [])
            summary = {
                "recipe": run["protocol"],
                "public_model": cfg.get("model"),
                "origins": origins,
                "optimizer": cfg.get("optim"),
                "stage_learning_rates": [
                    {key: stage.get(key) for key in ("lr_scale", "head_group_lr_scale", "iters")}
                    for stage in cfg.get("stages", [])
                ],
                "RAD_duration_seconds": training.get("wall_clock_s"),
                "source_checkpoint": run.get("source_checkpoint"),
            }
            story.append(
                paragraph(
                    "Initialization and optimizer provenance\n"
                    + json.dumps(summary, sort_keys=True),
                    "PaperSmall",
                )
            )
        story.append(PageBreak())
        title(model.replace("_", " ") + "\nClass metrics and false alarms")
        common = next(
            entry for entry in entries if entry["protocol"] == protocol["headline_protocol"]
        )
        rows = [
            [
                "Class",
                "Precision (%)\nMean / SD",
                "Recall (%)\nMean / SD",
                "Dice (%)\nMean / SD",
                "Any-pixel alarm (%)\nMean / SD",
                "0.1% area alarm (%)\nMean / SD",
            ]
        ]
        for name in report["class_names"]:
            values = common["per_class"][name]
            rows.append(
                [
                    name,
                    *[
                        format_summary(values[field])
                        for field in (
                            "precision",
                            "recall",
                            "dice",
                            "negative_image_false_alarm_rate",
                            "negative_image_false_alarm_rate_area",
                        )
                    ],
                ]
            )
        table(rows, [0.3, 0.14, 0.14, 0.14, 0.14, 0.14])
        story.append(
            paragraph(
                "False-alarm rates use only images with zero ground-truth pixels of the named class. The two fixed rules count any predicted pixel, or predicted area at least 0.1 percent of valid pixels. N/A records zero negative images. Precise positive/negative image and pixel denominators remain in rad-paper.json.",
                "PaperSmall",
            )
        )
        common_runs = [
            run for run in model_runs if run["protocol"] == protocol["headline_protocol"]
        ]
        story.append(PageBreak())
        title(model.replace("_", " ") + "\nScene-block sensitivity")
        for field, heading in (
            ("per_block", "Per-block test scores"),
            ("leave_one_block_out", "Leave-one-block-out sensitivity"),
        ):
            story.append(paragraph(heading, "Heading2"))
            rows = [
                [
                    "Block",
                    "Scored images",
                    "GT classes",
                    "Scored classes by seed",
                    "Pooled mIoU mean (%)",
                    "SD",
                ]
            ]
            for block in common_runs[0]["metrics"][field]:
                statistics = seed_summary(
                    {
                        run["seed"]: run["metrics"][field][block]["pixel_pooled"]["miou"]
                        for run in common_runs
                    }
                )
                first = common_runs[0]["metrics"][field][block]
                rows.append(
                    [
                        block,
                        first["images"],
                        first["pixel_pooled"]["ground_truth_present_classes"],
                        "/".join(
                            str(
                                run["metrics"][field][block]["pixel_pooled"]["macro_scored_classes"]
                            )
                            for run in sorted(common_runs, key=lambda value: value["seed"])
                        ),
                        metric(statistics["mean"]),
                        metric(statistics["sample_sd"]),
                    ]
                )
            table(rows, [0.3, 0.12, 0.11, 0.17, 0.18, 0.12])
        story.append(
            paragraph(
                "Each block has a different ground-truth class subset. The scored-class denominator also includes classes with predicted union. Class-by-class block IoU, support and negative-image false alarms are retained for every seed in the JSON. Leave-one-block-out rows exclude the named block. Four inferred scene blocks provide descriptive sensitivity, with recording independence unconfirmed.",
                "PaperSmall",
            )
        )
        job = next(
            job
            for job in request["jobs"]
            if job["model"] == model
            and job["protocol"] == protocol["headline_protocol"]
            and job["seed"] == 0
        )
        keys = protocol["qualitative_keys"]
        for start in range(0, len(keys), 4):
            story.append(PageBreak())
            title(model.replace("_", " ") + "\nFull semantic overlays")
            story.append(
                paragraph(
                    "Prespecified common recipe | fixed seed 0 | complete model predictions | GT void transparent and ignored in scores",
                    "PaperSmall",
                )
            )
            table([["Original RGB", "Ground truth - all classes", "Prediction - all classes"]])
            for key in keys[start : start + 4]:
                story.append(paragraph(key, "PaperSmall"))
                panel = semantic_panel(request, job, key, classes, samples[key])
                story.append(PdfImage(panel, width=width, height=width * 300 / 1500))
                story.append(Spacer(1, 3))
            legend(classes)
    story.append(PageBreak())
    title("Exact provenance")
    for field in (
        "request",
        "request_sha256",
        "training_plan_sha256",
        "training_campaign_sha256",
        "training_code_sha",
        "split_sha256",
        "samples_sha256",
    ):
        story.append(paragraph(field.replace("_", " ") + "\n" + report[field], "PaperSmall"))
    story.append(
        paragraph(
            "Every RAD run binds its configuration and final checkpoint. Full state hashes, raw timing samples, optimizer recipes, source records, per-block statistics and individual-seed metrics remain in rad-paper.json and the hashed artifacts it references.",
            "PaperSmall",
        )
    )
    for run in report["runs"]:
        story.append(
            paragraph(
                run["name"]
                + "\nconfig "
                + run["config_sha256"]
                + "\nfinal "
                + run["final_checkpoint_sha256"],
                "PaperSmall",
            )
        )
    SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=35,
        bottomMargin=35,
        title="RAD semantic segmentation - three-seed paper study",
    ).build(story, onFirstPage=footer, onLaterPages=footer)


def build(request_path: Path, out: Path) -> dict:
    report = load_report(request_path)
    out.mkdir(parents=True, exist_ok=True)
    write(out / "rad-paper.json", report)
    write_csv(out / "rad-paper.csv", report)
    build_pdf(out / "rad-paper.pdf", report)
    return {
        "status": "completed",
        "files": [str(out / name) for name in ("rad-paper.json", "rad-paper.csv", "rad-paper.pdf")],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.request.resolve(), args.out.resolve()), indent=2))


if __name__ == "__main__":
    main()
