"""Independent pixel checks for native reference dataset auditing."""

import json

import numpy as np
import pytest
from PIL import Image, ImageDraw
from scripts.audit_reference_datasets import (
    CITY_NAMES,
    audit,
    city_geometry,
    mask_stats,
    polygon_region,
)


def test_common_mask_denominators_and_ignore():
    stats = mask_stats(np.array([[0, 0], [255, 77]], dtype=np.uint8), {0, 255}, {255}, 0.5)
    assert stats["pixels"] == 4
    assert stats["ignore_pixels"] == 1
    assert stats["invalid_ids"] == [77]
    assert stats["dominant_classes"] == [0]
    assert stats["boundary_pairs"] == 3
    assert stats["neighbor_pairs"] == 4
    assert mask_stats(np.full((2, 2), 255), {255}, {255})["flags"] == ["all_ignore"]


@pytest.mark.parametrize(
    "points",
    [
        [[0, 0], [7, 0], [7, 5], [0, 5]],
        [[1.2, 0.7], [6.9, 2.1], [4.4, 4.7]],
        [[-3, -2], [5, 2], [1, 8]],
        [[30, 30], [40, 30], [30, 40]],
    ],
)
def test_crop_raster_matches_full_pil(points):
    image = Image.new("1", (8, 6))
    ImageDraw.Draw(image).polygon([tuple(p) for p in points], fill=1)
    crop, region = polygon_region(points, (8, 6))
    actual = np.zeros((6, 8), bool)
    actual[crop] = region
    np.testing.assert_array_equal(actual, np.asarray(image))


def test_city_official_order_deleted_group_negative_label():
    whole = [[0, 0], [3, 0], [3, 3], [0, 3]]
    bottom = [[0, 2], [3, 2], [3, 3], [0, 3]]
    data = dict(
        imgWidth=4,
        imgHeight=4,
        objects=[
            dict(label="sky", polygon=whole),
            dict(label="cargroup", polygon=bottom),
            dict(label="person", polygon=whole, deleted=1),
            dict(label="license plate", polygon=whole),
        ],
    )
    final = np.full((4, 4), CITY_NAMES.index("sky"), np.uint8)
    final[2:] = CITY_NAMES.index("car")
    result = city_geometry(data, final)
    assert result["mismatch_pixels"] == 0
    assert result["source_objects"] == 2
    assert result["cross_class_overlap_pixels"] == 8
    assert result["objects_lost_at_least_half"] == 1
    assert result["lost_objects"][0]["cross_class_lost_pixels"] == 8


def test_rail_fixture_uses_split_lists_sparse_source_not_full_render(tmp_path):
    root = tmp_path / "rail"
    for sub in ["uint8/rs19_val", "jpgs/rs19_val", "jsons/rs19_val", "splits"]:
        (root / sub).mkdir(parents=True)
    (root / "rs19-config.json").write_text(json.dumps({"labels": [{"name": "road"}]}))
    (root / "splits/train.txt").write_text("rs00001\n")
    Image.fromarray(np.zeros((4, 4), np.uint8)).save(root / "uint8/rs19_val/rs00001.png")
    Image.fromarray(np.zeros((4, 4, 3), np.uint8)).save(root / "jpgs/rs19_val/rs00001.jpg")
    (root / "jsons/rs19_val/rs00001.json").write_text(
        json.dumps(
            dict(
                imgWidth=4,
                imgHeight=4,
                objects=[dict(label="pole", polygon=[[0, 0], [1, 0], [1, 1]])],
            )
        )
    )
    summary = audit("railsem19", root, tmp_path / "audit")
    assert summary["splits"]["train"]["images"] == 1
    assert summary["splits"]["train"]["geometry_checked_images"] == 0
    assert summary["splits"]["train"]["geometry"]["mismatch_pixels"] is None
    assert summary["splits"]["train"]["flags"] == {"dominant_class": 1}
    assert summary["classes"]["0"]["total_pixels"] == 16
    assert "Unavailable" in summary["geometry_comparison"]
    row = json.loads((tmp_path / "audit/images.jsonl").read_text())
    assert "geometry" not in row
    assert row["source_geometry_types"] == {"polygon": 1}
    with pytest.raises(ValueError, match="outside"):
        audit("railsem19", root, root / "audit")


def test_boundary_tolerance_keeps_large_interior_differences_visible():
    from scripts.audit_reference_datasets import mismatch_distances

    expected = np.zeros((15, 15), np.uint8)
    actual = expected.copy()
    actual[2:13, 2:13] = 1
    result = mismatch_distances(expected, actual)
    assert result["mismatch_near_boundary_2px"] + result["mismatch_interior_beyond_2px"] == 121
    assert result["mismatch_interior_beyond_2px"] == 25


def test_original_coordinates_preserve_pil_edge_rounding():
    # Translating this polygon to a bounding-box origin changes PIL edge pixels.
    points = [[38, 52], [9, 30], [38, 20], [34, 59]]
    full = Image.new("L", (64, 64))
    ImageDraw.Draw(full).polygon([tuple(point) for point in points], fill=1)
    selection, region = polygon_region(points, (64, 64))
    actual = np.zeros((64, 64), bool)
    actual[selection] = region
    np.testing.assert_array_equal(actual, np.asarray(full, bool))
