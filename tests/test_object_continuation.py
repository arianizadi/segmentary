"""Resume must reproduce optimizer state, sampling and stochastic query matching."""

import json
import math
import random
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import torch

from segmentary.objects import runner
from segmentary.objects.continuation import BatchOrder, restore_rng, rng_state
from test_object_workflow import fixture_config, tiny_model


def assert_tree_equal(left, right):
    if isinstance(left, torch.Tensor):
        assert torch.equal(left, right)
    elif isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left:
            assert_tree_equal(left[key], right[key])
    elif isinstance(left, (list, tuple)):
        assert len(left) == len(right)
        for a, b in zip(left, right, strict=True):
            assert_tree_equal(a, b)
    else:
        assert left == right


def test_rng_weights_only_roundtrip(tmp_path):
    state = rng_state()
    expected = (random.random(), np.random.rand(), torch.rand(4))
    path = tmp_path / "rng.pt"
    torch.save(state, path)
    restore_rng(torch.load(path, weights_only=True))
    assert_tree_equal(expected, (random.random(), np.random.rand(), torch.rand(4)))


def test_epoch_tail_and_order_restore():
    order = BatchOrder(11, 42)
    first = order.take(2, 3)
    assert list(map(len, first)) == [2, 2, 2]
    resumed = BatchOrder(11, 42)
    resumed.load_state_dict(order.state_dict())
    tail = order.take(2, 3)
    assert list(map(len, tail)) == [2, 2, 1]
    assert tail == resumed.take(2, 3)
    assert len({i for group in first + tail for i in group}) == 11
    assert order.take(2, 3) == resumed.take(2, 3)


@pytest.mark.parametrize(
    "precision,device",
    [
        ("float32", "cpu"),
        ("bfloat16", "cpu"),
        pytest.param("float16", "cuda:0", marks=pytest.mark.gpu),
        pytest.param("bfloat16", "cuda:0", marks=pytest.mark.gpu),
    ],
)
def test_interrupted_resume_is_bitwise_equal(
    tmp_path, monkeypatch, precision, device, record_property
):
    if device.startswith("cuda") and not torch.cuda.is_available():
        pytest.skip("CUDA required")
    if device.startswith("cuda") and precision == "bfloat16" and not torch.cuda.is_bf16_supported():
        pytest.skip("CUDA bfloat16 unsupported")
    config = fixture_config(tmp_path, "instance")
    # Five samples exercise a partial accumulation group and epoch rollover.
    annotation = Path(config.train.annotations)
    document = json.loads(annotation.read_text())
    document["images"] = [
        {**document["images"][0], "id": i, "file_name": f"{i}.png"} for i in range(1, 6)
    ]
    for i in range(1, 6):
        shutil.copyfile(
            Path(config.train.images) / "one.png", Path(config.train.images) / f"{i}.png"
        )
    document["annotations"] = [
        {**row, "id": i * 10 + row["id"], "image_id": i}
        for i in range(1, 6)
        for row in document["annotations"]
    ]
    annotation.write_text(json.dumps(document))
    config = replace(
        config,
        max_steps=4,
        val_every=2,
        gradient_accumulation=2,
        precision=precision,
        device=device,
    )
    monkeypatch.setattr(
        runner, "make_model", lambda cfg, classes: tiny_model(cfg, classes).to(cfg.device)
    )
    complete = runner.train(config)
    expected = torch.load(Path(config.output) / "last.pt", weights_only=True)
    split = replace(config, output=str(tmp_path / "resumed"))
    original_save = runner._save_checkpoint

    def interrupt(path, state):
        original_save(path, state)
        if path.name == "last.pt" and state["step"] == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_save_checkpoint", interrupt)
    partial = runner.train(split)
    assert partial["status"] == "interrupted" and partial["steps"] == 2
    monkeypatch.setattr(runner, "_save_checkpoint", original_save)
    actual_result = runner.train(split, resume=Path(split.output) / "last.pt")
    actual = torch.load(Path(split.output) / "last.pt", weights_only=True)
    for key in ("model", "optimizer", "rng", "batch_order", "scaler", "step", "best_step", "best"):
        assert_tree_equal(expected[key], actual[key])
    assert [row["loss"] for row in complete["history"]] == [
        row["loss"] for row in actual_result["history"]
    ]
    for key in ("micro_batches", "samples", "epoch"):
        assert [row[key] for row in actual_result["history"]] == [
            row[key] for row in complete["history"]
        ]
    if device == "cpu":
        assert [row["micro_batches"] for row in actual_result["history"]] == [2, 2, 1, 2]

    # FP16 overflow consumes sample groups without a successful optimizer update.
    # The persisted epoch/cursor gives an independent count of attempted groups.
    def skipped_updates(checkpoint):
        order = checkpoint["batch_order"]
        samples_per_update = config.batch_size * config.gradient_accumulation
        attempted = order["epoch"] * math.ceil(order["size"] / samples_per_update)
        attempted += math.ceil(order["cursor"] / samples_per_update)
        return attempted - checkpoint["step"]

    skipped = skipped_updates(actual)
    assert skipped == skipped_updates(expected) and skipped >= 0
    record_property("overflow_skipped_updates", skipped)
    if precision == "float16":
        assert actual["scaler"]["scale"] > 0
        assert "_growth_tracker" in actual["scaler"]
        if skipped:
            # This four-step fixture cannot reach GradScaler's 2000-update growth interval.
            assert actual["scaler"]["scale"] < 65536
    else:
        assert skipped == 0
    with pytest.raises(ValueError, match="configuration"):
        runner.train(replace(split, lr=0.02), resume=Path(split.output) / "last.pt")
    # Image contents are covered even when annotation JSON is unchanged.
    from PIL import Image

    Image.fromarray(np.zeros((32, 32, 3), dtype=np.uint8)).save(Path(config.train.images) / "1.png")
    with pytest.raises(ValueError, match="dataset content"):
        runner.train(split, resume=Path(split.output) / "last.pt")


