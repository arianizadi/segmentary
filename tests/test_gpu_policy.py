"""The frozen GPU allowlist fails closed at every boundary; no GPU is needed."""

from __future__ import annotations

import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

from helpers_gpu_policy import (
    ALLOWED,
    HOST,
    INVENTORY,
    make_campaign,
    make_policy,
    patch_live,
    pinned_env,
    uuid_of,
)
from segmentary import gpu_policy
from segmentary.gpu_policy import GpuPolicyError

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("text", ["", "2,", "2,2", "-1", "2,x", "2 3"])
def test_parse_gpus_rejects_malformed_lists(text):
    with pytest.raises(GpuPolicyError):
        gpu_policy.parse_gpus(text)


def test_parse_gpus_keeps_distinct_indices():
    assert gpu_policy.parse_gpus("9, 2,3") == (9, 2, 3)


def test_freeze_records_allowed_and_forbidden_entries_only_from_inventory():
    policy = make_policy()
    assert [e["index"] for e in policy["allowed"]] == list(ALLOWED)
    assert [e["index"] for e in policy["forbidden"]] == [0, 1]
    assert policy["device_order"] == "PCI_BUS_ID"
    assert policy["hostname"] == HOST
    assert policy["host_gpu_count"] == 10
    assert policy["allowed"][0] == INVENTORY[2]
    with pytest.raises(GpuPolicyError, match="not in the host inventory"):
        gpu_policy.freeze([2, 11], INVENTORY, HOST)
    with pytest.raises(GpuPolicyError, match="distinct"):
        gpu_policy.freeze([], INVENTORY, HOST)


def test_freeze_refuses_hosts_where_index_order_is_not_pci_order():
    swapped = [dict(row) for row in INVENTORY]
    swapped[0]["pci_bus_id"], swapped[1]["pci_bus_id"] = (
        swapped[1]["pci_bus_id"],
        swapped[0]["pci_bus_id"],
    )
    with pytest.raises(GpuPolicyError, match="PCI bus order"):
        gpu_policy.freeze([2], swapped, HOST)


def test_policy_sha_is_canonical_and_sensitive():
    first, second = make_policy(), make_policy()
    second["allowed"] = list(reversed(second["allowed"]))
    assert gpu_policy.policy_sha256(first) == gpu_policy.policy_sha256(make_policy())
    assert gpu_policy.policy_sha256(first) != gpu_policy.policy_sha256(second)


@pytest.mark.parametrize("gpu", [0, 1, 10, "2", 2.0, True])
def test_require_allowed_rejects_forbidden_or_untyped_indices(gpu):
    with pytest.raises(GpuPolicyError):
        gpu_policy.require_allowed(make_policy(), gpu)


def test_require_allowed_returns_frozen_entry():
    assert gpu_policy.require_allowed(make_policy(), 2)["uuid"] == uuid_of(2)


def test_load_refuses_campaigns_without_policy(tmp_path):
    with pytest.raises(GpuPolicyError, match="no frozen gpu_policy"):
        gpu_policy.load({"code_sha": "x"})
    with pytest.raises(GpuPolicyError, match="no frozen gpu_policy"):
        gpu_policy.load({"gpu_policy": {"allowed": []}})
    path = tmp_path / "campaign.json"
    path.write_text("{}")
    with pytest.raises(GpuPolicyError):
        gpu_policy.load(path)
    with pytest.raises(GpuPolicyError, match="Cannot read"):
        gpu_policy.load(tmp_path / "missing.json")
    path.write_text(gpu_policy.json.dumps(make_campaign()))
    assert gpu_policy.load(path) == make_policy()


@pytest.mark.parametrize(
    "visible,order",
    [
        (None, "PCI_BUS_ID"),
        ("0", "PCI_BUS_ID"),
        ("2,3", "PCI_BUS_ID"),
        ("3", "PCI_BUS_ID"),
        ("", "PCI_BUS_ID"),
        ("2", None),
        ("2", "FASTEST_FIRST"),
    ],
)
def test_assert_env_requires_exactly_the_assigned_gpu_in_pci_order(visible, order):
    env = {}
    if visible is not None:
        env["CUDA_VISIBLE_DEVICES"] = visible
    if order is not None:
        env["CUDA_DEVICE_ORDER"] = order
    with pytest.raises(GpuPolicyError):
        gpu_policy.assert_env(make_policy(), 2, env)


