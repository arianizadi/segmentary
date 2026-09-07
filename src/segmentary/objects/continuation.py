"""Serializable optimizer-boundary sampling and random state for object training."""

from __future__ import annotations

import random
import signal
from contextlib import contextmanager
from typing import Any, cast

import numpy as np
import torch


def rng_state() -> dict:
    state = cast(Any, np.random.get_state())
    return {
        "python": random.getstate(),
        "numpy": [state[0], state[1].tolist(), state[2], state[3], state[4]],
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
    }


def restore_rng(state: dict) -> None:
    random.setstate(state["python"])
    n = state["numpy"]
    np.random.set_state((n[0], np.asarray(n[1], dtype=np.uint32), n[2], n[3], n[4]))
    torch.set_rng_state(state["torch"])
    if state["cuda"]:
        if len(state["cuda"]) != torch.cuda.device_count():
            raise ValueError("Resume requires the same CUDA device topology")
        torch.cuda.set_rng_state_all(state["cuda"])


class BatchOrder:
    """Persist the exact permutation and next sample; never cross epochs in an update."""

    def __init__(self, size: int, seed: int):
        self.size = size
        self.generator = torch.Generator().manual_seed(seed)
        self.order: list[int] = []
        self.cursor = 0
        self.epoch = -1

    def take(self, batch_size: int, accumulation: int) -> list[list[int]]:
        if self.cursor == len(self.order):
            self.order = torch.randperm(self.size, generator=self.generator).tolist()
            self.cursor = 0
            self.epoch += 1
        end = min(self.size, self.cursor + batch_size * accumulation)
        groups = [
            self.order[i : min(i + batch_size, end)] for i in range(self.cursor, end, batch_size)
        ]
        self.cursor = end
        return groups

    def state_dict(self) -> dict:
        return {
            "size": self.size,
            "order": self.order,
            "cursor": self.cursor,
            "epoch": self.epoch,
            "generator": self.generator.get_state(),
        }

    def load_state_dict(self, state: dict) -> None:
        if state["size"] != self.size:
            raise ValueError("Resume dataset size differs")
        self.order, self.cursor, self.epoch = state["order"], state["cursor"], state["epoch"]
        self.generator.set_state(state["generator"])


@contextmanager
def graceful_stop():
    """SIGINT/SIGTERM finish the current update before returning; restore caller handlers."""
    requested = {"stop": False}
    previous = {}

    def handle(signum, frame):
        requested["stop"] = True

    try:
        for kind in (signal.SIGINT, signal.SIGTERM):
            previous[kind] = signal.signal(kind, handle)
        yield requested
    finally:
        for kind, handler in previous.items():
            signal.signal(kind, handler)
