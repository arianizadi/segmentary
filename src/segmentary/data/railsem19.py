"""RailSem19 dataset (Zendel et al., CVPRW 2019).

Layout (as produced by unzipping rs19_val.zip):

    <root>/jpgs/rs19_val/rsNNNNN.jpg     FullHD 1920x1080 RGB
    <root>/uint8/rs19_val/rsNNNNN.png    uint8 label map, ids 0..18, 255 = void
    <root>/jsons/rs19_val/rsNNNNN.json   polygon/polyline geometry (unused here)
    <root>/rs19-config.json              the dataset's own 19-class definition

Verified against the real extraction: 8500 matched triplets, every mask 1080x1920
mode-L, observed ids exactly {0..18} u {255}, void ~3.2% of pixels.

SPLITTING. The v1 release names files <Sequence-Id> with one frame per sequence,
so unlike a dashcam video dataset there are no near-duplicate adjacent frames and
a random split does not leak. That is a property of THIS dataset, not a general
licence to split randomly -- the custom dataset must still split by run.

Splits live in the repo (committed JSON), not in the dataset directory, so an
experiment's split is versioned alongside the code that produced it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Sample, SegDataset

IMAGE_DIR = Path("jpgs") / "rs19_val"
LABEL_DIR = Path("uint8") / "rs19_val"
CONFIG_NAME = "rs19-config.json"


class RailSem19Dataset(SegDataset):
    """RailSem19, mapped into a canonical label space.

    Args:
        split_file: JSON mapping split name -> list of frame ids. Required; there
            is no official split, so leaving it implicit would make results
            irreproducible.
    """

    def __init__(self, *args, split_file: Path | str | None = None, **kwargs) -> None:
        if split_file is None:
            raise ValueError(
                "RailSem19 has no official train/val split. Pass split_file=<committed json> "
                "so the split is reproducible; scripts/make_railsem19_split.py generates one."
            )
        self.split_file = Path(split_file)
        super().__init__(*args, **kwargs)

    def index(self) -> list[Sample]:
        if not self.split_file.is_file():
            raise FileNotFoundError(f"RailSem19 split file not found: {self.split_file}")
        splits = self._load_splits()
        if self.split not in splits:
            raise KeyError(
                f"{self.split_file} defines splits {sorted(k for k in splits if not k.startswith('_'))}, "
                f"not {self.split!r}"
            )

        image_dir = self.root / IMAGE_DIR
        label_dir = self.root / LABEL_DIR
        for d in (image_dir, label_dir):
            if not d.is_dir():
                raise FileNotFoundError(f"RailSem19: expected directory {d}")

        samples: list[Sample] = []
        missing: list[str] = []
        for key in splits[self.split]:
            image_path = image_dir / f"{key}.jpg"
            label_path = label_dir / f"{key}.png"
            if not image_path.is_file() or not label_path.is_file():
                missing.append(key)
                continue
            # One frame per sequence in v1, so the frame id IS the group.
            samples.append(Sample(image=image_path, label=label_path, key=key, group=key))

        if missing:
            raise FileNotFoundError(
                f"RailSem19 {self.split}: {len(missing)} frames listed in {self.split_file.name} "
                f"are missing from {self.root}; first is {missing[0]}"
            )
        return samples

    def _load_splits(self) -> dict[str, list[str]]:
        try:
            payload: Any = json.loads(self.split_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"RailSem19 cannot read valid JSON from {self.split_file}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(f"RailSem19 {self.split_file} must contain a JSON object")

        splits: dict[str, list[str]] = {}
        for name, values in payload.items():
            if name.startswith("_"):
                continue
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values
            ):
                raise ValueError(
                    f"RailSem19 {self.split_file}: split {name!r} must be a list of "
                    "non-empty frame ids"
                )
            if len(values) != len(set(values)):
                raise ValueError(
                    f"RailSem19 {self.split_file}: split {name!r} contains duplicate frame ids"
                )
            splits[name] = values

        names = sorted(splits)
        for index, left in enumerate(names):
            for right in names[index + 1 :]:
                overlap = set(splits[left]) & set(splits[right])
                if overlap:
                    raise ValueError(
                        f"RailSem19 {self.split_file}: splits {left!r} and {right!r} share "
                        f"frame ids {sorted(overlap)[:5]}"
                    )
        return splits


def load_native_classes(root: Path | str) -> dict[int, str]:
    """Read the dataset's own class list from rs19-config.json.

    Used by verify_dataset.py to assert the shipped taxonomy YAML still agrees
    with the dataset on disk, rather than trusting a transcription.
    """
    cfg_path = Path(root) / CONFIG_NAME
    if not cfg_path.is_file():
        raise FileNotFoundError(f"RailSem19: {CONFIG_NAME} not found at {cfg_path}")
    cfg = json.loads(cfg_path.read_text())
    return {i: label["name"] for i, label in enumerate(cfg["labels"])}
