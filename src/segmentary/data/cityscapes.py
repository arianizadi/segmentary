"""Cityscapes gtFine dataset.

Layout (as produced by unzipping leftImg8bit_trainvaltest.zip + gtFine_trainvaltest.zip):

    <root>/leftImg8bit/<split>/<city>/<city>_<seq>_<frame>_leftImg8bit.png
    <root>/gtFine/<split>/<city>/<city>_<seq>_<frame>_gtFine_labelIds.png

Verified against the real extraction: 2975 train / 500 val / 1525 test, 1024x2048,
labels are uint8 mode-L PNGs holding ids 0..33 (no *_labelTrainIds.png ships with
the archive, so the LUT runs on raw labelIds).

The official test split has no public labels -- its gtFine masks are all zeros --
so it is rejected rather than silently evaluated to a meaningless number.
"""

from __future__ import annotations

from pathlib import Path

from .base import Sample, SegDataset

IMAGE_SUFFIX = "_leftImg8bit.png"
LABEL_SUFFIX = "_gtFine_labelIds.png"
VALID_SPLITS = ("train", "val")


class CityscapesDataset(SegDataset):
    """Cityscapes finely-annotated split, mapped into a canonical label space."""

    def index(self) -> list[Sample]:
        if self.split not in VALID_SPLITS:
            raise ValueError(
                f"Cityscapes split must be one of {VALID_SPLITS}, got {self.split!r}. "
                f"The official `test` split ships blank labels (evaluation is server-side), "
                f"so training or scoring on it would produce a meaningless number."
            )

        image_dir = self.root / "leftImg8bit" / self.split
        label_dir = self.root / "gtFine" / self.split
        for d in (image_dir, label_dir):
            if not d.is_dir():
                raise FileNotFoundError(f"Cityscapes: expected directory {d}")

        images: dict[tuple[str, str], Path] = {}
        for image_path in sorted(image_dir.glob(f"*/*{IMAGE_SUFFIX}")):
            stem = image_path.name[: -len(IMAGE_SUFFIX)]
            city = image_path.parent.name
            images[(city, stem)] = image_path

        labels: dict[tuple[str, str], Path] = {}
        for label_path in sorted(label_dir.glob(f"*/*{LABEL_SUFFIX}")):
            stem = label_path.name[: -len(LABEL_SUFFIX)]
            city = label_path.parent.name
            labels[(city, stem)] = label_path

        missing_labels = sorted(set(images) - set(labels))
        missing_images = sorted(set(labels) - set(images))
        if missing_labels or missing_images:
            first_label = (
                label_dir / missing_labels[0][0] / f"{missing_labels[0][1]}{LABEL_SUFFIX}"
                if missing_labels
                else "<none>"
            )
            first_image = (
                image_dir / missing_images[0][0] / f"{missing_images[0][1]}{IMAGE_SUFFIX}"
                if missing_images
                else "<none>"
            )
            raise FileNotFoundError(
                f"Cityscapes {self.split} is not one-to-one: {len(missing_labels)} images have "
                f"no matching label (first {first_label}); {len(missing_images)} labels have "
                f"no matching image (first {first_image})"
            )

        samples: list[Sample] = []
        for (city, stem), image_path in sorted(images.items()):
            samples.append(
                Sample(
                    image=image_path,
                    label=labels[(city, stem)],
                    key=stem,
                    # City is the natural group: frames from one city share
                    # appearance. The official splits are already city-disjoint,
                    # so this is recorded for auditing rather than re-splitting.
                    group=city,
                )
            )

        return samples


def cityscapes_root(path: Path | str) -> Path:
    """Resolve a Cityscapes root, accepting either the parent or the extracted dir."""
    p = Path(path)
    if (p / "leftImg8bit").is_dir() and (p / "gtFine").is_dir():
        return p
    nested = p / "cityscapes"
    if (nested / "leftImg8bit").is_dir() and (nested / "gtFine").is_dir():
        return nested
    raise FileNotFoundError(
        f"no Cityscapes layout under {p}: expected leftImg8bit/ and gtFine/ subdirectories"
    )
