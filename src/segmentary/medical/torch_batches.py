"""Bounded CPU prefetch with sampling RNG committed only for consumed batches."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
from torch import Tensor

from .torch_config import TorchConfig
from .torch_data import sample_patch


@dataclass
class _Batch:
    images: Tensor
    labels: Tensor
    sampling_state: dict[str, Any]


class BatchStream(Iterator[tuple[Tensor, Tensor]]):
    """Sample batches synchronously or prepare exactly one CPU batch ahead.

    Use as a context manager. ``load_case`` must be a deterministic, read-only
    loader, including when called by the single producer thread. The stream owns
    the supplied sampling generator until it closes; other code must not advance
    it concurrently. Only a consumed batch commits its post-sampling RNG state.
    Discarding an unused prefetched batch therefore cannot alter checkpoint or
    resume behavior. The producer never uses Torch or Python random generators.

    ``prefetch_batches=False`` preserves synchronous CPU tensors and transfers.
    On CUDA, prefetch also pins float32 images and compact uint8 labels; labels
    return to int64 on the device. No GPU stream or device work runs in the
    producer thread, except allocating pinned host memory through Torch.
    """

    def __init__(
        self,
        config: TorchConfig,
        train_ids: Sequence[str],
        load_case: Callable[[str], dict],
        rng: np.random.Generator,
        device: torch.device | str,
    ) -> None:
        if not train_ids:
            raise ValueError("BatchStream requires at least one training case")
        self.config = config
        self.train_ids = tuple(train_ids)
        self.load_case = load_case
        self.rng = rng
        self.device = torch.device(device)
        self._executor: ThreadPoolExecutor | None = None
        self._future: Future[_Batch] | None = None
        self._entered = False
        self._closed = False

    def __enter__(self) -> BatchStream:
        if self._entered or self._closed:
            raise RuntimeError("BatchStream contexts cannot be entered twice")
        self._entered = True
        if self.config.prefetch_batches:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ct-batch")
            self._schedule()
        return self

    def _schedule(self) -> None:
        if self._executor is None or self._future is not None:
            raise RuntimeError("A BatchStream may have only one producer future")
        # Clone before dispatch: the worker never reads or mutates the generator
        # held by the main thread or serialized into its checkpoint.
        worker_rng = copy.deepcopy(self.rng)
        self._future = self._executor.submit(self._produce, worker_rng)

    def _produce(self, rng: np.random.Generator) -> _Batch:
        patches = [
            sample_patch(self.load_case(str(rng.choice(self.train_ids))), self.config, rng)
            for _ in range(self.config.batch_size)
        ]
        images = torch.from_numpy(np.stack([patch[0] for patch in patches]))
        labels = torch.from_numpy(np.stack([patch[1] for patch in patches]))
        if self.config.prefetch_batches and self.device.type == "cuda":
            # The medical ontology is 0=background, 1=pancreas, 2=mass. Validate
            # before narrowing rather than wrapping an unexpected target value.
            if labels.numel() and (labels.min() < 0 or labels.max() > 2):
                raise ValueError("Compact CT targets require labels in [0,2]")
            images = images.pin_memory()
            labels = labels.to(torch.uint8).pin_memory()
        return _Batch(images, labels, copy.deepcopy(dict(rng.bit_generator.state)))

    def __iter__(self) -> BatchStream:
        return self

    def __next__(self) -> tuple[Tensor, Tensor]:
        if not self._entered or self._closed:
            raise RuntimeError("Consume BatchStream inside its active context")
        try:
            if self._future is not None:
                batch = self._future.result()
                self._future = None
            else:
                batch = self._produce(copy.deepcopy(self.rng))
            asynchronous = self.config.prefetch_batches and self.device.type == "cuda"
            images = batch.images.to(self.device, non_blocking=asynchronous)
            labels = batch.labels.to(self.device, non_blocking=asynchronous)
            if labels.dtype != torch.int64:
                labels = labels.to(torch.int64)
            self.rng.bit_generator.state = copy.deepcopy(batch.sampling_state)
            if self._executor is not None:
                self._schedule()
            return images, labels
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        """Release the sole producer; discard its unused batch without RNG commit."""
        if self._closed:
            return
        self._closed = True
        if self._future is not None:
            self._future.cancel()
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
        self._future = None
        self._executor = None

    def __exit__(self, *_exc: Any) -> None:
        self.close()
