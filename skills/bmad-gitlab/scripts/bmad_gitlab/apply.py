"""Execute the actions of a plan against a GitLab client."""

from __future__ import annotations

from typing import assert_never

from bmad_gitlab.gitlab import Client, GitLabError
from bmad_gitlab.plan import (
    Action,
    Applied,
    CreateIssue,
    CreateLabel,
    Plan,
    UpdateIssue,
)


def apply(plan: Plan, client: Client) -> Applied:
    """Execute the actions of *plan* against *client* in order.

    The first failure raises :exc:`GitLabError` and stops everything:
    nothing is rolled back, nothing is retried.
    """
    total = Applied(0, 0, 0, 0, 0)
    for done, action in enumerate(plan.actions):
        try:
            total += _execute_one(action, client)
        except GitLabError as exc:
            raise GitLabError(f"{exc} ({done} of {len(plan.actions)} actions were done before it)") from exc
    return total


def _execute_one(action: Action, client: Client) -> Applied:
    """Execute a single action; what it did, as counts."""
    if isinstance(action, CreateLabel):
        client.create_label(action.name, action.color)
        return Applied(1, 0, 0, 0, 0)
    if isinstance(action, CreateIssue):
        iid = client.create_issue(action.title, action.description, action.labels)
        if action.close:
            client.update_issue(iid, state_event="close")
        return Applied(0, 1, 0, 0, 0, issues_created_closed=1 if action.close else 0)
    if isinstance(action, UpdateIssue):
        client.update_issue(
            action.iid,
            title=action.title,
            description=action.description,
            add_labels=action.add_labels,
            remove_labels=action.remove_labels,
            state_event=action.state_event,
        )
        return Applied(0, 0, 1, int(action.state_event == "close"), int(action.state_event == "reopen"))
    assert_never(action)  # a new kind of action must be given a case here: mypy says where
