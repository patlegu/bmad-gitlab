"""Decide what to create or change in GitLab for a BMAD sprint."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from bmad_gitlab.model import Item, RemoteIssue


@dataclass(frozen=True)
class CreateLabel:
    """Create the label ``name`` with this colour."""

    name: str
    color: str  # "#RRGGBB"


@dataclass(frozen=True)
class CreateIssue:
    """Create an issue for the item with this key, and close it when ``close``."""

    key: str
    title: str
    description: str
    labels: tuple[str, ...]
    close: bool  # True when status is "done"


@dataclass(frozen=True)
class UpdateIssue:
    """Change issue ``iid``: only what is not ``None`` or empty differs from what GitLab holds."""

    iid: int
    key: str
    title: str | None  # None = unchanged
    description: str | None  # None = unchanged
    add_labels: tuple[str, ...]
    remove_labels: tuple[str, ...]
    state_event: Literal["close", "reopen"] | None


@dataclass(frozen=True)
class Marker:
    """What the hidden marker of an issue says: its sprint, its BMAD key and the hash of its source text."""

    sprint: str
    key: str
    digest: str


Action = CreateLabel | CreateIssue | UpdateIssue


@dataclass(frozen=True)
class Plan:
    """The actions that bring GitLab in step with a sprint, and what was seen on the way."""

    actions: tuple[Action, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class Applied:
    """What a run did, as counts; ``issues_closed`` counts the updates that closed an issue, and
    ``issues_created_closed`` the issues that were closed as they were created."""

    labels_created: int
    issues_created: int
    issues_updated: int
    issues_closed: int
    issues_reopened: int
    issues_created_closed: int = 0

    def __add__(self, other: Applied) -> Applied:
        return Applied(
            self.labels_created + other.labels_created,
            self.issues_created + other.issues_created,
            self.issues_updated + other.issues_updated,
            self.issues_closed + other.issues_closed,
            self.issues_reopened + other.issues_reopened,
            self.issues_created_closed + other.issues_created_closed,
        )


# ---------------------------------------------------------------------------
# Labels and their colours
# ---------------------------------------------------------------------------

_STATIC_COLORS: dict[str, str] = {
    "type:epic": "#6B5CE7",
    "type:story": "#428BCA",
    "status:backlog": "#95A5A6",
    "status:ready-for-dev": "#F0AD4E",
    "status:in-progress": "#3498DB",
    "status:review": "#E67E22",
    "status:done": "#44AD8E",
}
# The status labels the tool owns: a label of the same family that a person added is left alone.
_STATUS_LABELS = frozenset(name for name in _STATIC_COLORS if name.startswith("status:"))
_PRD_COLOR = "#6C757D"
_EPIC_COLORS = (
    "#428BCA", "#44AD8E", "#F0AD4E", "#D9534F", "#6B5CE7",
    "#1ABC9C", "#E74C8B", "#95A5A6", "#3498DB", "#E67E22",
)  # fmt: skip

_MARKER_RE = re.compile(r"<!--\s*bmad:v1\s+sprint=(\S+)\s+key=(\S+)\s+hash=(\S+)\s*-->")


def issue_title(item: Item, prefix: str = "") -> str:
    """The issue title of an epic or a story, behind ``prefix`` when given (``[extras] Story 1.1: ...``)."""
    base = (
        f"Epic {item.epic}: {item.title}"
        if item.kind == "epic"
        else f"Story {item.epic}.{item.story}: {item.title}"
    )
    return f"{prefix} {base}" if prefix else base


def item_labels(sprint: str, item: Item) -> tuple[str, ...]:
    """The labels an item needs, in the order: type, status, sprint, epic."""
    return (
        "type:epic" if item.kind == "epic" else "type:story",
        f"status:{item.status}",
        f"prd:{sprint}",
        f"epic:{sprint}:{item.epic}",
    )


def label_color(name: str) -> str:
    """The colour of a label name; an unknown family is an error, never a default."""
    if name in _STATIC_COLORS:
        return _STATIC_COLORS[name]
    if name.startswith("prd:"):
        return _PRD_COLOR
    if name.startswith("epic:"):
        number = name.rsplit(":", 1)[1]
        if number.isdigit() and int(number) >= 1:
            return _EPIC_COLORS[(int(number) - 1) % len(_EPIC_COLORS)]
    raise ValueError(f"no colour for label {name!r}")


def source_hash(item: Item, prefix: str = "") -> str:
    """The first 12 hex digits of the SHA-256 of the title and the body: the identity of the source text."""
    return hashlib.sha256(f"{issue_title(item, prefix)}\n{item.body}".encode()).hexdigest()[:12]


def render_description(sprint: str, item: Item, prefix: str = "") -> str:
    """The body of the item and the hidden marker that ties the issue to its BMAD key."""
    footer = f"---\n<!-- bmad:v1 sprint={sprint} key={item.key} hash={source_hash(item, prefix)} -->"
    return f"{item.body}\n\n{footer}" if item.body else footer


def parse_marker(description: str) -> Marker | None:
    """The LAST marker of a description, or ``None``."""
    found = [Marker(*match.groups()) for match in _MARKER_RE.finditer(description)]
    return found[-1] if found else None


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


def _label_actions(sprint: str, items: tuple[Item, ...], labels: frozenset[str]) -> list[Action]:
    missing = dict.fromkeys(
        name for item in items for name in item_labels(sprint, item) if name not in labels
    )
    return [CreateLabel(name, label_color(name)) for name in missing]


def _issues_by_key(sprint: str, issues: tuple[RemoteIssue, ...]) -> dict[str, list[RemoteIssue]]:
    """The issues of this sprint (by their marker) grouped by BMAD key; others are not ours."""
    grouped: dict[str, list[RemoteIssue]] = {}
    for issue in issues:
        marker = parse_marker(issue.description)
        if marker is not None and marker.sprint == sprint:
            grouped.setdefault(marker.key, []).append(issue)
    return grouped


def _state_event(item: Item, remote: RemoteIssue) -> Literal["close", "reopen"] | None:
    if item.status == "done":
        return "close" if remote.state == "opened" else None
    return "reopen" if remote.state == "closed" else None


def _update(sprint: str, item: Item, remote: RemoteIssue, prefix: str) -> UpdateIssue | None:
    """What differs between an issue and its item, or ``None`` when nothing does."""
    title = issue_title(item, prefix)
    marker = parse_marker(remote.description)
    wanted_labels = item_labels(sprint, item)
    wanted_status = f"status:{item.status}"
    update = UpdateIssue(
        iid=remote.iid,
        key=item.key,
        title=title if title != remote.title else None,
        description=(
            render_description(sprint, item, prefix)
            if marker is None or marker.digest != source_hash(item, prefix)
            else None
        ),
        add_labels=tuple(name for name in wanted_labels if name not in remote.labels),
        remove_labels=tuple(name for name in remote.labels if name in _STATUS_LABELS - {wanted_status}),
        state_event=_state_event(item, remote),
    )
    changes = (update.title, update.description, update.add_labels, update.remove_labels, update.state_event)
    return update if any(change for change in changes) else None


def _create(sprint: str, item: Item, prefix: str) -> CreateIssue:
    return CreateIssue(
        key=item.key,
        title=issue_title(item, prefix),
        description=render_description(sprint, item, prefix),
        labels=item_labels(sprint, item),
        close=item.status == "done",
    )


def _orphan_warnings(grouped: dict[str, list[RemoteIssue]], item_keys: set[str]) -> list[str]:
    orphans = sorted(
        (issue.iid, key) for key, found in grouped.items() if key not in item_keys for issue in found
    )
    return [f"issue #{iid} (key {key}) has no entry in the sprint status" for iid, key in orphans]


def plan(
    sprint: str,
    items: tuple[Item, ...],
    labels: frozenset[str],
    issues: tuple[RemoteIssue, ...],
    prefix: str = "",
) -> Plan:
    """What to create or change in GitLab so that its issues mirror ``items`` (no retrospectives).

    ``prefix`` goes in front of every title of the sprint, to tell apart two sprints that share numbers.
    """
    wanted = tuple(item for item in items if item.kind != "retrospective")
    grouped = _issues_by_key(sprint, issues)
    actions = _label_actions(sprint, wanted, labels)
    warnings: list[str] = []
    for item in wanted:
        found = grouped.get(item.key, [])
        if len(found) > 1:
            iids = ", ".join(f"#{iid}" for iid in sorted(issue.iid for issue in found))
            warnings.append(f"key {item.key} has {len(found)} issues: {iids}; nothing done for it")
        elif not found:
            actions.append(_create(sprint, item, prefix))
        elif (update := _update(sprint, item, found[0], prefix)) is not None:
            actions.append(update)
    warnings.extend(_orphan_warnings(grouped, {item.key for item in wanted}))
    return Plan(actions=tuple(actions), warnings=tuple(warnings))
