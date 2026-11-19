"""The ``bmad-gitlab sync`` command: a dry run by default, ``--apply`` to write."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TextIO

from bmad_gitlab.apply import apply
from bmad_gitlab.gitlab import Client, GitLabError, Runner, ViewSpec, run_glab
from bmad_gitlab.model import (
    Item,
    RemoteIssue,
    SprintError,
    build_items,
    read_epics,
    read_status,
    sprint_name,
)
from bmad_gitlab.plan import CreateLabel, Plan, label_color
from bmad_gitlab.plan import plan as make_plan
from bmad_gitlab.report import render_applied, render_plan

BOARD_NAME = "BMAD Sprint Board"
BOARD_STATUS_LABELS = ("status:backlog", "status:ready-for-dev", "status:in-progress", "status:review")

# One saved view of the work items per status, for the whole project: the status labels are the same for
# every epic, so four views cover them all (GitLab shows five per person).
STATUS_VIEWS = (
    ViewSpec(
        "BMAD: Backlog",
        "Stories not started: backlog and ready for development.",
        {"state": "opened", "or": {"labelNames": ["status:backlog", "status:ready-for-dev"]}},
    ),
    ViewSpec(
        "BMAD: In progress",
        "Stories being built.",
        {"state": "opened", "labelName": ["status:in-progress"]},
    ),
    ViewSpec(
        "BMAD: Review",
        "Stories built and waiting for review.",
        {"state": "opened", "labelName": ["status:review"]},
    ),
    ViewSpec(
        "BMAD: Done",
        "Stories and epics that are done.",
        {"state": "all", "labelName": ["status:done"]},
    ),
)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PROBLEMS = 3
EXIT_GITLAB = 4


@dataclass(frozen=True)
class _Sprint:
    project: str
    items: tuple[Item, ...]
    problems: tuple[str, ...]
    prefix: str = ""


def main(
    argv: Sequence[str] | None = None,
    *,
    run: Runner = run_glab,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
) -> int:
    """Run ``bmad-gitlab``: 0 done, 2 usage or bad files, 3 problems with ``--apply``, 4 GitLab error."""
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse exits on a usage error and on --help: return the code instead
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    return _sync(args, run, out, err)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bmad-gitlab", description="Mirror a BMAD sprint into GitLab.")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    sync = sub.add_parser("sync", help="Plan or apply a sprint synchronisation.")
    sync.add_argument("--project", required=True, help="GitLab project (GROUP/PROJECT).")
    sync.add_argument(
        "--sprint",
        action="append",
        nargs=2,
        required=True,
        metavar=("STATUS_FILE", "EPICS_FILE"),
        help="A sprint: its sprint-status file and its epics file (repeat for several sprints).",
    )
    sync.add_argument(
        "--prefix",
        action="append",
        default=[],
        metavar="SPRINT=TEXT",
        help="Put TEXT in front of every issue title of the sprint named SPRINT (its `project`), for example "
        "'orbit-extras=[extras]'.",
    )
    sync.add_argument("--hostname", default=None, help="GitLab host, when it is not gitlab.com.")
    sync.add_argument("--no-views", action="store_true", help="Do not create the saved views by status.")
    sync.add_argument("--apply", action="store_true", help="Write to GitLab (the default is a dry run).")
    sync.add_argument("--allow-problems", action="store_true", help="Go on when the files show problems.")
    return parser


def _sync(args: argparse.Namespace, run: Runner, out: TextIO, err: TextIO) -> int:
    sprints = _read_sprints(args.sprint, err)
    if sprints is None:
        return EXIT_USAGE
    sprints = _with_prefixes(sprints, args.prefix, err)
    if sprints is None:
        return EXIT_USAGE
    problems = [problem for sprint in sprints for problem in sprint.problems]
    for problem in problems:
        print(f"problem: {problem}", file=err)
    if args.apply and problems and not args.allow_problems:
        print("error: refusing to apply with problems (use --allow-problems to go on)", file=err)
        return EXIT_PROBLEMS
    client = Client(args.project, run=run, hostname=args.hostname)
    try:
        labels = client.labels()
        issues = client.issues()
    except GitLabError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_GITLAB
    plans = _plan_sprints(sprints, frozenset(labels), issues, out)
    if not args.apply:
        return EXIT_OK
    try:
        _apply_and_board(plans, client, out)
    except GitLabError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_GITLAB
    if not args.no_views:
        _apply_views(client, out, err)
    return EXIT_OK


def _read_sprints(pairs: Sequence[Sequence[str]], err: TextIO) -> list[_Sprint] | None:
    """Read and join every pair of files; ``None`` (after a message) when one cannot be used."""
    sprints: list[_Sprint] = []
    for status_path, epics_path in pairs:
        try:
            given, entries = read_status(_read_text(status_path))
            project = sprint_name(given)
            items, problems = build_items(entries, read_epics(_read_text(epics_path)))
        except (OSError, UnicodeDecodeError, SprintError) as exc:
            print(f"error: {exc}", file=err)
            return None
        if project != given:
            print(
                f"note: the project name {given!r} is written as {project!r} in labels and markers", file=err
            )
        if any(sprint.project == project for sprint in sprints):
            print(f"error: two sprints have the same project name {project!r}", file=err)
            return None
        sprints.append(_Sprint(project, items, problems))
    return sprints


def _with_prefixes(sprints: list[_Sprint], given: Sequence[str], err: TextIO) -> list[_Sprint] | None:
    """Attach each ``SPRINT=TEXT`` to its sprint; ``None`` (after a message) when one cannot be used."""
    prefixes: dict[str, str] = {}
    for entry in given:
        name, _, text = entry.partition("=")
        if not name or not text.strip() or "\n" in text:
            print(f"error: --prefix wants SPRINT=TEXT with a text on one line, got {entry!r}", file=err)
            return None
        prefixes[name] = text.strip()
    unknown = sorted(set(prefixes) - {sprint.project for sprint in sprints})
    if unknown:
        known = ", ".join(sorted(sprint.project for sprint in sprints))
        message = (
            f"--prefix names a sprint that is not given: {', '.join(unknown)} (the sprints are: {known})"
        )
        print(f"error: {message}", file=err)
        return None
    return [replace(sprint, prefix=prefixes.get(sprint.project, "")) for sprint in sprints]


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _plan_sprints(
    sprints: Sequence[_Sprint], labels: frozenset[str], issues: tuple[RemoteIssue, ...], out: TextIO
) -> list[Plan]:
    """Plan the sprints in order; a label that an earlier sprint creates is not created again."""
    plans: list[Plan] = []
    known = set(labels)
    for sprint in sprints:
        plan = make_plan(sprint.project, sprint.items, frozenset(known), issues, sprint.prefix)
        plans.append(plan)
        known.update(action.name for action in plan.actions if isinstance(action, CreateLabel))
        print(render_plan(sprint.project, plan), file=out)
    return plans


def _apply_and_board(plans: Sequence[Plan], client: Client, out: TextIO) -> None:
    for plan in plans:
        print(render_applied(apply(plan, client)), file=out)
    known = client.labels()
    missing = [name for name in BOARD_STATUS_LABELS if name not in known]
    for name in missing:  # the plan only creates the labels that items use; the board needs all four
        client.create_label(name, label_color(name))
    if client.ensure_board(BOARD_NAME, BOARD_STATUS_LABELS):
        extra = f" ({len(missing)} status labels created)" if missing else ""
        print(f"board created{extra}", file=out)


def _apply_views(client: Client, out: TextIO, err: TextIO) -> None:
    """Create or correct the views by status. A refusal is a warning: the issues and the board are done.

    The views need a GitLab that has them, and room for them under the five that a person can show.
    """
    try:
        created, updated = client.ensure_saved_views(STATUS_VIEWS)
    except GitLabError as exc:
        print(f"warning: the views by status were not made: {exc}", file=err)
        return
    print(
        f"views: {created} created, {updated} updated, {len(STATUS_VIEWS) - created - updated} unchanged",
        file=out,
    )
