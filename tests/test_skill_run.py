"""The skill's launcher: configuration, prerequisites, the decision to write, the engine's arguments."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "bmad-gitlab" / "scripts" / "gl_run.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gl_run", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["gl_run"] = module
    spec.loader.exec_module(module)
    return module


gl = _load()

CONFIG = {
    "modules": {
        "bgl": {"gitlab_project": "team/app"},
        "bmm": {
            "implementation_artifacts": "{project-root}/_bmad-output/implementation-artifacts",
            "planning_artifacts": "{project-root}/_bmad-output/planning-artifacts",
        },
    }
}


def _project(tmp_path: Path, config: dict[str, object] | None = None) -> Path:
    """A BMAD project with a resolver stand-in that prints ``config``, and the two sprint files."""
    (tmp_path / "_bmad" / "scripts").mkdir(parents=True)
    (tmp_path / "_bmad" / "scripts" / "resolve_config.py").write_text("# stand-in\n", encoding="utf-8")
    for name in ("implementation-artifacts/sprint-status.yaml", "planning-artifacts/epics.md"):
        target = tmp_path / "_bmad-output" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n", encoding="utf-8")
    return tmp_path


class FakeRuns:
    """Answers the resolver with ``config``, ``glab auth status`` with ``auth_code``; records the commands."""

    def __init__(self, config: object = CONFIG, auth_code: int = 0, resolver_code: int = 0) -> None:
        self.config, self.auth_code, self.resolver_code = config, auth_code, resolver_code
        self.commands: list[list[str]] = []

    def __call__(self, command):
        self.commands.append(list(command))
        if command[0] == "glab":
            return subprocess.CompletedProcess(command, self.auth_code, "", "")
        text = self.config if isinstance(self.config, str) else json.dumps(self.config)
        return subprocess.CompletedProcess(
            command, self.resolver_code, text, "boom" if self.resolver_code else ""
        )


def _which(found: set[str]):
    return lambda name: f"/usr/bin/{name}" if name in found else None


BOTH = {"uv", "glab"}


def test_read_config_refuses_a_project_without_bmad(tmp_path: Path) -> None:
    with pytest.raises(gl.SetupError, match="no BMAD installation"):
        gl.read_config(tmp_path, FakeRuns())


@pytest.mark.parametrize(
    ("runs", "message"),
    [
        (FakeRuns(resolver_code=1), "cannot be read: boom"),
        (FakeRuns(config="not json"), "not valid JSON"),
        (FakeRuns(config="[1]"), "not a table"),
    ],
)
def test_read_config_says_why_it_failed(tmp_path: Path, runs: FakeRuns, message: str) -> None:
    with pytest.raises(gl.SetupError, match=message):
        gl.read_config(_project(tmp_path), runs)


def test_read_config_returns_the_merged_table(tmp_path: Path) -> None:
    assert gl.read_config(_project(tmp_path), FakeRuns()) == CONFIG


def test_settings_resolve_the_standard_pair_and_the_options(tmp_path: Path) -> None:
    config = json.loads(json.dumps(CONFIG))
    config["modules"]["bgl"].update(
        gitlab_hostname="git.example",
        auto_apply=True,
        title_prefixes=["app-extras=[extras]"],
        extra_sprints=[{"status": "{project-root}/other/status.yaml", "epics": "other/epics.md"}],
    )
    settings = gl.settings_from(config, tmp_path)
    assert settings.project == "team/app"
    assert settings.hostname == "git.example"
    assert settings.auto_apply is True
    assert settings.prefixes == ("app-extras=[extras]",)
    assert settings.sprints == (
        (
            str(tmp_path / "_bmad-output/implementation-artifacts/sprint-status.yaml"),
            str(tmp_path / "_bmad-output/planning-artifacts/epics.md"),
        ),
        (str(tmp_path / "other/status.yaml"), str(tmp_path / "other/epics.md")),
    )


def test_auto_apply_is_off_when_absent_and_an_error_unless_it_is_true_or_false(tmp_path: Path) -> None:
    assert gl.settings_from(CONFIG, tmp_path).auto_apply is False
    for value in ("true", 1, None):
        config = json.loads(json.dumps(CONFIG))
        config["modules"]["bgl"]["auto_apply"] = value
        with pytest.raises(gl.SetupError, match="auto_apply must be true or false"):
            gl.settings_from(config, tmp_path)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"gitlab_project": ""}, "gitlab_project is not set"),
        ({"extra_sprints": "x"}, "must be a list of tables"),
        ({"extra_sprints": [{"status": "a"}]}, "needs `status` and `epics`"),
        ({"extra_sprints": ["a"]}, "needs `status` and `epics`"),
        ({"title_prefixes": "x"}, "SPRINT=TEXT"),
        ({"title_prefixes": ["no-equal"]}, "SPRINT=TEXT"),
    ],
)
def test_settings_refuse_a_bad_table(tmp_path: Path, change: dict[str, object], message: str) -> None:
    config = json.loads(json.dumps(CONFIG))
    config["modules"]["bgl"].update(change)
    with pytest.raises(gl.SetupError, match=message):
        gl.settings_from(config, tmp_path)


def test_settings_refuse_a_missing_artifact_folder(tmp_path: Path) -> None:
    config = {"modules": {"bgl": {"gitlab_project": "team/app"}, "bmm": {}}}
    with pytest.raises(gl.SetupError, match="implementation_artifacts"):
        gl.settings_from(config, tmp_path)


def _settings(tmp_path: Path, **change: object) -> object:
    config = json.loads(json.dumps(CONFIG))
    config["modules"]["bgl"].update(change)
    return gl.settings_from(config, tmp_path)


def test_prerequisites_pass_when_everything_is_there(tmp_path: Path) -> None:
    runs = FakeRuns()
    gl.check_prerequisites(_settings(_project(tmp_path)), runs, _which(BOTH))
    assert runs.commands == [["glab", "auth", "status", "--hostname", "gitlab.com"]]


@pytest.mark.parametrize(
    ("found", "message"), [({"glab"}, "`uv` is not installed"), ({"uv"}, "`glab` is not installed")]
)
def test_prerequisites_name_the_missing_tool(tmp_path: Path, found: set[str], message: str) -> None:
    with pytest.raises(gl.SetupError, match=message):
        gl.check_prerequisites(_settings(_project(tmp_path)), FakeRuns(), _which(found))


def test_prerequisites_name_the_host_glab_is_not_signed_in_to(tmp_path: Path) -> None:
    settings = _settings(_project(tmp_path), gitlab_hostname="git.example")
    with pytest.raises(
        gl.SetupError, match=r"not signed in to git\.example: run `glab auth login --hostname git\.example`"
    ):
        gl.check_prerequisites(settings, FakeRuns(auth_code=1), _which(BOTH))


def test_prerequisites_refuse_a_missing_sprint_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "_bmad-output/planning-artifacts/epics.md").unlink()
    with pytest.raises(gl.SetupError, match=r"epics\.md does not exist: run sprint planning first"):
        gl.check_prerequisites(_settings(root), FakeRuns(), _which(BOTH))


def test_engine_arguments_carry_every_setting(tmp_path: Path) -> None:
    settings = _settings(tmp_path, gitlab_hostname="h.example", title_prefixes=["a=[a]", "b=[b]"])
    argv = gl.engine_argv(settings, apply=True)
    status, epics = settings.sprints[0]
    assert argv == [
        "sync", "--project", "team/app", "--sprint", status, epics,
        "--prefix", "a=[a]", "--prefix", "b=[b]", "--hostname", "h.example", "--apply",
    ]  # fmt: skip
    assert "--apply" not in gl.engine_argv(settings, apply=False)


@pytest.mark.parametrize(
    ("intent", "apply", "headless", "auto", "expected"),
    [
        ("status", True, True, True, False),
        ("sync", False, False, False, False),
        ("sync", True, False, False, True),
        ("sync", False, True, False, False),
        ("sync", False, True, True, True),
        ("sync", False, False, True, False),
    ],
)
def test_the_decision_to_write(
    tmp_path: Path, intent: str, apply: bool, headless: bool, auto: bool, expected: bool
) -> None:
    settings = _settings(tmp_path, auto_apply=auto)
    assert gl.decide_apply(settings, intent=intent, apply=apply, headless=headless) is expected


def _main(
    tmp_path: Path, args: list[str], runs: FakeRuns | None = None, found: set[str] = BOTH
) -> tuple[int, list[list[str]]]:
    seen: list[list[str]] = []

    def engine(argv):
        seen.append(list(argv))
        return 3

    code = gl.main(
        ["--project-root", str(_project(tmp_path)), *args],
        run=runs or FakeRuns(),
        which=_which(found),
        engine=engine,
    )
    return code, seen


def test_a_sync_without_apply_is_a_dry_run_and_returns_the_engine_code(tmp_path: Path) -> None:
    code, seen = _main(tmp_path, ["sync"])
    assert code == 3
    assert len(seen) == 1
    assert "--apply" not in seen[0]


def test_apply_reaches_the_engine_only_for_a_sync(tmp_path: Path) -> None:
    assert "--apply" in _main(tmp_path, ["sync", "--apply"])[1][0]
    assert "--apply" not in _main(tmp_path / "b", ["status", "--apply"])[1][0]


def test_headless_applies_only_with_auto_apply(tmp_path: Path) -> None:
    auto = json.loads(json.dumps(CONFIG))
    auto["modules"]["bgl"]["auto_apply"] = True
    assert "--apply" not in _main(tmp_path, ["--headless"])[1][0]
    assert "--apply" in _main(tmp_path / "b", ["--headless"], FakeRuns(config=auto))[1][0]


def test_a_missing_prerequisite_stops_before_the_engine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, seen = _main(tmp_path, ["sync"], found={"uv"})
    assert code == gl.EXIT_SETUP
    assert seen == []
    assert "bmad-gitlab: `glab` is not installed" in capsys.readouterr().err


def test_a_usage_error_returns_the_argparse_code(tmp_path: Path) -> None:
    assert gl.main(["--bogus"]) == 2


def test_settings_need_both_artifact_folders(tmp_path: Path) -> None:
    for only in ("implementation_artifacts", "planning_artifacts"):
        bmm = {only: "{project-root}/x"}
        with pytest.raises(gl.SetupError, match="not set"):
            gl.settings_from({"modules": {"bgl": {"gitlab_project": "team/app"}, "bmm": bmm}}, tmp_path)


def test_help_ends_with_zero() -> None:
    assert gl.main(["--help"]) == 0


def test_the_real_runner_gives_the_answer_of_the_command_and_127_when_there_is_none() -> None:
    done = gl.run_command([sys.executable, "-c", "print('hi')"])
    assert (done.returncode, done.stdout.strip()) == (0, "hi")
    assert gl.run_command(["/nonexistent-command-bmad-gitlab"]).returncode == 127


def test_the_engine_is_the_vendored_one() -> None:
    assert gl._engine()(["--help"]) == 0


def test_a_usage_error_is_the_usage_code() -> None:
    assert gl.main(["--bogus"]) == gl.EXIT_USAGE
