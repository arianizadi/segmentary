"""Static and dry-run checks of the Paul-fork recipes and patch series (no GPU, no HDRFS).

The recipes run in ``--dry-run`` mode against a fake run root: they must refuse GPUs 0/1,
write a complete provenance.json, and print the fork_gpu_run.py command instead of running
it. The helper modules that the patches add to the forks are extracted from the patch
files themselves and unit-tested here.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


SHARED = ROOT / "scripts/paul_forks/hyperparameters"


def paul_shared(name):
    """Key settings from the hyperparameter files Paul shared on 2026-09-23."""
    text = (SHARED / name).read_text()
    if name.endswith(".yml"):
        pairs = re.findall(r"^\s*([a-z_]+):\s*(.+?),?\s*$", text, re.M)
        values = {k: v.strip("'\"[]") for k, v in pairs}
    else:
        values = dict(re.findall(r"--([a-z_]+) +([^\s\\]+)", text))
    return values


def test_paul_shared_hyperparameter_copy_is_intact():
    for line in (SHARED / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        assert hashlib.sha256((SHARED / name).read_bytes()).hexdigest() == digest, name


FORKS = ROOT / "scripts" / "paul_forks"
RECIPES = FORKS / "recipes"
PATCHES = FORKS / "patches"
LAUNCHER = FORKS / "fork_gpu_run.py"
SCRIPTS = ["hrnet-rs19-ours.sh", "sfnet-rs19-ours.sh", "paper-hrnet.sh", "paper-sfnet.sh"]
ARMS = ["paul", "fixed-grouped"]
SERIES = {
    "hrnet": [
        "P0-september-baseline",
        "P1-env-paths",
        "P2-shape-matched-init",
        "P3-best-mud-checkpoint",
        "P4-dump-preds",
        "P5-throughput",
        "P6-resume-rng-scaler",
    ],
    "sfnet": [
        "P0-september-baseline",
        "P1-env-paths",
        "P1b-rs19-loader-wiring",
        "P2-shape-matched-init",
        "P3-best-mud-checkpoint",
        "P4-dump-preds",
        "P5-throughput",
    ],
}
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PROV = load_module("paul_write_provenance", RECIPES / "write_provenance.py")
TREE = load_module("paul_tree_digest", PATCHES / "tree_digest.py")


# --------------------------------------------------------------------------- static checks


@pytest.mark.parametrize("script", [*SCRIPTS, "_common.sh"])
def test_recipes_parse(script):
    subprocess.run([BASH, "-n", str(RECIPES / script)], check=True)


def test_apply_patches_parses_and_lists_existing_series():
    script = PATCHES / "apply_patches.sh"
    subprocess.run([BASH, "-n", str(script)], check=True)
    text = script.read_text()
    for fork, names in SERIES.items():
        listed = re.search(rf"{fork}\)\n.*?series=\((.*?)\)", text, re.S)
        assert listed, fork
        assert listed.group(1).split() == names
        on_disk = sorted(p.stem for p in (PATCHES / fork).glob("*.patch"))
        assert on_disk == sorted(names)


def test_patches_are_ordered_one_concern_and_documented():
    doc = (PATCHES / "PATCHES.md").read_text()
    for fork, names in SERIES.items():
        for name in names:
            patch = PATCHES / fork / f"{name}.patch"
            assert patch.read_text().startswith("diff --git"), patch
            assert f"{fork}/{name}.patch" in doc
            assert sha256(patch) in doc, f"PATCHES.md lacks the sha256 of {fork}/{name}"


def test_allowed_labels_are_exactly_the_planned_set():
    expected = {"hrnet-rs19-ours", "sfnet-rs19-ours"} | {
        f"{base}__arm-{arm}{suffix}"
        for base, suffixes in (
            ("paper-hrnet__rs19-paul", ("", "__recipe-train_2", "__recipe-train_1")),
            ("paper-hrnet__rs19-ours", ("", "__recipe-train_2", "__recipe-train_1")),
            ("paper-hrnet__mapcity-direct", ("",)),
            ("paper-sfnet__rs19-ours", ("", "__recipe-train_2")),
            ("paper-sfnet__rs19-paul", ("", "__recipe-train_2")),
            ("paper-sfnet__mapcity-direct", ("",)),
        )
        for suffix in suffixes
        for arm in ARMS
    }
    assert set(PROV.ALLOWED_LABELS) == expected
    # The labels of the runs already going on HDRFS (default recipe) are unchanged.
    assert "paper-hrnet__rs19-paul__arm-fixed-grouped" in PROV.ALLOWED_LABELS
    assert PROV.split_label("paper-hrnet__rs19-paul__arm-paul") == (
        "paper-hrnet__rs19-paul",
        "paul",
        "paul-shared-20260923",
    )
    assert PROV.split_label("paper-hrnet__rs19-paul__arm-paul__recipe-train_2")[2] == "train_2"
    for bad in (
        "paper-hrnet__rs19-paul__arm-paul__recipe-paul-shared-20260923",
        "paper-hrnet__rs19-paul__recipe-train_2__arm-paul",
        "paper-hrnet__mapcity-direct__arm-paul__recipe-train_2",
    ):
        assert bad not in PROV.ALLOWED_LABELS
    assert "paul-reference__rr22-0.8964" in PROV.REFERENCE_LABELS
    assert not set(PROV.REFERENCE_LABELS) & set(PROV.ALLOWED_LABELS)
    assert set(PROV.OWNERS) == {"paul", "nvidia", "ours", "public-sfnet-authors"}


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_training_command_uses_ddp_apex(script):
    text = (RECIPES / script).read_text()
    assert "set -euo pipefail" in text
    assert "--apex" in text
    assert "pf_launch" in text


# --------------------------------------------------------------------------- fake run root


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def fake_root(tmp_path):
    run_root = tmp_path / "run-root"
    for fork, commit_file in (("hrnet", "train.py"), ("sfnet", "train.py")):
        src = run_root / "src" / fork
        src.mkdir(parents=True)
        (src / commit_file).write_text("# fork\n")
        _git(src, "init", "-q")
        _git(src, "add", "-A")
        _git(src, "commit", "-qm", "upstream")
        _git(src, "remote", "add", "origin", f"https://github.com/pauls3/{fork}.git")
        lines = [
            f"{sha256(PATCHES / fork / f'{name}.patch')}  {fork}/{name}.patch"
            for name in SERIES[fork]
        ]
        (src / "PAUL_PATCHES_APPLIED").write_text("\n".join(lines) + "\n")
        TREE.main([str(src), "--write"])
    ckpt = run_root / "checkpoints"
    for rel in (
        "hrnet/cityscapes_trainval_ocr.HRNet_Mscale_nimble-chihuahua.pth",
        "hrnet/rs19_cityscapes_ep98_miou_0.7385.pth",
        "hrnet/hrnet_w48_timm_imagenet.pth",
        "sfnet/pretrained_cityscapes_mapillary_rs18_miou-0.799.pth",
        "sfnet/resnet18-deep-inplane128.pth",
    ):
        (ckpt / rel).parent.mkdir(parents=True, exist_ok=True)
        (ckpt / rel).write_bytes(rel.encode())
    for arm in ARMS:
        arm_root = tmp_path / "datasets" / f"rad_9_24_2026-{arm}"
        (arm_root / "audit").mkdir(parents=True)
        (arm_root / "splits.json").write_text(json.dumps({"train": [arm]}))
        (arm_root / "classes.json").write_text(json.dumps({"classes": []}))
        (arm_root / "audit" / "samples.json").write_text("[]")
        adapter = run_root / "adapters" / arm
        (adapter / "trainVal_images").mkdir(parents=True)
        (adapter / "classes.json").write_text(json.dumps({"labels": [{"name": "x"}]}))
        manifest = {
            "arm_name": arm_root.name,
            "arm_root": str(arm_root),
            "splits_sha256": sha256(arm_root / "splits.json"),
            "classes_sha256": sha256(arm_root / "classes.json"),
            "samples_sha256": sha256(arm_root / "audit" / "samples.json"),
        }
        (adapter / "manifest.json").write_text(json.dumps(manifest))
    paul_sf = tmp_path / "railsem19_sfnet_resnet18_mean-iu_0.75268.pth"
    paul_sf.write_bytes(b"paul")
    rs19 = tmp_path / "rs19"
    for sub in ("train_images", "trainVal_images", "val_images", "test_images"):
        (rs19 / sub).mkdir(parents=True)
    (rs19 / "rs19-config.json").write_text("{}")
    (rs19 / "manifest.json").write_text("{}")
    pins = tmp_path / "pins.json"
    pinned = {
        ("nvidia", "map_city"): "hrnet/cityscapes_trainval_ocr.HRNet_Mscale_nimble-chihuahua.pth",
        ("paul", "rs19", "hrnet"): "hrnet/rs19_cityscapes_ep98_miou_0.7385.pth",
        ("public-sfnet-authors", "map_city"): (
            "sfnet/pretrained_cityscapes_mapillary_rs18_miou-0.799.pth"
        ),
    }
    rows = [{"key": list(k), "sha256": sha256(ckpt / v)} for k, v in pinned.items()]
    pins.write_text(json.dumps(rows))
    # A test-only pin for Paul's SFNet RS19 file, so the reserved label's dry run is covered.
    pins_with_sfnet = tmp_path / "pins-with-sfnet-rs19.json"
    pins_with_sfnet.write_text(
        json.dumps([*rows, {"key": ["paul", "rs19", "sfnet"], "sha256": sha256(paul_sf)}])
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CUDA_", "PAUL_", "PROBE_", "NVIDIA_VISIBLE"))
    }
    env.update(
        PAUL_FORK_RUN_ROOT=str(run_root),
        PAUL_FORK_RS19_ROOT=str(rs19),
        PAUL_FORK_PYTHON="/nonexistent/fork-env/bin/python",
        PAUL_FORK_TOOL_PYTHON=sys.executable,
        FORK_GPU_RUN=str(LAUNCHER),
        PAUL_FORK_PATCHES=str(PATCHES),
        PAUL_FORK_PINS_FILE=str(pins_with_sfnet),
    )
    return {"root": run_root, "env": env, "tmp": tmp_path, "pins": pins, "paul_sf": paul_sf}


def run_recipe(fake, script, *args, extra_env=None):
    env = dict(fake["env"], **(extra_env or {}))
    return subprocess.run(
        [BASH, str(RECIPES / script), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def fake_rs19_run(fake, label, name="rs19-run"):
    run = fake["tmp"] / name
    (run / "train").mkdir(parents=True)
    (run / "provenance.json").write_text(
        json.dumps({"label": label, "dry_run": False, "probe_epochs": None})
    )
    (run / "gpu-assignment.json").write_text(json.dumps({"status": "exited", "exit_code": 0}))
    ckpt = run / "train" / "best_checkpoint_ep98.pth"
    ckpt.write_bytes(b"ours")
    return ckpt


def invocations(fake):
    """``(label, script, args, env)`` for every label ``write_provenance.py`` can write."""
    hrnet_ours = fake_rs19_run(fake, "hrnet-rs19-ours", "hrnet-rs19")
    sfnet_ours = fake_rs19_run(fake, "sfnet-rs19-ours", "sfnet-rs19")
    paul_sf = fake["paul_sf"]
    yield "hrnet-rs19-ours", "hrnet-rs19-ours.sh", ["--gpus", "2,3,4,5"], {}
    yield "sfnet-rs19-ours", "sfnet-rs19-ours.sh", ["--gpus", "6,7,8,9"], {}
    hrnet = {
        "rs19-paul": ["--rs19", "paul"],
        "rs19-ours": ["--rs19", "ours", "--rs19-ckpt", str(hrnet_ours)],
    }
    sfnet = {
        "rs19-ours": ["--rs19", "ours", "--rs19-ckpt", str(sfnet_ours)],
        "rs19-paul": ["--rs19", "paul", "--rs19-ckpt", str(paul_sf)],
    }
    for arm in ARMS:
        for chain, args in hrnet.items():
            for recipe in ("", "train_2", "train_1"):
                yield (
                    f"paper-hrnet__{chain}__arm-{arm}" + (f"__recipe-{recipe}" if recipe else ""),
                    "paper-hrnet.sh",
                    [
                        *args,
                        "--arm",
                        arm,
                        "--gpus",
                        "2,3,4,5" if chain == "rs19-paul" else "6,7,8,9",
                    ],
                    {"HRNET_RAD_RECIPE": recipe} if recipe else {},
                )
        for chain, args in sfnet.items():
            for recipe in ("", "train_2"):
                yield (
                    f"paper-sfnet__{chain}__arm-{arm}" + (f"__recipe-{recipe}" if recipe else ""),
                    "paper-sfnet.sh",
                    [*args, "--arm", arm, "--gpus", "2,3" if chain == "rs19-ours" else "4,5,6,7"],
                    {"SFNET_RAD_RECIPE": recipe} if recipe else {},
                )
        yield (
            f"paper-hrnet__mapcity-direct__arm-{arm}",
            "paper-hrnet.sh",
            ["--rs19", "none", "--arm", arm, "--gpus", "6,7,8,9"],
            {},
        )
        yield (
            f"paper-sfnet__mapcity-direct__arm-{arm}",
            "paper-sfnet.sh",
            ["--rs19", "none", "--arm", arm, "--gpus", "8,9"],
            {},
        )


EXPECTED_OWNERS = {
    "hrnet-rs19-ours": {"map_city": "nvidia", "rs19": "ours"},
    "sfnet-rs19-ours": {"map_city": "public-sfnet-authors", "rs19": "ours"},
    "paper-hrnet__rs19-paul": {"map_city": "nvidia", "rs19": "paul", "rad": "ours"},
    "paper-hrnet__rs19-ours": {"map_city": "nvidia", "rs19": "ours", "rad": "ours"},
    "paper-sfnet__rs19-ours": {"map_city": "public-sfnet-authors", "rs19": "ours", "rad": "ours"},
    "paper-sfnet__rs19-paul": {"map_city": "public-sfnet-authors", "rs19": "paul", "rad": "ours"},
    "paper-hrnet__mapcity-direct": {"map_city": "nvidia", "rad": "ours"},
    "paper-sfnet__mapcity-direct": {"map_city": "public-sfnet-authors", "rad": "ours"},
}


# --------------------------------------------------------------------------- GPU refusals


@pytest.mark.parametrize("script", SCRIPTS)
@pytest.mark.parametrize("gpus", ["0,2,3,4", "2,3,4,1", "1", "0", "0,1,2,3", "2,3,4,10", "2,2,3,4"])
def test_recipes_refuse_reserved_or_bad_gpus(fake_root, script, gpus):
    args = ["--gpus", gpus, "--run-dir", str(fake_root["tmp"] / "run"), "--dry-run"]
    if script.startswith("paper-"):
        args += ["--arm", "paul", "--rs19", "paul"]
    result = run_recipe(fake_root, script, *args)
    assert result.returncode != 0
    assert "REFUSING" in result.stderr
    assert not (fake_root["tmp"] / "run" / "provenance.json").exists()


def test_recipe_refuses_inherited_cuda_visible_devices(fake_root):
    def run(value, *extra):
        return run_recipe(
            fake_root,
            "hrnet-rs19-ours.sh",
            "--gpus",
            "2,3,4,5",
            "--run-dir",
            str(fake_root["tmp"] / f"run{len(extra)}{value}"),
            *extra,
            extra_env={"CUDA_VISIBLE_DEVICES": value},
        )

    for result in (run(""), run("2", "--dry-run"), run("0,1", "--dry-run")):
        assert result.returncode != 0 and "CUDA_VISIBLE_DEVICES" in result.stderr
    # A dry run never starts the launcher, so the workflow rule CUDA_VISIBLE_DEVICES="" is ok.
    dry = run("", "--dry-run")
    assert dry.returncode == 0, dry.stderr


def test_provenance_writer_refuses_reserved_gpus_independently(tmp_path):
    with pytest.raises(SystemExit, match="REFUSING"):
        PROV.gpu_assignment("1,2", LAUNCHER)
    with pytest.raises(SystemExit, match="REFUSING"):
        PROV.gpu_assignment("0", LAUNCHER)


def test_provenance_records_gpus_in_launcher_order_and_pins_the_launcher(tmp_path):
    record = PROV.gpu_assignment("5,3", LAUNCHER)
    assert record["indices"] == [3, 5]  # the launcher sorts; rank 0 is the lowest index
    stale = tmp_path / "fork_gpu_run.py"
    stale.write_text(LAUNCHER.read_text())
    with pytest.raises(SystemExit, match="FORK_GPU_RUN may only"):
        PROV.gpu_assignment("2", stale, dry_run=False)
    assert PROV.gpu_assignment("2", stale, dry_run=True)["launcher"] == str(stale)
    assert PROV.OFFICIAL_LAUNCHER.resolve() == LAUNCHER.resolve()


# --------------------------------------------------------------------------- dry runs


def test_dry_run_provenance_for_every_label(fake_root):
    seen = set()
    for label, script, args, env in invocations(fake_root):
        run_dir = fake_root["tmp"] / "runs" / label
        result = run_recipe(
            fake_root, script, *args, "--run-dir", str(run_dir), "--dry-run", extra_env=env
        )
        assert result.returncode == 0, (label, result.stderr)
        assert "DRY-RUN command:" in result.stdout
        tokens = shlex.split(result.stdout.split("DRY-RUN command:")[1])
        gpus = args[args.index("--gpus") + 1]
        assert tokens[1] == str(LAUNCHER)
        assert tokens[2:6] == ["--gpus", gpus, "--run-dir", str(run_dir)]
        separator = tokens.index("--")
        assert tokens[separator + 2 : separator + 4] == ["-m", "torch.distributed.run"]
        assert "--apex" in tokens[separator:]
        assert (run_dir / "centroids").is_dir()
        assert not any((run_dir / "centroids").iterdir())

        prov = json.loads((run_dir / "provenance.json").read_text())
        assert prov["label"] == label and label in PROV.ALLOWED_LABELS
        assert prov["dry_run"] is True
        base, label_arm, recipe = PROV.split_label(label)
        if label_arm is not None:
            assert prov["extra"]["recipe_variant"] == recipe
        owners = prov["owner_of_each_checkpoint_in_chain"]
        assert owners == EXPECTED_OWNERS[base]
        assert set(prov["checkpoints"]) == set(owners)
        this_run = "rad" if "__arm-" in label else "rs19"
        for stage, entry in prov["checkpoints"].items():
            if stage == this_run:
                assert entry["path"] is None and entry["role"] == "this-run"
            else:
                assert entry["sha256"] == sha256(Path(entry["resolved_path"]))
        assert prov["build_time_weights"]
        fork = prov["fork"]["name"]
        assert re.fullmatch(r"[0-9a-f]{40}", prov["fork"]["git_commit"])
        assert [p["path"] for p in prov["fork"]["patches"]] == [
            f"{fork}/{n}.patch" for n in SERIES[fork]
        ]
        assert "--apex" in prov["recipe_args"] and "--dataset" in prov["recipe_args"]
        assert "torch.distributed.run" in prov["command"]
        assert f"--nproc_per_node={len(gpus.split(','))}" in prov["command"]
        assert prov["deviations"]
        assert any(d.startswith("P0 seeds random") for d in prov["deviations"])
        rmi = any("loss/rmi.py" in d for d in prov["deviations"])
        assert rmi == (fork == "hrnet")
        assert re.fullmatch(r"[0-9a-f]{64}", prov["fork"]["tree_digest"])
        indices = [int(x) for x in gpus.split(",")]
        assert prov["gpu_assignment"]["indices"] == indices
        assert all(u.startswith("GPU-") for u in prov["gpu_assignment"]["uuids"])
        assert not {0, 1} & set(prov["gpu_assignment"]["indices"])
        if label_arm is not None:
            assert prov["arm"] == label_arm
            assert prov["environment"]["PAUL_ADAPTER_ROOT"].endswith(f"/adapters/{label_arm}")
        assert prov["environment"]["PAUL_CENTROID_ROOT"] == str(run_dir / "centroids")
        seen.add(label)
    assert seen == set(PROV.ALLOWED_LABELS)


def recipe_args(prov):
    return prov["recipe_args"]


def value_after(args, flag):
    return args[args.index(flag) + 1]


def test_recipe_hyperparameters_match_paul(fake_root):
    runs = {}
    for label, script, args, env in invocations(fake_root):
        if "__arm-paul" in label or "__arm-" not in label:
            run_dir = fake_root["tmp"] / "hp" / label
            result = run_recipe(
                fake_root, script, *args, "--run-dir", str(run_dir), "--dry-run", extra_env=env
            )
            assert result.returncode == 0, result.stderr
            runs[label] = recipe_args(json.loads((run_dir / "provenance.json").read_text()))
    hr = runs["hrnet-rs19-ours"]
    shared = paul_shared("hrnet/train_rs19.yml")
    assert value_after(hr, "--lr") == shared["lr"] == "1e-4"
    assert value_after(hr, "--max_epoch") == shared["max_epoch"] == "150"
    assert value_after(hr, "--supervised_mscale_loss_wt") == shared["supervised_mscale_loss_wt"]
    assert value_after(hr, "--n_scales") == shared["n_scales"]
    assert value_after(hr, "--dataset") == "railsem19"
    assert value_after(hr, "--snapshot").endswith("nimble-chihuahua.pth")
    rad = runs["paper-hrnet__rs19-paul__arm-paul"]
    shared = paul_shared("hrnet/train_rtisrail22.yml")
    assert value_after(rad, "--lr") == shared["lr"] == "7e-5"
    assert value_after(rad, "--max_epoch") == shared["max_epoch"] == "1000"
    assert value_after(rad, "--n_scales") == shared["n_scales"] == "0.5,1.0,1.5"
    assert value_after(rad, "--supervised_mscale_loss_wt") == shared["supervised_mscale_loss_wt"]
    assert value_after(rad, "--snapshot").endswith("rs19_cityscapes_ep98_miou_0.7385.pth")
    sf = runs["sfnet-rs19-ours"]
    shared = paul_shared("sfnet/train_railsem19_sfnet_res18.sh")
    assert value_after(sf, "--lr") == shared["lr"] and value_after(sf, "--max_epoch") == "400"
    assert value_after(sf, "--max_epoch") == shared["max_epoch"]
    assert value_after(sf, "--bs_mult") == "8" and "--ohem" in sf
    assert value_after(sf, "--allow_skip") == "layer0.*,layer1.0.conv1.weight,layer1.0.downsample.*"
    sfr = runs["paper-sfnet__rs19-ours__arm-paul"]
    shared = paul_shared("sfnet/train_rtisrail22_sfnet_res18.sh")
    assert value_after(sfr, "--lr") == shared["lr"] == "0.002"
    assert value_after(sfr, "--max_epoch") == shared["max_epoch"] == "1000"
    assert value_after(sfr, "--bs_mult") == "16"  # 2 GPUs x 16 = 32
    assert value_after(runs["paper-sfnet__rs19-paul__arm-paul"], "--bs_mult") == "8"
    assert "--allow_skip" not in sfr

    # Checkpoint-embedded variants, each under its own label.
    rad2 = runs["paper-hrnet__rs19-paul__arm-paul__recipe-train_2"]
    assert value_after(rad2, "--lr") == "1e-4" and value_after(rad2, "--max_epoch") == "500"
    assert value_after(rad2, "--n_scales") == "0.5,1.0,1.5"
    assert value_after(rad2, "--supervised_mscale_loss_wt") == "0.05"
    assert value_after(rad2, "--snapshot").endswith("rs19_cityscapes_ep98_miou_0.7385.pth")
    rad1 = runs["paper-hrnet__rs19-ours__arm-paul__recipe-train_1"]
    assert value_after(rad1, "--supervised_mscale_loss_wt") == "0.1"
    sfr2 = runs["paper-sfnet__rs19-ours__arm-paul__recipe-train_2"]
    assert value_after(sfr2, "--lr") == "0.001"

    # Map->City -> RAD directly: SFNet reproduces train_rs19_rtisrail22_sfnet_res18.sh flag by
    # flag (only --exp/--ckpt/--tb_path/--snapshot ours, bs_mult for 2 GPUs, + --allow_skip).
    direct = runs["paper-sfnet__mapcity-direct__arm-paul"]
    shared = paul_shared("sfnet/train_rs19_rtisrail22_sfnet_res18.sh")
    ours_only = {"exp", "ckpt", "tb_path", "snapshot", "bs_mult"}
    for flag, value in shared.items():
        if flag not in ours_only:
            assert value_after(direct, f"--{flag}") == value, flag
    shared_text = (SHARED / "sfnet/train_rs19_rtisrail22_sfnet_res18.sh").read_text()
    switches = set(re.findall(r"--([a-z_]+) *\\$", shared_text, re.M))
    assert switches == {"syncbn", "sgd", "ohem", "gblur", "bblur", "apex"}
    for flag in switches:
        assert f"--{flag}" in direct
    assert value_after(direct, "--lr") == "0.0025" and value_after(direct, "--max_epoch") == "700"
    assert value_after(direct, "--bs_mult") == "16"  # 2 GPUs x 16 = Paul's 4 x 8
    assert value_after(direct, "--snapshot").endswith(
        "pretrained_cityscapes_mapillary_rs18_miou-0.799.pth"
    )
    assert shared["snapshot"].endswith("pretrained_cityscapes_mapillary_rs18_miou-0.799.pth")
    assert value_after(direct, "--allow_skip") == (
        "layer0.*,layer1.0.conv1.weight,layer1.0.downsample.*"
    )
    hdirect = runs["paper-hrnet__mapcity-direct__arm-paul"]
    shared = paul_shared("hrnet/train_rtisrail22.yml")
    for flag in ("lr", "max_epoch", "n_scales", "supervised_mscale_loss_wt", "poly_exp"):
        assert value_after(hdirect, f"--{flag}") == shared[flag], flag
    assert value_after(hdirect, "--snapshot").endswith("nimble-chihuahua.pth")


def test_hrnet_git_head_variant_is_selectable_and_flagged(fake_root):
    run_dir = fake_root["tmp"] / "variant"
    result = run_recipe(
        fake_root,
        "hrnet-rs19-ours.sh",
        "--gpus",
        "2,3,4,5",
        "--run-dir",
        str(run_dir),
        "--dry-run",
        extra_env={"HRNET_RS19_RECIPE": "git-head-9fbd50f"},
    )
    assert result.returncode == 0, result.stderr
    prov = json.loads((run_dir / "provenance.json").read_text())
    assert value_after(recipe_args(prov), "--lr") == "1e-4"
    assert value_after(recipe_args(prov), "--max_epoch") == "150"
    assert any("not the one that produced" in d for d in prov["deviations"])


def test_probe_needs_probe_dir_and_shortens_schedule(fake_root):
    args = ["--gpus", "2,3,4,5", "--dry-run"]
    bad = run_recipe(
        fake_root,
        "hrnet-rs19-ours.sh",
        *args,
        "--run-dir",
        str(fake_root["tmp"] / "real"),
        extra_env={"PROBE_EPOCHS": "1"},
    )
    assert bad.returncode != 0 and "probe" in bad.stderr
    run_dir = fake_root["tmp"] / "hrnet-rs19-probe1"
    good = run_recipe(
        fake_root,
        "hrnet-rs19-ours.sh",
        *args,
        "--run-dir",
        str(run_dir),
        extra_env={"PROBE_EPOCHS": "1"},
    )
    assert good.returncode == 0, good.stderr
    prov = json.loads((run_dir / "provenance.json").read_text())
    assert prov["probe_epochs"] == 1
    assert value_after(recipe_args(prov), "--max_epoch") == "1"
    assert any("TIMING PROBE" in d for d in prov["deviations"])


def test_refuses_reused_run_dir_and_unknown_arm(fake_root):
    run_dir = fake_root["tmp"] / "used"
    run_dir.mkdir()
    (run_dir / "something").write_text("x")
    used = run_recipe(
        fake_root, "hrnet-rs19-ours.sh", "--gpus", "2,3,4,5", "--run-dir", str(run_dir), "--dry-run"
    )
    assert used.returncode != 0 and "not empty" in used.stderr
    arm = run_recipe(
        fake_root,
        "paper-hrnet.sh",
        "--rs19",
        "paul",
        "--arm",
        "test",
        "--gpus",
        "2,3,4,5",
        "--run-dir",
        str(fake_root["tmp"] / "x"),
        "--dry-run",
    )
    assert arm.returncode != 0 and "--arm" in arm.stderr


def test_ours_rs19_checkpoint_must_come_from_finished_matching_run(fake_root):
    wrong = fake_rs19_run(fake_root, "sfnet-rs19-ours", "wrong-fork")
    probe_run = fake_root["tmp"] / "probe-run"
    (probe_run / "train").mkdir(parents=True)
    (probe_run / "provenance.json").write_text(
        json.dumps({"label": "hrnet-rs19-ours", "dry_run": False, "probe_epochs": 1})
    )
    (probe_run / "train" / "c.pth").write_bytes(b"x")
    running = fake_rs19_run(fake_root, "hrnet-rs19-ours", "still-running")
    (running.parent.parent / "gpu-assignment.json").write_text(json.dumps({"status": "running"}))
    for ckpt in (wrong, probe_run / "train" / "c.pth", running):
        result = run_recipe(
            fake_root,
            "paper-hrnet.sh",
            "--rs19",
            "ours",
            "--rs19-ckpt",
            str(ckpt),
            "--arm",
            "paul",
            "--gpus",
            "2,3,4,5",
            "--run-dir",
            str(fake_root["tmp"] / f"r-{ckpt.parent.parent.name}"),
            "--dry-run",
        )
        assert result.returncode != 0 and "REFUSING" in result.stderr


def test_reference_label_and_unknown_labels_are_never_written(tmp_path):
    for label in (
        "paul-reference__rr22-0.8964",
        "paul-reference__rr22-0.8964__arm-paul",
        "paper-hrnet__rs19-paul__arm-test",
        "paper-hrnet__rs19-none__arm-paul",
        "paper-hrnet__mapcity-direct__arm-paul__recipe-train_2",
        "paper-sfnet__rs19-ours__arm-paul__recipe-train_1",
        "paper-hrnet__rs19-paul__arm-paul__recipe-paul-shared-20260923",
        "x",
    ):
        with pytest.raises(SystemExit, match="REFUSING"):
            PROV.main(
                [
                    "--label",
                    label,
                    "--stage",
                    "rad",
                    "--fork",
                    "hrnet",
                    "--run-dir",
                    str(tmp_path),
                    "--src",
                    str(tmp_path),
                    "--gpus",
                    "2",
                    "--launcher",
                    str(LAUNCHER),
                    "--recipe-source",
                    "x",
                    "--recipe-script",
                    __file__,
                    "--",
                    "true",
                ]
            )


def dump(fake, script, ckpt, arm, run_dir, split="test"):
    return run_recipe(
        fake,
        script,
        "--dump",
        split,
        "--checkpoint",
        str(ckpt),
        "--arm",
        arm,
        "--gpus",
        "9",
        "--run-dir",
        str(run_dir),
        "--dry-run",
    )


def test_dump_provenance_satisfies_the_scorer_contract(fake_root, monkeypatch):
    label, script, args, _ = next(
        item for item in invocations(fake_root) if item[0] == "paper-sfnet__rs19-ours__arm-paul"
    )
    run_dir = fake_root["tmp"] / "finished"
    trained = run_recipe(fake_root, script, *args, "--run-dir", str(run_dir), "--dry-run")
    assert trained.returncode == 0, trained.stderr
    ckpt = run_dir / "ckpt" / "best_mud_epoch_7.pth"
    ckpt.parent.mkdir(parents=True)
    ckpt.write_bytes(b"w")
    refused = dump(fake_root, script, ckpt, "paul", run_dir)
    assert refused.returncode != 0 and "not a finished run" in refused.stderr
    assert not (run_dir / "dumps").exists()

    training = json.loads((run_dir / "provenance.json").read_text())
    training["dry_run"] = False  # pretend the training run happened
    (run_dir / "provenance.json").write_text(json.dumps(training))
    result = dump(fake_root, script, ckpt, "paul", run_dir)
    assert result.returncode == 0, result.stderr
    dump_dir = run_dir / "dumps" / "test-single-best_mud_epoch_7"
    prov = json.loads((dump_dir / "dump-provenance.json").read_text())
    assert prov["label"] == label and prov["stage"] == "dump"
    assert prov["checkpoints"]["rad"]["sha256"] == sha256(ckpt)
    assert prov["checkpoints"]["rs19"] == training["checkpoints"]["rs19"]
    assert prov["dump"]["training_recipe_args"] == training["recipe_args"]
    assert "--dump_preds" in recipe_args(prov)
    assert value_after(recipe_args(prov), "--dump_split") == "test"
    assert dump(fake_root, script, ckpt, "fixed-grouped", run_dir, "val").returncode != 0

    try:
        from scripts.paul_forks import score_predictions
    except ImportError as error:  # pragma: no cover - scorer owned by another workflow
        pytest.skip(f"score_predictions not importable: {error}")
    fake_pins = {
        (family, "map_city"): prov["checkpoints"]["map_city"]["sha256"]
        for family in ("paper-hrnet", "paper-sfnet")
    }
    monkeypatch.setattr(score_predictions, "PINNED", fake_pins)
    with pytest.raises(score_predictions.ScoreError, match="not a scored run"):
        score_predictions.check_provenance(prov, "paul")  # test pins override is recorded
    prov.update(dry_run=False, pins_override=None)
    assert score_predictions.check_provenance(prov, "paul") == ("paper-sfnet__rs19-ours", "paul")


def test_dropped_label_fix_arm_is_refused(fake_root):
    """The RAD 9/24 study has only the paul and fixed-grouped arms (fixed-stratified dropped)."""
    run_dir = fake_root["tmp"] / "dropped-arm"
    args = ["--rs19", "paul", "--arm", "fixed-stratified", "--gpus", "2,3,4,5"]
    result = run_recipe(fake_root, "paper-hrnet.sh", *args, "--run-dir", str(run_dir), "--dry-run")
    assert result.returncode != 0 and "--arm must be one of: paul fixed-grouped" in result.stderr
    assert not (run_dir / "provenance.json").exists()


def test_dump_of_a_recipe_variant_run_keeps_its_label(fake_root):
    run_dir = fake_root["tmp"] / "variant-run"
    args = ["--rs19", "paul", "--arm", "fixed-grouped", "--gpus", "2,3,4,5"]
    env = {"HRNET_RAD_RECIPE": "train_2"}
    trained = run_recipe(
        fake_root, "paper-hrnet.sh", *args, "--run-dir", str(run_dir), "--dry-run", extra_env=env
    )
    assert trained.returncode == 0, trained.stderr
    training = json.loads((run_dir / "provenance.json").read_text())
    training["dry_run"] = False
    (run_dir / "provenance.json").write_text(json.dumps(training))
    ckpt = run_dir / "train" / "best_mud_epoch_3.pth"
    ckpt.parent.mkdir(parents=True)
    ckpt.write_bytes(b"w")
    assert dump(fake_root, "paper-hrnet.sh", ckpt, "paul", run_dir).returncode != 0
    result = dump(fake_root, "paper-hrnet.sh", ckpt, "fixed-grouped", run_dir)
    assert result.returncode == 0, result.stderr
    prov = json.loads(
        (run_dir / "dumps" / "test-single-best_mud_epoch_3" / "dump-provenance.json").read_text()
    )
    assert prov["label"] == "paper-hrnet__rs19-paul__arm-fixed-grouped__recipe-train_2"


def test_mapcity_direct_chain_provenance(fake_root):
    for script, owner, init in (
        ("paper-hrnet.sh", "nvidia", "nimble-chihuahua.pth"),
        ("paper-sfnet.sh", "public-sfnet-authors", "rs18_miou-0.799.pth"),
    ):
        family = script.removesuffix(".sh")
        gpus = "2,3,4,5" if family == "paper-hrnet" else "2,3"
        run_dir = fake_root["tmp"] / f"{family}-direct"
        args = ["--rs19", "none", "--arm", "fixed-grouped", "--gpus", gpus]
        result = run_recipe(fake_root, script, *args, "--run-dir", str(run_dir), "--dry-run")
        assert result.returncode == 0, result.stderr
        prov = json.loads((run_dir / "provenance.json").read_text())
        assert prov["label"] == f"{family}__mapcity-direct__arm-fixed-grouped"
        assert prov["owner_of_each_checkpoint_in_chain"] == {"map_city": owner, "rad": "ours"}
        assert set(prov["checkpoints"]) == {"map_city", "rad"}
        assert prov["checkpoints"]["map_city"]["role"] == "init"
        assert prov["checkpoints"]["map_city"]["path"].endswith(init)
        assert any("chain mapcity-direct" in d for d in prov["deviations"])
        assert any("19-class Cityscapes head" in d for d in prov["deviations"])
        # --rs19-ckpt, a non-default recipe and a wrong pin are refused
        bad_dir = fake_root["tmp"] / f"{family}-direct-bad"
        variant = "HRNET_RAD_RECIPE" if family == "paper-hrnet" else "SFNET_RAD_RECIPE"
        for extra_args, env in (
            (["--rs19-ckpt", str(fake_root["paul_sf"])], {}),
            ([], {variant: "train_2"}),
            ([], {"PAUL_FORK_PINS_FILE": ""}),
        ):
            bad = run_recipe(
                fake_root,
                script,
                *args,
                *extra_args,
                "--run-dir",
                str(bad_dir),
                "--dry-run",
                extra_env=env,
            )
            assert bad.returncode != 0 and "REFUSING" in bad.stderr, (extra_args, env)
            assert not (bad_dir / "provenance.json").exists()


def test_recipe_variants_never_share_a_label_or_run_dir(fake_root):
    labels = set()
    for recipe in ("", "train_2", "train_1"):
        run_dir = fake_root["tmp"] / f"variant-{recipe or 'default'}"
        result = run_recipe(
            fake_root,
            "paper-hrnet.sh",
            "--rs19",
            "paul",
            "--arm",
            "paul",
            "--gpus",
            "2,3,4,5",
            "--run-dir",
            str(run_dir),
            "--dry-run",
            extra_env={"HRNET_RAD_RECIPE": recipe} if recipe else {},
        )
        assert result.returncode == 0, result.stderr
        prov = json.loads((run_dir / "provenance.json").read_text())
        labels.add(prov["label"])
        assert prov["extra"]["recipe_variant"] == recipe or (
            not recipe and prov["extra"]["recipe_variant"] == "paul-shared-20260923"
        )
    assert labels == {
        "paper-hrnet__rs19-paul__arm-paul",
        "paper-hrnet__rs19-paul__arm-paul__recipe-train_2",
        "paper-hrnet__rs19-paul__arm-paul__recipe-train_1",
    }


def _write_provenance_args(tmp_path, label, *extra):
    return [
        "--label",
        label,
        "--stage",
        "rad",
        "--fork",
        "hrnet",
        "--arm",
        "paul",
        "--run-dir",
        str(tmp_path),
        "--src",
        str(tmp_path),
        "--gpus",
        "2",
        "--launcher",
        str(LAUNCHER),
        "--recipe-source",
        "x",
        "--recipe-script",
        __file__,
        *extra,
        "--",
        "true",
    ]


@pytest.mark.parametrize(
    ("label", "recorded"),
    [
        ("paper-hrnet__rs19-paul__arm-paul", "train_2"),  # train_2 under the default label
        ("paper-hrnet__rs19-paul__arm-paul__recipe-train_2", "paul-shared-20260923"),
        ("paper-hrnet__rs19-paul__arm-paul__recipe-train_2", "train_1"),
        ("paper-hrnet__rs19-paul__arm-paul", None),
    ],
)
def test_label_recipe_suffix_must_match_recorded_variant(tmp_path, label, recorded):
    extra = ["--extra", f"recipe_variant={recorded}"] if recorded else []
    with pytest.raises(SystemExit, match="recipe"):
        PROV.main(_write_provenance_args(tmp_path, label, *extra))


def test_real_pins_are_enforced_at_launch(fake_root):
    env = {"PAUL_FORK_PINS_FILE": ""}
    result = run_recipe(
        fake_root,
        "paper-hrnet.sh",
        "--rs19",
        "paul",
        "--arm",
        "paul",
        "--gpus",
        "2,3,4,5",
        "--run-dir",
        str(fake_root["tmp"] / "pinned"),
        "--dry-run",
        extra_env=env,
    )
    assert result.returncode != 0 and "pinned" in result.stderr
    assert PROV.PINS[("nvidia", "map_city")].startswith("9c3779cd")
    assert PROV.PINS[("paul", "rs19", "hrnet")].startswith("873fa92c")
    assert PROV.PINS[("public-sfnet-authors", "map_city")].startswith("133f1b6a")


def test_reserved_sfnet_rs19_paul_label_is_refused_without_a_pin(fake_root):
    result = run_recipe(
        fake_root,
        "paper-sfnet.sh",
        "--rs19",
        "paul",
        "--rs19-ckpt",
        str(fake_root["paul_sf"]),
        "--arm",
        "paul",
        "--gpus",
        "2,3",
        "--run-dir",
        str(fake_root["tmp"] / "reserved"),
        "--dry-run",
        extra_env={"PAUL_FORK_PINS_FILE": str(fake_root["pins"])},  # the real pin set's keys
    )
    assert result.returncode != 0 and "no pinned sha256" in result.stderr
    assert not (fake_root["tmp"] / "reserved" / "provenance.json").exists()
    assert ("paul", "rs19", "sfnet") not in PROV.PINS


def test_hand_edited_fork_tree_is_refused(fake_root):
    (fake_root["root"] / "src" / "hrnet" / "train.py").write_text("# edited after patching\n")
    result = run_recipe(
        fake_root,
        "hrnet-rs19-ours.sh",
        "--gpus",
        "2,3,4,5",
        "--run-dir",
        str(fake_root["tmp"] / "edited"),
        "--dry-run",
    )
    assert result.returncode != 0 and "differs from the tree" in result.stderr


def test_tree_digest_covers_edits_additions_and_deletions(tmp_path):
    src = tmp_path / "clone"
    src.mkdir()
    (src / "a.py").write_text("a\n")
    (src / "b.py").write_text("b\n")
    _git(src, "init", "-q")
    _git(src, "add", "-A")
    _git(src, "commit", "-qm", "x")
    base = TREE.tree_digest(src)
    (src / "PAUL_PATCHES_APPLIED").write_text("x")
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "a.cpython-311.pyc").write_bytes(b"\0")
    assert TREE.tree_digest(src) == base  # bookkeeping and bytecode do not count
    (src / "new.py").write_text("n\n")
    added = TREE.tree_digest(src)
    assert added != base
    (src / "b.py").unlink()
    assert TREE.tree_digest(src) not in (base, added)
    (src / "b.py").write_text("b\n")
    (src / "b.py").chmod(0o755)
    assert TREE.tree_digest(src) != added


def test_adapter_must_come_from_the_requested_arm_and_be_current(fake_root):
    def attempt(name):
        return run_recipe(
            fake_root,
            "paper-hrnet.sh",
            "--rs19",
            "paul",
            "--arm",
            "paul",
            "--gpus",
            "2,3,4,5",
            "--run-dir",
            str(fake_root["tmp"] / name),
            "--dry-run",
        )

    manifest_path = fake_root["root"] / "adapters" / "paul" / "manifest.json"
    original = manifest_path.read_text()
    swapped = json.loads(original)
    swapped["arm_name"] = "rad_9_24_2026-fixed-grouped"
    manifest_path.write_text(json.dumps(swapped))
    wrong_arm = attempt("wrong-arm")
    assert wrong_arm.returncode != 0 and "arm_name" in wrong_arm.stderr
    manifest_path.write_text(original)
    splits = Path(json.loads(original)["arm_root"]) / "splits.json"
    splits.write_text(json.dumps({"train": ["re-prepared"]}))
    stale = attempt("stale-arm")
    assert stale.returncode != 0 and "rebuild the adapter" in stale.stderr
    assert not (fake_root["tmp"] / "stale-arm" / "provenance.json").exists()


# --------------------------------------------------------------------------- patch helpers


def new_file_from_patch(patch: Path, name: str) -> str:
    text = patch.read_text()
    start = text.index(f"diff --git a/{name} b/{name}\n")
    body = text[start:].split("\n@@ ", 1)[1].split("\n", 1)[1]
    lines = []
    for line in body.split("\n"):
        if line.startswith("diff --git "):
            break
        if line.startswith("+"):
            lines.append(line[1:])
        elif line.startswith("\\"):
            continue
        else:
            break
    return "\n".join(lines) + "\n"


HELPERS = {
    "paul_env.py": "P1-env-paths",
    "paul_init.py": "P2-shape-matched-init",
    "paul_best_mud.py": "P3-best-mud-checkpoint",
    "paul_dump.py": "P4-dump-preds",
}


@pytest.fixture(scope="module")
def helpers(tmp_path_factory):
    out = tmp_path_factory.mktemp("helpers")
    modules = {}
    for name, patch in HELPERS.items():
        texts = {
            fork: new_file_from_patch(PATCHES / fork / f"{patch}.patch", name) for fork in SERIES
        }
        if name != "paul_env.py":  # the env docstring names fork-specific variables
            assert texts["hrnet"] == texts["sfnet"], name
        path = out / name
        path.write_text(texts["hrnet"])
        modules[name] = load_module(f"test_{name[:-3]}", path)
    return modules


def test_shape_matched_load_allows_only_heads(helpers):
    torch = pytest.importorskip("torch")
    init = helpers["paul_init.py"]
    arch = "network.sfnet_resnet.DeepR18_SF_deeply"
    model = {
        "module.layer0.0.0.weight": torch.zeros(64, 3, 3, 3),
        "module.layer1.0.conv1.weight": torch.zeros(4, 4),
        "module.head.conv_last.1.weight": torch.zeros(21, 128, 1, 1),
        "module.head.conv_last.1.bias": torch.zeros(21),
    }
    ckpt = {
        "layer0.0.0.weight": torch.ones(64, 3, 3, 3),
        "layer1.0.conv1.weight": torch.ones(4, 4),
        "head.conv_last.1.weight": torch.ones(19, 128, 1, 1),
        "head.conv_last.1.bias": torch.ones(19),
        "extra.unused": torch.ones(1),
    }
    merged, report = init.plan_load(model, ckpt, arch)
    assert report["status"] == "ok"
    assert {s["key"] for s in report["skipped"]} == {
        "head.conv_last.1.weight",
        "head.conv_last.1.bias",
    }
    assert torch.equal(merged["module.layer0.0.0.weight"], ckpt["layer0.0.0.weight"])
    assert torch.equal(merged["module.head.conv_last.1.bias"], torch.zeros(21))
    assert report["checkpoint_tensors_unused"] == ["extra.unused"]

    bad = dict(ckpt, **{"layer0.0.0.weight": torch.ones(32, 3, 3, 3)})
    _, report = init.plan_load(model, bad, arch)
    assert report["status"] == "FAILED" and report["unexpected_skips"] == ["layer0.0.0.weight"]
    _, report = init.plan_load(model, bad, arch, ["layer0.*"])
    assert report["status"] == "ok"
    headless = {k: v for k, v in ckpt.items() if not k.startswith("head.")}
    _, report = init.plan_load(model, headless, arch)
    assert report["status"] == "FAILED"  # a head missing from the checkpoint is not allowed
    assert set(report["unexpected_skips"]) == {"head.conv_last.1.weight", "head.conv_last.1.bias"}
    _, report = init.plan_load(model, ckpt, arch, ["layer9.*"])
    assert report["status"] == "FAILED"
    assert report["allow_skip_patterns_matching_nothing"] == ["layer9.*"]
    with pytest.raises(RuntimeError, match="no classifier-head table"):
        init.plan_load(model, ckpt, "deepv3.DeepWV3Plus")
    assert init.HEAD_TENSORS["ocrnet.HRNet_Mscale"] == (
        "ocr.cls_head.weight",
        "ocr.cls_head.bias",
        "ocr.aux_head.2.weight",
        "ocr.aux_head.2.bias",
    )
    assert init.parse_allow_skip(" a.*, ,b ") == ["a.*", "b"]


def test_shape_matched_load_raises_and_reports(helpers, tmp_path):
    torch = pytest.importorskip("torch")
    init = helpers["paul_init.py"]
    net = torch.nn.Sequential()
    net.add_module("head", torch.nn.Module())
    net.head.add_module("conv_last", torch.nn.Sequential(torch.nn.ReLU(), torch.nn.Conv2d(2, 3, 1)))
    net.add_module("layer0", torch.nn.Conv2d(3, 2, 1))
    source = tmp_path / "ckpt.pth"
    source.write_bytes(b"x")
    state = {k: torch.ones_like(v) for k, v in net.state_dict().items()}
    state["layer0.weight"] = torch.ones(5, 3, 1, 1)
    coverage = tmp_path / "cov" / "init-coverage.json"
    arch = "network.sfnet_resnet.DeepR18_SF_deeply"
    with pytest.raises(RuntimeError, match="refusing partial load"):
        init.shape_matched_load(net, state, arch, str(source), str(coverage), log=lambda m: None)
    assert json.loads(coverage.read_text())["status"] == "FAILED"
    report = init.shape_matched_load(
        net,
        state,
        arch,
        str(source),
        str(coverage),
        allow_skip=["layer0.weight"],
        log=lambda m: None,
    )
    assert report["source_sha256"] == sha256(source)
    assert torch.equal(net.layer0.bias, torch.ones(2))


def test_best_mud_rule(helpers, tmp_path):
    mud = helpers["paul_best_mud.py"]
    classes = tmp_path / "classes.json"
    names = [f"c{i}" for i in range(21)]
    names[13] = "mud-pumping"
    classes.write_text(json.dumps({"labels": [{"name": n} for n in names]}))
    saved = []

    def save(path):
        saved.append(Path(path).name)
        Path(path).write_bytes(b"c")

    def iu(value):
        out = [0.5] * 21
        out[13] = value
        return out

    assert mud.update(str(tmp_path), 0, iu(math.nan), 0.4, save, str(classes)) is False
    assert mud.update(str(tmp_path), 1, iu(0.10), 0.40, save, str(classes)) is True
    assert mud.update(str(tmp_path), 2, iu(0.05), 0.90, save, str(classes)) is False
    assert mud.update(str(tmp_path), 3, iu(0.10), 0.39, save, str(classes)) is False
    assert mud.update(str(tmp_path), 4, iu(0.10), 0.41, save, str(classes)) is True
    assert saved == ["best_mud_epoch_1.pth", "best_mud_epoch_4.pth"]
    assert not (tmp_path / "best_mud_epoch_1.pth").exists()
    state = json.loads((tmp_path / "best_mud.json").read_text())
    assert state["epoch"] == 4 and state["class_id"] == 13
    names[13] = "fence"
    classes.write_text(json.dumps({"labels": [{"name": n} for n in names]}))
    with pytest.raises(RuntimeError, match="expected 'mud-pumping'"):
        mud.update(str(tmp_path), 5, iu(0.9), 0.9, save, str(classes))


def test_dump_writes_uint8_pngs_and_checks_coverage(helpers, tmp_path):
    np = pytest.importorskip("numpy")
    from PIL import Image

    dump = helpers["paul_dump.py"]
    out = tmp_path / "pred"
    dump.prepare(str(out))
    with pytest.raises(RuntimeError, match="already exists"):
        dump.prepare(str(out))
    preds = np.array([[[0, 20], [13, 1]], [[2, 2], [2, 2]]], dtype=np.int64)
    dump.write(str(out), ["g1__a", "g2__b"], preds, 21)
    with pytest.raises(RuntimeError, match="duplicate"):
        dump.write(str(out), ["g1__a"], preds[:1], 21)
    with pytest.raises(RuntimeError, match="outside"):
        dump.write(str(out), ["g3__c"], np.full((1, 2, 2), 21), 21)
    image = Image.open(out / "g1__a.png")
    assert image.mode == "L" and np.array(image).tolist() == [[0, 20], [13, 1]]
    with pytest.raises(RuntimeError, match="incomplete"):
        dump.finalize(str(out), ["g1__a", "g2__b", "g9__z"], {})
    manifest = dump.finalize(str(out), ["g2__b", "g1__a"], {"split": "val"})
    assert manifest["count"] == 2 and manifest["images"] == ["g1__a", "g2__b"]
    assert sorted(p.name for p in out.iterdir()) == ["g1__a.png", "g2__b.png"]
    assert json.loads(Path(str(out) + ".manifest.json").read_text())["split"] == "val"
    (out / "notes.txt").write_text("x")
    with pytest.raises(RuntimeError, match="non-PNG"):
        dump.finalize(str(out), ["g2__b", "g1__a"], {})


def test_env_paths_fail_closed(helpers, tmp_path, monkeypatch):
    env = helpers["paul_env.py"]
    monkeypatch.delenv("PAUL_ADAPTER_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="not set"):
        env.require_dir("PAUL_ADAPTER_ROOT")
    monkeypatch.setenv("PAUL_ADAPTER_ROOT", "relative/path")
    with pytest.raises(RuntimeError, match="absolute"):
        env.require_dir("PAUL_ADAPTER_ROOT")
    monkeypatch.setenv("PAUL_ADAPTER_ROOT", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="not an existing"):
        env.require_dir("PAUL_ADAPTER_ROOT")
    monkeypatch.setenv("PAUL_ADAPTER_ROOT", str(tmp_path))
    assert env.require_dir("PAUL_ADAPTER_ROOT") == str(tmp_path)


def test_resume_state_round_trip(tmp_path):
    torch = pytest.importorskip("torch")
    np = pytest.importorskip("numpy")
    import random

    source = new_file_from_patch(
        PATCHES / "hrnet" / "P6-resume-rng-scaler.patch", "paul_resume_state.py"
    )
    path = tmp_path / "paul_resume_state.py"
    path.write_text(source)
    state_mod = load_module("test_paul_resume_state", path)
    random.seed(1)
    np.random.seed(2)
    torch.manual_seed(3)
    saved = state_mod.gather()
    path_ckpt = tmp_path / "ck.pth"
    torch.save({"paul_rng_states": saved, "paul_grad_scaler": {"scale": 8.0}}, path_ckpt)
    expected = (random.random(), np.random.rand(), torch.rand(1).item())
    random.seed(9)
    np.random.seed(9)
    torch.manual_seed(9)
    checkpoint = torch.load(path_ckpt, weights_only=True)

    class Scaler:
        loaded = None

        def load_state_dict(self, value):
            self.loaded = value

    scaler = Scaler()
    assert state_mod.restore(checkpoint, 0, 1, scaler, log=lambda m: None) is True
    assert (random.random(), np.random.rand(), torch.rand(1).item()) == expected
    assert scaler.loaded == {"scale": 8.0}
    with pytest.raises(RuntimeError, match="ranks"):
        state_mod.restore(checkpoint, 0, 4, scaler, log=lambda m: None)
