"""The engine copied into the skill is the engine: it cannot drift without this test failing."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "vendor.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vendor", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["vendor"] = module
    spec.loader.exec_module(module)
    return module


vendor = _load()


def test_the_copy_in_the_skill_is_the_engine() -> None:
    """When this fails, run `python scripts/vendor.py`: only src/bmad_gitlab is edited."""
    assert vendor.differences() == []


def _package(folder: Path, **files: str) -> Path:
    folder.mkdir(parents=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def test_a_changed_a_missing_and_an_extra_file_are_each_named(tmp_path: Path) -> None:
    source = _package(tmp_path / "src", **{"a.py": "1", "b.py": "2", "c.py": "3"})
    target = _package(tmp_path / "copy", **{"a.py": "1", "b.py": "changed", "z.py": "extra"})
    assert vendor.differences(source, target) == [
        "missing in the copy: c.py",
        "not in the engine: z.py",
        "differs: b.py",
    ]


def test_a_missing_copy_is_every_file_missing(tmp_path: Path) -> None:
    source = _package(tmp_path / "src", **{"a.py": "1"})
    assert vendor.differences(source, tmp_path / "nope") == ["missing in the copy: a.py"]


def test_vendoring_replaces_the_copy_and_leaves_caches_out(tmp_path: Path) -> None:
    source = _package(tmp_path / "src", **{"a.py": "1", "py.typed": ""})
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "a.pyc").write_bytes(b"x")
    (source / "sub").mkdir()
    (source / "sub" / "b.py").write_text("2", encoding="utf-8")
    target = _package(tmp_path / "copy", **{"stale.py": "old"})
    vendor.vendor(source, target)
    assert sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()) == [
        "a.py",
        "py.typed",
        "sub/b.py",
    ]
    assert vendor.differences(source, target) == []


def test_check_exits_1_on_a_difference_and_0_otherwise(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(vendor, "differences", lambda: ["differs: x"])
    assert vendor.main(["--check"]) == 1
    assert "differs: x" in capsys.readouterr().err
    monkeypatch.setattr(vendor, "differences", lambda: [])
    assert vendor.main(["--check"]) == 0
