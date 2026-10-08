"""nnFoundation-style pretrained encoders in a separate nnU-Net master environment.

nnU-Net master (``nnUNetv2_plan_like_dynamic`` + ``DynamicPretrainedTrainer``)
keeps our frozen ResEnc L plan and adapts a pretrained encoder at load time:
3x3x3 kernels become 1x3x3 by averaging over z where the plan has a 1 there,
stages the checkpoint lacks keep their initialisation, and the decoder is new.
This module adds what the experiment needs on top of that route:

- ``runtime_identity``: the environment is bound by its ``pip freeze`` SHA256
  and by the nnU-Net source commit. Master still reports version 2.8.1, so the
  installed ``nnunetv2`` tree must also hash equal to a clean checkout of that
  commit (and the dynamic-network-architectures tree is recorded).
- ``nnUNetTrainerPretrainedDS`` (defined lazily; nnU-Net master only): the
  shipped trainers turn deep supervision off and make its toggle a no-op, and
  refuse non-ResEnc class names. This subclass re-enables both, builds any
  plan class (ResEnc L or ``HRCResEncUNet``) through the official
  ``build_network_architecture`` signature that the predictor also uses, and
  takes ``num_epochs``/``initial_lr`` from the bound config. Its whole-network
  warm-up keeps the vendor ratio (50 of 1000 epochs, so 15 of 300).
- ``load_pretrained_encoder``: runs the vendor dynamic loader on the
  SHA256-verified checkpoint bytes, then independently classifies every
  network tensor as copied, adapted or left at initialisation and fails
  closed on anything else. The classification is the origin record.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

RUNTIME = "nnunet-master-nnssl"
TRAINER = "nnUNetTrainerPretrainedDS"
# DynamicPretrainedTrainer warms the whole network up for 50 of its 1000 epochs.
VENDOR_WARMUP_FRACTION = 50 / 1000
_TREE_PROBE = r"""
import hashlib, importlib.metadata as m, importlib.util as u, json
from pathlib import Path
def tree(root):
    h, n = hashlib.sha256(), 0
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(root).as_posix().encode() + b"\0")
        h.update(hashlib.sha256(p.read_bytes()).hexdigest().encode() + b"\n")
        n += 1
    return h.hexdigest(), n
out = {}
for dist, package in (("nnunetv2", "nnunetv2"),
                      ("dynamic_network_architectures", "dynamic_network_architectures")):
    root = Path(u.find_spec(package).submodule_search_locations[0])
    digest, files = tree(root)
    out[package] = {"version": m.version(dist), "direct_url": m.distribution(dist).read_text("direct_url.json"),
                    "installed_python_tree_sha256": digest, "python_files": files}
print(json.dumps(out))
"""


def python_tree_sha256(root: Path) -> tuple[str, int]:
    """SHA256 over a package's ``.py`` files (relative path and content), as the probe hashes."""
    digest, count = hashlib.sha256(), 0
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
        count += 1
    return digest.hexdigest(), count


