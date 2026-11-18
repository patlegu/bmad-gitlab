"""Tests for the apply module."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bmad_gitlab.apply import Applied, apply
from bmad_gitlab.gitlab import GitLabError
from bmad_gitlab.plan import CreateIssue, CreateLabel, Plan, UpdateIssue
from fake_gitlab import FakeGitLab

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(fake=None):
    if fake is None:
        fake = FakeGitLab()
    from bmad_gitlab.gitlab import Client

    return Client("test-project", run=fake), fake


def _plan(actions=None, warnings=None):
    return Plan(
        actions=tuple(actions or []),
        warnings=tuple(warnings or []),
    )


# ---------------------------------------------------------------------------
# apply — empty plan
# ---------------------------------------------------------------------------


class TestApplyEmptyPlan:
    def test_no_call_for_empty_plan(self):
        c, fake = _client()
        result = apply(_plan(), c)
        assert result == Applied(0, 0, 0, 0, 0)
        assert fake.calls == []

    def test_no_call_for_plan_with_only_warnings(self):
        c, fake = _client()
        result = apply(_plan(warnings=["something"]), c)
        assert result == Applied(0, 0, 0, 0, 0)
        assert fake.calls == []


# ---------------------------------------------------------------------------
# apply — CreateLabel
# ---------------------------------------------------------------------------


class TestApplyCreateLabel:
    def test_creates_label_and_counts(self):
        c, fake = _client()
        result = apply(_plan([CreateLabel("status:backlog", "#95A5A6")]), c)
        assert result.labels_created == 1
        assert fake._labels["status:backlog"] == 1

    def test_multiple_labels(self):
        c, _fake = _client()
        actions = [
            CreateLabel("a", "#111111"),
            CreateLabel("b", "#222222"),
        ]
        result = apply(_plan(actions), c)
        assert result.labels_created == 2


# ---------------------------------------------------------------------------
# apply — CreateIssue
# ---------------------------------------------------------------------------


class TestApplyCreateIssue:
    def test_creates_issue_and_counts(self):
        c, _fake = _client()
        action = CreateIssue(
            key="epic-1",
            title="Epic 1: Title",
            description="Body",
            labels=("type:epic", "status:backlog"),
            close=False,
        )
        result = apply(_plan([action]), c)
        assert result.issues_created == 1

    def test_close_after_creation(self):
        c, fake = _client()
        action = CreateIssue(
            key="epic-1",
            title="Epic 1: Title",
            description="Body",
            labels=("type:epic", "status:done"),
            close=True,
        )
        result = apply(_plan([action]), c)
        assert result.issues_created == 1
        assert result.issues_created_closed == 1
        assert result.issues_closed == 0  # that count is for updates
        # The issue should be closed in the fake
        assert fake._issues[0]["state"] == "closed"

    def test_close_is_second_call(self):
        c, fake = _client()
        action = CreateIssue(
            key="epic-1",
            title="Epic 1: Title",
            description="Body",
            labels=("type:epic", "status:done"),
            close=True,
        )
        apply(_plan([action]), c)
        # First call: POST issue, second call: PUT update
        assert len(fake.calls) == 2
        assert fake.calls[0]["args"][-1] == "projects/test-project/issues"
        assert fake.calls[1]["args"][-1] == "projects/test-project/issues/1"


# ---------------------------------------------------------------------------
# apply — UpdateIssue
# ---------------------------------------------------------------------------


class TestApplyUpdateIssue:
    def test_updates_issue_and_counts(self):
        c, fake = _client()
        fake._issues.append(
            {
                "iid": 1,
                "title": "Old",
                "description": "D",
                "labels": [],
                "state": "opened",
            }
        )
        action = UpdateIssue(
            iid=1,
            key="epic-1",
            title="New Title",
            description=None,
            add_labels=("a",),
            remove_labels=(),
            state_event=None,
        )
        result = apply(_plan([action]), c)
        assert result.issues_updated == 1
        assert fake._issues[0]["title"] == "New Title"
        assert "a" in fake._issues[0]["labels"]

    def test_close_update_counts(self):
        c, fake = _client()
        fake._issues.append(
            {
                "iid": 1,
                "title": "T",
                "description": "D",
                "labels": [],
                "state": "opened",
            }
        )
        action = UpdateIssue(
            iid=1,
            key="epic-1",
            title=None,
            description=None,
            add_labels=(),
            remove_labels=(),
            state_event="close",
        )
        result = apply(_plan([action]), c)
        assert result.issues_updated == 1
        assert result.issues_closed == 1

    def test_reopen_update_counts(self):
        c, fake = _client()
        fake._issues.append(
            {
                "iid": 1,
                "title": "T",
                "description": "D",
                "labels": [],
                "state": "closed",
            }
        )
        action = UpdateIssue(
            iid=1,
            key="epic-1",
            title=None,
            description=None,
            add_labels=(),
            remove_labels=(),
            state_event="reopen",
        )
        result = apply(_plan([action]), c)
        assert result.issues_updated == 1
        assert result.issues_reopened == 1


# ---------------------------------------------------------------------------
# apply — order: labels before issues
# ---------------------------------------------------------------------------


class TestApplyOrder:
    def test_labels_before_issues(self):
        c, fake = _client()
        actions = [
            CreateLabel("a", "#111111"),
            CreateIssue(
                key="epic-1",
                title="Epic 1: T",
                description="B",
                labels=("a",),
                close=False,
            ),
        ]
        apply(_plan(actions), c)
        # First call should be create_label, then create_issue
        assert fake.calls[0]["args"][-1] == "projects/test-project/labels"
        assert fake.calls[1]["args"][-1] == "projects/test-project/issues"


# ---------------------------------------------------------------------------
# apply — stop at first failure
# ---------------------------------------------------------------------------


class TestApplyStopOnFailure:
    def test_raises_GitLabError_on_failure(self):
        c, fake = _client()
        fake._fail_nth = 1  # fail on first call
        with pytest.raises(GitLabError):
            apply(_plan([CreateLabel("a", "#111111")]), c)

    def test_nothing_after_first_failure(self):
        c, fake = _client()
        # Fail on the second action (the issue creation)
        fake._fail_nth = 2
        actions = [
            CreateLabel("a", "#111111"),
            CreateLabel("b", "#222222"),
        ]
        with pytest.raises(GitLabError):
            apply(_plan(actions), c)
        # Only the first label was created
        assert "a" in fake._labels
        assert "b" not in fake._labels

    def test_create_issue_fails_nothing_after(self):
        c, fake = _client()
        fake._issues.append(
            {
                "iid": 1,
                "title": "T",
                "description": "D",
                "labels": [],
                "state": "opened",
            }
        )
        # Fail on the update_issue call (second action)
        fake._fail_nth = 2
        actions = [
            UpdateIssue(1, "k", None, None, (), (), "close"),
            UpdateIssue(1, "k", "New", None, (), (), None),
        ]
        with pytest.raises(GitLabError):
            apply(_plan(actions), c)
        # First update (close) succeeded, second (title change) failed
        assert fake._issues[0]["state"] == "closed"
        assert fake._issues[0]["title"] == "T"


# ---------------------------------------------------------------------------
# apply — counters are accurate
# ---------------------------------------------------------------------------


class TestApplyCounters:
    def test_combined_counters(self):
        c, fake = _client()
        fake._issues.append(
            {
                "iid": 1,
                "title": "T",
                "description": "D",
                "labels": [],
                "state": "closed",
            }
        )
        actions = [
            CreateLabel("a", "#111111"),
            CreateIssue(
                key="epic-1",
                title="Epic 1: T",
                description="B",
                labels=("a",),
                close=True,
            ),
            UpdateIssue(
                iid=1,
                key="epic-1",
                title=None,
                description=None,
                add_labels=(),
                remove_labels=(),
                state_event="reopen",
            ),
        ]
        result = apply(_plan(actions), c)
        assert result.labels_created == 1
        assert result.issues_created == 1
        assert result.issues_updated == 1
        assert result.issues_created_closed == 1  # from CreateIssue
        assert result.issues_closed == 0
        assert result.issues_reopened == 1  # from UpdateIssue


# ---------------------------------------------------------------------------
# apply — only given fields
# ---------------------------------------------------------------------------


class TestApplyOnlyGivenFields:
    def test_update_issue_passes_only_non_none(self):
        c, fake = _client()
        fake._issues.append(
            {
                "iid": 1,
                "title": "T",
                "description": "D",
                "labels": [],
                "state": "opened",
            }
        )
        action = UpdateIssue(
            iid=1,
            key="k",
            title="New",
            description=None,
            add_labels=(),
            remove_labels=(),
            state_event=None,
        )
        apply(_plan([action]), c)
        body = __import__("json").loads(fake.calls[-1]["stdin"])
        assert body == {"title": "New"}


def test_an_action_of_an_unknown_kind_is_not_skipped_in_silence():
    """A fourth kind of action added to the plan without a case in the executor must stop the run."""
    from bmad_gitlab.apply import _execute_one

    with pytest.raises(AssertionError):
        _execute_one(object(), None)  # type: ignore[arg-type]


def test_a_failure_says_how_many_actions_were_done_before_it():
    c, fake = _client()
    fake._fail_nth = 3
    actions = [CreateLabel("a", "#111111"), CreateLabel("b", "#222222"), CreateLabel("c", "#333333")]
    with pytest.raises(GitLabError, match=r"\(2 of 3 actions were done before it\)"):
        apply(_plan(actions), c)


def test_an_issue_created_open_counts_no_closing():
    c, _ = _client()
    action = CreateIssue("k", "T", "D", ("type:epic",), close=False)
    result = apply(_plan([action]), c)
    assert (result.issues_created, result.issues_created_closed, result.issues_closed) == (1, 0, 0)
