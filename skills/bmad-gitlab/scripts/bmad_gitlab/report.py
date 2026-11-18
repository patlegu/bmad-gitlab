"""Render dry-run and applied summaries for a BMAD sprint plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from bmad_gitlab.plan import (
    Action,
    Applied,
    CreateIssue,
    CreateLabel,
    Plan,
    UpdateIssue,
)


def render_plan(sprint: str, plan: Plan) -> str:
    """Return the text of a dry run for one sprint.

    One line per action and per warning, then a summary line.
    """
    lines: list[str] = [f"sprint {sprint}"]

    for action in plan.actions:
        lines.append(_render_action(action))

    for warning in plan.warnings:
        lines.append(f"! {warning}")

    if not plan.actions and not plan.warnings:
        return f"sprint {sprint}\nnothing to do"

    counts = _counts(plan)
    summary = (
        f"{counts.labels} labels to create, "
        f"{counts.issues} issues to create, "
        f"{counts.updates} issues to update, "
        f"{len(plan.warnings)} warnings"
    )
    lines.append(summary)
    return "\n".join(lines)


def render_applied(applied: Applied) -> str:
    """``created 3 labels, 31 issues; updated 2 issues (1 closed, 0 reopened)``, or ``nothing to do``."""
    parts: list[str] = []
    if applied.labels_created or applied.issues_created:
        created = f"created {applied.labels_created} labels, {applied.issues_created} issues"
        if applied.issues_created_closed:
            created += f" ({applied.issues_created_closed} closed as created)"
        parts.append(created)
    if applied.issues_updated:
        parts.append(
            f"updated {applied.issues_updated} issues "
            f"({applied.issues_closed} closed, {applied.issues_reopened} reopened)"
        )
    return "; ".join(parts) if parts else "nothing to do"


def _render_action(action: Action) -> str:
    if isinstance(action, CreateLabel):
        return f"+ label {action.name} {action.color}"
    if isinstance(action, CreateIssue):
        line = f'+ issue "{action.title}" [{" ".join(action.labels)}]'
        return f"{line} then close" if action.close else line
    if isinstance(action, UpdateIssue):
        return _render_update_issue(action)
    assert_never(action)  # a new kind of action must be given a case here: mypy says where


def _render_update_issue(action: UpdateIssue) -> str:
    """``~ issue #12 (key 1-1-slug): title, description, labels +a -b, close`` (only what changes)."""
    changes: list[str] = []
    if action.title is not None:
        changes.append("title")
    if action.description is not None:
        changes.append("description")
    if action.add_labels or action.remove_labels:
        changes.append(
            "labels "
            + " ".join(
                [*(f"+{name}" for name in action.add_labels), *(f"-{name}" for name in action.remove_labels)]
            )
        )
    if action.state_event is not None:
        changes.append(action.state_event)
    return f"~ issue #{action.iid} (key {action.key}): {', '.join(changes)}"


@dataclass(frozen=True)
class _Counts:
    labels: int
    issues: int
    updates: int


def _counts(plan: Plan) -> _Counts:
    labels = 0
    issues = 0
    updates = 0
    for action in plan.actions:
        if isinstance(action, CreateLabel):
            labels += 1
        elif isinstance(action, CreateIssue):
            issues += 1
        elif isinstance(action, UpdateIssue):
            updates += 1
        else:
            assert_never(action)
    return _Counts(labels, issues, updates)
