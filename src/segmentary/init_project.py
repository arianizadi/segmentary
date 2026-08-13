"""Create a small, editable Segmentary project without machine-specific paths."""

from __future__ import annotations

import argparse
import re
import shutil
from importlib import resources
from pathlib import Path

import yaml

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _copy_tree(source, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            _copy_tree(child, target)
        else:
            with resources.as_file(child) as local:
                shutil.copyfile(local, target)


def create_project(destination: Path | str, *, name: str = "my_experiment") -> Path:
    """Copy the packaged starter project into an empty directory.

    Existing non-empty directories are rejected so a quickstart command cannot
    overwrite a dataset, config, or experiment result by accident.
    """
    if not _NAME.fullmatch(name):
        raise ValueError(
            "project name must start with a letter or number and contain only "
            "letters, numbers, dots, underscores, or hyphens"
        )

    target = Path(destination).expanduser().resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise FileExistsError(f"refusing to overwrite non-empty project destination: {target}")

    template = resources.files("segmentary").joinpath("templates", "project")
    _copy_tree(template, target)

    experiment_path = target / "experiment.yaml"
    experiment = yaml.safe_load(experiment_path.read_text(encoding="utf-8"))
    experiment["name"] = name
    experiment_path.write_text(
        yaml.safe_dump(experiment, sort_keys=False),
        encoding="utf-8",
    )
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a portable Segmentary starter project in an empty directory."
    )
    parser.add_argument("destination", type=Path, help="new or empty project directory")
    parser.add_argument(
        "--name",
        default="my_experiment",
        help="experiment name stored in results (default: my_experiment)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        target = create_project(args.destination, name=args.name)
    except (FileExistsError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Created Segmentary project at {target}")
    print("Next:")
    print(f"  cd {target}")
    print("  edit taxonomy/example/*.yaml and experiment.yaml")
    print("  segmentary-train base.yaml model.yaml experiment.yaml --print-config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
