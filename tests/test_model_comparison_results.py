"""Contracts for a clean public results starting point."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_historical_quality_result_bundle_is_tracked() -> None:
    removed = (
        ROOT / "docs/findings.md",
        ROOT / "docs/results/model-comparison/README.md",
        ROOT / "docs/results/model-comparison/results.csv",
        ROOT / "docs/results/model-comparison/status.json",
        ROOT / "docs/results/model-comparison/records/segformer_b2.json",
        ROOT / "docs/results/rail-transfer-m5/audit-summary.json",
        ROOT / "docs/results/rail-transfer-m5/results.csv",
        ROOT / "docs/results/rail-transfer-m5/results.md",
    )
    assert all(not path.exists() for path in removed)


def test_markdown_never_uses_plus_minus_result_formatting() -> None:
    offenders = []
    for path in ROOT.rglob("*.md"):
        if any(part in {".git", ".venv", "build", "dist"} for part in path.parts):
            continue
        if "±" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
