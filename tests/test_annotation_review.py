"""Review priorities preserve observations without asserting annotation errors."""

import json

import pytest
from scripts.annotation_review import write_review

SCHEMA = {"classes": [{"id": 13, "name": "mud-pumping"}, {"id": 16, "name": "sky"}]}


def sample(key="image", **kwargs):
    return {
        "key": key,
        "split": "train",
        "pixels": 1000,
        "class_pixels": {"13": 600},
        "class_source_pixels": {"13": 1000},
        "objects": [],
        "flags": [],
        **kwargs,
    }


def test_full_frame_unflagged_candidates_and_notice_separation(tmp_path):
    rows = [sample(str(i)) for i in range(17)]
    rows += [
        sample(
            "legacy",
            class_pixels={},
            class_source_pixels={},
            flags=["source_annotation_packaging_hash_unavailable"],
        )
    ]
    summary = write_review(tmp_path, {"samples": rows}, SCHEMA, "mud-pumping")
    assert summary["source_full_frame_candidates"] == 17
    assert summary["priority_counts"]["focus"] == 17
    assert summary["priority_counts"]["notices"] == 1
    assert summary["priority_counts"]["integrity"] == 0
    assert rows[0]["flags"] == []
    assert (tmp_path / "review-ranked.csv").is_file()


def test_integrity_precedes_focus_and_payload_is_safe(tmp_path):
    s = sample(
        "</script><script>alert(1)</script>", flags=["training_mask_differs_from_native_render"]
    )
    summary = write_review(tmp_path, {"samples": [s]}, SCHEMA, "13")
    assert summary["priority_counts"]["integrity"] == 1
    page = (tmp_path / "index.html").read_text()
    assert "</script><script>alert(1)</script>" not in page
    raw = page.split('<script id="data" type="application/json">')[1].split("</script>")[0]
    assert json.loads(raw)["rows"][0]["key"] == s["key"]


def test_loss_recipients_and_context_retained(tmp_path):
    obj = {
        "id": "mud1",
        "class_id": 13,
        "source_pixels": 10,
        "cross_class_lost_pixels": 9,
        "lost_fraction": 0.9,
    }
    s = sample(
        class_pixels={"13": 1},
        class_source_pixels={"13": 10},
        objects=[obj],
        overwrite_events=[{"from_object": "mud1", "to_class": 16, "pixels": 9}],
        flags=["object_class_coverage_lost:mud1"],
    )
    write_review(tmp_path, {"samples": [s]}, SCHEMA, "mud-pumping")
    page = (tmp_path / "index.html").read_text()
    raw = page.split('<script id="data" type="application/json">')[1].split("</script>")[0]
    row = json.loads(raw)["rows"][0]
    assert row["priority"] == "focus"
    assert row["losses"][0]["recipients"] == [{"class": "sky", "pixels": 9}]
    assert row["flags"] == s["flags"]


@pytest.mark.parametrize("focus", ["bogus", "", "14"])
def test_unknown_focus_rejected(tmp_path, focus):
    with pytest.raises(ValueError, match="focus class"):
        write_review(tmp_path, {"samples": []}, SCHEMA, focus)


@pytest.mark.parametrize(
    "path", ["../bad.jpg", "/bad.jpg", "https://example.com/a.jpg", "a\\bad.jpg"]
)
def test_preview_path_rejected(tmp_path, path):
    with pytest.raises(ValueError, match="safe relative"):
        write_review(tmp_path, {"samples": [sample(preview=path)]}, SCHEMA, None)
