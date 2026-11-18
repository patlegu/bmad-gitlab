"""The skill's setup: what it writes, what it refuses to overwrite, and that the launcher reads it back."""

import importlib.util
import json
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "bmad-gitlab" / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gs = _load("gl_setup")
gl = _load("gl_run")


def _root(tmp_path: Path) -> Path:
    (tmp_path / "_bmad").mkdir()
    return tmp_path


def _run(root: Path, *args: str) -> int:
    return gs.main(["--project-root", str(root), "--project", "team/app", *args])


def _config(root: Path) -> dict[str, object]:
    return tomllib.loads((root / "_bmad/custom/config.toml").read_text(encoding="utf-8"))


def test_setup_writes_a_table_the_launcher_reads_back(tmp_path: Path) -> None:
    root = _root(tmp_path)
    code = _run(
        root,
        "--hostname", "git.example", "--auto-apply",
        "--extra-sprint", "x/status.yaml=x/epics.md", "--prefix", "app-extras=[extras]",
    )  # fmt: skip
    assert code == 0
    table = _config(root)["modules"]["bgl"]  # type: ignore[index]
    assert table == {
        "gitlab_project": "team/app",
        "gitlab_hostname": "git.example",
        "auto_apply": True,
        "title_prefixes": ["app-extras=[extras]"],
        "extra_sprints": [{"status": "x/status.yaml", "epics": "x/epics.md"}],
    }
    merged = {
        "modules": {
            **_config(root)["modules"],
            "bmm": {"implementation_artifacts": "a", "planning_artifacts": "p"},
        }
    }  # type: ignore[dict-item]
    settings = gl.settings_from(merged, root)
    assert (settings.project, settings.hostname, settings.auto_apply) == ("team/app", "git.example", True)
    assert settings.prefixes == ("app-extras=[extras]",)
    assert settings.sprints[1] == (str(root / "x/status.yaml"), str(root / "x/epics.md"))


def test_the_defaults_are_a_safe_table(tmp_path: Path) -> None:
    root = _root(tmp_path)
    assert _run(root) == 0
    assert _config(root)["modules"]["bgl"] == {"gitlab_project": "team/app", "auto_apply": False}  # type: ignore[index]


def test_a_second_run_changes_the_block_and_keeps_the_rest(tmp_path: Path) -> None:
    root = _root(tmp_path)
    custom = root / "_bmad" / "custom"
    custom.mkdir()
    (custom / "config.toml").write_text('[agents.x]\ndescription = "mine"\n', encoding="utf-8")
    _run(root)
    before = (custom / "config.toml").read_text(encoding="utf-8")
    _run(root)
    assert (custom / "config.toml").read_text(encoding="utf-8") == before
    _run(root, "--auto-apply")
    after = _config(root)
    assert after["agents"] == {"x": {"description": "mine"}}
    assert after["modules"]["bgl"]["auto_apply"] is True  # type: ignore[index]
    assert (custom / "config.toml").read_text(encoding="utf-8").count("[modules.bgl]") == 1


def test_a_table_written_by_hand_is_not_duplicated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path)
    (root / "_bmad" / "custom").mkdir()
    (root / "_bmad/custom/config.toml").write_text(
        '[modules.bgl]\ngitlab_project = "a/b"\n', encoding="utf-8"
    )
    assert _run(root) == 5
    assert "outside the markers" in capsys.readouterr().err


def test_a_block_without_its_closing_marker_is_not_guessed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path)
    (root / "_bmad" / "custom").mkdir()
    (root / "_bmad/custom/config.toml").write_text(f"{gs.START}\n[modules.bgl]\n", encoding="utf-8")
    assert _run(root) == 5
    assert "closing marker" in capsys.readouterr().err


def test_a_project_without_bmad_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(tmp_path) == 5
    assert "no BMAD installation" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["--extra-sprint", "--prefix"])
