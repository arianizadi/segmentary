"""Ordered bounded CPU overlap preserves inference and releases worker resources."""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
import torch
from torch import nn

from segmentary.medical import torch_data, torch_geometry
from segmentary.medical.torch_config import TorchConfig


class _Classifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.calls = []

    def forward(self, x):
        self.calls.append((tuple(x.shape), threading.get_ident(), self.training))
        middle = x[:, x.shape[1] // 2 : x.shape[1] // 2 + 1]
        return torch.cat([-middle, 0.25 - (middle - 0.5).abs(), middle - 0.5], 1)


def _cases(tmp_path):
    cases = []
    affine = np.array([[0, -1.5, 0, 15], [0.75, 0, 0, -10], [0, 0, -3, 50], [0, 0, 0, 1]])
    for index in range(3):
        values = np.random.default_rng(index).uniform(0, 100, (9, 8, 7)).astype(np.float32)
        image = nib.Nifti1Image(values, affine)
        image.header.set_xyzt_units("mm")
        image.set_qform(affine, code=1)
        image.set_sform(affine, code=1)
        path = tmp_path / f"case-{index}.nii.gz"
        nib.save(image, path)
        cases.append({"case_id": str(index), "image": str(path), "label": "/never/open/labels"})
    return cases


@pytest.mark.parametrize("mode,context", [("3d", 1), ("2d", 1), ("2.5d", 5)])
@pytest.mark.parametrize("workers", [1, 2, 4])
def test_pipeline_matches_original_native_argmax_and_every_forward_batch(
    tmp_path, monkeypatch, mode, context, workers
):
    cases = _cases(tmp_path)
    config = TorchConfig(
        str(tmp_path / "run"),
        gpu="cpu",
        mode=mode,
        context_slices=context,
        patch_size=(4, 5, 6) if mode == "3d" else (5, 6),
        workers=workers,
        spacing_mm=(1.5, 0.75, 3),
        hu_window=(0, 100),
        inference_batch_size=3,
    )
    model = _Classifier().train()
    with monkeypatch.context() as patch:
        patch.setattr(
            torch_geometry,
            "native_argmax",
            lambda channels: np.stack(channels).argmax(0).astype(np.uint8),
        )
        expected = [
            torch_data.predict_case(model, case, config, torch.device("cpu")) for case in cases
        ]
    expected_calls = list(model.calls)
    model.calls.clear()
    with contextlib.closing(
        torch_data.iter_predictions(model, cases, config, torch.device("cpu"))
    ) as stream:
        actual = list(stream)
    assert model.training
    assert model.calls == expected_calls
    assert all(
        thread == threading.get_ident() and not training for _, thread, training in model.calls
    )
    assert [item.case for item in actual] == cases
    for item, reference in zip(actual, expected, strict=True):
        assert item.error is None
        np.testing.assert_array_equal(item.prediction, reference)
        assert set(item.timings) == {
            "preprocess_seconds",
            "inference_seconds",
            "reconstruction_seconds",
            "export_seconds",
        }
        assert item.wall_seconds >= 0


def test_pipeline_overlaps_one_prepared_and_one_reconstruction_then_closes_early(
    tmp_path, monkeypatch
):
    next_prepared = threading.Event()
    reconstruction_started = threading.Event()
    second_inference = threading.Event()
    prepared_ids = []
    inference_ids = []
    reconstruction_ids = []
    caller_thread = threading.get_ident()

    def prepare(case, *_):
        index = int(case["case_id"])
        prepared_ids.append(index)
        if index == 1:
            next_prepared.set()
        return {"image": np.full((1, 1, 1), index, np.float32)}

    def infer(_model, image, *_):
        assert threading.get_ident() == caller_thread
        index = int(image.item())
        inference_ids.append(index)
        if index == 0:
            assert next_prepared.wait(5)
        elif index == 1:
            assert reconstruction_started.wait(5)
            second_inference.set()
        return image

    def finish(probabilities, _geometry, case, *_):
        index = int(case["case_id"])
        reconstruction_ids.append(index)
        if index == 0:
            reconstruction_started.set()
            assert second_inference.wait(5)
        return probabilities.astype(np.uint8)

    monkeypatch.setattr(torch_data, "_prepare_prediction", prepare)
    monkeypatch.setattr(torch_data, "_inference_probabilities", infer)
    monkeypatch.setattr(torch_data, "_finish_prediction", finish)
    config = TorchConfig(str(tmp_path), gpu="cpu", workers=4)
    cases = [{"case_id": str(index)} for index in range(5)]
    with contextlib.closing(
        torch_data.iter_predictions(nn.Identity(), cases, config, torch.device("cpu"))
    ) as stream:
        first = next(stream)
        assert first.error is None
        assert first.case == cases[0]
    # After yielding case0, case1 may finish and case2 may be prepared. No later
    # images or model calls may run, and all executor threads must be joined.
    assert prepared_ids in ([0, 1], [0, 1, 2])
    assert inference_ids == [0, 1]
    assert reconstruction_ids in ([0], [0, 1])
    assert not any(
        thread.name.startswith(("ct-prepare", "ct-reconstruct")) for thread in threading.enumerate()
    )


@pytest.mark.parametrize("failure_stage", ["prepare", "infer", "finish"])
def test_pipeline_keeps_failed_case_order_and_continues(tmp_path, monkeypatch, failure_stage):
    def prepare(case, *_):
        if case["case_id"] == "1" and failure_stage == "prepare":
            raise ValueError("bad preparation")
        return {"image": np.full((1, 1, 1), int(case["case_id"]), np.float32)}

    def infer(_model, image, *_):
        if image.item() == 1 and failure_stage == "infer":
            raise ValueError("bad inference")
        return image

    def finish(probabilities, _geometry, case, *_):
        if case["case_id"] == "1" and failure_stage == "finish":
            raise OSError("bad reconstruction")
        return probabilities.astype(np.uint8)

    monkeypatch.setattr(torch_data, "_prepare_prediction", prepare)
    monkeypatch.setattr(torch_data, "_inference_probabilities", infer)
    monkeypatch.setattr(torch_data, "_finish_prediction", finish)
    cases = [{"case_id": str(index)} for index in range(3)]
    config = TorchConfig(str(tmp_path), gpu="cpu", workers=4)
    with contextlib.closing(
        torch_data.iter_predictions(nn.Identity(), cases, config, torch.device("cpu"))
    ) as stream:
        results = list(stream)
    assert [item.case for item in results] == cases
    assert results[0].error is results[2].error is None
    assert results[1].prediction is None
    assert isinstance(results[1].error, (ValueError, OSError))


def test_model_mode_restored_if_inference_raises(tmp_path):
    class Broken(nn.Module):
        def forward(self, _):
            raise ValueError("model failure")

    model = Broken().train()
    config = TorchConfig(str(tmp_path), gpu="cpu", patch_size=(2, 2, 2))
    with pytest.raises(ValueError, match="model failure"):
        torch_data._inference_probabilities(
            model, np.zeros((2, 2, 2), np.float32), config, torch.device("cpu")
        )
    assert model.training


def test_verified_cache_export_is_used_without_reauditing_raw_image(tmp_path, monkeypatch):
    calls = []

    class Cache:
        def load(self, case):
            calls.append(("load", case))
            return {
                "image": np.zeros((2, 2, 2), np.float32),
                "affine": np.eye(4),
                "native_shape": (2, 2, 2),
                "native_affine": np.eye(4),
            }

        def check(self, case):
            calls.append(("check", case))

        def export_prediction(self, case, prediction, path):
            assert prediction.shape == (2, 2, 2)
            calls.append(("export", case, path))

    def forbidden(*_, **__):
        raise AssertionError("Cache hit opened raw CT or label through preprocessing")

    monkeypatch.setattr(torch_data, "preprocess_case", forbidden)
    case = {"case_id": "cached", "image": "/not/opened", "label": "/not/opened"}
    config = TorchConfig(str(tmp_path), gpu="cpu", patch_size=(2, 2, 2))
    output = Path(tmp_path) / "result.nii.gz"
    torch_data.predict_case(
        _Classifier(), case, config, torch.device("cpu"), output=output, cache=Cache()
    )
    assert [call[0] for call in calls] == ["load", "check", "export"]
