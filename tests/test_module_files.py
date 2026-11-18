"""The module's files agree with each other: one version, real skill paths, a help entry per capability."""

import csv
import json
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "bmad-gitlab"
HEADER = [
    "module", "skill", "display-name", "menu-code", "description", "action", "args", "phase",
    "preceded-by", "followed-by", "required", "output-location", "outputs",
]  # fmt: skip


def _module() -> dict[str, object]:
    return yaml.safe_load((SKILL / "assets" / "module.yaml").read_text(encoding="utf-8"))


def _manifest() -> dict[str, object]:
    return json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))


def _rows() -> list[dict[str, str]]:
    with (SKILL / "assets" / "module-help.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_the_version_is_the_same_everywhere() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    plugin = _manifest()["plugins"][0]["version"]  # type: ignore[index]
    assert _module()["module_version"] == project == plugin


def test_the_module_has_its_identity_and_the_code_matches_the_manifest() -> None:
    module = _module()
    assert {"code", "name", "description"} <= module.keys()
    assert module["code"] == "bgl"
    manifest = _manifest()
    assert manifest["name"] == module["code"]
    assert manifest["plugins"][0]["name"] == module["code"]  # type: ignore[index]


def test_the_manifest_points_at_a_skill_that_exists() -> None:
    for path in _manifest()["plugins"][0]["skills"]:  # type: ignore[index]
        assert (ROOT / path / "SKILL.md").is_file()


def test_every_question_of_the_module_is_read_by_the_launcher() -> None:
    """The installer writes these keys under [modules.bgl]; the launcher reads them by name."""
    script = (SKILL / "scripts" / "gl_run.py").read_text(encoding="utf-8")
    questions = [
        key
        for key in _module()
        if key not in {"code", "name", "description", "module_version", "default_selected", "module_greeting"}
    ]
    assert questions
    for key in questions:
        assert re.search(rf"[\"']{key}[\"']", script), key


def test_the_help_catalogue_covers_each_intent_of_the_skill_once() -> None:
    rows = _rows()
    assert list(rows[0].keys()) == HEADER
    assert {row["skill"] for row in rows} == {"bmad-gitlab"}
    assert sorted(row["action"] for row in rows) == ["setup", "status", "sync"]
    codes = [row["menu-code"] for row in rows]
    assert len(set(codes)) == len(codes)
    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for row in rows:
        assert f"**{row['action']}**" in skill_text, row["action"]


def test_the_version_of_the_package_is_the_version_of_the_module() -> None:
    import bmad_gitlab

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert bmad_gitlab.__version__ == project
