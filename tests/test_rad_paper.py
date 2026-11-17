"""CPU-only complete-run freezing, report arithmetic and PDF integration checks."""

from __future__ import annotations

import copy
import csv
import gzip
import hashlib
import io
import json
from itertools import product
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml
from PIL import Image
from scripts import build_rad_paper_report as report
from scripts import evaluate_rad_source_stages as source_evaluator
from scripts import run_rad_paper as controller
from scripts.profile_rad_test import deployment_contract
from scripts.rad_paper_metrics import paper_metrics, pooled_metrics
from scripts.run_rad_test import digest, write

from segmentary import gpu_policy


@pytest.fixture
def paper_campaign(tmp_path, monkeypatch, request):
    smp = getattr(request, "param", None) == "smp"
    root = tmp_path / "campaign"
    root.mkdir()
    data = tmp_path / "dataset"
    models = ["tiny_model"] + [f"tiny_model_{index}" for index in range(1, 8)]
    taxonomy = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "taxonomy/paul-test-rtis/canonical.yaml").read_text()
    )
    write(data / "classes.json", taxonomy)
    names = [value["name"] for value in taxonomy["classes"]]
    target = np.arange(21, dtype=np.uint8).reshape(3, 7)
    samples = []
    for index in range(59):
        key = f"block-{index % 4}/sample-{index}"
        rgb = np.full((3, 7, 3), 80 + index, dtype=np.uint8)
        image_path = data / "images/test" / (key + ".png")
        mask_path = data / "masks/test" / (key + ".png")
        image_path.parent.mkdir(parents=True, exist_ok=True)
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgb).save(image_path)
        Image.fromarray(target).save(mask_path)
        samples.append(
            {
                "key": key,
                "split": "test",
                "group": f"block-{index % 4}",
                "image_extension": ".png",
                "image_sha256": digest(image_path),
                "mask_sha256": hashlib.sha256(target.tobytes()).hexdigest(),
                "width": 7,
                "height": 3,
                "class_pixels": {str(index): 1 for index in range(21)},
            }
        )
    train_labels = np.tile(target, (2, 1))
    train_samples = []
    for index in range(255):
        key = f"train-group/sample-{index}"
        train_image = data / "images/train" / (key + ".png")
        train_mask = data / "masks/train" / (key + ".png")
        train_image.parent.mkdir(parents=True, exist_ok=True)
        train_mask.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (7, 6), color=(index, 100, 120)).save(train_image)
        Image.fromarray(train_labels).save(train_mask)
        train_samples.append(
            {
                "key": key,
                "split": "train",
                "group": "train-group",
                "image_extension": ".png",
                "image_sha256": digest(train_image),
                "mask_sha256": hashlib.sha256(train_labels.tobytes()).hexdigest(),
                "width": 7,
                "height": 6,
                "class_pixels": {str(label): 2 for label in range(21)},
            }
        )
    write(
        data / "splits.json",
        {
            "train": [sample["key"] for sample in train_samples],
            "val": [],
            "test": [sample["key"] for sample in samples],
        },
    )
    write(data / "audit/samples.json", [*samples, *train_samples])
    source_spec = tmp_path / "source-request.json"
    write(source_spec, {"output_root": str(tmp_path / "source-stage")})
    source_metrics = {
        "miou": 1.0,
        "support": dict.fromkeys(names, 2),
        **{
            field: dict.fromkeys(names, 1.0)
            for field in (
                "per_class_iou",
                "per_class_precision",
                "per_class_recall",
                "per_class_dice",
            )
        },
    }
    source_report = {
        "models": [
            {
                "model": "tiny_model",
                "stages": [
                    {
                        "stage": stage,
                        "dataset": dataset,
                        "split": "val",
                        "taxonomy": taxonomy,
                        "class_names": names,
                        "source_seed": 0,
                        "metrics": {
                            "metrics": source_metrics,
                            "config": {"evaluation": {"weights": "raw"}},
                        },
                        "performance": {
                            "measurements": {"latency": {"fps": 100}},
                            "model": {"parameter_count": 100, "resident_parameter_bytes": 400},
                        },
                        "training": {
                            "wall_clock_s": 90,
                            "config": {
                                "optim": {"backbone_lr": 1e-4},
                                "model": {"checkpoint": "synthetic"},
                            },
                        },
                        "public_pretraining": {"identity": "synthetic-fixture"},
                        **{
                            field: {"path": "synthetic", "sha256": "b" * 64}
                            for field in (
                                "checkpoint",
                                "config",
                                "evaluation_receipt",
                                "performance_receipt",
                                "training_receipt",
                            )
                        },
                    }
                    for stage, dataset, taxonomy in (
                        ("cityscapes", "cityscapes", "cityscapes19"),
                        ("cityscapes_to_railsem19", "railsem19", "rail_union"),
                    )
                ],
            }
        ]
    }
    base_source = source_report["models"][0]
    source_report["models"] = [{**copy.deepcopy(base_source), "model": model} for model in models]
    if smp:
        for source in source_report["models"]:
            for stage in source["stages"]:
                stage["public_pretraining"] = {
                    "model": source["model"],
                    "public_checkpoint": "smp-hub/resnet50.imagenet",
                    "public_revision_status": "Pinned inside installed SMP encoder registry",
                    "smp_registry_pinned_revision": "c" * 40,
                }
    write(tmp_path / "source-stage/source-stage-reports.json", source_report)
    monkeypatch.setattr(
        source_evaluator, "load_verified_report", lambda *args: source_report, raising=False
    )
    protocol = {
        "models": models,
        "matrix": "staged24",
        "seeds": [0, 1, 2],
        "primary_metric": "pixel_pooled_miou",
        "headline_protocol": "cityscapes_to_railsem19_to_rtis",
        "qualitative_seed": 0,
        "qualitative_keys": [samples[0]["key"]],
        "failure_rule": "max-three infrastructure attempts; nonfinite loss is terminal",
        "split_policy": "finalfit",
        "source_stage_reports": {"spec": str(source_spec), "spec_sha256": digest(source_spec)},
    }
    jobs = []
    code = "a" * 40
    for model, seed in product(models, range(3)):
        name = f"{model}--cityscapes_to_railsem19_to_rtis--seed-{seed}"
        config = root / "configs" / (name + ".yaml")
        config.parent.mkdir(exist_ok=True)
        cfg = {
            "name": name,
            "stages": [
                {
                    "data": [
                        {
                            "name": "rad_2026_11_paper_finalfit",
                            "root": str(data),
                            "loader": "folder",
                            "mapping": "paul-test-rtis",
                            "limit": None,
                        }
                    ],
                    "lr_scale": 0.1,
                }
            ],
            "model": {"arch": "smp", "encoder_name": "resnet50", "encoder_weights": "imagenet"}
            if smp
            else {"arch": "tiny"},
            "optim": {"backbone_lr": 1e-5},
            "train": {"seed": seed, "devices": 1, "validation_enabled": False, "iters": 4000},
            "eval": {
                "batch_size": 1,
                "sliding_window": True,
                "window": [1024, 1024],
                "stride": [768, 768],
            },
        }
        config.write_text(yaml.safe_dump(cfg))
        checkpoint = root / name / "last.ckpt"
        checkpoint.parent.mkdir()
        checkpoint.write_bytes(f"checkpoint-{seed}".encode())
        job = {
            "name": name,
            "model": model,
            "protocol": protocol["headline_protocol"],
            "seed": seed,
            "config": str(config),
            "config_sha256": digest(config),
            "source_checkpoint": None,
        }
        jobs.append(job)
        train_matrix = np.diag(np.full(21, 510, dtype=np.int64))
        train_matrix[0, 0] -= seed * 5
        train_matrix[0, 20] += seed * 5
        train_scores = pooled_metrics(train_matrix, names)
        train_cfg = copy.deepcopy(cfg)
        train_cfg["evaluation"] = {
            "data": cfg["stages"][0]["data"][0],
            "split": "train",
            "num_workers": 2,
            "deterministic": True,
            "weights": "raw",
            "tta": {"enabled": False, "scales": [1.0], "flip": False},
            "prediction": {"task": "multiclass", "activation": "softmax", "threshold": None},
            "padding": {
                "multiple": 32,
                "position": "bottom_right",
                "target_fill": 255,
                "padded_pixels_scored": False,
            },
        }
        train_record = {
            "name": name,
            "seed": seed,
            "stage": "eval:rad_2026_11_paper_finalfit:train",
            "git_sha": code,
            "git_dirty": False,
            "dataset_sizes": {"eval": 255},
            "config": train_cfg,
            "config_hash": report.config_hash(train_cfg),
            "metrics": {
                "miou": train_scores["miou"],
                "confusion": train_matrix.tolist(),
                "support": {name: 510 for name in names},
            },
        }
        train_path = checkpoint.parent / "final-train.json"
        write(train_path, train_record)
        write(
            root / "state" / (name + ".json"),
            {
                "name": name,
                "status": "completed",
                "code_sha": code,
                "config_sha256": job["config_sha256"],
                "final_step": 4000,
                "evaluation_checkpoint": "final",
                "evaluation_split": "train",
                "evaluation": train_record,
                "evaluation_result": {"path": str(train_path), "sha256": digest(train_path)},
                "performance": {
                    "source": {
                        "checkpoint_sha256": digest(checkpoint),
                        "config_sha256": job["config_sha256"],
                        "result_sha256": digest(train_path),
                        "weights": "raw",
                    }
                },
                "checkpoints": {
                    "final": {
                        "path": str(checkpoint),
                        "sha256": digest(checkpoint),
                        "global_step": 4000,
                    }
                },
                "collection": {
                    "verified": True,
                    "contract": "rtis-final-train-statistics-v2",
                    "diagnostics": {
                        "standalone_confusion_exact_match": True,
                        "results": {
                            "final-auto-train": {
                                "checkpoint_sha256": digest(checkpoint),
                                "weights": "raw",
                                "images": 255,
                            }
                        },
                    },
                    "resources": {
                        "phase_wall_seconds_including_failed_attempts": {"training": 90 + seed}
                    },
                },
                "training": {
                    "config": cfg,
                    "peak_vram_bytes": {"cuda:0": 2**30},
                    "wall_clock_s": 90 + seed,
                    "env": {
                        "final_weights_policy": "raw",
                        "model_origins": []
                        if smp
                        else [{"hf_name_or_path": "synthetic", "hf_commit": "pinned"}],
                    },
                },
            },
        )
    plan = {
        "jobs": jobs,
        "collection_contract": "rtis-final-train-statistics-v2",
        "target_steps_per_job": 4000,
        "validation_enabled": False,
        "primary_checkpoint": "final",
        "research_protocol": protocol,
        "research_protocol_sha256": hashlib.sha256(
            json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "split_sha256": digest(data / "splits.json"),
    }
    write(root / "plan.json", plan)
    policy = gpu_policy.freeze(
        [0], [{"index": 0, "uuid": "GPU-0", "pci_bus_id": "00"}], "test-host"
    )
    training = {
        "code_sha": code,
        "plan_sha256": digest(root / "plan.json"),
        "research_protocol": protocol,
        "research_protocol_sha256": plan["research_protocol_sha256"],
        "split_sha256": plan["split_sha256"],
        "dataset_audit_sha256": digest(data / "audit/samples.json"),
        "dataset_classes_sha256": digest(data / "classes.json"),
        "gpu_policy": policy,
        "gpu_policy_sha256": gpu_policy.policy_sha256(policy),
        "launch_requirements": {"expected_gpu_allowlist": [0]},
    }
    write(root / "campaign.json", training)
    monkeypatch.setattr(
        controller.subprocess,
        "check_output",
        lambda command, **kwargs: "" if "status" in command else code,
    )
    request_path = controller.freeze_request(root, root / "plan.json", root, 0)
    request = json.loads(request_path.read_text())
    request_sha = digest(request_path)
    for job in request["jobs"]:
        directory = Path(request["output_root"]) / job["name"]
        directory.mkdir(parents=True)
        matrices = {}
        rows = []
        for sample in samples:
            predicted = target.copy()
            predicted.ravel()[: job["seed"]] = 20
            matrix = np.bincount(
                (target.astype(np.int64) * 21 + predicted).ravel(), minlength=21**2
            ).reshape(21, 21)
            matrices[sample["key"]] = matrix
            destination = directory / "predictions" / (sample["key"] + ".png")
            destination.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(predicted).save(destination)
            rows.append({"key": sample["key"], "prediction_sha256": digest(destination)})
        with (directory / "per-image.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (directory / "per-image-confusion.json.gz").write_bytes(
            gzip.compress(
                json.dumps({key: value.tolist() for key, value in matrices.items()}).encode()
            )
        )
        metrics = paper_metrics(
            matrices, names, {sample["key"]: sample["group"] for sample in samples}
        )
        write(directory / "paper-metrics.json", metrics)
        write(directory / "metrics.json", metrics)
        write(
            directory / "coverage.json",
            {name: {"positive_images": 59, "pixels": 59} for name in names},
        )
        filenames = (
            "per-image.csv",
            "per-image-confusion.json.gz",
            "paper-metrics.json",
            "metrics.json",
            "coverage.json",
        )
        result = {
            **{
                field: job[field]
                for field in ("name", "model", "protocol", "seed", "config_sha256")
            },
            "status": "completed",
            "split": "test",
            "test_evaluated": True,
            "request_sha256": request_sha,
            "checkpoint_sha256": job["final_checkpoint_sha256"],
            "images": 59,
            "weights": "raw",
            "deterministic": True,
            "precision": "bf16_autocast",
            "padding": {"multiple": 32, "prediction_cropped_to_original": True},
            "inference": {
                "sliding_window": True,
                "window": [1024, 1024],
                "stride": [768, 768],
                "scales": [1.0],
                "flip": False,
            },
            "present_image": {
                "images": 59,
                "miou_present_images_classes": 21,
                "per_class": {name: {} for name in names},
            },
            "artifacts": {
                name: {"path": str(directory / name), "sha256": digest(directory / name)}
                for name in filenames
            },
        }
        write(directory / "result.json", result)
        profile_dir = directory.parent.parent / "deployment-performance" / job["name"]
        milliseconds = 10 + job["seed"]
        performance = {
            "source": {
                "checkpoint_sha256": job["final_checkpoint_sha256"],
                "config_sha256": job["config_sha256"],
                "source_test_result_sha256": digest(directory / "result.json"),
            },
            "hardware": {"gpu_uuid": "GPU-0"},
            "model": {"parameter_count": 100, "resident_parameter_bytes": 400},
            "contract": deployment_contract(),
            "measurements": {
                "latency": {
                    "raw_ms": [milliseconds] * 100,
                    "mean_ms": milliseconds,
                    "fps": 1000 / milliseconds,
                },
                "peak_reserved_bytes": 2**30,
                "process_total_bytes": 2**31,
            },
            "native_pipeline": {
                "contract": {"timing": "synthetic"},
                "measurements": {
                    "latency": {"fps": 20},
                    "peak_reserved_bytes": 2**30,
                    "process_total_bytes": 2**31,
                    "per_image": [
                        {"key": sample["key"], "width": 7, "height": 3, "ms": 50}
                        for sample in samples
                    ],
                },
            },
        }
        write(profile_dir / "performance.json", performance)
        write(
            profile_dir / "result.json",
            {
                "status": "completed",
                "task": "rad-final-deployment-profile",
                "request_sha256": request_sha,
                "checkpoint_sha256": job["final_checkpoint_sha256"],
                "performance": performance,
                "artifacts": {
                    "performance.json": {
                        "path": str(profile_dir / "performance.json"),
                        "sha256": digest(profile_dir / "performance.json"),
                    }
                },
            },
        )
    return SimpleNamespace(root=root, request=request_path, data=data, plan=plan)


def test_complete_request_is_immutable_and_uses_policy_campaign_basename(paper_campaign):
    case = paper_campaign
    raw = case.request.read_bytes()
    assert (
        controller.freeze_request(case.root, case.root / "plan.json", case.root, 0) == case.request
    )
    assert case.request.read_bytes() == raw
    assert Path(json.loads(raw)["campaign_json"]).name == "campaign.json"
    with pytest.raises(ValueError, match="Benchmark GPU"):
        controller.freeze_request(case.root, case.root / "plan.json", case.root, 1)


def test_request_cannot_cover_partial_training(paper_campaign):
    case = paper_campaign
    job = case.plan["jobs"][0]
    state = case.root / "state" / (job["name"] + ".json")
    value = json.loads(state.read_text())
    value["status"] = "failed"
    write(state, value)
    with pytest.raises(ValueError, match="complete fixed-budget"):
        controller.freeze_request(case.root, case.root / "plan.json", case.root, 0)


def test_report_recomputes_full_metrics_and_three_seed_sample_sd(paper_campaign):
    result = report.load_report(paper_campaign.request)
    aggregate = result["aggregates"][0]
    values = [
        run["metrics"]["pixel_pooled"]["miou"]
        for run in result["runs"]
        if run["model"] == aggregate["model"]
    ]
    assert aggregate["pixel_pooled_miou"]["mean"] == pytest.approx(np.mean(values))
    assert aggregate["pixel_pooled_miou"]["sample_sd"] == pytest.approx(np.std(values, ddof=1))
    assert len(aggregate["per_class"]) == 21
    assert result["qualitative"]["seed"] == 0
    assert result["split_totals"] == {
        "train": {"images": 255, "valid_pixels": 10710},
        "test": {"images": 59, "valid_pixels": 1239},
    }
    assert result["class_split_support"]["mud-pumping"]["train"]["positive_images"] == 255
    assert result["class_split_support"]["mud-pumping"]["test"]["positive_images"] == 59
    selected = [run for run in result["runs"] if run["model"] == aggregate["model"]]
    gaps = [
        run["train_pixel_pooled_miou"] - run["metrics"]["pixel_pooled"]["miou"] for run in selected
    ]
    assert aggregate["train_test_miou_gap"]["mean"] == pytest.approx(np.mean(gaps))
    assert aggregate["train_test_miou_gap"]["sample_sd"] == pytest.approx(np.std(gaps, ddof=1))
    assert aggregate["train_test_miou_gap"]["sample_sd"] != pytest.approx(
        np.hypot(
            aggregate["train_pixel_pooled_miou"]["sample_sd"],
            aggregate["pixel_pooled_miou"]["sample_sd"],
        )
    )


@pytest.mark.parametrize("split", ["train", "test"])
def test_class_split_support_requires_every_class_on_both_sides(paper_campaign, split):
    names = json.loads(paper_campaign.request.read_text())["class_names"]
    samples = json.loads((paper_campaign.data / "audit/samples.json").read_text())
    for sample in samples:
        if sample["split"] == split:
            sample["class_pixels"]["13"] = 0
    with pytest.raises(ValueError, match=f"positive {split} support"):
        report.class_split_support(samples, names)


def test_class_split_pixel_fractions_exclude_ignored_pixels(paper_campaign):
    names = json.loads(paper_campaign.request.read_text())["class_names"]
    samples = json.loads((paper_campaign.data / "audit/samples.json").read_text())
    for sample in samples:
        sample["class_pixels"]["255"] = 100
    support = report.class_split_support(samples, names)
    assert support["totals"]["train"]["valid_pixels"] == 10710
    assert support["classes"]["mud-pumping"]["train"]["valid_pixel_fraction"] == pytest.approx(
        2 / 42
    )


def test_report_rejects_tampered_paper_metrics(paper_campaign):
    request = json.loads(paper_campaign.request.read_text())
    directory = Path(request["output_root"]) / request["jobs"][0]["name"]
    (directory / "paper-metrics.json").write_text("{}")
    with pytest.raises(ValueError, match="artifact changed"):
        report.load_report(paper_campaign.request)


def test_report_rejects_missing_native_pipeline_coverage(paper_campaign):
    request = json.loads(paper_campaign.request.read_text())
    directory = (
        Path(request["output_root"]).parent / "deployment-performance" / request["jobs"][0]["name"]
    )
    performance = json.loads((directory / "performance.json").read_text())
    performance["native_pipeline"]["measurements"]["per_image"].pop()
    write(directory / "performance.json", performance)
    profile = json.loads((directory / "result.json").read_text())
    profile["performance"] = performance
    profile["artifacts"]["performance.json"]["sha256"] = digest(directory / "performance.json")
    write(directory / "result.json", profile)
    with pytest.raises(ValueError, match="Native-pipeline"):
        report.load_report(paper_campaign.request)


def test_csv_json_pdf_build_retains_all_classes_and_seed_columns(paper_campaign):
    pytest.importorskip("reportlab")
    reader = pytest.importorskip("pypdf")
    out = paper_campaign.root / "report"
    report.build(paper_campaign.request, out)
    text = "\n".join(page.extract_text() for page in reader.PdfReader(out / "rad-paper.pdf").pages)
    assert "RAD test pooled IoU" in text
    assert "Class-positive-image IoU" in text
    assert "Full semantic overlays" in text
    assert "best seed" not in text.lower()
    assert "+/-" not in text
    for name in json.loads(paper_campaign.request.read_text())["class_names"]:
        assert name in text
    with (out / "rad-paper.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 8
    assert "pixel_pooled_miou:seed_2" in rows[0]
    assert "pixels:mud-pumping" in rows[0]
    assert "iou:mud-pumping:seed_0" in rows[0]
    assert "iou:mud-pumping:maximum" in rows[0]
    assert "training_hours:seed_2" in rows[0]
    assert "per_block:block-0:pixel_pooled_miou:seed_2" in rows[0]
    assert "train_pixel_pooled_miou:seed_2" in rows[0]
    assert "train_test_miou_gap:sample_sd" in rows[0]
    assert "Speed and segmentation accuracy" in text
    assert "Individual RAD replicates and observed range" in text
    assert "Evaluation weight bank raw" in text
    assert "report code sha" in text
    assert "report code dirty" in text
    assert "RAD_duration_seconds" not in text
    assert "Train pooled mIoU (%)" in text
    assert "Train-test mIoU gap (pp)" in text
    assert "combines fitting and train/test distribution differences" in " ".join(text.split())
    assert json.loads((out / "rad-paper.json").read_text())["request_sha256"] == digest(
        paper_campaign.request
    )


def test_semantic_panel_verifies_saved_prediction_hash(paper_campaign):
    request = json.loads(paper_campaign.request.read_text())
    job = request["jobs"][0]
    classes = yaml.safe_load((paper_campaign.data / "classes.json").read_text())["classes"]
    sample = json.loads((paper_campaign.data / "audit/samples.json").read_text())[0]
    panel = report.semantic_panel(request, job, sample["key"], classes, sample)
    assert Image.open(io.BytesIO(panel.getvalue())).size == (1500, 300)
    destination = (
        Path(request["output_root"]) / job["name"] / "predictions" / (sample["key"] + ".png")
    )
    destination.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="prediction differs"):
        report.semantic_panel(request, job, sample["key"], classes, sample)


def test_semantic_predictions_remain_visible_outside_ground_truth_support(paper_campaign):
    request = json.loads(paper_campaign.request.read_text())
    job = request["jobs"][0]
    classes = json.loads((paper_campaign.data / "classes.json").read_text())["classes"]
    sample = json.loads((paper_campaign.data / "audit/samples.json").read_text())[0]
    path = paper_campaign.data / "masks/test" / (sample["key"] + ".png")
    labels = np.asarray(Image.open(path)).copy()
    labels[0, 0] = 255
    Image.fromarray(labels).save(path)
    sample["mask_sha256"] = hashlib.sha256(labels.tobytes()).hexdigest()
    panel = np.asarray(
        Image.open(report.semantic_panel(request, job, sample["key"], classes, sample))
    )
    assert np.array_equal(panel[80, 540], [80, 80, 80])
    assert not np.array_equal(panel[80, 1040], [80, 80, 80])


def test_controller_runs_source_test_fixed_gpu_profile_report_and_propagates_cache(
    paper_campaign, monkeypatch
):
    calls = []
    verified = []
    monkeypatch.setattr(
        controller.source_stages,
        "validate_request",
        lambda *args: (
            {
                "models": paper_campaign.plan["research_protocol"]["models"],
                "jobs": [{"name": str(index)} for index in range(16)],
            },
            {},
            "spec",
        ),
    )
    monkeypatch.setattr(
        controller.source_stages, "verify_source", lambda job: verified.append(job["name"])
    )

    def command(words, **kwargs):
        name = Path(words[1]).name
        calls.append((name, words, kwargs["env"]))
        if name == "build_rad_paper_report.py":
            output = paper_campaign.root / "paper/report"
            output.mkdir(exist_ok=True)
            write(output / "rad-paper.json", {"request_sha256": digest(paper_campaign.request)})
            (output / "rad-paper.csv").write_text("synthetic\n")
            (output / "rad-paper.pdf").write_bytes(b"%PDF synthetic test")

    monkeypatch.setattr(controller.subprocess, "run", command)
    args = SimpleNamespace(
        campaign=paper_campaign.root,
        plan=None,
        repo=paper_campaign.root,
        python="python",
        benchmark_gpu=0,
        hf_home=paper_campaign.root / "cache",
    )
    result = controller.run(args)
    assert result["status"] == "completed"
    assert [call[0] for call in calls] == [
        "evaluate_rad_source_stages.py",
        "run_rad_test.py",
        "run_rad_test_profiles.py",
        "build_rad_paper_report.py",
    ]
    assert calls[2][1][-2:] == ["--gpu", "0"]
    assert all(call[2]["HF_HOME"] == str(args.hf_home) for call in calls)
    assert len(verified) == 16


def test_controller_blocks_before_test_if_training_recovery_cannot_finish(
    paper_campaign, monkeypatch
):
    monkeypatch.setattr(
        controller, "completed_jobs", lambda *args: (_ for _ in ()).throw(ValueError("incomplete"))
    )
    monkeypatch.setattr(controller.full, "recover_paper_job", lambda *args: False)
    calls = []
    with pytest.raises(ValueError, match="remains unavailable"):
        controller.train_until_complete(
            paper_campaign.root, paper_campaign.plan, lambda: calls.append("training")
        )
    assert calls == ["training"]


@pytest.mark.parametrize(
    "field,value",
    [("target_steps_per_job", 3999), ("validation_enabled", True), ("primary_checkpoint", "best")],
)
def test_confirmed_scope_rejects_changed_training_protocol(paper_campaign, field, value):
    plan = copy.deepcopy(paper_campaign.plan)
    plan[field] = value
    with pytest.raises(ValueError, match="confirmed paper scope"):
        controller.confirmed_scope(plan)


def test_preflight_validates_all_sources_before_training(paper_campaign, monkeypatch):
    verified = []
    monkeypatch.setattr(
        controller.source_stages,
        "validate_request",
        lambda *args: (
            {
                "models": paper_campaign.plan["research_protocol"]["models"],
                "jobs": [{"name": str(index)} for index in range(16)],
            },
            {},
            "spec",
        ),
    )

    def verify(job):
        verified.append(job["name"])
        if job["name"] == "15":
            raise ValueError("source checkpoint changed")

    monkeypatch.setattr(controller.source_stages, "verify_source", verify)
    monkeypatch.setattr(
        controller,
        "train_until_complete",
        lambda *args: pytest.fail("Training started before source verification"),
    )
    with pytest.raises(ValueError, match="source checkpoint changed"):
        controller.run(
            SimpleNamespace(
                campaign=paper_campaign.root,
                plan=None,
                repo=paper_campaign.root,
                python="python",
                benchmark_gpu=0,
                hf_home=None,
            )
        )
    assert len(verified) == 16


def test_dataset_binding_rejects_a_changed_frozen_audit(paper_campaign):
    path = paper_campaign.data / "audit/samples.json"
    path.write_text(path.read_text() + "\n")
    campaign = json.loads((paper_campaign.root / "campaign.json").read_text())
    with pytest.raises(ValueError, match="sample audit"):
        controller.dataset_binding(paper_campaign.plan, campaign)


def test_resource_summary_preserves_partial_measurement_counts():
    value = report.nullable_summary({0: 12.0, 1: None, 2: 14.0})
    assert value["mean"] == 13.0
    assert value["sample_sd"] == pytest.approx(np.sqrt(2))
    assert value["n"] == 2 and value["complete_three_seeds"] is False
    assert report.nullable_summary({0: None, 1: None, 2: None})["mean"] is None
    assert report.nullable_summary({0: 12.0, 1: None, 2: None})["sample_sd"] is None


def test_training_allocator_peak_uses_verified_invocation_history(tmp_path):
    prior = tmp_path / "prior.json"
    write(prior, {"peak_vram_bytes": {"cuda:0": 4 * 2**30}})
    state = {
        "training": {"peak_vram_bytes": {"cuda:0": 0}},
        "training_invocation_receipts": [{"path": str(prior), "sha256": digest(prior)}],
        "training_allocator_peak_accounting_complete": False,
        "missing_training_allocator_peak_attempts": ["interrupted"],
        "collection": {
            "resources": {"attempts": [{"phase": "training", "sampled_peak_device_used_mib": 9000}]}
        },
    }
    memory = report.training_memory(state)
    assert memory["allocator_peak_bytes"] == 4 * 2**30
    assert memory["sampled_driver_peak_bytes"] == 9000 * 2**20
    assert memory["allocator_accounting_complete"] is False


@pytest.mark.parametrize("paper_campaign", ["smp"], indirect=True)
def test_smp_public_encoder_evidence_prevents_false_missing_origin_warning(paper_campaign):
    value = report.load_report(paper_campaign.request)
    assert not any(
        "public checkpoint origins" in missing for missing in value["missing_provenance"]
    )
    for run in value["runs"]:
        assert run["training"]["env"]["model_origins"] == []
        origin = run["public_origin_evidence"]
        assert origin["basis"] == "source_public_pretraining_and_encoder_recipe"
        assert origin["runtime_model_origins_recorded"] is False
        assert "package-registry pin" in origin["revision_evidence"]
        assert "RAD runtime observation" in origin["revision_evidence"]
        assert origin["public_pretraining"]["public_checkpoint"] == "smp-hub/resnet50.imagenet"
        assert origin["public_pretraining"]["smp_registry_pinned_revision"] == "c" * 40


def test_smp_origin_requires_matching_public_pretraining_and_encoder_recipe():
    run = {
        "model": "smp-model",
        "training": {
            "env": {"model_origins": []},
            "config": {
                "model": {"arch": "smp", "encoder_name": "resnet50", "encoder_weights": "imagenet"}
            },
        },
    }
    stages = {
        "models": [
            {
                "model": "smp-model",
                "stages": [
                    {
                        "stage": "cityscapes",
                        "public_pretraining": {"public_checkpoint": "smp-hub/resnet101.imagenet"},
                    }
                ],
            }
        ]
    }
    assert report.public_origin_evidence(run, stages) is None
    stages["models"][0]["stages"][0]["public_pretraining"]["public_checkpoint"] = (
        "smp-hub/resnet50.imagenet"
    )
    assert report.public_origin_evidence(run, stages) is None
    stages["models"][0]["stages"][0]["public_pretraining"]["smp_registry_pinned_revision"] = (
        "c" * 40
    )
    assert report.public_origin_evidence(run, stages) is not None
    run["training"]["config"]["model"]["encoder_weights"] = None
    assert report.public_origin_evidence(run, stages) is None


@pytest.mark.parametrize("revision", [None, "", "c" * 39, "c" * 41, "g" * 40, 123])
def test_smp_origin_requires_a_valid_40_hex_registry_revision(revision):
    run = {
        "model": "smp-model",
        "training": {
            "env": {"model_origins": []},
            "config": {
                "model": {"arch": "smp", "encoder_name": "resnet50", "encoder_weights": "imagenet"}
            },
        },
    }
    stages = {
        "models": [
            {
                "model": "smp-model",
                "stages": [
                    {
                        "stage": "cityscapes",
                        "public_pretraining": {
                            "public_checkpoint": "smp-hub/resnet50.imagenet",
                            "smp_registry_pinned_revision": revision,
                        },
                    }
                ],
            }
        ]
    }
    assert report.public_origin_evidence(run, stages) is None


def test_training_timing_distinguishes_latest_invocation_and_accumulated_process_time():
    value = report.training_timing(
        {"wall_clock_s": 1.25},
        {
            "phase_wall_seconds_including_failed_attempts": {"training": 90.5},
            "phase_wall_seconds_are_lower_bounds": {"training": True},
            "phase_accounting_complete": {"training": False},
        },
    )
    assert value["latest_invocation_run_record_wall_seconds"] == 1.25
    assert value["recorded_training_process_wall_seconds_all_attempts"] == 90.5
    assert value["recorded_training_process_seconds_is_lower_bound"] is True
    assert value["training_process_accounting_complete"] is False
    missing = report.training_timing({"wall_clock_s": 1.25}, {})
    assert missing["recorded_training_process_wall_seconds_all_attempts"] is None


def test_report_code_identity_preserves_frozen_training_execution_identity(
    paper_campaign, monkeypatch
):
    request = json.loads(paper_campaign.request.read_text())
    monkeypatch.setattr(report, "git_sha", lambda path: ("report-only-code", True))
    value = report.load_report(paper_campaign.request)
    assert value["report_code_sha"] == "report-only-code"
    assert value["report_code_dirty"] is True
    assert value["training_code_sha"] == request["training_code_sha"]
    assert (
        json.loads(paper_campaign.request.read_text())["training_code_sha"]
        == request["training_code_sha"]
    )


def test_recorded_duration_lower_bounds_preserve_observed_statistics_without_full_run_sd():
    runs = {
        seed: {
            "training": {"wall_clock_s": 1.0},
            "training_resources": {
                "phase_wall_seconds_including_failed_attempts": {"training": seconds},
                "phase_wall_seconds_are_lower_bounds": {"training": seed == 0},
            },
        }
        for seed, seconds in enumerate((3600, 7200, None))
    }
    value = report.recorded_training_hours(runs)
    assert value["mean"] == 1.5
    assert value["sample_sd"] is None
    assert value["observed_sample_sd"] == pytest.approx(np.sqrt(0.5))
    assert value["lower_bound_seeds"] == [0]
    assert value["mean_and_range_are_lower_bounds"] is True
    assert value["n"] == 2


def test_lower_bound_resource_json_csv_and_pdf_keep_unknown_full_run_sd(paper_campaign, tmp_path):
    pytest.importorskip("reportlab")
    reader = pytest.importorskip("pypdf")
    value = report.load_report(paper_campaign.request)
    model = value["runs"][0]["model"]
    for run in value["runs"]:
        if run["model"] != model:
            continue
        seed = run["seed"]
        run["training_memory"]["allocator_peak_bytes"] = (seed + 1) * 2**30
        run["training_memory"]["allocator_accounting_complete"] = False
        run["training_resources"]["phase_wall_seconds_including_failed_attempts"]["training"] = (
            seed + 1
        ) * 3600
        run["training_resources"]["phase_wall_seconds_are_lower_bounds"] = {"training": True}
        run["training"]["env"]["training_observations"] = {
            "examples_seen_this_invocation": 100,
            "optimizer_steps_this_invocation": 10,
        }
        run["training_timing"] = report.training_timing(run["training"], run["training_resources"])
    value["aggregates"] = report.aggregate(value["runs"], value["class_names"])
    summary = next(entry for entry in value["aggregates"] if entry["model"] == model)
    assert summary["training_peak_bytes"]["sample_sd"] is None
    assert summary["training_peak_bytes"]["observed_sample_sd"] == 2**30
    assert summary["training_hours"]["sample_sd"] is None
    assert summary["training_hours"]["observed_sample_sd"] == 1.0
    json_path = tmp_path / "lower-bound-report.json"
    write(json_path, value)
    stored = json.loads(json_path.read_text())["aggregates"][0]
    assert stored["training_peak_bytes"]["sample_sd"] is None
    csv_path = tmp_path / "lower-bound-report.csv"
    report.write_csv(csv_path, value)
    with csv_path.open() as stream:
        row = next(row for row in csv.DictReader(stream) if row["model"] == model)
    for field in ("training_hours", "training_peak_bytes"):
        assert row[f"{field}:sample_sd"] == ""
        assert row[f"{field}:seed_0_is_lower_bound"] == "True"
        assert row[f"{field}:observed_sample_sd"]
    pdf_path = tmp_path / "lower-bound-report.pdf"
    report.build_pdf(pdf_path, value)
    text = "\n".join(page.extract_text() for page in reader.PdfReader(pdf_path).pages)
    assert ">= 2.00" in text and "Unknown" in text
    assert "Latest-invocation training observations" in text
    assert "Earlier source invocation history is unknown" in text
    assert "hash-verified training invocation receipts" in text


def full_train_inputs(case):
    request = json.loads(case.request.read_text())
    job = request["jobs"][0]
    state = json.loads(Path(job["state_path"]).read_text())
    test_result = json.loads(
        (Path(request["output_root"]) / job["name"] / "result.json").read_text()
    )
    support = report.class_split_support(
        json.loads((case.data / "audit/samples.json").read_text()), request["class_names"]
    )
    return job, state, request, request["class_names"], support, test_result


def test_full_train_record_supplies_all_255_images_even_with_limited_diagnostics(paper_campaign):
    arguments = full_train_inputs(paper_campaign)
    arguments[1]["collection"]["diagnostics"]["results"]["final-auto-train"]["images"] = 2
    value = report.full_train_evaluation(*arguments)
    assert value["images"] == 255
    assert value["pixel_pooled"]["valid_pixels"] == 10710
    assert value["record"]["dataset_sizes"] == {"eval": 255}
    assert Path(value["source"]["path"]).name == "final-train.json"


@pytest.mark.parametrize(
    "defect",
    [
        "sha",
        "inline",
        "endpoint",
        "config",
        "bank",
        "final_policy",
        "count",
        "determinism",
        "padding",
        "tta",
        "support",
        "score",
        "test_bank",
        "test_inference",
        "profile_result",
    ],
)
def test_full_train_evaluation_rejects_inconsistent_evidence(paper_campaign, defect):
    arguments = full_train_inputs(paper_campaign)
    _job, state, _request, _names, _support, test_result = arguments
    record = copy.deepcopy(state["evaluation"])
    if defect == "sha":
        state["evaluation_result"]["sha256"] = "0" * 64
    elif defect == "inline":
        state["evaluation"]["metrics"]["miou"] = 0.0
    else:
        if defect == "endpoint":
            state["checkpoints"]["final"]["sha256"] = "0" * 64
        elif defect == "config":
            record["config"]["optim"]["backbone_lr"] = 0.5
        elif defect == "bank":
            record["config"]["evaluation"]["weights"] = "ema"
        elif defect == "final_policy":
            state["training"]["env"]["final_weights_policy"] = "ema"
        elif defect == "count":
            record["dataset_sizes"]["eval"] = 2
        elif defect == "determinism":
            record["config"]["evaluation"]["deterministic"] = False
        elif defect == "padding":
            record["config"]["evaluation"]["padding"]["multiple"] = 16
        elif defect == "tta":
            record["config"]["evaluation"]["tta"]["flip"] = True
        elif defect == "support":
            record["metrics"]["confusion"][0][0] -= 1
        elif defect == "score":
            record["metrics"]["miou"] = 0.5
        elif defect == "test_bank":
            test_result["weights"] = "ema"
        elif defect == "test_inference":
            test_result["inference"]["window"] = [512, 512]
        record["config_hash"] = report.config_hash(record["config"])
        path = Path(state["evaluation_result"]["path"])
        write(path, record)
        state["evaluation"] = record
        state["evaluation_result"]["sha256"] = digest(path)
        state["performance"]["source"]["result_sha256"] = digest(path)
        if defect == "profile_result":
            state["performance"]["source"]["result_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        report.full_train_evaluation(*arguments)
