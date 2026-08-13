"""Seeding for python/numpy/torch, albumentations pipelines and DataLoader workers.

Segmentation training draws randomness from generators that do not share state:
python ``random``, numpy's legacy global, torch, *and* -- since albumentations
2.x -- a private ``random.Random`` plus ``np.random.Generator`` owned by each
Compose. Seeding only torch is the usual mistake: model init is reproducible but
the augmentation stream is not, so two "identical" runs differ by more than the
ablation being measured. Missing the albumentations generators is the subtler
version of the same mistake and is worse, because their default seeding from OS
entropy happens once at construction and is then *frozen* into every forked
worker -- see ``seed_transforms``.
"""

from __future__ import annotations

import os
import random

import numpy as np
import torch
import torch.utils.data

# numpy's legacy seeder rejects anything outside this range, and PYTHONHASHSEED
# is read as a 32-bit value, so a seed valid for torch alone can still explode.
_MAX_SEED = 2**32


def seed_everything(seed: int, deterministic: bool = False) -> None:
    """Seed every RNG this project draws from.

    Args:
        seed: non-negative value below 2**32.
        deterministic: force bitwise-reproducible kernels. This costs real
            throughput -- cuDNN loses autotuning and the deterministic
            scatter/gather fallbacks are markedly slower, so expect a
            noticeable slowdown on a full training run. Use it to debug a
            divergence, not to produce reported benchmark numbers.

    With ``deterministic=False`` cuDNN autotuning is enabled instead, which is
    the right default for fixed-size crops but makes runs reproducible only to
    within kernel-selection noise.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError(f"seed must be an int, got {type(seed).__name__}; pass e.g. seed=42.")
    if not 0 <= seed < _MAX_SEED:
        raise ValueError(
            f"seed must be in [0, {_MAX_SEED}), got {seed}. numpy and PYTHONHASHSEED "
            "both reject values outside that range."
        )

    # Read only at interpreter startup, so this reaches spawned children (and
    # nothing else -- forked DataLoader workers inherit the parent's hash seed
    # and are unaffected either way).
    os.environ["PYTHONHASHSEED"] = str(seed)
    # Lightning reads this when it replaces a loader's sampler for DDP. Calling
    # Lightning's seed_everything here would also change its worker seeding,
    # bypassing the project's albumentations-aware worker_init_fn below.
    os.environ["PL_GLOBAL_SEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)  # no-op without CUDA, safe to call unconditionally

    if deterministic:
        # cuBLAS reads this once, when it creates its handle. Setting it after the
        # first matmul is silently useless, so warn rather than pretend.
        if torch.cuda.is_initialized():
            raise RuntimeError(
                "seed_everything(deterministic=True) must run before the first CUDA "
                "call: CUBLAS_WORKSPACE_CONFIG is read when cuBLAS initialises, so "
                "setting it now would not make matmuls deterministic. Move the call "
                "to the top of the entrypoint."
            )
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    else:
        torch.backends.cudnn.benchmark = True


def seed_transforms(dataset: object, seed: int) -> None:
    """Re-seed the albumentations pipeline(s) a dataset holds.

    albumentations 2.x gives every Compose its own ``random.Random`` and
    ``np.random.Generator``, seeded from OS entropy when the Compose is built.
    ``random.seed``/``np.random.seed`` cannot reach them, and because the parent
    process never draws from them, every forked worker inherits the *same* frozen
    state: all workers emit identical crops and every epoch replays the same
    augmentations. Call this from ``worker_init_fn``, and directly after building
    the loaders when ``num_workers == 0``.

    Accepts a single dataset or anything exposing ``.datasets`` (MixedDataset,
    ConcatDataset), and is a no-op for members that carry no transform.
    """
    if not 0 <= seed < _MAX_SEED:
        raise ValueError(f"seed must be in [0, {_MAX_SEED}), got {seed}.")
    members = getattr(dataset, "datasets", None)
    for member in members if members is not None else [dataset]:
        transform = getattr(member, "transform", None)
        if transform is None:
            continue
        if not hasattr(transform, "set_random_seed"):
            raise TypeError(
                f"{type(member).__name__}.transform is a {type(transform).__name__}, "
                "which has no set_random_seed; its randomness cannot be made "
                "reproducible, so the run's augmentation stream would be unseeded."
            )
        transform.set_random_seed(seed)


def worker_init_fn(worker_id: int) -> None:
    """Give each DataLoader worker its own reproducible RNG state.

    Forked workers inherit the parent's ``random``, numpy and albumentations
    state verbatim, so without this every worker generates the *same* crops and
    flips and the effective augmentation diversity drops by a factor of
    ``num_workers``. torch already re-seeds itself per worker and per epoch; this
    propagates that seed to the generators torch does not own.
    """
    seed = (torch.initial_seed() + worker_id) % _MAX_SEED
    random.seed(seed)
    np.random.seed(seed)

    info = torch.utils.data.get_worker_info()
    if info is not None:  # None only if called outside a worker, e.g. from a test
        seed_transforms(info.dataset, seed)