def _git(source: Path, *args: str) -> str:
    # --no-optional-locks: never refresh (write) the index of a checkout we only read.
    return subprocess.run(
        ["git", "--no-optional-locks", "-C", str(source), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout.strip()


def _source_commit(package: dict[str, Any], name: str) -> dict[str, Any]:
    """Prove where an installed package came from: VCS commit, or a clean local checkout."""
    direct = json.loads(package.get("direct_url") or "null")
    if not isinstance(direct, dict) or not isinstance(direct.get("url"), str):
        raise RuntimeError(f"{name} has no PEP 610 direct_url record; cannot prove its commit")
    vcs = direct.get("vcs_info")
    if isinstance(vcs, dict) and isinstance(vcs.get("commit_id"), str):
        return {"url": direct["url"], "commit": vcs["commit_id"], "proof": "pep610_vcs_info"}
    url = urlparse(direct["url"])
    if url.scheme != "file" or "dir_info" not in direct or direct["dir_info"].get("editable"):
        raise RuntimeError(f"{name} must be a VCS or non-editable local-checkout install")
    source = Path(unquote(url.path))
    try:
        commit = _git(source, "rev-parse", "HEAD")
        dirty = _git(source, "status", "--porcelain", "--untracked-files=all")
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Cannot read the {name} source checkout {source}") from exc
    tree, files = python_tree_sha256(source / name)
    if dirty or tree != package["installed_python_tree_sha256"]:
        raise RuntimeError(
            f"Installed {name} differs from its clean source checkout at {commit}; "
            "rebuild the environment from the bound commit"
        )
    return {
        "url": direct["url"],
        "commit": commit,
        "proof": "clean_checkout_python_tree_equals_installed",
        "source_python_files": files,
    }


def runtime_identity(python: str, environment: dict[str, str]) -> dict[str, Any]:
    """``pip freeze`` SHA256 and installed nnU-Net/architecture sources of an interpreter."""
    freeze = subprocess.run(
        [python, "-m", "pip", "--disable-pip-version-check", "freeze"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    probe = subprocess.run(
        [python, "-c", _TREE_PROBE],
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if freeze.returncode or probe.returncode:
        raise RuntimeError(
            f"Cannot fingerprint backend interpreter: {(freeze.stderr + probe.stderr).strip()}"
        )
    packages = json.loads(probe.stdout)
    sources = {name: _source_commit(packages[name], name) for name in ("nnunetv2",)}
    return {
        "pip_freeze_sha256": hashlib.sha256(freeze.stdout.encode()).hexdigest(),
        "nnunetv2_commit": sources["nnunetv2"]["commit"],
        "packages": packages,
        "sources": sources,
    }


@contextlib.contextmanager
def _serve_verified_bytes(path: str, data: bytes) -> Iterator[None]:
    """Make the vendor loader read the SHA256-verified bytes (on CPU), not the path again."""
    import torch

    original = torch.load

    def load(source: Any, *args: Any, **kwargs: Any) -> Any:
        if str(source) != path:
            return original(source, *args, **kwargs)
        return original(io.BytesIO(data), *args, **{**kwargs, "map_location": "cpu"})

    torch.load = load  # type: ignore[assignment]
    try:
        yield
    finally:
        torch.load = original  # type: ignore[assignment]


def _storage_groups(state: dict[str, Any]) -> dict[str, list[str]]:
    """Canonical (first) state-dict name -> every name aliasing the same tensor."""
    groups: dict[tuple, list[str]] = {}
    for name, tensor in state.items():
        key = (
            tensor.device.type,
            tensor.untyped_storage().data_ptr(),
            tensor.storage_offset(),
            tuple(tensor.shape),
            tuple(tensor.stride()),
        )
        groups.setdefault(key, []).append(name)
    return {names[0]: names for names in groups.values()}


def _adapted(source: Any, shape: Sequence[int]) -> tuple[Any, list[int]]:
    """The vendor kernel adaptation: mean over spatial axes reduced to size 1."""
    if source.ndim != len(shape) or source.ndim < 3 or tuple(source.shape[:2]) != tuple(shape[:2]):
        raise ValueError("Only convolution kernels may be adapted")
    axes = []
    for axis in range(2, source.ndim):
        if source.shape[axis] != shape[axis]:
            if shape[axis] != 1:
                raise ValueError("Only kernel reductions to size 1 are supported")
            axes.append(axis)
    return (source.mean(dim=axes, keepdim=True) if axes else source), axes


def classify_transfer(
    before: dict[str, Any],
    after: dict[str, Any],
    checkpoint: dict[str, Any],
    groups: dict[str, list[str]],
    *,
    allowed_random_prefixes: Sequence[str],
    transferable_prefix: str = "encoder.",
) -> dict[str, Any]:
    """Classify each tensor after loading; refuse anything but copy, adaptation or initialisation.

    Under ``transferable_prefix`` a tensor whose name is in the checkpoint must
    now equal it (``copied``) or its kernel adaptation (``adapted``). Every other
    tensor must be unchanged since construction (``random``) and must lie under
    an allowed prefix. Aliases (for example ``decoder.encoder.*``, or a
    convolution reachable as ``conv`` and ``all_modules.0``) are classified once.
    """
    import torch

    prefixes = tuple(allowed_random_prefixes)
    copied: list[str] = []
    adapted: list[dict[str, Any]] = []
    random: list[str] = []
    numel = {"copied": 0, "adapted": 0, "random": 0}
    errors: list[str] = []
    for name in groups:
        old, new = before[name].cpu(), after[name].detach().cpu()
        source = checkpoint.get(name)
        if name.startswith(transferable_prefix) and source is not None:
            source = source.cpu()
            if tuple(source.shape) == tuple(new.shape):
                if torch.equal(source.to(new.dtype), new):
                    copied.append(name)
                    numel["copied"] += new.numel()
                    continue
                errors.append(f"{name}: differs from the checkpoint")
                continue
            try:
                expected, axes = _adapted(source.float(), tuple(new.shape))
            except ValueError as exc:
                errors.append(f"{name}: {exc}")
                continue
            if torch.allclose(expected, new.float(), rtol=1e-6, atol=1e-7):
                adapted.append(
                    {
                        "name": name,
                        "from_shape": list(source.shape),
                        "to_shape": list(new.shape),
                        "rule": f"mean over axes {axes}",
                    }
                )
                numel["adapted"] += new.numel()
                continue
            errors.append(f"{name}: not the vendor kernel adaptation of the checkpoint")
            continue
        if not torch.equal(old, new):
            errors.append(f"{name}: changed although it is not a transferable checkpoint tensor")
        elif not name.startswith(prefixes):
            errors.append(f"{name}: kept its initialisation outside {list(prefixes)}")
        else:
            random.append(name)
            numel["random"] += new.numel()
    if errors:
        raise ValueError("Pretrained encoder transfer is not as declared: " + "; ".join(errors[:8]))
    if not copied:
        raise ValueError("No checkpoint tensor was transferred")
    canonical = set(copied) | {item["name"] for item in adapted}
    loaded = {alias for name in canonical for alias in groups[name]}
    return {
        "copied": sorted(copied),
        "adapted": sorted(adapted, key=lambda item: item["name"]),
        "random": sorted(random),
        "aliases": sorted(alias for names in groups.values() for alias in names[1:]),
        "parameters": numel,
        "checkpoint_tensors_unused": sorted(set(checkpoint) - loaded),
    }


def load_pretrained_encoder(trainer: Any, config: Any) -> dict[str, Any]:
    """Load a SHA256-bound nnssl checkpoint with the vendor dynamic loader and record it."""
    import torch

    if not callable(getattr(trainer, "load_pretrained_weights_dynamic", None)):
        raise ValueError("This trainer has no dynamic pretrained-weight loader")
    info = trainer.adaptation_info
    path = str(config.init_checkpoint)
    if info.get("checkpoint_path") != path:
        raise ValueError("The plan's pretrain_info names a different checkpoint")
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != config.init_checkpoint_sha256:
        raise ValueError(f"Initial checkpoint hash changed: {path}")
    checkpoint = torch.load(io.BytesIO(data), map_location="cpu", weights_only=True)
    weights = checkpoint.get("network_weights") if isinstance(checkpoint, dict) else None
    if not isinstance(weights, dict) or not weights:
        raise ValueError("Pretrained checkpoint has no network_weights")
    module = getattr(trainer.network, "_orig_mod", trainer.network)
    groups = _storage_groups(module.state_dict())
    before = {name: tensor.detach().cpu().clone() for name, tensor in module.state_dict().items()}
    arch = trainer.configuration_manager.network_arch_init_kwargs
    with _serve_verified_bytes(path, data):
        _, mismatch = trainer.load_pretrained_weights_dynamic(
            module,
            pretrained_weights_path=path,
            pt_input_channels=info["pt_num_in_channels"],
            downstream_input_channels=trainer.num_input_channels,
            pt_input_patchsize=info["pt_used_patchsize"],
            downstream_input_patchsize=trainer.configuration_manager.patch_size,
            pt_key_to_encoder=info["key_to_encoder"],
            pt_key_to_stem=info["key_to_stem"],
            pt_keys_to_in_proj=tuple(info["keys_to_in_proj"]),
            pt_key_to_lpe=info["key_to_lpe"],
            target_kernel_sizes=arch["kernel_sizes"],
            target_n_stages=arch["n_stages"],
        )
    if mismatch:
        raise ValueError("Pretrained input channels differ; the stem would be repeated")
    record = classify_transfer(
        before,
        module.state_dict(),
        weights,
        groups,
        allowed_random_prefixes=config.init_allowed_missing_prefixes or (),
    )
    from .backend import _state_digest

    plan = checkpoint.get("nnssl_adaptation_plan", {})
    return {
        "initialization": config.initialization,
        "external_weight_loads": 1,
        "init_checkpoint": path,
        "init_checkpoint_sha256": config.init_checkpoint_sha256,
        "loader": "nnunetv2 DynamicPretrainedTrainer.load_pretrained_weights_dynamic "
        "on the verified bytes, then independently classified",
        "pretrained_architecture": plan.get("architecture_plans"),
        "pretrained_key_to_encoder": plan.get("key_to_encoder"),
        "pretrained_key_to_stem": plan.get("key_to_stem"),
        "allowed_random_prefixes": list(config.init_allowed_missing_prefixes or ()),
        **record,
        "missing_keys": record["random"],
        "unexpected_keys": [],
        "initial_weights_sha256": _state_digest(module.state_dict()),
        "optimizer_state_loaded": False,
        "epoch_counter": "restarts_at_0",
    }


def _define_trainer() -> type:
    import torch
    from nnunetv2.training.dataloading.nnunet_dataset import infer_dataset_class
    from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer
    from nnunetv2.training.nnUNetTrainer.pretraining.dynamicPretrainedTrainer import (
        DynamicPretrainedTrainer,
    )
    from nnunetv2.utilities.label_handling.label_handling import determine_num_input_channels

    class nnUNetTrainerPretrainedDS(DynamicPretrainedTrainer):
        """``DynamicPretrainedTrainer`` with deep supervision and plan-built networks.

        ``initialize`` builds the network without loading weights: the backend
        loads and records them afterwards (``load_pretrained_encoder``), so the
        architecture's own initialisation can be compared tensor by tensor.
        """

        def __init__(
            self,
            plans: dict,
            configuration: str,
            fold: int,
            dataset_json: dict,
            device: torch.device = torch.device("cuda"),
        ) -> None:
            super().__init__(plans, configuration, fold, dataset_json, device)
            self.enable_deep_supervision = True

        @staticmethod
        def build_network_architecture(
            plans_manager: Any,
            configuration_manager: Any,
            num_input_channels: int,
            num_output_channels: int,
            enable_deep_supervision: bool = True,
        ) -> torch.nn.Module:
            # The official (non-pretraining) signature: the predictor calls it too.
            return nnUNetTrainer.build_network_architecture(
                plans_manager,
                configuration_manager,
                num_input_channels,
                num_output_channels,
                enable_deep_supervision,
            )

        def set_deep_supervision_enabled(self, enabled: bool) -> None:
            nnUNetTrainer.set_deep_supervision_enabled(self, enabled)

        def initialize(self) -> None:
            if self.was_initialized:  # type: ignore[has-type]
                raise RuntimeError("The trainer is already initialized")
            if self.is_ddp:
                raise RuntimeError("Distributed training is not part of this recipe")
            # The bound epoch count is set before initialize(); keep the vendor ratio.
            self.warmup_duration_whole_net = max(1, round(self.num_epochs * VENDOR_WARMUP_FRACTION))
            self._set_batch_size_and_oversample()
            self.num_input_channels = determine_num_input_channels(
                self.plans_manager, self.configuration_manager, self.dataset_json
            )
            self.network = self.build_network_architecture(
                self.plans_manager,
                self.configuration_manager,
                self.num_input_channels,
                self.label_manager.num_segmentation_heads,
                self.enable_deep_supervision,
            ).to(self.device)
            if self._do_i_compile():
                self.print_to_log_file("Using torch.compile...")
                self.network = torch.compile(self.network)  # type: ignore[assignment]
            self.optimizer, self.lr_scheduler = self.configure_optimizers()
            self.loss = self._build_loss()
            self.dataset_class = infer_dataset_class(self.preprocessed_dataset_folder)
            self.was_initialized = True

    nnUNetTrainerPretrainedDS.__module__ = __name__
    nnUNetTrainerPretrainedDS.__qualname__ = TRAINER
    return nnUNetTrainerPretrainedDS


def __getattr__(name: str) -> Any:
    # Defined lazily: this module imports without nnU-Net master in the harness.
    if name == TRAINER:
        cls = _define_trainer()
        globals()[name] = cls
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
