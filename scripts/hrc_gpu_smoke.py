#!/usr/bin/env python3
"""HRC-ResEnc vs ResEnc L smoke on one device: equality, finite training, time and memory.

Builds both networks from a frozen nnU-Net ``nnUNetResEncUNetLPlans.json`` through
nnU-Net's own ``get_network_from_plans``, copies the ResEnc weights into the
zero-initialised HRC network and checks that every deep-supervision output is
identical in fp32 with deterministic cuDNN kernels (fp16 autocast equality is
reported too). It then switches to the production training settings
(``cudnn.benchmark=True``, ``cudnn.deterministic=False``, as the backend uses
with ``deterministic=false``), times fp16-autocast inference forwards, and trains
each network for ``--steps`` updates on random patches with nnU-Net's optimizer
settings, mixed precision, gradient clipping at 12 and deep-supervised DC+CE
loss. It records step time, peak memory, and gradient norms per parameter group
(ResEnc base, HRC FiLM, other HRC) with the fraction of clipped steps. Synthetic
inputs only: no dataset, workspace or checkpoint is read or written.

Run it in the nnU-Net backend interpreter. ``--gpu N`` uses one physical GPU
(forbidden GPUs are refused); it takes the same per-GPU lock as backend jobs
and refuses a GPU that already holds more than ``--busy-limit-gib`` of memory,
so it cannot start beside a running training job. ``--device cpu`` is a slow
functional check. Writes one JSON record to a fresh ``--output`` path.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from segmentary.gpu_policy import refuse_forbidden
from segmentary.medical.backend import _lock
from segmentary.medical.recipe_plan import transfer_plan

GIB = 1024**3


def _networks(plan: dict, options: dict | None, num_classes: int) -> tuple[Any, Any, dict]:
    import torch
    from nnunetv2.utilities.get_network_from_plans import get_network_from_plans

    def build(document: dict) -> Any:
        architecture = document["configurations"]["3d_fullres"]["architecture"]
        return get_network_from_plans(
            architecture["network_class_name"],
            architecture["arch_kwargs"],
            architecture["_kw_requires_import"],
            1,
            num_classes,
            allow_init=True,
            deep_supervision=True,
        )

    torch.manual_seed(0)
    base = build(plan)
    hrc_plan, changes = transfer_plan(plan, "hrc", options)
    torch.manual_seed(1)
    hrc = build(hrc_plan)
    loaded = hrc.load_state_dict(base.state_dict(), strict=False)
    if loaded.unexpected_keys or any(not k.startswith("hrc.") for k in loaded.missing_keys):
        raise RuntimeError("HRC state dict is not a superset of ResEnc L")
    return base, hrc, changes


def _labels(shape: tuple[int, ...], device: Any, generator: Any) -> Any:
    """Smooth random blobs in three classes, so Dice terms are non-trivial."""
    import torch
    from torch.nn import functional as F

    field = torch.randn((shape[0], 1, *shape[2:]), generator=generator).to(device)
    field = F.avg_pool3d(field, (3, 9, 9), stride=1, padding=(1, 4, 4))
    low, high = torch.quantile(
        field.flatten()[::97].float(), torch.tensor([0.6, 0.9], device=device)
    )
    return (field > low).long() + (field > high).long()


def _equality(base: Any, hrc: Any, image: Any, *, autocast: bool = False) -> dict:
    import torch

    base.eval()
    hrc.eval()
    with (
        torch.no_grad(),
        torch.autocast(image.device.type, enabled=autocast, dtype=torch.float16),
    ):
        expected, actual = base(image), hrc(image)
    return {
        "bitwise_equal": all(torch.equal(a, b) for a, b in zip(actual, expected, strict=True)),
        "max_abs_difference": max(
            float((a.float() - b.float()).abs().max())
            for a, b in zip(actual, expected, strict=True)
        ),
        "outputs": len(actual),
    }


def _groups(network: Any) -> dict[str, list[Any]]:
    """ResEnc base parameters, HRC FiLM layers, and the other HRC parameters."""
    groups: dict[str, list[Any]] = {"base": [], "hrc_film": [], "hrc_other": []}
    for name, parameter in network.named_parameters():
        if not name.startswith("hrc."):
            groups["base"].append(parameter)
        elif ".film." in name:
            groups["hrc_film"].append(parameter)
        else:
            groups["hrc_other"].append(parameter)
    return {name: members for name, members in groups.items() if members}


def _group_norms(groups: dict[str, list[Any]]) -> dict[str, float]:
    import torch

    norms = {}
    for name, parameters in groups.items():
        grads = [p.grad.detach().float().norm() for p in parameters if p.grad is not None]
        norms[name] = float(torch.linalg.vector_norm(torch.stack(grads))) if grads else 0.0
    return norms


def _train(
    network: Any, *, steps: int, warmup: int, patch: list[int], batch: int, device: Any
) -> dict:
    import numpy as np
    import torch
    from nnunetv2.training.loss.compound_losses import DC_and_CE_loss
    from nnunetv2.training.loss.deep_supervision import DeepSupervisionWrapper
    from nnunetv2.training.loss.dice import MemoryEfficientSoftDiceLoss
    from torch.nn import functional as F

    network.train().to(device)
    groups = _groups(network)
    # nnU-Net 2.8.1 defaults: SGD, Nesterov momentum 0.99, weight decay 3e-5.
    optimizer = torch.optim.SGD(
        network.parameters(), lr=1e-2, momentum=0.99, nesterov=True, weight_decay=3e-5
    )
    outputs = len(network.decoder.stages)
    weights = np.array([1 / (2**i) for i in range(outputs)])
    weights[-1] = 0
    loss_function = DeepSupervisionWrapper(
        DC_and_CE_loss(
            {"batch_dice": False, "smooth": 1e-5, "do_bg": False, "ddp": False},
            {},
            weight_ce=1,
            weight_dice=1,
            ignore_label=None,
            dice_class=MemoryEfficientSoftDiceLoss,
        ),
        weights / weights.sum(),
    )
    cuda = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda") if cuda else None
    generator = torch.Generator().manual_seed(0)
    image = torch.randn((batch, 1, *patch), generator=generator).to(device)
    label = _labels((batch, 1, *patch), device, generator)
    # Precomputed, as nnU-Net's data loader supplies the downsampled targets.
    targets = [
        F.interpolate(label.float(), size=shape, mode="nearest").long()
        for shape in _output_shapes(network, image)
    ]
    if cuda:
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    times, losses, totals, group_norms = [], [], [], []
    for step in range(steps):
        started = time.perf_counter()
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device.type, enabled=cuda, dtype=torch.float16):
            predictions = network(image)
            loss = loss_function(predictions, targets)
        if scaler is not None:
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
        else:
            loss.backward()
        # Per-group norms only on untimed warm-up steps; they cost extra kernels.
        if step < warmup:
            group_norms.append(_group_norms(groups))
        total = torch.nn.utils.clip_grad_norm_(network.parameters(), 12)
        if scaler is not None:
            scaler.step(optimizer)
            scaler.update()
        else:
            optimizer.step()
        if cuda:
            torch.cuda.synchronize()
        losses.append(float(loss.detach()))
        totals.append(float(total))
        if step >= warmup:
            times.append(time.perf_counter() - started)
    film = {
        name: float(block.film.weight.detach().norm())
        for name, block in getattr(network, "hrc", {}).items()
    }
    finite = [value for value in totals if math.isfinite(value)]
    result = {
        "steps": steps,
        "timed_steps": len(times),
        "median_step_seconds": statistics.median(times) if times else None,
        "mean_step_seconds": statistics.fmean(times) if times else None,
        "finite_losses": all(np.isfinite(losses)),
        "first_loss": losses[0],
        "last_loss": losses[-1],
        "peak_allocated_gib": torch.cuda.max_memory_allocated() / GIB if cuda else None,
        "peak_reserved_gib": torch.cuda.max_memory_reserved() / GIB if cuda else None,
        "film_weight_norms": film,
        "gradient_norms": {
            "clip_threshold": 12,
            "nonfinite_steps_skipped_by_scaler": len(totals) - len(finite),
            "clipped_fraction": sum(value > 12 for value in finite) / len(finite)
            if finite
            else None,
            "total_median": statistics.median(finite) if finite else None,
            "total_first": totals[0],
            "per_group_first_step": group_norms[0] if group_norms else None,
            "per_group_warmup_median": {
                name: statistics.median(step[name] for step in group_norms)
                for name in (group_norms[0] if group_norms else {})
            },
        },
    }
    network.to("cpu")
    del optimizer
    if cuda:
        torch.cuda.empty_cache()
    return result


def _output_shapes(network: Any, image: Any) -> list[tuple[int, ...]]:
    import torch

    with torch.no_grad(), torch.autocast(image.device.type, enabled=image.is_cuda):
        return [tuple(p.shape[2:]) for p in network(image[:1])]


def _forward(network: Any, *, repeats: int, patch: list[int], batch: int, device: Any) -> float:
    """Median inference forward time, under fp16 autocast on CUDA as nnU-Net predicts."""
    import torch

    network.eval().to(device)
    image = torch.randn((batch, 1, *patch), device=device)
    times = []
    with torch.no_grad(), torch.autocast(device.type, enabled=device.type == "cuda"):
        for repeat in range(repeats + 1):
            started = time.perf_counter()
            network(image)
            if device.type == "cuda":
                torch.cuda.synchronize()
            if repeat:
                times.append(time.perf_counter() - started)
    network.to("cpu")
    return statistics.median(times)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gpu")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--patch", type=int, nargs=3, help="defaults to the plan patch")
    parser.add_argument("--batch", type=int, help="defaults to the plan batch size")
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--forward-repeats", type=int, default=5)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--reference-mode", default="robust")
    parser.add_argument(
        "--levels", type=int, nargs="+", help="HRC block levels (default: the plan's 2 1 0)"
    )
    parser.add_argument("--busy-limit-gib", type=float, default=2.0)
    parser.add_argument("--memory-limit-gib", type=float, default=34.0)
    parser.add_argument("--overhead-limit", type=float, default=0.15)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError("Use a fresh --output path")
    if (args.device == "cuda") != (args.gpu is not None):
        raise ValueError("Use --device cuda with one --gpu, or --device cpu without one")
    if args.gpu is not None:
        refuse_forbidden([args.gpu])
        inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
        if inherited is not None and args.gpu not in inherited.split(","):
            raise ValueError("Requested GPU exceeds inherited CUDA_VISIBLE_DEVICES")
    with contextlib.ExitStack() as stack:
        if args.gpu is not None:
            # The backend's per-GPU lock: never share a GPU with a Segmentary job.
            lock_root = Path(
                os.environ.get(
                    "SEGMENTARY_MEDICAL_LOCK_DIR",
                    str(Path(tempfile.gettempdir()) / f"segmentary-medical-{os.getuid()}"),
                )
            )
            stack.enter_context(_lock(lock_root / f"gpu-{args.gpu}.lock"))
        return _run(args)


def _run(args: argparse.Namespace) -> int:
    # Bind visibility before Torch initialises CUDA.
    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu if args.gpu is not None else ""
    import torch

    torch.set_num_threads(args.threads)
    device = torch.device("cuda", 0) if args.gpu is not None else torch.device("cpu")
    if device.type == "cuda":
        if torch.cuda.device_count() != 1:
            raise RuntimeError("Exactly one GPU must be visible")
        free, total = torch.cuda.mem_get_info(0)
        if (total - free) / GIB > args.busy_limit_gib:
            # Another process (for example an unfinished training run) holds memory.
            raise RuntimeError(
                f"GPU {args.gpu} already uses {(total - free) / GIB:.1f} GiB; refusing to share it"
            )
    # Equality under deterministic kernels; timing and memory under production settings.
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    plan = json.loads(args.plan.read_text())
    selected = plan["configurations"]["3d_fullres"]
    patch = list(args.patch or selected["patch_size"])
    batch = args.batch or selected["batch_size"]
    options: dict[str, Any] = {"reference_mode": args.reference_mode}
    if args.levels:
        options["levels"] = args.levels
    base, hrc, changes = _networks(plan, options, 3)
    parameters = {
        "resenc": sum(p.numel() for p in base.parameters()),
        "hrc": sum(p.numel() for p in hrc.parameters()),
    }
    image = torch.randn((1, 1, *patch), generator=torch.Generator().manual_seed(5)).to(device)
    base.to(device)
    hrc.to(device)
    equality = _equality(base, hrc, image)
    equality_fp16 = _equality(base, hrc, image, autocast=True) if device.type == "cuda" else None
    base.to("cpu")
    hrc.to("cpu")
    del image
    torch.backends.cudnn.deterministic = False
    torch.backends.cudnn.benchmark = device.type == "cuda"
    forward = {
        name: _forward(
            network, repeats=args.forward_repeats, patch=patch, batch=batch, device=device
        )
        for name, network in (("resenc", base), ("hrc", hrc))
    }
    training = {
        name: _train(
            network, steps=args.steps, warmup=args.warmup, patch=patch, batch=batch, device=device
        )
        for name, network in (("resenc", base), ("hrc", hrc))
    }
    step = {name: training[name]["median_step_seconds"] for name in training}
    overhead = step["hrc"] / step["resenc"] - 1 if step["resenc"] and step["hrc"] else None
    record = {
        "device": str(device),
        "gpu": args.gpu,
        "gpu_name": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
        "torch": torch.__version__,
        "plan": str(args.plan),
        "patch": patch,
        "batch": batch,
        "threads": args.threads,
        "hrc_options": changes["hrc_options"],
        "parameters": parameters,
        "parameter_overhead": parameters["hrc"] / parameters["resenc"] - 1,
        "zero_init_equality_fp32": equality,
        "zero_init_equality_fp16_autocast": equality_fp16,
        "settings": {
            "equality": "cudnn.deterministic=True, benchmark=False, fp32",
            "timing_and_memory": "cudnn.deterministic=False, benchmark=True (production), "
            "fp16 autocast for forwards and training",
        },
        "forward_median_seconds": forward,
        "forward_overhead": forward["hrc"] / forward["resenc"] - 1,
        "training": training,
        "step_time_overhead": overhead,
        "criteria": {
            "equality": equality["bitwise_equal"],
            "finite_losses": all(item["finite_losses"] for item in training.values()),
            "memory_below_limit": None
            if device.type != "cuda"
            else training["hrc"]["peak_allocated_gib"] < args.memory_limit_gib,
            "step_overhead_below_limit": None
            if overhead is None or device.type != "cuda"
            else overhead < args.overhead_limit,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "criteria": record["criteria"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
