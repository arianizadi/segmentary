"""Legacy custom rail dataset compatibility loader.

    <root>/images/<split>/*.png|jpg
    <root>/masks/<split>/*.png        single-channel index PNG, canonical ids, 255=ignore
    <root>/splits.json                provenance: seed, per-file group, how it was split

THE SPLITTING RULE. If frames come from video, the split must be by run/sequence,
never by frame. Adjacent frames are near-duplicates, so a random split puts a
frame's own neighbour in val and inflates mIoU by ~10 points. splits.json records
a `groups` map from file key to run id, and this loader ASSERTS that no group
appears in two splits. The generic public path is
``FolderSegmentationDataset``; this loader keeps the original stricter manifest
behavior for existing rail experiment configs.

If splits.json is absent the loader refuses to run rather than guessing, because
a silently-random split is exactly the failure it exists to prevent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Sample, SegDataset

IMAGE_EXTS = (".png", ".jpg", ".jpeg")
SPLITS_NAME = "splits.json"


class CustomRailDataset(SegDataset):
    """Legacy labelled-frame layout authored directly in canonical ids."""

    def index(self) -> list[Sample]:
        image_dir = self.root / "images" / self.split
        mask_dir = self.root / "masks" / self.split
        for d in (image_dir, mask_dir):
            if not d.is_dir():
                raise FileNotFoundError(
                    f"custom dataset: expected {d}. Layout is "
                    f"<root>/images/<split>/ and <root>/masks/<split>/."
                )

        groups, split_keys = self._load_manifest()
        images = self._files_by_key(image_dir, IMAGE_EXTS, "images")
        masks = self._files_by_key(mask_dir, (".png",), "masks")
        missing_masks = sorted(set(images) - set(masks))
        missing_images = sorted(set(masks) - set(images))
        if missing_masks or missing_images:
            raise FileNotFoundError(
                f"custom {self.split!r} is not one-to-one: {len(missing_masks)} images have "
                f"no mask (first {missing_masks[0] if missing_masks else '<none>'!r}); "
                f"{len(missing_images)} masks have no image "
                f"(first {missing_images[0] if missing_images else '<none>'!r})"
            )

        expected = set(split_keys[self.split])
        actual = set(images)
        if expected != actual:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(
                f"custom dataset {self.root / SPLITS_NAME}: split {self.split!r} does not "
                f"match disk; missing={missing[:5]}, extra={extra[:5]}"
            )

        return [
            Sample(image=images[key], label=masks[key], key=key, group=groups[key])
            for key in sorted(images)
        ]

    @staticmethod
    def _files_by_key(directory: Path, extensions: tuple[str, ...], kind: str) -> dict[str, Path]:
        found: dict[str, Path] = {}
        for path in sorted(
            candidate
            for candidate in directory.iterdir()
            if candidate.is_file() and candidate.suffix.lower() in extensions
        ):
            key = path.stem
            if key in found:
                raise ValueError(
                    f"custom dataset: multiple {kind} resolve to key {key!r}: "
                    f"{found[key]} and {path}"
                )
            found[key] = path
        return found

    def _load_manifest(self) -> tuple[dict[str, str], dict[str, list[str]]]:
        """Load and validate splits.json, enforcing group disjointness."""
        path = self.root / SPLITS_NAME
        if not path.is_file():
            raise FileNotFoundError(
                f"custom dataset: {path} is required. It records how the split was made "
                f"(seed, and the run/sequence each frame came from) and lets this loader "
                f"prove no run spans two splits. Generate it with "
                f"scripts/make_custom_split.py -- do not split by frame."
            )
        try:
            meta: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"custom dataset cannot read valid JSON from {path}: {exc}") from exc
        if not isinstance(meta, dict):
            raise ValueError(f"custom dataset {path} must contain a JSON object")

        raw_groups = meta.get("groups")
        if not isinstance(raw_groups, dict) or not all(
            isinstance(key, str) and key and isinstance(value, str) and value.strip()
            for key, value in raw_groups.items()
        ):
            raise ValueError(
                f"custom dataset {path}: groups must map non-empty frame keys to group names"
            )
        groups = {key: value.strip() for key, value in raw_groups.items()}

        members: dict[str, set[str]] = {}
        split_keys: dict[str, list[str]] = {}
        key_membership: dict[str, str] = {}
        for split_name, keys in meta.items():
            if split_name.startswith("_") or split_name == "groups":
                continue
            if not isinstance(keys, list) or not all(isinstance(key, str) and key for key in keys):
                raise ValueError(
                    f"custom dataset {path}: split {split_name!r} must be a list of "
                    "non-empty frame keys"
                )
            if len(keys) != len(set(keys)):
                raise ValueError(
                    f"custom dataset {path}: split {split_name!r} contains duplicate keys"
                )
            split_keys[split_name] = keys
            for key in keys:
                previous = key_membership.setdefault(key, split_name)
                if previous != split_name:
                    raise ValueError(
                        f"custom dataset {path}: frame {key!r} appears in splits "
                        f"{previous!r} and {split_name!r}"
                    )

        if self.split not in split_keys:
            raise ValueError(
                f"custom dataset {path}: requested split {self.split!r} is absent; "
                f"available splits are {sorted(split_keys)}"
            )

        manifest_keys = set(key_membership)
        supplied_groups = set(groups)
        if manifest_keys != supplied_groups:
            missing = sorted(manifest_keys - supplied_groups)
            extra = sorted(supplied_groups - manifest_keys)
            raise ValueError(
                f"custom dataset {path}: groups do not exactly match manifest keys; "
                f"missing={missing[:5]}, extra={extra[:5]}"
            )

        members = {
            split_name: {groups[key] for key in keys} for split_name, keys in split_keys.items()
        }

        names = sorted(members)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                shared = members[a] & members[b]
                if shared:
                    raise ValueError(
                        f"{path}: splits {a!r} and {b!r} share {len(shared)} group(s) "
                        f"{sorted(shared)[:5]}. Frames from one run are near-duplicates, so "
                        f"this leaks val into train. Re-split by group."
                    )
        return groups, split_keys

    def group_counts(self) -> dict[str, int]:
        """Frames per group, for reporting split composition."""
        counts: dict[str, int] = {}
        for s in self.samples:
            counts[s.group] = counts.get(s.group, 0) + 1
        return dict(sorted(counts.items()))
