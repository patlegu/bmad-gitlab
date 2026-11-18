"""Tests for the report module."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bmad_gitlab.apply import Applied
from bmad_gitlab.plan import (
    CreateIssue,
    CreateLabel,
    Plan,
    UpdateIssue,
)
from bmad_gitlab.report import render_applied, render_plan

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _plan(actions=None, warnings=None):
    return Plan(
        actions=tuple(actions or []),
        warnings=tuple(warnings or []),
    )


# ---------------------------------------------------------------------------
# render_plan — empty plan
# ---------------------------------------------------------------------------


class TestRenderPlanEmpty:
    def test_no_actions_no_warnings(self):
        result = render_plan("orbit", _plan())
        assert result == "sprint orbit\nnothing to do"

    def test_only_warnings(self):
        result = render_plan("x", _plan(warnings=["orphan issue"]))
        lines = result.split("\n")
        assert lines[0] == "sprint x"
        assert lines[1] == "! orphan issue"
        assert "1 warnings" in lines[2]


# ---------------------------------------------------------------------------
# render_plan — CreateLabel
# ---------------------------------------------------------------------------


class TestRenderPlanCreateLabel:
    def test_one_label(self):
        result = render_plan("orbit", _plan([CreateLabel("status:backlog", "#95A5A6")]))
        lines = result.split("\n")
        assert lines[0] == "sprint orbit"
        assert lines[1] == "+ label status:backlog #95A5A6"
        assert lines[2] == "1 labels to create, 0 issues to create, 0 issues to update, 0 warnings"


# ---------------------------------------------------------------------------
# render_plan — CreateIssue
# ---------------------------------------------------------------------------


class TestRenderPlanCreateIssue:
    def test_epic_no_close(self):
        result = render_plan(
            "orbit",
            _plan(
                [
                    CreateIssue(
                        key="epic-1",
                        title="Epic 1: Title",
                        description="Body",
                        labels=("type:epic", "status:backlog", "prd:orbit", "epic:orbit:1"),
                        close=False,
                    )
                ]
            ),
        )
        lines = result.split("\n")
        assert lines[0] == "sprint orbit"
        assert '+ issue "Epic 1: Title"' in lines[1]
        assert "then close" not in lines[1]
        assert lines[2] == "0 labels to create, 1 issues to create, 0 issues to update, 0 warnings"

    def test_story_close(self):
        result = render_plan(
            "orbit",
            _plan(
                [
                    CreateIssue(
                        key="1-1-slug",
                        title="Story 1.1: Title",
                        description="Body",
                        labels=("type:story", "status:done", "prd:orbit", "epic:orbit:1"),
                        close=True,
                    )
                ]
            ),
        )
        lines = result.split("\n")
        assert "then close" in lines[1]


# ---------------------------------------------------------------------------
# render_plan — UpdateIssue
# ---------------------------------------------------------------------------


class TestRenderPlanUpdateIssue:
    def test_title_and_labels(self):
        result = render_plan(
            "orbit",
            _plan(
                [
                    UpdateIssue(
                        iid=12,
                        key="1-1-slug",
                        title="New title",
                        description=None,
                        add_labels=("status:review",),
                        remove_labels=("status:backlog",),
                        state_event=None,
                    )
                ]
            ),
        )
        lines = result.split("\n")
        assert "~ issue #12 (key 1-1-slug):" in lines[1]
        assert "title" in lines[1]
        assert "+status:review" in lines[1]
        assert "-status:backlog" in lines[1]

    def test_close_update(self):
        result = render_plan(
            "orbit",
            _plan(
                [
                    UpdateIssue(
                        iid=5,
                        key="epic-2",
                        title=None,
                        description=None,
                        add_labels=(),
                        remove_labels=(),
                        state_event="close",
                    )
                ]
            ),
        )
        assert "close" in result

    def test_reopen_update(self):
        result = render_plan(
            "orbit",
            _plan(
                [
                    UpdateIssue(
                        iid=5,
                        key="epic-2",
                        title=None,
                        description=None,
                        add_labels=(),
                        remove_labels=(),
                        state_event="reopen",
                    )
                ]
            ),
        )
        assert "reopen" in result

    def test_all_fields(self):
        result = render_plan(
            "orbit",
            _plan(
                [
                    UpdateIssue(
                        iid=12,
                        key="1-1-slug",
                        title="New title",
                        description="New body",
                        add_labels=("status:review",),
                        remove_labels=("status:backlog",),
                        state_event="close",
                    )
                ]
            ),
        )
        lines = result.split("\n")
        assert "title" in lines[1]
        assert "description" in lines[1]
        assert "+status:review" in lines[1]
        assert "-status:backlog" in lines[1]
        assert "close" in lines[1]


# ---------------------------------------------------------------------------
# render_plan — warnings
# ---------------------------------------------------------------------------


class TestRenderPlanWarnings:
    def test_one_warning(self):
        result = render_plan("sprint", _plan(warnings=["orphan #5"]))
        assert "! orphan #5" in result

    def test_warning_and_actions(self):
        result = render_plan(
            "sprint",
            _plan(
                actions=[CreateLabel("a", "#111")],
                warnings=["orphan"],
            ),
        )
        assert "+ label a #111" in result
        assert "! orphan" in result


# ---------------------------------------------------------------------------
# render_plan — summary line
# ---------------------------------------------------------------------------


class TestRenderPlanSummary:
    def test_counts(self):
        actions = [
            CreateLabel("a", "#111"),
            CreateLabel("b", "#222"),
            CreateIssue("k1", "E1", "B", ("a",), False),
            UpdateIssue(1, "k2", None, None, (), (), None),
        ]
        result = render_plan("sprint", _plan(actions))
        lines = result.split("\n")
        summary = lines[-1]
        assert summary == "2 labels to create, 1 issues to create, 1 issues to update, 0 warnings"


# ---------------------------------------------------------------------------
# render_applied
# ---------------------------------------------------------------------------


class TestRenderApplied:
    def test_labels_only(self):
        result = render_applied(Applied(3, 0, 0, 0, 0))
        assert result == "created 3 labels, 0 issues"

    def test_issues_only(self):
        result = render_applied(Applied(0, 5, 0, 0, 0))
        assert result == "created 0 labels, 5 issues"

    def test_updates_with_close(self):
        result = render_applied(Applied(0, 0, 2, 1, 0))
        assert result == "updated 2 issues (1 closed, 0 reopened)"

    def test_updates_with_reopen(self):
        result = render_applied(Applied(0, 0, 1, 0, 1))
        assert result == "updated 1 issues (0 closed, 1 reopened)"

    def test_updates_with_both(self):
        result = render_applied(Applied(0, 0, 3, 1, 2))
        assert result == "updated 3 issues (1 closed, 2 reopened)"

    def test_combined(self):
        result = render_applied(Applied(3, 31, 2, 1, 0))
        assert result == "created 3 labels, 31 issues; updated 2 issues (1 closed, 0 reopened)"

    def test_empty(self):
        result = render_applied(Applied(0, 0, 0, 0, 0))
        assert result == "nothing to do"


# ---------------------------------------------------------------------------
# render_plan — exact format from brief
# ---------------------------------------------------------------------------


class TestRenderPlanExactFormat:
    def test_full_example(self):
        actions = [
            CreateLabel("status:backlog", "#95A5A6"),
            CreateIssue(
                "epic-1",
                "Epic 1: Title",
                "B",
                ("type:epic", "status:backlog", "prd:orbit", "epic:orbit:1"),
                False,
            ),
            CreateIssue(
                "1-1-slug",
                "Story 1.1: Title",
                "B",
                ("type:story", "status:backlog", "prd:orbit", "epic:orbit:1"),
                True,
            ),
            UpdateIssue(
                12, "1-1-slug", "New title", "New body", ("status:review",), ("status:backlog",), "close"
            ),
        ]
        result = render_plan("orbit", _plan(actions))
        lines = result.split("\n")
        assert lines[0] == "sprint orbit"
        assert lines[1] == "+ label status:backlog #95A5A6"
        assert '+ issue "Epic 1: Title"' in lines[2]
        assert "then close" in lines[3]
        assert "~ issue #12 (key 1-1-slug):" in lines[4]
        assert "close" in lines[4]


def test_an_action_of_an_unknown_kind_is_not_rendered_as_an_update():
    """The renderers end in assert_never: a new kind of action gets a case, it is not drawn as an update."""
    from bmad_gitlab.report import _counts, _render_action

    with pytest.raises(AssertionError):
        _render_action(object())  # type: ignore[arg-type]

    class _Plan:
        actions = (object(),)

    with pytest.raises(AssertionError):
        _counts(_Plan())  # type: ignore[arg-type]


class TestWhatTheSummariesSay:
    def test_an_issue_created_closed_is_said_under_the_creations(self):
        text = render_applied(Applied(0, 2, 1, 0, 0, issues_created_closed=2))
        assert (
            text
            == "created 0 labels, 2 issues (2 closed as created); updated 1 issues (0 closed, 0 reopened)"
        )

    def test_nothing_is_said_of_a_closing_when_none_was_made_at_creation(self):
        assert render_applied(Applied(1, 2, 0, 0, 0)) == "created 1 labels, 2 issues"

    def test_an_update_that_only_adds_or_only_removes_labels(self):
        only_add = UpdateIssue(1, "k", None, None, ("a",), (), None)
        only_remove = UpdateIssue(2, "k", None, None, (), ("b",), None)
        assert _line(only_add) == "~ issue #1 (key k): labels +a"
        assert _line(only_remove) == "~ issue #2 (key k): labels -b"


def _line(action):
    from bmad_gitlab.report import _render_action

    return _render_action(action)
