#!/usr/bin/env python3
"""Copy the engine into the skill, or check that the copy is the engine.

    python scripts/vendor.py          # write skills/bmad-gitlab/scripts/bmad_gitlab/
    python scripts/vendor.py --check  # exit 1 when the copy differs from src/bmad_gitlab/

The skill carries its own copy so that installing the module is copying one folder. `src/bmad_gitlab/` is the
only place the engine is edited; a copy that could drift without any alarm is a defect waiting, so the test
suite runs the check.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "bmad_gitlab"
TARGET = ROOT / "skills" / "bmad-gitlab" / "scripts" / "bmad_gitlab"


def engine_files(folder: Path) -> dict[str, bytes]:
    """Every file of the package (``.py`` and ``py.typed``) by relative name, caches left out."""
    return {
        str(path.relative_to(folder)): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts and path.suffix in {".py", ".typed"}
    }


def differences(source: Path = SOURCE, target: Path = TARGET) -> list[str]:
    """What differs between the engine and its copy: missing, extra and changed files."""
    wanted = engine_files(source)
    found = engine_files(target) if target.is_dir() else {}
    return (
        [f"missing in the copy: {name}" for name in sorted(wanted.keys() - found.keys())]
        + [f"not in the engine: {name}" for name in sorted(found.keys() - wanted.keys())]
        + [f"differs: {name}" for name in sorted(wanted.keys() & found.keys()) if wanted[name] != found[name]]
    )


def vendor(source: Path = SOURCE, target: Path = TARGET) -> None:
    """Make the copy identical to the engine."""
    if target.is_dir():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name, content in engine_files(source).items():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only compare, write nothing")
    args = parser.parse_args(argv)
    if not args.check:
        vendor()
        return 0
    problems = differences()
    for line in problems:
        print(line, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
