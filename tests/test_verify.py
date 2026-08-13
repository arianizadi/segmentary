"""Dataset-verifier safety and custom-loader contract tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from segmentary.verify import _overlay_filename, _scan_native_labels, main


def test_native_scan_uses_the_dataset_label_decoder(tmp_path: Path) -> None:
    class EncodedDataset:
        def __init__(self) -> None:
            self.samples = [SimpleNamespace(label=tmp_path / "encoded.mask")]
            self.calls: list[Path] = []

        def load_label(self, path: Path) -> np.ndarray:
            self.calls.append(path)
            return np.array([[0, 7], [7, 255]], dtype=np.uint16)

    dataset = EncodedDataset()
    ids, histogram = _scan_native_labels(dataset, [0])

    assert dataset.calls == [dataset.samples[0].label]
    assert ids == {0, 7, 255}
    assert histogram == {0: 1, 7: 2, 255: 1}


def test_overlay_filename_flattens_and_hashes_untrusted_keys() -> None:
    first = _overlay_filename("../../dataset", 2, "run/../frame:001")
    second = _overlay_filename("../../dataset", 2, "run/../frame:002")

    assert "/" not in first and "\\" not in first
    assert ".." not in first
    assert first.endswith(".png")
    assert first != second


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--n-scan", "0"], "--n-scan must be at least 1"),
        (["--n-overlays", "-1"], "--n-overlays cannot be negative"),
        (["--crop", "0", "64"], "--crop dimensions must be positive"),
    ],
)
def test_verify_rejects_invalid_work_sizes(
    arguments: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--dataset",
                "example",
                "--root",
                "/unused",
                "--space",
                "example",
                *arguments,
            ]
        )
    assert message in capsys.readouterr().err
