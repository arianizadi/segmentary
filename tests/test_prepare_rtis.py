"""Geometry checks against hand-specified pixels, independent of real exports."""

import base64
import io
import xml.etree.ElementTree as ET
import zlib

import numpy as np
import pytest
from PIL import Image
from scripts.prepare_rtis import cvat_bitmap, polygon, render, sly_bitmap


def test_polygon_preserves_hole():
    result = polygon((7, 7), [[1, 1], [5, 1], [5, 5], [1, 5]], [[[2, 2], [4, 2], [4, 4], [2, 4]]])
    assert result.sum() == 16
    assert result[1, 1] and not result[3, 3] and not result[0, 0]


def test_cvat_row_major_rle_and_origin():
    obj = ET.fromstring('<mask width="3" height="2" left="2" top="1" rle="1, 2, 2, 1"/>')
    result = cvat_bitmap(obj, (5, 6))
    assert set(map(tuple, np.argwhere(result))) == {(1, 3), (1, 4), (2, 4)}
    obj.set("rle", "1, 2")
    with pytest.raises(ValueError, match="RLE"):
        cvat_bitmap(obj, (5, 6))


def test_supervisely_uses_alpha_not_rgb():
    arr = np.full((2, 3, 4), 255, np.uint8)
    arr[:, :, 3] = [[0, 255, 0], [255, 0, 255]]
    stream = io.BytesIO()
    Image.fromarray(arr).save(stream, format="PNG")
    obj = {
        "bitmap": {
            "origin": [2, 1],
            "data": base64.b64encode(zlib.compress(stream.getvalue())).decode(),
        }
    }
    result = sly_bitmap(obj, (5, 6))
    assert set(map(tuple, np.argwhere(result))) == {(1, 3), (2, 2), (2, 4)}


def test_mixed_geometry_preserves_class_and_void_priority():
    objects = [
        ET.fromstring('<polygon label="road" points="0,0;4,0;4,4;0,4"/>'),
        ET.fromstring('<mask label="water" width="2" height="2" left="1" top="1" rle="0,4"/>'),
        ET.fromstring('<mask label="void" width="1" height="1" left="2" top="2" rle="0,1"/>'),
    ]
    result, stats = render(objects, (6, 6), {"road": 0, "water": 1, "void": 255}, "cvat")
    assert result[0, 0] == 0
    assert result[1, 1] == 1
    assert result[2, 2] == result[5, 5] == 255
    assert stats["overlap_pixels"] == 4