def test_assert_env_accepts_pinned_environment_and_rejects_forbidden_gpu():
    assert gpu_policy.assert_env(make_policy(), 2, pinned_env(2))["uuid"] == uuid_of(2)
    with pytest.raises(GpuPolicyError, match="not in the campaign allowlist"):
        gpu_policy.assert_env(make_policy(), 0, pinned_env(0))
    env = {**pinned_env(2), gpu_policy.ASSIGNED_ENV: "3"}
    with pytest.raises(GpuPolicyError, match="disagrees"):
        gpu_policy.assert_env(make_policy(), 2, env)


@pytest.mark.parametrize("index", [0, 2])
@pytest.mark.parametrize("field", ["uuid", "pci_bus_id"])
def test_verify_inventory_detects_card_changes_on_any_index(index, field):
    live = [dict(row) for row in INVENTORY]
    live[index][field] = "changed"
    with pytest.raises(GpuPolicyError, match=f"GPU {index}"):
        gpu_policy.verify_inventory(make_policy(), live, HOST)


def test_verify_inventory_detects_wrong_host_or_count():
    gpu_policy.verify_inventory(make_policy(), INVENTORY, HOST)
    with pytest.raises(GpuPolicyError, match="frozen on"):
        gpu_policy.verify_inventory(make_policy(), INVENTORY, "other")
    with pytest.raises(GpuPolicyError, match="now has 9"):
        gpu_policy.verify_inventory(make_policy(), INVENTORY[:9], HOST)


def test_child_env_pins_exactly_one_allowed_gpu(tmp_path):
    base = {"CUDA_VISIBLE_DEVICES": "0,1,2", "PATH": "/bin"}
    env = gpu_policy.child_env(base, make_policy(), 2, tmp_path / "campaign.json")
    assert env["CUDA_VISIBLE_DEVICES"] == "2"
    assert env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"
    assert env[gpu_policy.POLICY_ENV] == str(tmp_path / "campaign.json")
    assert env[gpu_policy.ASSIGNED_ENV] == "2"
    assert env["PATH"] == "/bin"
    assert base["CUDA_VISIBLE_DEVICES"] == "0,1,2"
    with pytest.raises(GpuPolicyError):
        gpu_policy.child_env(base, make_policy(), 1, tmp_path / "campaign.json")
    with pytest.raises(GpuPolicyError, match=r"campaign\.json"):
        gpu_policy.child_env(base, make_policy(), 2, tmp_path / "plan.json")


def test_shell_prefixes():
    assert gpu_policy.shell_prefix(make_policy(), 5) == [
        "env",
        "CUDA_DEVICE_ORDER=PCI_BUS_ID",
        "CUDA_VISIBLE_DEVICES=5",
    ]
    with pytest.raises(GpuPolicyError):
        gpu_policy.shell_prefix(make_policy(), 1)
    assert gpu_policy.no_gpu_prefix() == ["env", "CUDA_VISIBLE_DEVICES="]


def test_normalize_uuid_handles_prefix_and_case():
    assert gpu_policy.normalize_uuid("GPU-ABC-1") == gpu_policy.normalize_uuid("abc-1")
    assert gpu_policy.normalize_uuid("MIG-x") == "x"


def test_enforce_from_env_is_a_no_op_without_a_policy(monkeypatch):
    monkeypatch.setattr(gpu_policy, "inventory", lambda: pytest.fail("must not query"))
    assert gpu_policy.enforce_from_env(init_cuda=True, environ={}) is None


def _campaign_file(tmp_path):
    path = tmp_path / "campaign.json"
    path.write_text(gpu_policy.json.dumps(make_campaign()))
    return path


def test_enforce_from_env_fails_closed_on_mismatch(tmp_path, monkeypatch):
    patch_live(monkeypatch)
    path = _campaign_file(tmp_path)
    with pytest.raises(GpuPolicyError, match="must name the assigned"):
        gpu_policy.enforce_from_env(init_cuda=False, environ={gpu_policy.POLICY_ENV: str(path)})
    with pytest.raises(GpuPolicyError, match="not in the campaign allowlist"):
        gpu_policy.enforce_from_env(init_cuda=False, environ=pinned_env(1, path))
    env = {**pinned_env(2, path), "CUDA_VISIBLE_DEVICES": "3"}
    with pytest.raises(GpuPolicyError, match="CUDA_VISIBLE_DEVICES"):
        gpu_policy.enforce_from_env(init_cuda=False, environ=env)
    evidence = gpu_policy.enforce_from_env(init_cuda=False, environ=pinned_env(2, path))
    assert evidence == {"index": 2, "uuid": uuid_of(2), "verified_by": "nvidia-smi"}
    monkeypatch.setattr(gpu_policy, "inventory", lambda: INVENTORY[:9])
    with pytest.raises(GpuPolicyError, match="now has 9"):
        gpu_policy.enforce_from_env(init_cuda=False, environ=pinned_env(2, path))


