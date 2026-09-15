"""Portable reviews remain bound to evidence and preserve reviewer revisions."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess

import pytest

from segmentary.medical.failure_review import (
    _PAGE,
    _payload,
    decision_summary,
    validate_decisions,
    write_failure_review,
)


def report():
    return {
        "schema_version": 1,
        "kind": "medical_failure_analysis",
        "report_id": "report-a",
        "partition": "val",
        "models": [{"id": "dynunet"}, {"id": "swin"}],
        "protocol": {"selection": "native best", "partition_sha256": "a" * 64},
        "cases": [
            {
                "case_key": "case-opaque-a",
                "status": "completed",
                "features": {"spacing_mm": [1.0, 1.0, 2.5]},
                "models": {
                    "dynunet": {
                        "status": "completed",
                        "mass_dice": 0.2,
                        "pancreas_dice": 0.8,
                        "missed_lesions": 2,
                        "false_positive_lesions": 1,
                        "flags": ["missed_mass"],
                        "panels": {"axial": ["panels/a.png", "panels/b.png"]},
                    },
                    "swin": {
                        "status": "completed",
                        "mass_dice": 0.3,
                        "flags": [],
                        "panels": {"axial": ["panels/c.png", "panels/d.png"]},
                    },
                },
            }
        ],
    }


def export(value=None):
    value = value or report()
    payload = _payload(value)
    key = value["cases"][0]["case_key"]
    return {
        "schema_version": 1,
        "kind": "medical_failure_review_decisions",
        "report_id": value["report_id"],
        "report_evidence_sha256": payload["report_evidence_sha256"],
        "decisions": [
            {
                "case_key": key,
                "model_id": "dynunet",
                "evidence_sha256": payload["case_evidence"][key],
                "reviewer_id": "r1",
                "verdict": "model_failure",
                "categories": ["localization_miss", "small_lesion"],
                "confidence": "medium",
                "notes": "Suspicious missed lesion; radiologist review requested.",
                "reviewed_at": "2026-09-15T02:00:00.000Z",
                "is_blinded": True,
                "revision": 1,
            }
        ],
    }


def make_panels(root, value):
    for case in value["cases"]:
        for result in case["models"].values():
            for paths in result.get("panels", {}).values():
                for relative in paths:
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"png-test-placeholder")


def test_revision_history_summary_counts_latest_per_reviewer_and_scope():
    value = report()
    original = copy.deepcopy(value)
    reviews = export(value)
    first = reviews["decisions"][0]
    revised = {
        **first,
        "revision": 2,
        "reviewed_at": "2026-09-15T02:01:00Z",
        "verdict": "annotation_uncertain",
        "categories": ["annotation_ambiguity"],
        "is_blinded": False,
    }
    reviews["decisions"] += [
        revised,
        {**first, "reviewer_id": "r2"},
        {**first, "model_id": None},
    ]
    validated = validate_decisions(value, reviews)
    assert validated["decisions"] == reviews["decisions"]
    summary = decision_summary(value, validated)
    assert summary["history_records"] == 4
    assert summary["effective_decisions"] == 3
    assert summary["cases_reviewed"] == 1
    assert summary["reviewers"] == 2
    assert summary["verdict_counts"]["annotation_uncertain"] == 1
    assert summary["verdict_counts"]["model_failure"] == 2
    assert summary["blinded_decisions"] == 2
    assert summary["category_counts"]["annotation_ambiguity"] == 1
    assert value == original


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("report_id", "different"),
        ("report_evidence_sha256", "f" * 64),
        ("schema_version", True),
        ("kind", "annotation_edits"),
        ("extra", "unrecognized"),
        ("decisions", {}),
        ("summary", {"cases_reviewed": 100}),
    ],
)
def test_reject_invalid_export(field, value):
    reviews = export()
    reviews[field] = value
    with pytest.raises(ValueError):
        validate_decisions(report(), reviews)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case_key", "unknown"),
        ("model_id", "unknown"),
        ("model_id", ["dynunet"]),
        ("evidence_sha256", "f" * 64),
        ("reviewer_id", ""),
        ("reviewer_id", "x" * 101),
        ("verdict", "labels_modified"),
        ("confidence", 1),
        ("categories", ["localization_miss", "localization_miss"]),
        ("categories", ["unknown"]),
        ("categories", {}),
        ("notes", "x" * 10001),
        ("notes", "bad\0text"),
        ("reviewed_at", "2026-09-15T02:00:00"),
        ("reviewed_at", "2026-02-30T02:00:00Z"),
        ("reviewed_at", "2026-09-15T02:00:00+25:00"),
        ("revision", True),
        ("revision", 2),
        ("is_blinded", 1),
        ("extra", "field"),
    ],
)
def test_reject_invalid_decision(field, value):
    reviews = export()
    reviews["decisions"][0][field] = value
    with pytest.raises(ValueError):
        validate_decisions(report(), reviews)


def test_unknown_case_model_rejected_even_if_present_elsewhere_in_report():
    value = report()
    del value["cases"][0]["models"]["dynunet"]
    reviews = export(value)
    with pytest.raises(ValueError, match="Unknown model for case"):
        validate_decisions(value, reviews)


@pytest.mark.parametrize("change", ["duplicate", "skipped", "reverse_time"])
def test_invalid_revision_history_rejected(change):
    reviews = export()
    second = {**reviews["decisions"][0], "revision": 2}
    if change == "duplicate":
        second["revision"] = 1
    if change == "skipped":
        second["revision"] = 3
    if change == "reverse_time":
        second["reviewed_at"] = "2026-09-15T01:00:00Z"
    reviews["decisions"].append(second)
    with pytest.raises(ValueError):
        validate_decisions(report(), reviews)


def test_evidence_includes_geometry_predictions_protocol_and_panel_paths():
    baseline = report()
    reviews = export(baseline)
    mutations = []
    for field, value in [("mass_dice", 0.9), ("prediction_sha256", "1" * 64)]:
        changed = copy.deepcopy(baseline)
        changed["cases"][0]["models"]["dynunet"][field] = value
        mutations.append(changed)
    changed = copy.deepcopy(baseline)
    changed["cases"][0]["features"]["spacing_mm"][2] = 1.0
    mutations.append(changed)
    changed = copy.deepcopy(baseline)
    changed["protocol"]["partition_sha256"] = "f" * 64
    mutations.append(changed)
    changed = copy.deepcopy(baseline)
    changed["cases"][0]["models"]["dynunet"]["panels"]["axial"][0] = "panels/other.png"
    mutations.append(changed)
    for changed in mutations:
        with pytest.raises(ValueError, match="different report evidence"):
            validate_decisions(changed, reviews)
    # Even copying a new report-level hash does not rebind the per-case evidence.
    changed = mutations[0]
    reviews["report_evidence_sha256"] = _payload(changed)["report_evidence_sha256"]
    with pytest.raises(ValueError, match="Case evidence mismatch"):
        validate_decisions(changed, reviews)


@pytest.mark.parametrize(
    "path",
    [
        "../private.png",
        "/private.png",
        "https://example.com/image.png",
        "//example.com/image.png",
        "a/../private.png",
        "a\\private.png",
        "a/%2e%2e/private.png",
        "a/private.png?secret",
        "a/private.png#fragment",
        "a\nimage.png",
        "a//image.png",
        "a/./image.png",
        "a/image.svg",
    ],
)
def test_unsafe_panel_paths_rejected(tmp_path, path):
    value = report()
    value["cases"][0]["models"]["dynunet"]["panels"]["axial"][0] = path
    with pytest.raises(ValueError, match="safe relative PNG"):
        write_failure_review(tmp_path, value)


def test_panel_existence_symlink_and_immutable_output(tmp_path):
    value = report()
    with pytest.raises(ValueError, match="Missing or outside"):
        write_failure_review(tmp_path, value)
    make_panels(tmp_path, value)
    outside = tmp_path.parent / "unrelated.png"
    outside.write_bytes(b"unrelated")
    inside = tmp_path / "panels/a.png"
    inside.unlink()
    inside.symlink_to(outside)
    with pytest.raises(ValueError, match="outside report"):
        write_failure_review(tmp_path, value)
    inside.unlink()
    inside.write_bytes(b"panel")
    write_failure_review(tmp_path, value)
    with pytest.raises(FileExistsError):
        write_failure_review(tmp_path, value)
    assert outside.read_bytes() == b"unrelated"


def test_counts_must_be_synchronized_but_missing_model_panels_allowed(tmp_path):
    value = report()
    value["cases"][0]["models"]["swin"]["panels"]["axial"].pop()
    with pytest.raises(ValueError, match="matching panel counts"):
        write_failure_review(tmp_path, value)
    value["cases"][0]["models"]["swin"]["panels"] = {}
    make_panels(tmp_path, value)
    assert write_failure_review(tmp_path, value)["cases"] == 1


def test_safe_html_payload_and_offline_default_blinding(tmp_path):
    value = report()
    attack = '</script><script>alert("unsafe")</script>&\u2028'
    value["cases"][0]["case_key"] = attack
    value["cases"][0]["features"]["comment"] = attack
    make_panels(tmp_path, value)
    summary = write_failure_review(tmp_path, value)
    page = (tmp_path / "review.html").read_text()
    encoded = page.split('<script id="reviewData" type="application/json">')[1].split("</script>")[
        0
    ]
    payload = json.loads(encoded)
    assert payload["report"] == value
    assert attack not in page
    assert "\\u003c/script\\u003e" in encoded
    assert "connect-src 'none'" in page
    assert "innerHTML" not in page
    assert "blinded=true" in page
    assert summary["blinded_by_default"] is True
    assert "is_blinded:blinded&&!everRevealed" in page
    assert "localStorage.setItem(storeKey+':revealed','true')" in page
    assert "No annotations changed" in page


def test_empty_report_supported_without_images(tmp_path):
    value = report()
    value["cases"] = []
    value["models"] = []
    summary = write_failure_review(tmp_path, value)
    assert summary["cases"] == summary["models"] == 0
    reviews = {
        "schema_version": 1,
        "kind": "medical_failure_review_decisions",
        "report_id": value["report_id"],
        "report_evidence_sha256": summary["report_evidence_sha256"],
        "decisions": [],
    }
    assert decision_summary(value, reviews)["cases_reviewed"] == 0


@pytest.mark.parametrize("change", ["duplicate_case", "duplicate_model", "reserved_test"])
def test_report_membership_contract(change):
    value = report()
    if change == "duplicate_case":
        value["cases"].append(copy.deepcopy(value["cases"][0]))
    elif change == "duplicate_model":
        value["models"].append({"id": "dynunet"})
    else:
        value["partition"] = "test"
    with pytest.raises(ValueError):
        _payload(value)


def run_browser_validation(value, reviews, tail="validate(fixture.reviews)"):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node is unavailable for offline JavaScript parity check")
    script = _PAGE.split("<script>\n")[1].split("</script>")[0]
    # Execute the exact browser validation/merge code without a DOM implementation.
    validation_code = script.split("\nfillOptions(el('verdict')")[0]
    program = (
        "const fixture=JSON.parse(require('node:fs').readFileSync(0,'utf8'));"
        "global.document={getElementById:()=>({textContent:JSON.stringify(fixture.payload)})};\n"
        + validation_code
        + "\nconsole.log(JSON.stringify("
        + tail
        + "));"
    )
    return subprocess.run(
        [executable, "-e", program],
        input=json.dumps({"payload": _payload(value), "reviews": reviews}),
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )


def test_browser_python_validation_and_summary_match():
    value = report()
    reviews = validate_decisions(value, export(value))
    result = run_browser_validation(value, reviews, "exportObject(validate(fixture.reviews))")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == reviews


@pytest.mark.parametrize("change", ["date", "summary", "unknown", "duplicate", "evidence"])
def test_browser_rejects_same_malformed_reviews_as_python(change):
    value = report()
    reviews = export(value)
    if change == "date":
        reviews["decisions"][0]["reviewed_at"] = "2026-02-30T02:00:00Z"
    elif change == "summary":
        reviews["summary"] = {"cases_reviewed": 100}
    elif change == "unknown":
        reviews["decisions"][0]["anything"] = "unexpected"
    elif change == "duplicate":
        reviews["decisions"].append(reviews["decisions"][0].copy())
    else:
        reviews["decisions"][0]["evidence_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        validate_decisions(value, reviews)
    result = run_browser_validation(value, reviews)
    assert result.returncode != 0


def test_browser_import_deduplicates_identical_and_rejects_conflicts():
    value = report()
    reviews = export(value)
    result = run_browser_validation(
        value,
        reviews,
        "(()=>{records=validate(fixture.reviews);return mergeImport(records)})()",
    )
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)) == 1
    result = run_browser_validation(
        value,
        reviews,
        "(()=>{records=validate(fixture.reviews);const imported=structuredClone(records);"
        "imported[0].notes='conflicting edit';return mergeImport(imported)})()",
    )
    assert result.returncode != 0
    assert "Conflicting revision" in result.stderr
