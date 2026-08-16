"""EMA tests. The failure modes here are all silent ones.

An EMA that never moves, one that averages BatchNorm counters, or one that
forgets to restore the live weights after validation all produce a training run
that looks completely normal and evaluates wrong. Each test below pins one of
those.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
import torch
from torch import nn

from segmentary.config import EvalConfig, OptimConfig, TrainConfig
from segmentary.engine.ema import (
    EMA_CHECKPOINT_KEY,
    EmaConfig,
    ModelEma,
    effective_decay,
    ema_evaluation_safe,
)
from segmentary.engine.module import SegLitModule


def _toy(seed: int = 0) -> nn.Module:
    torch.manual_seed(seed)
    return nn.Sequential(nn.Conv2d(3, 4, 3, padding=1), nn.BatchNorm2d(4), nn.ReLU())


def _fill(model: nn.Module, value: float) -> None:
    with torch.no_grad():
        for p in model.parameters():
            p.fill_(value)


def test_ema_evaluation_safety_detects_running_stat_batchnorm() -> None:
    assert not ema_evaluation_safe(_toy())
    assert ema_evaluation_safe(nn.Sequential(nn.Conv2d(3, 4, 3), nn.GroupNorm(2, 4)))
    assert ema_evaluation_safe(nn.BatchNorm2d(4, track_running_stats=False))


def test_lightning_validation_uses_raw_weights_for_running_batchnorm() -> None:
    with pytest.warns(UserWarning, match="validation uses raw weights"):
        module = _lit()
    assert module.ema is not None
    assert module.validation_weights == "raw"


def _lit(seed: int = 0, *, ema_decay: float | None = 0.9) -> SegLitModule:
    """Small real LightningModule for exercising checkpoint hooks."""
    model = _toy(seed)
    space = SimpleNamespace(
        num_classes=4,
        ignore_index=255,
        names=("a", "b", "c", "d"),
        thin_classes=(),
    )
    return SegLitModule(
        model=model,
        loss_fn=nn.Identity(),
        space=space,
        optim_cfg=OptimConfig(),
        train_cfg=TrainConfig(ema_decay=ema_decay),
        eval_cfg=EvalConfig(sliding_window=False),
    )


# --------------------------------------------------------------------------
# decay ramp
# --------------------------------------------------------------------------


def test_decay_ramp_is_low_at_step_zero_and_reaches_config_decay():
    cfg = EmaConfig(decay=0.9998, warmup_iters=2000)
    assert effective_decay(cfg, 0) == pytest.approx(1.0 / 10.0)
    assert effective_decay(cfg, 100) == pytest.approx(101.0 / 110.0)
    assert effective_decay(cfg, 100_000) == pytest.approx(0.9998)


def test_decay_ramp_is_monotone_and_capped_by_config():
    cfg = EmaConfig(decay=0.9998, warmup_iters=2000)
    values = [effective_decay(cfg, s) for s in range(0, 3000, 7)]
    assert values == sorted(values)
    assert max(values) == pytest.approx(cfg.decay)


def test_zero_warmup_disables_the_ramp():
    cfg = EmaConfig(decay=0.99, warmup_iters=0)
    assert effective_decay(cfg, 0) == pytest.approx(0.99)


def test_negative_step_is_rejected():
    with pytest.raises(ValueError, match="step must be >= 0"):
        effective_decay(EmaConfig(), -1)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"decay": 1.0}, "decay must be in"),
        ({"decay": -0.1}, "decay must be in"),
        ({"warmup_iters": -1}, "warmup_iters must be >= 0"),
        ({"update_every": 0}, "update_every must be >= 1"),
    ],
)
def test_config_rejects_nonsense(kwargs, match):
    with pytest.raises(ValueError, match=match):
        EmaConfig(**kwargs)


# --------------------------------------------------------------------------
# the average actually moves
# --------------------------------------------------------------------------


def test_update_moves_ema_toward_the_model_by_exactly_one_minus_decay():
    model = _toy()
    _fill(model, 0.0)
    ema = ModelEma(model, EmaConfig(decay=0.9998, warmup_iters=2000))
    _fill(model, 1.0)

    ema.update(model, step=0)  # ramped decay = 0.1

    assert ema.params["0.weight"].mean().item() == pytest.approx(0.9, abs=1e-6)
    assert torch.allclose(ema.params["0.weight"], torch.full_like(ema.params["0.weight"], 0.9))
    assert ema.num_updates == 1


def test_repeated_updates_converge_to_the_model():
    model = _toy()
    _fill(model, 0.0)
    ema = ModelEma(model, EmaConfig(decay=0.99, warmup_iters=50))
    _fill(model, 1.0)
    for step in range(500):
        ema.update(model, step)
    assert ema.params["0.bias"].max().item() == pytest.approx(1.0, abs=1e-2)


def test_ema_lags_the_model_it_does_not_track_it():
    """A shadow equal to the live weights would mean update() is a no-op copy."""
    model = _toy()
    _fill(model, 0.0)
    ema = ModelEma(model, EmaConfig(decay=0.9998, warmup_iters=2000))
    _fill(model, 1.0)
    ema.update(model, step=5000)  # full decay
    assert ema.params["0.weight"].max().item() == pytest.approx(2e-4, abs=1e-9)


def test_update_every_skips_intermediate_steps():
    model = _toy()
    _fill(model, 0.0)
    ema = ModelEma(model, EmaConfig(decay=0.5, warmup_iters=0, update_every=4))
    _fill(model, 1.0)
    for step in range(4):
        ema.update(model, step)
    assert ema.num_updates == 1
    assert ema.params["0.bias"].max().item() == pytest.approx(0.5)


def test_cached_plan_is_rebuilt_for_a_different_model_instance():
    """The per-step tensor cache must not survive being handed another module."""
    first = _toy()
    _fill(first, 0.0)
    ema = ModelEma(first, EmaConfig(decay=0.5, warmup_iters=0))
    ema.update(first, step=0)

    second = _toy(seed=4)
    _fill(second, 1.0)
    del first
    ema.update(second, step=0)
    assert ema.params["0.bias"].max().item() == pytest.approx(0.5)


def test_update_follows_parameters_replaced_in_place():
    """`.to()`, `load_state_dict(assign=True)` and adapter injection swap Parameter
    objects without changing the module; a cached pairing would keep averaging the
    detached originals and the shadow would silently stop moving."""
    model = _toy()
    _fill(model, 0.0)
    ema = ModelEma(model, EmaConfig(decay=0.5, warmup_iters=0))
    ema.update(model, step=0)

    ones = {k: torch.ones_like(v) for k, v in model.state_dict().items()}
    model.load_state_dict(ones, assign=True)
    ema.update(model, step=1)
    assert ema.params["0.bias"].max().item() == pytest.approx(0.5)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a GPU")
def test_shadow_follows_the_model_to_another_device():
    """SegLitModule builds the EMA before Lightning moves the model to the GPU."""
    model = _toy()
    _fill(model, 0.0)
    ema = ModelEma(model, EmaConfig(decay=0.5, warmup_iters=0))
    ema.update(model, step=0)
    model.cuda()
    _fill(model, 1.0)
    ema.update(model, step=1)
    assert ema.params["0.bias"].device.type == "cuda"
    assert ema.params["0.bias"].max().item() == pytest.approx(0.5)


def test_shadow_stays_float32_under_bf16_weights():
    model = _toy().to(torch.bfloat16)
    _fill(model, 0.0)
    ema = ModelEma(model, EmaConfig(decay=0.9998, warmup_iters=0))
    assert ema.params["0.weight"].dtype == torch.float32
    _fill(model, 1.0)
    ema.update(model, step=10_000)
    # 2e-4 is below bf16's resolution near 0 relative to 1.0; a bf16 accumulator
    # would have rounded this update away entirely.
    assert ema.params["0.weight"].dtype == torch.float32
    assert ema.params["0.weight"].max().item() == pytest.approx(2e-4, abs=1e-9)


# --------------------------------------------------------------------------
# buffers
# --------------------------------------------------------------------------


def test_buffers_are_copied_not_averaged():
    model = _toy()
    ema = ModelEma(model, EmaConfig(decay=0.9998, warmup_iters=0))
    bn = model[1]
    with torch.no_grad():
        bn.running_mean.fill_(3.0)
        bn.running_var.fill_(7.0)
        bn.num_batches_tracked.fill_(12)

    ema.update(model, step=0)

    assert torch.equal(ema.buffers["1.running_mean"], torch.full((4,), 3.0))
    assert torch.equal(ema.buffers["1.running_var"], torch.full((4,), 7.0))
    assert ema.buffers["1.num_batches_tracked"].dtype == torch.int64
    assert ema.buffers["1.num_batches_tracked"].item() == 12


def test_buffers_track_real_batchnorm_statistics():
    model = _toy()
    ema = ModelEma(model, EmaConfig(decay=0.9998, warmup_iters=0))
    model.train()
    for _ in range(3):
        model(torch.randn(2, 3, 8, 8))
        ema.update(model, step=0)
    assert torch.equal(ema.buffers["1.running_mean"], model[1].running_mean)
    assert ema.buffers["1.num_batches_tracked"].item() == 3


# --------------------------------------------------------------------------
# copy_to / swapped
# --------------------------------------------------------------------------


def test_copy_to_installs_shadow_weights_and_buffers():
    model = _toy()
    _fill(model, 0.0)
    ema = ModelEma(model, EmaConfig(decay=0.5, warmup_iters=0))
    with torch.no_grad():
        model[1].running_mean.fill_(2.0)
    _fill(model, 1.0)
    ema.update(model, step=100)

    target = _toy(seed=1)
    ema.copy_to(target)
    for name, p in target.named_parameters():
        assert torch.equal(p, ema.params[name])
    assert torch.equal(target[1].running_mean, ema.buffers["1.running_mean"])


def test_copy_to_validates_before_it_writes_anything():
    """A mismatch found halfway through the loop would leave the model half-EMA."""
    ema = ModelEma(_toy(), EmaConfig())
    wider = nn.Sequential(
        nn.Conv2d(3, 4, 3, padding=1), nn.BatchNorm2d(4), nn.ReLU(), nn.Conv2d(4, 4, 1)
    )
    _fill(wider, 7.0)
    before = {name: p.detach().clone() for name, p in wider.named_parameters()}

    with pytest.raises(ValueError, match="half-EMA"):
        ema.copy_to(wider)

    for name, p in wider.named_parameters():
        assert torch.equal(p, before[name]), f"{name} was overwritten before validation failed"


def test_copy_to_refuses_to_broadcast_a_shape_mismatch():
    """Tensor.copy_ broadcasts, so an unchecked mismatch fills a whole row."""

    class Head(nn.Module):
        def __init__(self, n: int) -> None:
            super().__init__()
            self.w = nn.Parameter(torch.full((n,), 5.0))

    ema = ModelEma(Head(1), EmaConfig())
    with pytest.raises(ValueError, match="shape"):
        ema.copy_to(Head(4))


def test_swapped_restores_when_installing_the_shadow_fails():
    model = _toy()
    ema = ModelEma(model, EmaConfig(decay=0.5, warmup_iters=0))
    _fill(model, 1.0)
    live = {name: p.detach().clone() for name, p in model.named_parameters()}
    ema.params.pop("0.bias")  # shadow no longer describes the model

    with pytest.raises(ValueError, match="half-EMA"):
        with ema.swapped(model):
            pass

    for name, p in model.named_parameters():
        assert torch.equal(p, live[name])


def test_swapped_installs_ema_then_restores_bitwise():
    model = _toy()
    ema = ModelEma(model, EmaConfig(decay=0.5, warmup_iters=0))
    _fill(model, 1.0)
    with torch.no_grad():
        model[1].running_mean.fill_(5.0)
    ema.update(model, step=0)  # shadow now 0.5 * init + 0.5 * ones
    live = {name: p.detach().clone() for name, p in model.named_parameters()}
    live_buf = {name: b.detach().clone() for name, b in model.named_buffers()}

    with ema.swapped(model) as swapped_model:
        assert swapped_model is model
        for name, p in model.named_parameters():
            assert torch.equal(p, ema.params[name])

    for name, p in model.named_parameters():
        assert torch.equal(p, live[name])
    for name, b in model.named_buffers():
        assert torch.equal(b, live_buf[name])


def test_swapped_restores_when_the_body_raises():
    model = _toy()
    ema = ModelEma(model, EmaConfig(decay=0.5, warmup_iters=0))
    _fill(model, 1.0)
    ema.update(model, step=0)
    live = {name: p.detach().clone() for name, p in model.named_parameters()}

    with pytest.raises(RuntimeError, match="CUDA out of memory"):
        with ema.swapped(model):
            raise RuntimeError("CUDA out of memory")

    for name, p in model.named_parameters():
        assert torch.equal(p, live[name])


def test_swapped_leaves_gradients_usable_afterwards():
    """The swap must not detach parameters from the graph the optimizer holds."""
    model = _toy()
    ema = ModelEma(model, EmaConfig(decay=0.5, warmup_iters=0))
    opt = torch.optim.SGD(model.parameters(), lr=0.1)
    tracked = next(iter(opt.param_groups[0]["params"]))
    with ema.swapped(model):
        pass
    assert tracked is next(model.parameters())
    model(torch.randn(1, 3, 8, 8)).sum().backward()
    opt.step()  # would raise if the swap replaced Parameter objects


# --------------------------------------------------------------------------
# state_dict
# --------------------------------------------------------------------------


def test_state_dict_round_trip(tmp_path):
    model = _toy()
    _fill(model, 0.0)
    ema = ModelEma(model, EmaConfig(decay=0.9, warmup_iters=0))
    _fill(model, 1.0)
    with torch.no_grad():
        model[1].running_mean.fill_(4.0)
    for step in range(5):
        ema.update(model, step)

    path = tmp_path / "ema.pt"
    torch.save(ema.state_dict(), path)

    fresh = ModelEma(_toy(seed=3), EmaConfig(decay=0.9, warmup_iters=0))
    assert not torch.equal(fresh.params["0.weight"], ema.params["0.weight"])
    fresh.load_state_dict(torch.load(path, weights_only=True))

    assert fresh.num_updates == ema.num_updates
    for name, tensor in ema.params.items():
        assert torch.equal(fresh.params[name], tensor)
    for name, tensor in ema.buffers.items():
        assert torch.equal(fresh.buffers[name], tensor)


def test_lightning_checkpoint_hooks_round_trip_shadow_buffers_and_counter():
    source = _lit(seed=1)
    _fill(source.model, 7.0)
    assert source.ema is not None
    for tensor in source.ema.params.values():
        tensor.fill_(2.0)
    source.ema.buffers["1.running_mean"].fill_(3.0)
    source.ema.buffers["1.num_batches_tracked"].fill_(11)
    source.ema.num_updates = 19

    checkpoint: dict[str, object] = {}
    source.on_save_checkpoint(checkpoint)
    assert EMA_CHECKPOINT_KEY in checkpoint

    target = _lit(seed=9)
    raw_before = {name: p.detach().clone() for name, p in target.model.named_parameters()}
    target.on_load_checkpoint(checkpoint)
    assert target.ema is not None
    assert target.ema.num_updates == 19
    assert target.ema.buffers["1.num_batches_tracked"].item() == 11
    assert torch.equal(target.ema.buffers["1.running_mean"], torch.full((4,), 3.0))
    assert all(tensor.eq(2.0).all() for tensor in target.ema.params.values())
    # Lightning restores the raw model through its ordinary state_dict later;
    # this hook must touch only the separate EMA shadow.
    for name, parameter in target.model.named_parameters():
        assert torch.equal(parameter, raw_before[name])


def test_ema_enabled_resume_rejects_a_legacy_raw_only_checkpoint():
    with pytest.raises(RuntimeError, match=r"EMA enabled.*no saved EMA state"):
        _lit().on_load_checkpoint({"state_dict": {}})


def test_no_ema_run_accepts_a_raw_only_checkpoint():
    _lit(ema_decay=None).on_load_checkpoint({"state_dict": {}})


def test_load_state_dict_rejects_a_mismatched_model():
    ema = ModelEma(_toy(), EmaConfig())
    sd = ema.state_dict()
    sd["params"].pop("0.bias")
    with pytest.raises(ValueError, match="params keys do not match"):
        ModelEma(_toy(), EmaConfig()).load_state_dict(sd)


def test_load_state_dict_rejects_a_foreign_dict():
    with pytest.raises(ValueError, match="missing 'buffers'"):
        ModelEma(_toy(), EmaConfig()).load_state_dict({"params": {}, "num_updates": 0})


def test_update_rejects_a_model_the_shadow_does_not_describe():
    ema = ModelEma(_toy(), EmaConfig())
    other = nn.Sequential(nn.Conv2d(3, 5, 3, padding=1), nn.BatchNorm2d(5), nn.ReLU())
    with pytest.raises(ValueError, match="shape"):
        ema.update(other, step=0)


# --------------------------------------------------------------------------
# DDP
# --------------------------------------------------------------------------


def test_ddp_wrapped_model_uses_unprefixed_keys():
    os.environ.setdefault("MASTER_ADDR", "127.0.0.1")
    os.environ.setdefault("MASTER_PORT", "29734")
    torch.distributed.init_process_group("gloo", rank=0, world_size=1)
    try:
        model = _toy()
        _fill(model, 0.0)
        ddp = nn.parallel.DistributedDataParallel(model)
        ema = ModelEma(ddp, EmaConfig(decay=0.5, warmup_iters=0))
        assert set(ema.params) == {name for name, _ in model.named_parameters()}
        assert not any(name.startswith("module.") for name in ema.params)

        _fill(ddp, 1.0)
        ema.update(ddp, step=0)
        assert ema.params["0.bias"].max().item() == pytest.approx(0.5)

        # A shadow built under DDP must load into a bare module and back.
        bare = _toy(seed=9)
        ema.copy_to(bare)
        assert torch.equal(bare[0].bias.detach(), ema.params["0.bias"])
        with ema.swapped(ddp):
            assert torch.equal(model[0].bias.detach(), ema.params["0.bias"])
        assert model[0].bias.detach().max().item() == pytest.approx(1.0)
    finally:
        torch.distributed.destroy_process_group()