def test_enforce_from_env_uses_nvml_cross_check_without_a_context(tmp_path, monkeypatch):
    patch_live(monkeypatch)
    path = _campaign_file(tmp_path)
    monkeypatch.setattr(gpu_policy, "nvml_uuids", lambda: [row["uuid"] for row in INVENTORY])
    evidence = gpu_policy.enforce_from_env(init_cuda=False, environ=pinned_env(2, path))
    assert evidence["verified_by"] == "nvml"
    wrong = [row["uuid"] for row in INVENTORY]
    wrong[2] = uuid_of(0)
    monkeypatch.setattr(gpu_policy, "nvml_uuids", lambda: wrong)
    with pytest.raises(GpuPolicyError, match="NVML reports"):
        gpu_policy.enforce_from_env(init_cuda=False, environ=pinned_env(2, path))


def _fake_torch(monkeypatch, count, uuid, available=True):
    properties = types.SimpleNamespace(uuid=uuid, name="Fake")
    cuda = types.SimpleNamespace(
        is_available=lambda: available,
        device_count=lambda: count,
        get_device_properties=lambda index: properties,
    )
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(cuda=cuda))


@pytest.mark.parametrize(
    "count,uuid,match",
    [
        (2, uuid_of(2), "Exactly one GPU"),
        (1, uuid_of(0), "torch is on GPU"),
        (1, None, "cannot report"),
    ],
)
def test_enforce_from_env_with_cuda_requires_one_matching_device(
    tmp_path, monkeypatch, count, uuid, match
):
    patch_live(monkeypatch)
    _fake_torch(monkeypatch, count, uuid)
    with pytest.raises(GpuPolicyError, match=match):
        gpu_policy.enforce_from_env(init_cuda=True, environ=pinned_env(2, _campaign_file(tmp_path)))


def test_enforce_from_env_with_cuda_accepts_prefix_free_uuid(tmp_path, monkeypatch):
    patch_live(monkeypatch)
    _fake_torch(monkeypatch, 1, uuid_of(2).removeprefix("GPU-").upper())
    evidence = gpu_policy.enforce_from_env(
        init_cuda=True, environ=pinned_env(2, _campaign_file(tmp_path))
    )
    assert evidence["verified_by"] == "torch"
    _fake_torch(monkeypatch, 1, uuid_of(2), available=False)
    with pytest.raises(GpuPolicyError, match="CUDA is not available"):
        gpu_policy.enforce_from_env(init_cuda=True, environ=pinned_env(2, _campaign_file(tmp_path)))


def test_assert_pid_on_uuid_covers_descendants(monkeypatch):
    monkeypatch.setattr(gpu_policy, "descendant_pids", lambda pid: {pid, 101, 102})
    monkeypatch.setattr(gpu_policy, "compute_apps", lambda: [(999, uuid_of(0))])
    gpu_policy.assert_pid_on_uuid(100, uuid_of(2))
    monkeypatch.setattr(gpu_policy, "compute_apps", lambda: [(102, uuid_of(2))])
    gpu_policy.assert_pid_on_uuid(100, uuid_of(2))
    monkeypatch.setattr(gpu_policy, "compute_apps", lambda: [(102, uuid_of(2)), (101, uuid_of(0))])
    with pytest.raises(GpuPolicyError, match=f"Process 101 .* {uuid_of(0)}"):
        gpu_policy.assert_pid_on_uuid(100, uuid_of(2))


