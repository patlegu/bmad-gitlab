#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Run the bmad-gitlab engine for a BMAD project, from the module's configuration.

    gl_run.py --project-root DIR [--headless] [--apply] [sync|status]

``status`` never writes. ``sync`` is a dry run too, unless ``--apply`` is given, or ``--headless`` is
given and the module configuration says ``auto_apply = true``.

Exit codes: those of the engine (0 done, 2 usage or bad files, 3 problems found with --apply, 4 GitLab error)
and 5 when the configuration or a prerequisite is wrong: the message on stderr says which command to run.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # nosec B404 - runs `glab` and the BMAD resolver, with a list of arguments, no shell
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXIT_USAGE = 2
EXIT_SETUP = 5
ROOT_PLACEHOLDER = "{project-root}"  # the placeholder of the BMAD configuration for the project root

Run = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


class SetupError(RuntimeError):
    """The configuration or a prerequisite is wrong; the message says what to do."""


@dataclass(frozen=True)
class Settings:
    project: str
    hostname: str | None
    sprints: tuple[tuple[str, str], ...]
    prefixes: tuple[str, ...]
    auto_apply: bool


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """The real runner: no shell, text mode, a 60 second limit."""
    try:
        return subprocess.run(  # noqa: S603  # nosec B603
            list(command), capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(list(command), 127, "", str(exc))


def _fill(value: object, root: Path) -> str:
    return str(value).replace(ROOT_PLACEHOLDER, str(root))


def _path(value: object, root: Path) -> str:
    """A path of the configuration: the token replaced, then relative to the project root."""
    filled = Path(_fill(value, root))
    return str(filled if filled.is_absolute() else root / filled)


def read_config(root: Path, run: Run = run_command) -> Mapping[str, Any]:
    """The merged BMAD configuration, through the project's own resolver."""
    script = root / "_bmad" / "scripts" / "resolve_config.py"
    if not script.is_file():
        raise SetupError(f"no BMAD installation under {root}: {script} is missing")
    done = run([sys.executable, str(script), "--project-root", str(root)])
    if done.returncode != 0:
        raise SetupError(f"the BMAD configuration cannot be read: {done.stderr.strip()[:200]}")
    try:
        data = json.loads(done.stdout)
    except json.JSONDecodeError as exc:
        raise SetupError(f"the BMAD configuration is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SetupError("the BMAD configuration is not a table")
    return data


def _table(config: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    node: Any = config
    for key in keys:
        node = node.get(key) if isinstance(node, Mapping) else None
    return node if isinstance(node, Mapping) else {}


def _text(table: Mapping[str, Any], key: str) -> str:
    value = table.get(key)
    return value if isinstance(value, str) else ""


def _flag(table: Mapping[str, Any], key: str) -> bool:
    """A true/false setting, false when absent; any other value is an error and not a silent false."""
    value = table.get(key, False)
    if not isinstance(value, bool):
        raise SetupError(f"modules.bgl.{key} must be true or false, not {value!r}")
    return value


def _extra_sprints(table: Mapping[str, Any], root: Path) -> list[tuple[str, str]]:
    extra = table.get("extra_sprints", [])
    if not isinstance(extra, list):
        raise SetupError("modules.bgl.extra_sprints must be a list of tables with `status` and `epics`")
    pairs: list[tuple[str, str]] = []
    for entry in extra:
        if not isinstance(entry, Mapping) or not entry.get("status") or not entry.get("epics"):
            raise SetupError("modules.bgl.extra_sprints: each entry needs `status` and `epics`")
        pairs.append((_path(entry["status"], root), _path(entry["epics"], root)))
    return pairs


def settings_from(config: Mapping[str, Any], root: Path) -> Settings:
    """The module settings and the sprint files, from the merged configuration."""
    table = _table(config, "modules", "bgl")
    project = _text(table, "gitlab_project")
    if not project:
        raise SetupError("modules.bgl.gitlab_project is not set: run the bmad-gitlab skill with `setup`")
    bmm = _table(config, "modules", "bmm")
    status = _text(bmm, "implementation_artifacts")
    epics = _text(bmm, "planning_artifacts")
    if not status or not epics:
        raise SetupError("modules.bmm.implementation_artifacts and planning_artifacts are not set")
    sprints = [
        (_path(Path(status) / "sprint-status.yaml", root), _path(Path(epics) / "epics.md", root)),
        *_extra_sprints(table, root),
    ]
    prefixes = table.get("title_prefixes", [])
    if not isinstance(prefixes, list) or not all(isinstance(p, str) and "=" in p for p in prefixes):
        raise SetupError("modules.bgl.title_prefixes must be a list of SPRINT=TEXT strings")
    return Settings(
        project=project,
        hostname=_text(table, "gitlab_hostname") or None,
        sprints=tuple(sprints),
        prefixes=tuple(prefixes),
        auto_apply=_flag(table, "auto_apply"),
    )


def check_prerequisites(
    settings: Settings,
    run: Run = run_command,
    which: Callable[[str], str | None] = shutil.which,
) -> None:
    """``uv`` and ``glab`` are installed and ``glab`` is signed in to the host; else a SetupError."""
    if which("uv") is None:
        raise SetupError("`uv` is not installed: see https://docs.astral.sh/uv/ and run this again")
    if which("glab") is None:
        raise SetupError("`glab` is not installed: install the GitLab CLI, then run `glab auth login`")
    host = settings.hostname or "gitlab.com"
    if run(["glab", "auth", "status", "--hostname", host]).returncode != 0:
        raise SetupError(f"`glab` is not signed in to {host}: run `glab auth login --hostname {host}`")
    for status, epics in settings.sprints:
        for path in (status, epics):
            if not Path(path).is_file():
                raise SetupError(f"{path} does not exist: run sprint planning first")


def engine_argv(settings: Settings, *, apply: bool) -> list[str]:
    """The arguments of ``bmad-gitlab sync`` for these settings."""
    argv = ["sync", "--project", settings.project]
    for status, epics in settings.sprints:
        argv += ["--sprint", status, epics]
    for prefix in settings.prefixes:
        argv += ["--prefix", prefix]
    if settings.hostname:
        argv += ["--hostname", settings.hostname]
    if apply:
        argv.append("--apply")
    return argv


def decide_apply(settings: Settings, *, intent: str, apply: bool, headless: bool) -> bool:
    """Whether this run writes: never for ``status``; for ``sync`` on request, or headless with auto_apply."""
    if intent == "status":
        return False
    return apply or (headless and settings.auto_apply)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gl_run", description="Mirror the BMAD sprint into GitLab.")
    parser.add_argument("intent", nargs="?", choices=("sync", "status"), default="sync")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="write to GitLab (sync only)")
    parser.add_argument("--headless", action="store_true", help="apply only when auto_apply is true")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    run: Run = run_command,
    which: Callable[[str], str | None] = shutil.which,
    engine: Callable[[Sequence[str]], int] | None = None,
) -> int:
    """Run the engine for the project at ``--project-root``; its exit code, or 5 when the setup is wrong."""
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    root = args.project_root.resolve()
    try:
        settings = settings_from(read_config(root, run), root)
        check_prerequisites(settings, run, which)
    except SetupError as exc:
        print(f"bmad-gitlab: {exc}", file=sys.stderr)
        return EXIT_SETUP
    apply = decide_apply(settings, intent=args.intent, apply=args.apply, headless=args.headless)
    return (engine or _engine())(engine_argv(settings, apply=apply))


def _engine() -> Callable[[Sequence[str]], int]:
    """The engine vendored next to this script (see ``scripts/vendor.py`` of the repository)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from bmad_gitlab.cli import main as engine_main

    return engine_main


if __name__ == "__main__":
    sys.exit(main())
