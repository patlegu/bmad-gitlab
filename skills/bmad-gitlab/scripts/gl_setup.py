#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Register the bmad-gitlab module settings in a BMAD project.

    gl_setup.py --project-root DIR --project GROUP/PROJECT [--hostname HOST] [--auto-apply]
                [--extra-sprint STATUS=EPICS]... [--prefix SPRINT=TEXT]... [--no-hook]

Writes the ``[modules.bgl]`` table between two marker lines of ``_bmad/custom/config.toml`` (the team file,
never touched by the installer) and, unless ``--no-hook``, ``_bmad/custom/bmad-sprint-planning.toml`` with
the ``on_complete`` instruction that runs this skill after sprint planning. A file that is not the module's
own is never overwritten: the line to add by hand is reported instead. Prints a JSON object of what was done.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import tomllib
from collections.abc import Sequence
from pathlib import Path

START = (
    "# >>> bmad-gitlab: written by the skill's `setup`, which rewrites everything down to the closing line"
)
END = "# <<< bmad-gitlab"
HOOK_MARK = "# bmad-gitlab: the module's own hook, rewritten by `setup`"
EXIT_USAGE = 2
EXIT_SETUP = 5  # the same code as gl_run.py: the setup is wrong
ON_COMPLETE = "Run the bmad-gitlab skill in headless mode to mirror the sprint into GitLab."


class SetupError(RuntimeError):
    """The files cannot be written without losing something of the author's."""


def _string(value: str) -> str:
    """``value`` as a TOML basic string: JSON escapes the quote, the backslash and the control characters.

    A character outside the BMP stays as it is (a surrogate pair is not valid TOML); DEL is escaped."""
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def render_block(
    project: str,
    *,
    hostname: str | None,
    auto_apply: bool,
    extra_sprints: Sequence[tuple[str, str]],
    prefixes: Sequence[str],
) -> str:
    """The marked block of ``_bmad/custom/config.toml``."""
    lines = [START, "[modules.bgl]", f"gitlab_project = {_string(project)}"]
    if hostname:
        lines.append(f"gitlab_hostname = {_string(hostname)}")
    lines.append(f"auto_apply = {'true' if auto_apply else 'false'}")
    if prefixes:
        lines.append(f"title_prefixes = [{', '.join(_string(p) for p in prefixes)}]")
    if extra_sprints:
        items = ", ".join(f"{{ status = {_string(s)}, epics = {_string(e)} }}" for s, e in extra_sprints)
        lines.append(f"extra_sprints = [{items}]")
    return "\n".join([*lines, END]) + "\n"


def merge_block(existing: str, block: str) -> str:
    """``existing`` with the module's block replaced or appended; the author's own table is not duplicated."""
    if START in existing:
        head, _, rest = existing.partition(START)
        if END not in rest:
            raise SetupError(
                "the closing marker of the bmad-gitlab block is missing: repair the file by hand"
            )
        tail = rest.partition(END)[2].removeprefix("\n")
        merged = head + block + tail
    else:
        if "[modules.bgl]" in existing:
            raise SetupError(
                "[modules.bgl] is already written outside the markers: remove it or edit it by hand"
            )
        merged = existing + ("" if existing.endswith("\n") or not existing else "\n") + block
    try:
        tomllib.loads(merged)
    except tomllib.TOMLDecodeError as exc:
        raise SetupError(f"the result would not be valid TOML: {exc}") from exc
    return merged


def hook_text() -> str:
    return f"{HOOK_MARK}\n[workflow]\non_complete = {_string(ON_COMPLETE)}\n"


def _write_atomically(path: Path, text: str) -> None:
    """Write ``text`` to a temporary file next to ``path`` and put it in place: a failure loses nothing."""
    path = path.resolve()  # a link is followed: the file it points to is the one that changes
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        if path.exists():
            os.chmod(name, path.stat().st_mode & 0o7777)
        else:
            os.chmod(name, 0o644)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def _hook_is_ours(path: Path) -> bool:
    """True when there is no hook file yet or it carries the module's mark; a file of someone else is not."""
    return not path.exists() or HOOK_MARK in path.read_text(encoding="utf-8")


def write_hook(path: Path) -> str:
    """Write the hook file unless it is someone else's; the answer says which."""
    if not _hook_is_ours(path):
        return "kept"
    _write_atomically(path, hook_text())
    return "written"


def _pairs(values: Sequence[str], what: str) -> list[tuple[str, str]]:
    pairs = []
    for value in values:
        left, sep, right = value.partition("=")
        if not sep or not left or not right:
            raise SetupError(f"{what} {value!r} must look like LEFT=RIGHT")
        pairs.append((left, right))
    return pairs


def _prefixes(values: Sequence[str]) -> list[str]:
    """The ``SPRINT=TEXT`` entries, each with a text of one line that is not blank (what ``sync`` accepts)."""
    entries = []
    for left, right in _pairs(values, "--prefix"):
        if not right.strip() or "\n" in right:
            raise SetupError(f"--prefix {left}={right!r} must have a text of one line")
        entries.append(f"{left}={right}")
    return entries


def setup(args: argparse.Namespace) -> dict[str, str]:
    """Write the configuration (and the hook); return what was done."""
    custom = args.project_root / "_bmad" / "custom"
    if not (args.project_root / "_bmad").is_dir():
        raise SetupError(f"no BMAD installation under {args.project_root}")
    block = render_block(
        args.project,
        hostname=args.hostname,
        auto_apply=args.auto_apply,
        extra_sprints=_pairs(args.extra_sprint, "--extra-sprint"),
        prefixes=_prefixes(args.prefix),
    )
    config = custom / "config.toml"
    existing = config.read_text(encoding="utf-8") if config.exists() else ""
    merged = merge_block(existing, block)
    hook = custom / "bmad-sprint-planning.toml"
    if not args.no_hook:
        _hook_is_ours(hook)  # read before anything is written: an unreadable hook stops the setup untouched
    custom.mkdir(exist_ok=True)
    _write_atomically(config, merged)
    done = {"config": str(config)}
    if not args.no_hook:
        done["hook"] = f"{write_hook(hook)}: {hook}"
        if done["hook"].startswith("kept"):
            done["hook_line"] = f"on_complete = {_string(ON_COMPLETE)}  (under [workflow] in {hook})"
    return done


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gl_setup", description="Register the bmad-gitlab settings.")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--project", required=True, help="GROUP/PROJECT")
    parser.add_argument("--hostname")
    parser.add_argument("--auto-apply", action="store_true")
    parser.add_argument("--extra-sprint", action="append", default=[], metavar="STATUS=EPICS")
    parser.add_argument("--prefix", action="append", default=[], metavar="SPRINT=TEXT")
    parser.add_argument("--no-hook", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    args.project_root = args.project_root.resolve()
    try:
        print(json.dumps(setup(args), indent=2))
    except SetupError as exc:
        print(f"bmad-gitlab: {exc}", file=sys.stderr)
        return EXIT_SETUP
    except (OSError, UnicodeDecodeError) as exc:  # an unreadable, unwritable or non-UTF-8 file
        print(f"bmad-gitlab: cannot read or write the configuration: {exc}", file=sys.stderr)
        return EXIT_SETUP
    return 0


if __name__ == "__main__":
    sys.exit(main())
