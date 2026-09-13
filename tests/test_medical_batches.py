"""CPU prefetch must preserve consumed batches, RNG and interrupted optimization."""

from __future__ import annotations

import copy
import dataclasses
import random
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
import torch
from torch import nn

from segmentary.medical.torch_batches import BatchStream
from segmentary.medical.torch_config import TorchConfig
from segmentary.medical.torch_data import sample_patch


def cases() -> dict:
    result = {}
    for index, shape in enumerate(((7, 9, 11), (5, 6, 4), (8, 7, 6))):
        values = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
        image = values / values.max() + index
        label = (values.astype(np.int32) % 3).astype(np.uint8)
        image.flags.writeable = label.flags.writeable = False
        result[str(index)] = {"image": image, "label": label}
    return result


def config(tmp_path, mode: str = "3d", prefetch: bool = True) -> TorchConfig:
    return TorchConfig(
        workspace=str(tmp_path),
        gpu="cpu",
        mode=mode,
        context_slices=5 if mode == "2.5d" else 1,
        patch_size=(6, 8, 8) if mode == "3d" else (8, 8),
        batch_size=3,
        prefetch_batches=prefetch,
    )


@pytest.mark.parametrize("mode", ["2d", "2.5d", "3d"])
@pytest.mark.parametrize("prefetch", [False, True])
def test_batches_match_original_sampling_and_consumed_rng(tmp_path, mode, prefetch) -> None:
    cfg = config(tmp_path, mode, prefetch)
    data = cases()
    expected_rng, actual_rng = np.random.default_rng(25), np.random.default_rng(25)
    with BatchStream(cfg, list(data), data.__getitem__, actual_rng, "cpu") as stream:
        for _ in range(7):
            expected = [
                sample_patch(data[str(expected_rng.choice(list(data)))], cfg, expected_rng)
                for _ in range(cfg.batch_size)
            ]
            images, labels = next(stream)
            assert images.dtype == torch.float32 and labels.dtype == torch.int64
            np.testing.assert_array_equal(images.numpy(), np.stack([pair[0] for pair in expected]))
            np.testing.assert_array_equal(labels.numpy(), np.stack([pair[1] for pair in expected]))
            np.testing.assert_equal(
                actual_rng.bit_generator.state, expected_rng.bit_generator.state
            )
    np.testing.assert_equal(actual_rng.bit_generator.state, expected_rng.bit_generator.state)


def test_unused_batch_does_not_advance_main_or_global_rng(tmp_path) -> None:
    cfg = config(tmp_path)
    rng = np.random.Generator(np.random.MT19937(7))
    before = copy.deepcopy(rng.bit_generator.state)
    torch_state, python_state, numpy_state = (
        torch.get_rng_state(),
        random.getstate(),
        np.random.get_state(),
    )
    data = cases()
    with BatchStream(cfg, list(data), data.__getitem__, rng, "cpu") as stream:
        assert stream._future is not None
        stream._future.result(timeout=10)
        np.testing.assert_equal(rng.bit_generator.state, before)
    np.testing.assert_equal(rng.bit_generator.state, before)
    assert torch.equal(torch_state, torch.get_rng_state())
    assert python_state == random.getstate()
    np.testing.assert_equal(numpy_state, np.random.get_state())


def test_exactly_one_batch_ahead_and_worker_closes(tmp_path) -> None:
    cfg = config(tmp_path)
    data = cases()
    calls = []
    complete = threading.Event()

    def load(case_id):
        calls.append(threading.get_ident())
        if len(calls) == cfg.batch_size:
            complete.set()
        return data[case_id]

    stream = BatchStream(cfg, list(data), load, np.random.default_rng(1), "cpu")
    with stream:
        assert complete.wait(timeout=10)
        assert stream._future is not None
        stream._future.result(timeout=10)
        assert len(calls) == cfg.batch_size
        assert len(set(calls)) == 1 and calls[0] != threading.get_ident()
    assert stream._executor is None and stream._future is None
    with pytest.raises(RuntimeError, match="active context"):
        next(stream)