def test_sigterm_requests_boundary_stop_and_restores_handler():
    import signal

    from segmentary.objects.continuation import graceful_stop

    previous = signal.getsignal(signal.SIGTERM)
    with graceful_stop() as state:
        signal.raise_signal(signal.SIGTERM)
        assert state["stop"]
    assert signal.getsignal(signal.SIGTERM) == previous


def test_mid_update_interrupt_keeps_last_committed_boundary(tmp_path, monkeypatch):
    config = replace(fixture_config(tmp_path, "instance"), max_steps=3)
    monkeypatch.setattr(
        runner, "make_model", lambda cfg, classes: tiny_model(cfg, classes).to(cfg.device)
    )
    original = runner.query_output
    training_calls = 0

    def interrupted(model, images):
        nonlocal training_calls
        if model.training:
            training_calls += 1
            if training_calls == 2:
                raise KeyboardInterrupt
        return original(model, images)

    monkeypatch.setattr(runner, "query_output", interrupted)
    result = runner.train(config)
    state = torch.load(Path(config.output) / "last.pt", weights_only=True)
    assert result["steps"] == state["step"] == 1
    assert len(state["history"]) == 1
    assert result["status"] == "interrupted"
    monkeypatch.setattr(runner, "query_output", original)
    assert runner.train(config, resume=Path(config.output) / "last.pt")["steps"] == 3


def test_atomic_checkpoint_preserves_previous_on_write_failure(tmp_path, monkeypatch):
    path = tmp_path / "last.pt"
    runner._save_checkpoint(path, {"step": 5})

    def fail(state, target):
        target.write(b"incomplete serialization")
        raise OSError("disk failure")

    monkeypatch.setattr(torch, "save", fail)
    with pytest.raises(OSError, match="disk failure"):
        runner._save_checkpoint(path, {"step": 6})
    assert torch.load(path, weights_only=True)["step"] == 5