def test_descendant_pids_and_inventory_parse_real_process_tables(monkeypatch):
    table = "1 0\n10 1\n11 10\n12 11\n20 1\n"
    monkeypatch.setattr(gpu_policy.subprocess, "check_output", lambda *a, **k: table)
    assert gpu_policy.descendant_pids(10) == {10, 11, 12}
    rows = "0, GPU-a, 00000000:07:00.0\n1, GPU-b, 00000000:08:00.0\n"
    monkeypatch.setattr(gpu_policy.subprocess, "check_output", lambda *a, **k: rows)
    assert gpu_policy.inventory()[1] == {
        "index": 1,
        "uuid": "GPU-b",
        "pci_bus_id": "00000000:08:00.0",
    }
    monkeypatch.setattr(gpu_policy.subprocess, "check_output", lambda *a, **k: "garbage\n")
    with pytest.raises(GpuPolicyError):
        gpu_policy.inventory()
    monkeypatch.setattr(gpu_policy.subprocess, "check_output", lambda *a, **k: "12, GPU-a\n")
    assert gpu_policy.compute_apps() == [(12, "GPU-a")]


def test_inventory_retries_transient_nvidia_smi_failures_then_fails_closed(monkeypatch):
    calls, naps = [], []
    rows = "0, GPU-a, 00000000:07:00.0\n"

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) < 3:
            raise subprocess.TimeoutExpired("nvidia-smi", 20)
        return rows

    monkeypatch.setattr(gpu_policy.subprocess, "check_output", flaky)
    monkeypatch.setattr(gpu_policy.time, "sleep", naps.append)
    assert gpu_policy.inventory()[0]["uuid"] == "GPU-a"
    assert len(calls) == 3 and len(naps) == 2

    def broken(*a, **k):
        raise OSError("no nvidia-smi")

    monkeypatch.setattr(gpu_policy.subprocess, "check_output", broken)
    with pytest.raises(gpu_policy.GpuInspectionError, match="after 3 attempt"):
        gpu_policy.inventory()
    assert issubclass(gpu_policy.GpuInspectionError, GpuPolicyError)
    # A tool outage is an inspection error, distinguishable from an observed violation.
    with pytest.raises(gpu_policy.GpuInspectionError, match="compute processes"):
        gpu_policy.compute_apps()
    with pytest.raises(gpu_policy.GpuInspectionError, match="list processes"):
        gpu_policy.descendant_pids(1)
    with pytest.raises(gpu_policy.GpuInspectionError):
        gpu_policy.assert_pid_on_uuid(1, uuid_of(2))


def test_no_rtis_script_chooses_gpus_outside_the_policy():
    """No default GPU list, and visibility is only ever set through gpu_policy."""
    default_list = re.compile(r"[\"'](\d+,){2,}\d+[\"']")
    assignment = re.compile(r"CUDA_VISIBLE_DEVICES\s*[=:]\s*(?!\s*[\"']?\s*[\"'])")
    offenders = []
    for path in sorted(REPO.glob("scripts/*rtis*.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if default_list.search(line) and "gpus" in line.lower():
                offenders.append(f"{path.name}:{number}: default GPU list")
            if "CUDA_VISIBLE_DEVICES" in line and assignment.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, offenders
    source = (REPO / "scripts/run_rtis_campaign.py").read_text()
    assert 'add_argument("--gpus", default="' not in source


def test_forbidden_set_defaults_to_gpus_zero_and_one_and_can_only_grow():
    assert gpu_policy.forbidden_gpus({}) == frozenset({0, 1})
    assert gpu_policy.forbidden_gpus({gpu_policy.FORBIDDEN_ENV: "7"}) == frozenset({0, 1, 7})
    # Listing a subset never re-allows a default member.
    assert gpu_policy.forbidden_gpus({gpu_policy.FORBIDDEN_ENV: "1"}) == frozenset({0, 1})
    with pytest.raises(GpuPolicyError):
        gpu_policy.forbidden_gpus({gpu_policy.FORBIDDEN_ENV: "none"})


@pytest.mark.parametrize("gpus", [["0"], ["1"], [2, 1], ["9"]])
def test_refuse_forbidden_fails_closed(gpus):
    with pytest.raises(GpuPolicyError, match="forbidden"):
        gpu_policy.refuse_forbidden(gpus, {gpu_policy.FORBIDDEN_ENV: "9"})


@pytest.mark.parametrize("gpus", [["GPU-0000"], [""], [True], ["cpu"]])
def test_refuse_forbidden_requires_physical_indices(gpus):
    with pytest.raises(GpuPolicyError, match="physical numeric"):
        gpu_policy.refuse_forbidden(gpus, {})


def test_refuse_forbidden_allows_other_gpus():
    gpu_policy.refuse_forbidden(["2", 3, "9"], {})
    gpu_policy.refuse_forbidden([], {})
