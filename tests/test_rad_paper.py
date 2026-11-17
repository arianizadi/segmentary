"""CPU-only complete-run freezing, report arithmetic and PDF integration checks."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
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
from scripts.rad_paper_metrics import paper_metrics
from scripts.run_rad_test import digest, write

from segmentary import gpu_policy


@pytest.fixture
def paper_campaign(tmp_path, monkeypatch):
    root = tmp_path / "campaign"
    root.mkdir()
    data = tmp_path / "dataset"
    taxonomy = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "taxonomy/paul-test-rtis/canonical.yaml").read_text()
    )
    write(data / "classes.json", taxonomy)
    names = [value["name"] for value in taxonomy["classes"]]
    target = np.arange(21, dtype=np.uint8).reshape(3, 7)
    samples = []
    for index in range(2):
        key = f"block-{index}/sample"
        rgb = np.full((3, 7, 3), 80 + 20 * index, dtype=np.uint8)
        image_path = data / "images/test" / (key + ".png")
        mask_path = data / "masks/test" / (key + ".png")
        image_path.parent.mkdir(parents=True)
        mask_path.parent.mkdir(parents=True)
        Image.fromarray(rgb).save(image_path)
        Image.fromarray(target).save(mask_path)
        samples.append(
            {
                "key": key,
                "split": "test",
                "group": f"block-{index}",
                "image_extension": ".png",
                "image_sha256": digest(image_path),
                "mask_sha256": hashlib.sha256(target.tobytes()).hexdigest(),
                "width": 7,
                "height": 3,
                "class_pixels": {str(index): 1 for index in range(21)},
            }
        )
    write(
        data / "splits.json",
        {"train": ["train-group/sample"], "val": [], "test": [sample["key"] for sample in samples]},
    )
    train_labels = np.tile(target, (2, 1))
    train_image = data / "images/train/train-group/sample.png"
    train_mask = data / "masks/train/train-group/sample.png"
    train_image.parent.mkdir(parents=True)
    train_mask.parent.mkdir(parents=True)
    Image.new("RGB", (7, 6), color="gray").save(train_image)
    Image.fromarray(train_labels).save(train_mask)
    train_sample = {
        "key": "train-group/sample",
        "split": "train",
        "group": "train-group",
        "image_extension": ".png",
        "image_sha256": digest(train_image),
        "mask_sha256": hashlib.sha256(train_labels.tobytes()).hexdigest(),
        "width": 7,
        "height": 6,
        "class_pixels": {str(index): 2 for index in range(21)},
    }
    write(data / "audit/samples.json", [*samples, train_sample])
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
                        "metrics": {"metrics": source_metrics},
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
    write(tmp_path / "source-stage/source-stage-reports.json", source_report)
    monkeypatch.setattr(
        source_evaluator, "load_verified_report", lambda *args: source_report, raising=False
    )
    protocol = {
        "models": ["tiny_model"],
        "seeds": [0, 1, 2],
        "primary_metric": "pixel_pooled_miou",
        "headline_protocol": "cityscapes_to_railsem19_to_rtis",
        "qualitative_seed": 0,
        "qualitative_keys": [samples[0]["key"]],
        "failure_rule": "max-three infrastructure attempts; nonfinite loss is terminal",
        "split_policy": "255/0/59 frozen test membership",
        "source_stage_reports": {"spec": str(source_spec), "spec_sha256": digest(source_spec)},
    }
    jobs = []
    code = "a" * 40
    for seed in range(3):
        name = f"tiny_model--cityscapes_to_railsem19_to_rtis--seed-{seed}"
        config = root / "configs" / (name + ".yaml")
        config.parent.mkdir(exist_ok=True)
        cfg = {
            "stages": [{"data": [{"root": str(data)}], "lr_scale": 0.1}],
            "model": {"arch": "tiny"},
            "optim": {"backbone_lr": 1e-5},
        }
        config.write_text(yaml.safe_dump(cfg))
        checkpoint = root / name / "last.ckpt"
        checkpoint.parent.mkdir()
        checkpoint.write_bytes(f"checkpoint-{seed}".encode())
        job = {
            "name": name,
            "model": "tiny_model",
            "protocol": protocol["headline_protocol"],
            "seed": seed,
            "config": str(config),
            "config_sha256": digest(config),
            "source_checkpoint": None,
        }
        jobs.append(job)
        write(
            root / "state" / (name + ".json"),
            {
                "name": name,
                "status": "completed",
                "code_sha": code,
                "config_sha256": job["config_sha256"],
                "final_step": 4,
                "checkpoints": {
                    "final": {
                        "path": str(checkpoint),
                        "sha256": digest(checkpoint),
                        "global_step": 4,
                    }
                },
                "collection": {
                    "verified": True,
                    "contract": "rtis-final-train-statistics-v2",
                    "resources": {
                        "phase_wall_seconds_including_failed_attempts": {"training": 90 + seed}
                    },
                },
                "training": {
                    "config": cfg,
                    "peak_vram_bytes": {"cuda:0": 2**30},
                    "wall_clock_s": 90 + seed,
                    "env": {
                        "model_origins": [{"hf_name_or_path": "synthetic", "hf_commit": "pinned"}]
                    },
                },
            },
        )
    plan = {
        "jobs": jobs,
        "collection_contract": "rtis-final-train-statistics-v2",
        "target_steps_per_job": 4,
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
            destination.parent.mkdir(parents=True)
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
            {name: {"positive_images": 2, "pixels": 2} for name in names},
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
            "images": 2,
            "weights": "raw",
            "present_image": {
                "images": 2,
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
    values = [run["metrics"]["pixel_pooled"]["miou"] for run in result["runs"]]
    assert aggregate["pixel_pooled_miou"]["mean"] == pytest.approx(np.mean(values))
    assert aggregate["pixel_pooled_miou"]["sample_sd"] == pytest.approx(np.std(values, ddof=1))
    assert len(aggregate["per_class"]) == 21
    assert result["qualitative"]["seed"] == 0
    assert "+/-" not in report.format_summary(aggregate["pixel_pooled_miou"])
    assert result["split_totals"] == {
        "train": {"images": 1, "valid_pixels": 42},
        "test": {"images": 2, "valid_pixels": 42},
    }
    assert result["class_split_support"]["mud-pumping"]["train"]["positive_images"] == 1
    assert result["class_split_support"]["mud-pumping"]["test"]["positive_images"] == 2


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
    assert support["totals"]["train"]["valid_pixels"] == 42
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
    assert len(rows) == 1
    assert "pixel_pooled_miou:seed_2" in rows[0]
    assert "pixels:mud-pumping" in rows[0]
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