@pytest.mark.parametrize("value", ["noequal", "=x", "x="])
def test_a_pair_must_have_two_sides(
    tmp_path: Path, flag: str, value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(_root(tmp_path), flag, value) == 5
    assert "must look like LEFT=RIGHT" in capsys.readouterr().err


def test_the_hook_is_written_with_the_instruction(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _root(tmp_path)
    assert _run(root) == 0
    hook = tomllib.loads((root / "_bmad/custom/bmad-sprint-planning.toml").read_text(encoding="utf-8"))
    assert hook == {"workflow": {"on_complete": gs.ON_COMPLETE}}
    assert json.loads(capsys.readouterr().out)["hook"].startswith("written")


def test_a_hook_file_that_is_not_ours_is_kept_and_the_line_is_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path)
    (root / "_bmad" / "custom").mkdir()
    mine = root / "_bmad/custom/bmad-sprint-planning.toml"
    mine.write_text('[workflow]\non_complete = "my own"\n', encoding="utf-8")
    assert _run(root) == 0
    assert mine.read_text(encoding="utf-8") == '[workflow]\non_complete = "my own"\n'
    done = json.loads(capsys.readouterr().out)
    assert done["hook"].startswith("kept")
    assert gs.ON_COMPLETE in done["hook_line"]


def test_our_own_hook_is_rewritten(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _run(root)
    hook = root / "_bmad/custom/bmad-sprint-planning.toml"
    hook.write_text(hook.read_text(encoding="utf-8").replace(gs.ON_COMPLETE, "old"), encoding="utf-8")
    _run(root)
    assert gs.ON_COMPLETE in hook.read_text(encoding="utf-8")


def test_no_hook_writes_none(tmp_path: Path) -> None:
    root = _root(tmp_path)
    assert _run(root, "--no-hook") == 0
    assert not (root / "_bmad/custom/bmad-sprint-planning.toml").exists()


def test_a_usage_error_returns_the_argparse_code() -> None:
    assert gs.main(["--bogus"]) == 2


def test_what_follows_the_block_is_kept(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _run(root)
    config = root / "_bmad/custom/config.toml"
    config.write_text(
        config.read_text(encoding="utf-8") + '[agents.y]\ndescription = "after"\n', encoding="utf-8"
    )
    _run(root, "--auto-apply")
    assert _config(root)["agents"] == {"y": {"description": "after"}}


def test_a_file_that_is_not_valid_toml_is_not_made_worse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path)
    (root / "_bmad" / "custom").mkdir()
    broken = root / "_bmad/custom/config.toml"
    broken.write_text("[unclosed\n", encoding="utf-8")
    assert _run(root) == 5
    assert "not be valid TOML" in capsys.readouterr().err
    assert broken.read_text(encoding="utf-8") == "[unclosed\n"


def test_a_configuration_that_cannot_be_read_is_said_and_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path)
    (root / "_bmad" / "custom").mkdir()
    (root / "_bmad/custom/config.toml").write_bytes(b"\xff\xfe")
    assert _run(root) == 5
    assert "cannot read or write the configuration" in capsys.readouterr().err


@pytest.mark.parametrize("text", ["   ", "two\nlines"])
def test_a_prefix_that_sync_would_refuse_is_refused_here(
    tmp_path: Path, text: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(_root(tmp_path), "--prefix", f"app={text}") == 5
    assert "text of one line" in capsys.readouterr().err


def test_the_block_goes_on_its_own_line_after_a_file_without_a_final_newline() -> None:
    merged = gs.merge_block("a = 1", "# block\n")
    assert merged == "a = 1\n# block\n"


def test_a_failure_while_writing_keeps_the_file_and_leaves_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "config.toml"
    target.write_text("keep = true\n", encoding="utf-8")

    def refuse(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(gs.os, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        gs._write_atomically(target, "new = true\n")
    assert target.read_text(encoding="utf-8") == "keep = true\n"
    assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]


def test_the_mode_of_a_file_is_kept_and_a_new_file_is_readable(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text("a = 1\n", encoding="utf-8")
    target.chmod(0o600)
    gs._write_atomically(target, "a = 2\n")
    assert target.stat().st_mode & 0o777 == 0o600
    fresh = tmp_path / "fresh.toml"
    gs._write_atomically(fresh, "a = 1\n")
    assert fresh.stat().st_mode & 0o777 == 0o644


def test_the_exit_codes_of_the_three_entry_points_agree() -> None:
    from bmad_gitlab import cli

    assert gs.EXIT_USAGE == gl.EXIT_USAGE == cli.EXIT_USAGE == 2
    assert gs.EXIT_SETUP == gl.EXIT_SETUP == 5


def test_a_link_to_the_configuration_is_followed_and_kept(tmp_path: Path) -> None:
    real = tmp_path / "real.toml"
    real.write_text("a = 1\n", encoding="utf-8")
    link = tmp_path / "link.toml"
    link.symlink_to(real)
    gs._write_atomically(link, "a = 2\n")
    assert link.is_symlink()
    assert real.read_text(encoding="utf-8") == "a = 2\n"


def test_a_prefix_with_an_emoji_or_a_delete_character_is_written_and_read_back(tmp_path: Path) -> None:
    root = _root(tmp_path)
    assert _run(root, "--prefix", "app=[🚀\x7f]") == 0
    assert _config(root)["modules"]["bgl"]["title_prefixes"] == ["app=[🚀\x7f]"]  # type: ignore[index]


def test_several_prefixes_and_sprints_are_written_and_read_back(tmp_path: Path) -> None:
    root = _root(tmp_path)
    assert _run(root, "--prefix", "a=[x]", "--prefix", "b=[y]",
                "--extra-sprint", "s1=e1", "--extra-sprint", "s2=e2") == 0  # fmt: skip
    table = _config(root)["modules"]["bgl"]  # type: ignore[index]
    assert table["title_prefixes"] == ["a=[x]", "b=[y]"]
    assert table["extra_sprints"] == [{"status": "s1", "epics": "e1"}, {"status": "s2", "epics": "e2"}]


def test_a_hook_that_cannot_be_read_stops_the_setup_before_the_configuration_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path)
    (root / "_bmad" / "custom").mkdir()
    (root / "_bmad/custom/bmad-sprint-planning.toml").write_bytes(b"\xff\xfe")
    assert _run(root) == 5
    assert not (root / "_bmad/custom/config.toml").exists()


def test_a_setup_that_is_refused_creates_no_folder(tmp_path: Path) -> None:
    root = _root(tmp_path)
    assert _run(root, "--prefix", "noequal") == 5
    assert not (root / "_bmad" / "custom").exists()
