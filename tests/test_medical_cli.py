"""CLI contract tests for optional medical workflows."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from segmentary.medical.cli import _config, main
from segmentary.medical.runtime import doctor, write_report


def test_help_does_not_load_training_backend() -> None:
    code = (
        "import sys; from segmentary.medical.cli import _parser; _parser().format_help(); "
        "assert 'nnunetv2' not in sys.modules; assert 'torch' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_doctor_without_nvidia_smi_is_valid_cpu_inspection(monkeypatch) -> None:
    monkeypatch.setattr("segmentary.medical.runtime.shutil.which", lambda _: None)
    result = doctor()
    assert result["gpu"]["available"] is False
    assert result["missing_packages"] == []
    assert result["passed"] is True
    assert doctor(require_training=True)["passed"] is False


def test_final_test_gate_precedes_metric_evaluation(tmp_path, capsys) -> None:
    code = main(
        [
            "evaluate",
            "--manifest",
            str(tmp_path / "missing.json"),
            "--splits",
            str(tmp_path / "missing-split.json"),
            "--predictions",
            str(tmp_path),
            "--output",
            str(tmp_path / "out"),
            "--partition",
            "test",
        ]
    )
    assert code == 1
    assert "--final-test" in capsys.readouterr().err


def test_config_rejects_unknown_keys_and_resolves_relative_workspace(tmp_path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("workspace: runs/baseline\nunknown_recipe: true\n")
    with pytest.raises(ValueError, match="Unknown medical"):
        _config(config)
    config.write_text("workspace: runs/baseline\n")
    resolved = _config(config)
    assert Path(resolved.workspace) == tmp_path / "runs/baseline"


def test_report_preserves_undefined_metrics_and_refuses_overwrite(tmp_path) -> None:
    source = tmp_path / "evaluation.json"
    source.write_text(json.dumps({"schema_version": 1, "coverage": 2, "hd95_mm": None}))
    output = tmp_path / "report.md"
    write_report(str(source), str(output))
    assert '"hd95_mm": null' in output.read_text()
    assert "PDAC" in output.read_text()
    with pytest.raises(FileExistsError):
        write_report(str(source), str(output))


def test_doctor_reports_missing_external_backend_without_claiming_readiness(tmp_path) -> None:
    result = doctor(backend_python=str(tmp_path / "missing-python"))
    assert result["backend"]["passed"] is False
    assert result["passed"] is False
    assert result["missing_packages"] == []
