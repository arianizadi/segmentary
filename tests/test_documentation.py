"""Keep the repository's documentation library internally navigable."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SKIP_SCHEMES = ("http://", "https://", "mailto:", "data:")


def _local_target(document: Path, raw_target: str) -> Path | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if target.startswith(SKIP_SCHEMES) or target.startswith("#"):
        return None
    # Markdown permits an optional quoted title after the destination. None of
    # the repository paths needs spaces outside angle brackets.
    target = target.split(' "', maxsplit=1)[0]
    path = unquote(target.split("#", maxsplit=1)[0].split("?", maxsplit=1)[0])
    return (document.parent / path).resolve() if path else None


def test_every_repository_markdown_link_has_a_local_target() -> None:
    missing: list[str] = []
    documents = sorted(ROOT.rglob("*.md"))
    assert len(documents) >= 80  # catches an accidentally omitted docs tree

    for document in documents:
        if any(part in {".git", ".venv", "build", "dist", "runs"} for part in document.parts):
            continue
        for raw_target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            target = _local_target(document, raw_target)
            if target is not None and not target.exists():
                missing.append(f"{document.relative_to(ROOT)} -> {raw_target}")

    assert missing == []


def test_every_model_recipe_is_indexed_and_has_point_of_choice_guidance() -> None:
    index = (ROOT / "configs/models/README.md").read_text(encoding="utf-8")
    recipes = sorted((ROOT / "configs/models").glob("*.yaml"))
    assert recipes
    assert all(recipe.name in index for recipe in recipes)

    pages = sorted((ROOT / "docs/catalog/models").glob("*/README.md"))
    assert pages
    for page in pages:
        text = page.read_text(encoding="utf-8").lower()
        assert "pros" in text, page
        assert "cons" in text, page
        assert "benchmark" in text or "evidence" in text, page


def test_legacy_brand_only_appears_in_immutable_or_explicitly_archived_records() -> None:
    allowed = {
        Path("tests/test_progress.py"),
    }
    allowed.update(path.relative_to(ROOT) for path in (ROOT / "docs/benchmarks").rglob("*.json"))

    stale: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part == ".git" for part in path.parts):
            continue
        relative = path.relative_to(ROOT)
        if relative in allowed or any(
            part in {".pytest_cache", ".ruff_cache", "build", "dist", "__pycache__"}
            or part.endswith(".egg-info")
            for part in relative.parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        legacy_brand = "rail" + "yard"
        if re.search(legacy_brand, text, flags=re.IGNORECASE):
            stale.append(str(relative))

    assert stale == []
