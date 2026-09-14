"""Retention keeps recoverable/selected state without accumulating middle epochs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from segmentary.medical import torch_backend
from segmentary.medical.torch_config import TorchConfig


def _index(root: Path) -> dict:
    return json.loads((root / "checkpoint-index.json").read_text())


def _state(epoch: int) -> dict:
    return {"identity": "retention-fixture", "epoch": epoch, "model": {"w": torch.tensor([epoch])}}


def _assert_exact_retention(root: Path, epochs: dict[str, int]) -> dict:
    records = _index(root)["files"]
    assert set(records) == set(epochs)
    assert {p.name for p in (root / "checkpoints").iterdir()} == {
        record["path"] for record in records.values()
    }
    for alias, epoch in epochs.items():
        record = records[alias]
        path = root / "checkpoints" / record["path"]
        assert torch_backend._sha(path) == record["sha256"]
        state = torch.load(path, map_location="cpu", weights_only=True)
        assert state["epoch"] == epoch
        torch.testing.assert_close(state["model"]["w"], torch.tensor([epoch]))
    return records


def test_retention_preserves_earlier_best_and_parent_evidence_while_latest_rolls(tmp_path):
    config = TorchConfig(workspace=str(tmp_path), gpu="cpu")
    save = torch_backend._save_checkpoint
    save(config, _state(1), ["checkpoint_best.pth", "checkpoint_latest.pth"])
    first = _assert_exact_retention(
        tmp_path, {"checkpoint_best.pth": 1, "checkpoint_latest.pth": 1}
    )
    assert first["checkpoint_best.pth"] == first["checkpoint_latest.pth"]
    best = tmp_path / "checkpoints" / first["checkpoint_best.pth"]["path"]
    best_bytes = best.read_bytes()

    # Original continuation bytes deliberately live outside the active index.
    parent = tmp_path / "continuation-parent"
    parent.mkdir()
    evidence = parent / best.name
    evidence.write_bytes(best_bytes)

    save(config, _state(2), ["checkpoint_latest.pth"])
    middle = _assert_exact_retention(
        tmp_path, {"checkpoint_best.pth": 1, "checkpoint_latest.pth": 2}
    )["checkpoint_latest.pth"]["path"]
    save(config, _state(3), ["checkpoint_latest.pth", "checkpoint_final.pth"])
    final = _assert_exact_retention(
        tmp_path, {"checkpoint_best.pth": 1, "checkpoint_latest.pth": 3, "checkpoint_final.pth": 3}
    )
    assert not (tmp_path / "checkpoints" / middle).exists()
    assert best.read_bytes() == best_bytes
    assert final["checkpoint_latest.pth"] == final["checkpoint_final.pth"]
    assert final["checkpoint_best.pth"] != final["checkpoint_latest.pth"]

    # A final improvement needs one physical generation for all three aliases.
    save(config, _state(4), list(final))
    improved = _assert_exact_retention(tmp_path, dict.fromkeys(final, 4))
    assert len({record["path"] for record in improved.values()}) == 1
    assert evidence.read_bytes() == best_bytes


def test_next_successful_save_recovers_failed_publication_orphan(tmp_path, monkeypatch):
    config = TorchConfig(workspace=str(tmp_path), gpu="cpu")
    save = torch_backend._save_checkpoint
    save(config, _state(1), ["checkpoint_best.pth", "checkpoint_latest.pth"])
    previous = _index(tmp_path)
    previous_path = tmp_path / "checkpoints" / previous["files"]["checkpoint_best.pth"]["path"]
    previous_bytes = previous_path.read_bytes()
    publish = torch_backend._atomic_json

    def fail_publication(path, value):
        if path.name == "checkpoint-index.json":
            raise OSError("injected index publication failure")
        return publish(path, value)

    monkeypatch.setattr(torch_backend, "_atomic_json", fail_publication)
    with pytest.raises(OSError, match="injected index publication failure"):
        save(config, _state(2), ["checkpoint_latest.pth"])
    assert _index(tmp_path) == previous
    assert previous_path.read_bytes() == previous_bytes
    orphan_paths = set((tmp_path / "checkpoints").glob("generation-*.pth")) - {previous_path}
    assert len(orphan_paths) == 1

    monkeypatch.setattr(torch_backend, "_atomic_json", publish)
    save(config, _state(3), ["checkpoint_latest.pth", "checkpoint_final.pth"])
    _assert_exact_retention(
        tmp_path, {"checkpoint_best.pth": 1, "checkpoint_latest.pth": 3, "checkpoint_final.pth": 3}
    )
    assert all(not path.exists() for path in orphan_paths)
    assert previous_path.read_bytes() == previous_bytes