def test_producer_error_closes_and_preserves_rng(tmp_path) -> None:
    cfg = config(tmp_path)
    rng = np.random.default_rng(2)
    before = copy.deepcopy(rng.bit_generator.state)

    def fail(_case_id):
        raise ValueError("broken cache")

    with BatchStream(cfg, ["case"], fail, rng, "cpu") as stream:
        with pytest.raises(ValueError, match="broken cache"):
            next(stream)
        assert stream._closed and stream._executor is None
    np.testing.assert_equal(rng.bit_generator.state, before)


def test_close_waits_for_inflight_worker_without_committing_rng(tmp_path) -> None:
    cfg = dataclasses.replace(config(tmp_path), batch_size=1)
    data = cases()
    entered, release = threading.Event(), threading.Event()
    rng = np.random.default_rng(12)
    before = copy.deepcopy(rng.bit_generator.state)

    def load(case_id):
        entered.set()
        assert release.wait(timeout=10)
        return data[case_id]

    stream = BatchStream(cfg, list(data), load, rng, "cpu")
    stream.__enter__()
    try:
        assert entered.wait(timeout=10)
        with ThreadPoolExecutor(max_workers=1) as executor:
            closing = executor.submit(stream.close)
            assert not closing.done()
            release.set()
            closing.result(timeout=10)
    finally:
        release.set()
        stream.close()
    np.testing.assert_equal(rng.bit_generator.state, before)


def test_prefetched_epoch_checkpoint_resumes_exact_dropout_optimizer_weights(tmp_path) -> None:
    cfg = config(tmp_path, "2.5d")
    data = cases()

    def initialize():
        torch.manual_seed(43)
        model = nn.Sequential(nn.Conv2d(5, 3, 1), nn.Dropout(p=0.3))
        return model, torch.optim.AdamW(model.parameters(), lr=0.001)

    def updates(model, optimizer, rng, count, configuration):
        with BatchStream(configuration, list(data), data.__getitem__, rng, "cpu") as stream:
            for _ in range(count):
                images, labels = next(stream)
                optimizer.zero_grad(set_to_none=True)
                nn.functional.cross_entropy(model(images), labels).backward()
                optimizer.step()

    reference, reference_optimizer = initialize()
    reference_rng = np.random.default_rng(51)
    updates(
        reference,
        reference_optimizer,
        reference_rng,
        6,
        dataclasses.replace(cfg, prefetch_batches=False),
    )
    interrupted, optimizer = initialize()
    rng = np.random.default_rng(51)
    updates(interrupted, optimizer, rng, 3, cfg)
    checkpoint = copy.deepcopy(
        {
            "model": interrupted.state_dict(),
            "optimizer": optimizer.state_dict(),
            "sampling": rng.bit_generator.state,
            "torch": torch.get_rng_state(),
        }
    )
    resumed, optimizer = initialize()
    resumed.load_state_dict(checkpoint["model"])
    optimizer.load_state_dict(checkpoint["optimizer"])
    rng.bit_generator.state = checkpoint["sampling"]
    torch.set_rng_state(checkpoint["torch"])
    updates(resumed, optimizer, rng, 3, cfg)
    for name, value in reference.state_dict().items():
        assert torch.equal(value, resumed.state_dict()[name]), name
    np.testing.assert_equal(reference_rng.bit_generator.state, rng.bit_generator.state)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available")
def test_cuda_prefetch_pins_compact_targets_and_returns_exact_int64(tmp_path) -> None:
    cfg = dataclasses.replace(config(tmp_path), gpu="0")
    data = cases()
    rng = np.random.default_rng(4)
    with BatchStream(cfg, list(data), data.__getitem__, rng, "cuda") as stream:
        assert stream._future is not None
        prepared = stream._future.result(timeout=10)
        assert prepared.images.is_pinned() and prepared.labels.is_pinned()
        assert prepared.labels.dtype == torch.uint8
        images, labels = next(stream)
        assert images.is_cuda and labels.is_cuda and labels.dtype == torch.int64
        assert torch.equal(labels.cpu(), prepared.labels.to(torch.int64))
        assert torch.equal(images.cpu(), prepared.images)
