"""Contracts for a clean public results starting point."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_results_tree_is_either_clean_start_or_complete_live_bundle() -> None:
    historical = (
        ROOT / "docs/findings.md",
        ROOT / "docs/results/rail-transfer-m5/audit-summary.json",
        ROOT / "docs/results/rail-transfer-m5/results.csv",
        ROOT / "docs/results/rail-transfer-m5/results.md",
    )
    assert all(not path.exists() for path in historical)

    comparison = ROOT / "docs/results/model-comparison"
    if not comparison.exists():
        return
    assert (comparison / "README.md").is_file()
    assert (comparison / "results.csv").is_file()
    assert (comparison / "status.json").is_file()
    assert list((comparison / "records").glob("*.json"))


def test_markdown_never_uses_plus_minus_result_formatting() -> None:
    offenders = []
    for path in ROOT.rglob("*.md"):
        if any(part in {".git", ".venv", "build", "dist"} for part in path.parts):
            continue
        if "±" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_live_comparison_ends_with_accuracy_speed_leaderboard() -> None:
    readme = ROOT / "docs/results/model-comparison/README.md"
    if not readme.is_file():
        return
    content = readme.read_text(encoding="utf-8")
    heading = "## RailSem19 accuracy-speed leaderboard"
    assert heading in content
    assert content.index(heading) > content.index("## Fixed protocol and files")
    leaderboard = content.split(heading, maxsplit=1)[1]
    assert (
        "| rank | model | status | quality gate | recommendation score | "
        "RailSem19 mIoU | accuracy rank | FPS | speed rank |" in leaderboard
    )
    model_rows = [
        line for line in leaderboard.splitlines() if line.startswith("| ") and "](" in line
    ]
    assert len(model_rows) == 37
    assert all("| complete |" in line or "| pending |" in line for line in model_rows)
    assert "*(alias of `smp_deeplabv3plus_resnet101`)*" in leaderboard
    assert "| below 60% mIoU | not eligible |" in leaderboard
    assert "| below 60% mIoU | — |" not in leaderboard
    assert content.count("| not retained |") == 3
    assert "\n## " not in leaderboard
