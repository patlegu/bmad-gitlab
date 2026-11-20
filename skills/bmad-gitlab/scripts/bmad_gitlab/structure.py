"""A milestone for each epic and a checklist of its stories: the progress that GitLab Premium shows
for its epics, on the free tier.

The milestone of an epic holds its stories, so GitLab draws the bar and lists the epics itself; the
issue of the epic carries the list of its stories as task-list items, so its own progress shows in
the lists and on the board. Both are planned from what GitLab holds (never from memory) and run
after the issues exist, so they are as idempotent as the issues are.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from bmad_gitlab.gitlab import Client
from bmad_gitlab.model import Item, RemoteIssue, RemoteMilestone
from bmad_gitlab.plan import issue_title, issues_by_key, render_description


@dataclass(frozen=True)
class CreateMilestone:
    """Create the milestone ``title`` (active)."""

    title: str
    description: str


@dataclass(frozen=True)
class ReopenMilestone:
    """Open the closed milestone ``title`` again: its epic is not done."""

    title: str


@dataclass(frozen=True)
class AssignMilestone:
    """Put issue ``iid`` in the milestone ``title``."""

    iid: int
    title: str


@dataclass(frozen=True)
class WriteChecklist:
    """Replace the description of the epic issue ``iid`` by one that lists its stories."""

    iid: int
    key: str
    description: str


@dataclass(frozen=True)
class CloseMilestone:
    """Close the milestone ``title``: its epic is done."""

    title: str


StructureAction = CreateMilestone | ReopenMilestone | AssignMilestone | WriteChecklist | CloseMilestone


@dataclass(frozen=True)
class StructureOptions:
    """Which parts to make: the milestone of each epic, the checklist in its issue."""

    milestones: bool = True
    checklists: bool = True


@dataclass(frozen=True)
class StructureApplied:
    """What a run did, as counts."""

    milestones_created: int = 0
    milestones_closed: int = 0
    milestones_reopened: int = 0
    issues_assigned: int = 0
    checklists_written: int = 0


def checklist(stories: list[tuple[Item, RemoteIssue]]) -> str:
    """The stories of an epic as task-list items: ticked when the story is done, with its issue number."""
    lines = []
    for item, remote in stories:
        box = "x" if item.status == "done" else " "
        lines.append(f"- [{box}] Story {item.epic}.{item.story}: {item.title} (#{remote.iid})")
    return "### Stories\n\n" + "\n".join(lines)


def _same_text(left: str, right: str) -> bool:
    """Two descriptions are the same text: GitLab may change line ends and the space at the ends."""
    return left.replace("\r\n", "\n").strip() == right.replace("\r\n", "\n").strip()


@dataclass
class _Steps:
    """The actions of one run, in the order that works: open, then work, then close."""

    opening: list[StructureAction]
    working: list[StructureAction]
    closing: list[StructureAction]


def plan_structure(
    sprint: str,
    items: tuple[Item, ...],
    issues: tuple[RemoteIssue, ...],
    milestones: tuple[RemoteMilestone, ...],
    prefix: str = "",
    options: StructureOptions = StructureOptions(),
) -> tuple[StructureAction, ...]:
    """What to do so that each epic has its milestone and its checklist.

    Only the epics that have at least one story with exactly one issue are handled, and only the
    issues that exist now: a story created in this run is handled by the next call. The order is
    the one that works: create and reopen, then assign and write, then close (GitLab does not take an
    issue into a closed milestone).
    """
    wanted = tuple(item for item in items if item.kind != "retrospective")
    single = {key: found[0] for key, found in issues_by_key(sprint, issues).items() if len(found) == 1}
    known = {milestone.title: milestone for milestone in milestones}
    steps = _Steps([], [], [])
    for epic in (item for item in wanted if item.kind == "epic"):
        stories = _stories_of(epic, wanted, single)
        if not stories:
            continue
        if options.milestones:
            _plan_milestone(epic, stories, issue_title(epic, prefix), known, steps)
        if options.checklists and epic.key in single:
            remote = single[epic.key]
            wanted_text = render_description(sprint, epic, prefix, checklist(stories))
            if not _same_text(remote.description, wanted_text):
                steps.working.append(WriteChecklist(remote.iid, epic.key, wanted_text))
    return (*steps.opening, *steps.working, *steps.closing)


def _stories_of(
    epic: Item, wanted: tuple[Item, ...], single: dict[str, RemoteIssue]
) -> list[tuple[Item, RemoteIssue]]:
    """The stories of an epic that have one issue, in story order."""
    found = [
        (item, single[item.key])
        for item in wanted
        if item.kind == "story" and item.epic == epic.epic and item.key in single
    ]
    return sorted(found, key=lambda pair: pair[0].story or 0)


def _plan_milestone(
    epic: Item,
    stories: list[tuple[Item, RemoteIssue]],
    title: str,
    known: dict[str, RemoteMilestone],
    steps: _Steps,
) -> None:
    """The milestone of one epic: created or reopened, its stories put in it, closed when the epic is done."""
    found = known.get(title)
    if found is None:
        steps.opening.append(CreateMilestone(title, f"Stories of epic {epic.epic}, kept by bmad-gitlab."))
    elif found.state == "closed" and epic.status != "done":
        steps.opening.append(ReopenMilestone(title))
    steps.working.extend(
        AssignMilestone(remote.iid, title) for _, remote in stories if remote.milestone != title
    )
    if epic.status == "done" and (found is None or found.state == "active"):
        steps.closing.append(CloseMilestone(title))


def apply_structure(actions: tuple[StructureAction, ...], client: Client) -> StructureApplied:
    """Execute the actions in order; the first failure raises ``GitLabError`` and stops everything."""
    needs_ids = any(not isinstance(action, WriteChecklist) for action in actions)
    ids = {milestone.title: milestone.id for milestone in client.milestones()} if needs_ids else {}
    total = StructureApplied()
    for action in actions:
        total = _add(total, _execute_one(action, client, ids))
    return total


def _execute_one(action: StructureAction, client: Client, ids: dict[str, int]) -> StructureApplied:
    if isinstance(action, CreateMilestone):
        ids[action.title] = client.create_milestone(action.title, action.description)
        return StructureApplied(milestones_created=1)
    if isinstance(action, ReopenMilestone):
        client.update_milestone(ids[action.title], "activate")
        return StructureApplied(milestones_reopened=1)
    if isinstance(action, AssignMilestone):
        client.set_milestone(action.iid, ids[action.title])
        return StructureApplied(issues_assigned=1)
    if isinstance(action, WriteChecklist):
        client.update_issue(action.iid, description=action.description)
        return StructureApplied(checklists_written=1)
    if isinstance(action, CloseMilestone):
        client.update_milestone(ids[action.title], "close")
        return StructureApplied(milestones_closed=1)
    assert_never(action)  # a new kind of action must be given a case here: mypy says where


def _add(left: StructureApplied, right: StructureApplied) -> StructureApplied:
    return StructureApplied(
        left.milestones_created + right.milestones_created,
        left.milestones_closed + right.milestones_closed,
        left.milestones_reopened + right.milestones_reopened,
        left.issues_assigned + right.issues_assigned,
        left.checklists_written + right.checklists_written,
    )


def render_structure_plan(actions: tuple[StructureAction, ...]) -> str:
    """One line per action, or ``structure: nothing to do``."""
    if not actions:
        return "structure: nothing to do"
    lines = ["structure"]
    for action in actions:
        if isinstance(action, CreateMilestone):
            lines.append(f'+ milestone "{action.title}"')
        elif isinstance(action, ReopenMilestone):
            lines.append(f'~ milestone "{action.title}": reopen')
        elif isinstance(action, CloseMilestone):
            lines.append(f'~ milestone "{action.title}": close')
        elif isinstance(action, AssignMilestone):
            lines.append(f'~ issue #{action.iid}: milestone "{action.title}"')
        elif isinstance(action, WriteChecklist):
            lines.append(f"~ issue #{action.iid} (key {action.key}): checklist of stories")
        else:
            assert_never(action)
    return "\n".join(lines)


def render_structure_applied(applied: StructureApplied) -> str:
    """``milestones: 2 created, 1 closed, 0 reopened; 7 issues assigned; 2 checklists written``."""
    if applied == StructureApplied():
        return "structure: nothing to do"
    return (
        f"milestones: {applied.milestones_created} created, {applied.milestones_closed} closed, "
        f"{applied.milestones_reopened} reopened; {applied.issues_assigned} issues assigned; "
        f"{applied.checklists_written} checklists written"
    )
