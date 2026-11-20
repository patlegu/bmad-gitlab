"""The milestone of each epic and the checklist of its stories."""

from __future__ import annotations

import os
import sys

import pytest

from bmad_gitlab.gitlab import Client, GitLabError, Reply
from bmad_gitlab.model import Item, RemoteIssue, RemoteMilestone
from bmad_gitlab.plan import render_description
from bmad_gitlab.structure import (
    AssignMilestone,
    CloseMilestone,
    CreateMilestone,
    ReopenMilestone,
    StructureApplied,
    StructureOptions,
    WriteChecklist,
    apply_structure,
    checklist,
    plan_structure,
    render_structure_applied,
    render_structure_plan,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_gitlab import FakeGitLab

SPRINT = "demo"


def _epic(n: int, status: str = "in-progress", body: str = "") -> Item:
    return Item("epic", f"epic-{n}", n, None, status, f"Epic title {n}", body)


def _story(epic: int, n: int, status: str = "backlog") -> Item:
    return Item("story", f"{epic}-{n}-s", epic, n, status, f"Story title {epic}.{n}", "")


def _remote(
    item: Item, iid: int, *, milestone: str | None = None, description: str | None = None
) -> RemoteIssue:
    return RemoteIssue(
        iid=iid,
        title="t",
        description=description if description is not None else render_description(SPRINT, item),
        labels=(),
        state="opened",
        milestone=milestone,
    )


def _world(statuses: tuple[str, ...] = ("backlog", "backlog"), epic_status: str = "in-progress"):
    epic = _epic(1, epic_status)
    stories = [_story(1, n + 1, status) for n, status in enumerate(statuses)]
    items = (epic, *stories)
    issues = (_remote(epic, 1), *(_remote(story, 2 + n) for n, story in enumerate(stories)))
    return items, issues


# --- the checklist -----------------------------------------------------------------------------


def test_the_checklist_ticks_the_done_stories_and_names_their_issues():
    items, issues = _world(("done", "backlog"))
    pairs = [(items[1], issues[1]), (items[2], issues[2])]
    assert checklist(pairs) == (
        "### Stories\n\n- [x] Story 1.1: Story title 1.1 (#2)\n- [ ] Story 1.2: Story title 1.2 (#3)"
    )


# --- the plan ----------------------------------------------------------------------------------


def test_a_new_epic_gets_its_milestone_its_stories_and_its_checklist_in_that_order():
    items, issues = _world()
    actions = plan_structure(SPRINT, items, issues, ())
    title = "Epic 1: Epic title 1"
    assert actions[0] == CreateMilestone(title, "Stories of epic 1, kept by bmad-gitlab.")
    assert actions[1:3] == (AssignMilestone(2, title), AssignMilestone(3, title))
    assert isinstance(actions[3], WriteChecklist) and actions[3].iid == 1
    assert len(actions) == 4


def test_the_checklist_keeps_the_body_and_ends_with_the_marker():
    epic = _epic(1, body="What this epic is.")
    story = _story(1, 1)
    text = plan_structure(SPRINT, (epic, story), (_remote(epic, 1), _remote(story, 2)), ())[-1]
    assert isinstance(text, WriteChecklist)
    assert text.description.startswith("What this epic is.\n\n### Stories\n\n- [ ] Story 1.1")
    assert text.description.rstrip().endswith("-->")
    assert text.description.count("bmad:v1") == 1


def test_a_second_run_with_nothing_changed_plans_nothing():
    items, issues = _world(("done", "backlog"))
    title = "Epic 1: Epic title 1"
    pairs = [(items[1], issues[1]), (items[2], issues[2])]
    done = (
        _remote(items[0], 1, description=render_description(SPRINT, items[0], "", checklist(pairs))),
        _remote(items[1], 2, milestone=title),
        _remote(items[2], 3, milestone=title),
    )
    assert plan_structure(SPRINT, items, done, (RemoteMilestone(1, title, "active"),)) == ()


def test_a_description_that_differs_only_by_line_ends_and_edge_space_is_the_same():
    items, issues = _world()
    pairs = [(items[1], issues[1]), (items[2], issues[2])]
    text = render_description(SPRINT, items[0], "", checklist(pairs))
    changed = (_remote(items[0], 1, description="\r\n" + text.replace("\n", "\r\n") + "\r\n"), *issues[1:])
    actions = plan_structure(SPRINT, items, changed, (), options=StructureOptions(milestones=False))
    assert actions == ()


def test_a_story_that_became_done_ticks_its_box():
    items, issues = _world(("done", "backlog"))
    stale = (_remote(items[0], 1), *issues[1:])
    actions = plan_structure(SPRINT, items, stale, (), options=StructureOptions(milestones=False))
    assert isinstance(actions[0], WriteChecklist) and "- [x] Story 1.1" in actions[0].description


def test_a_done_epic_closes_its_milestone_after_its_stories_are_in_it():
    items, issues = _world(("done", "done"), "done")
    actions = plan_structure(SPRINT, items, issues, ())
    assert [type(a) for a in actions] == [
        CreateMilestone,
        AssignMilestone,
        AssignMilestone,
        WriteChecklist,
        CloseMilestone,
    ]


def test_an_epic_that_is_not_done_reopens_a_closed_milestone_before_anything_else():
    items, issues = _world()
    title = "Epic 1: Epic title 1"
    actions = plan_structure(SPRINT, items, issues, (RemoteMilestone(7, title, "closed"),))
    assert actions[0] == ReopenMilestone(title)
    assert not any(isinstance(a, CreateMilestone) for a in actions)


def test_a_done_epic_whose_milestone_is_already_closed_is_left_alone():
    items, issues = _world(("done", "done"), "done")
    title = "Epic 1: Epic title 1"
    issues = (issues[0], *(_remote(i, n + 2, milestone=title) for n, i in enumerate(items[1:])))
    actions = plan_structure(
        SPRINT,
        items,
        issues,
        (RemoteMilestone(7, title, "closed"),),
        options=StructureOptions(checklists=False),
    )
    assert actions == ()


def test_an_issue_in_another_milestone_is_moved():
    items, issues = _world()
    title = "Epic 1: Epic title 1"
    moved = (issues[0], _remote(items[1], 2, milestone="Old"), _remote(items[2], 3, milestone=title))
    actions = plan_structure(
        SPRINT,
        items,
        moved,
        (RemoteMilestone(1, title, "active"),),
        options=StructureOptions(checklists=False),
    )
    assert actions == (AssignMilestone(2, title),)


def test_the_prefix_is_in_the_title_of_the_milestone():
    items, issues = _world()
    actions = plan_structure(SPRINT, items, issues, (), "[x]")
    assert actions[0] == CreateMilestone(
        "[x] Epic 1: Epic title 1", "Stories of epic 1, kept by bmad-gitlab."
    )


def test_an_epic_with_no_story_issue_is_not_handled_and_a_story_without_issue_is_skipped():
    epic, one, two = _epic(1), _story(1, 1), _story(1, 2)
    only_epic = plan_structure(SPRINT, (epic, one), (_remote(epic, 1),), ())
    assert only_epic == ()
    some = plan_structure(SPRINT, (epic, one, two), (_remote(epic, 1), _remote(one, 2)), ())
    assert (
        AssignMilestone(2, "Epic 1: Epic title 1") in some and len(some) == 3
    )  # create, assign one, checklist


def test_two_issues_for_one_key_are_not_touched():
    epic, one = _epic(1), _story(1, 1)
    issues = (_remote(epic, 1), _remote(one, 2), _remote(one, 3))
    actions = plan_structure(SPRINT, (epic, one), issues, ())
    assert not any(isinstance(a, AssignMilestone) for a in actions)


def test_an_issue_of_another_sprint_is_not_ours():
    epic, one = _epic(1), _story(1, 1)
    foreign = RemoteIssue(9, "t", render_description("other", one), (), "opened")
    assert plan_structure(SPRINT, (epic, one), (_remote(epic, 1), foreign), ()) == ()


def test_the_options_turn_each_part_off():
    items, issues = _world()
    only_milestones = plan_structure(SPRINT, items, issues, (), options=StructureOptions(checklists=False))
    only_checklists = plan_structure(SPRINT, items, issues, (), options=StructureOptions(milestones=False))
    assert not any(isinstance(a, WriteChecklist) for a in only_milestones) and only_milestones
    assert [type(a) for a in only_checklists] == [WriteChecklist]
    assert plan_structure(SPRINT, items, issues, (), options=StructureOptions(False, False)) == ()


def test_retrospectives_are_not_handled():
    epic = _epic(1)
    retro = Item("retrospective", "epic-1-retrospective", 1, None, "optional", "r", "")
    assert plan_structure(SPRINT, (epic, retro), (_remote(epic, 1),), ()) == ()


# --- the execution -----------------------------------------------------------------------------


def _live(items, statuses_done: bool = False):
    """A fake GitLab that already holds the issues of ``items``."""
    fake = FakeGitLab()
    client = Client("g/p", run=fake)
    for item in items:
        fake._issues.append(
            {
                "iid": fake._next_issue_iid,
                "title": "t",
                "description": render_description(SPRINT, item),
                "labels": [],
                "state": "opened",
                "milestone": None,
            }
        )
        fake._next_issue_iid += 1
    return fake, client


def test_apply_makes_the_milestone_fills_it_and_writes_the_checklist_then_nothing_is_left():
    items, _ = _world(("done", "backlog"))
    fake, client = _live(items)
    actions = plan_structure(SPRINT, items, client.issues(), client.milestones())
    assert apply_structure(actions, client) == StructureApplied(1, 0, 0, 2, 1)
    assert [m["title"] for m in fake._milestones] == ["Epic 1: Epic title 1"]
    assert [i["milestone"]["title"] for i in fake._issues[1:]] == ["Epic 1: Epic title 1"] * 2
    assert "- [x] Story 1.1: Story title 1.1 (#2)" in fake._issues[0]["description"]
    assert plan_structure(SPRINT, items, client.issues(), client.milestones()) == ()


def test_apply_closes_the_milestone_of_a_done_epic_and_reopens_it_when_the_epic_is_not_done():
    done_items, _ = _world(("done", "done"), "done")
    fake, client = _live(done_items)
    apply_structure(plan_structure(SPRINT, done_items, client.issues(), client.milestones()), client)
    assert fake._milestones[0]["state"] == "closed"
    open_items, _ = _world(("done", "backlog"), "in-progress")
    result = apply_structure(plan_structure(SPRINT, open_items, client.issues(), client.milestones()), client)
    assert fake._milestones[0]["state"] == "active"
    assert result.milestones_reopened == 1


def test_apply_with_only_checklists_never_asks_for_the_milestones():
    items, _ = _world()
    fake, client = _live(items)
    actions = plan_structure(SPRINT, items, client.issues(), (), options=StructureOptions(milestones=False))
    fake.calls.clear()
    apply_structure(actions, client)
    assert not any("milestones" in call["args"][-1] for call in fake.calls)


def test_a_refusal_of_gitlab_stops_the_run_with_its_reason():
    items, _ = _world()
    _, client = _live(items)
    actions = plan_structure(SPRINT, items, client.issues(), ())
    with pytest.raises(GitLabError):
        apply_structure(
            actions,
            Client("g/p", run=lambda a, s: Reply(1, "", "403 Forbidden")),
        )


# --- the text -----------------------------------------------------------------------------------


def test_the_dry_run_lines():
    items, issues = _world()
    text = render_structure_plan(plan_structure(SPRINT, items, issues, ()))
    assert text.splitlines() == [
        "structure",
        '+ milestone "Epic 1: Epic title 1"',
        '~ issue #2: milestone "Epic 1: Epic title 1"',
        '~ issue #3: milestone "Epic 1: Epic title 1"',
        "~ issue #1 (key epic-1): checklist of stories",
    ]
    assert render_structure_plan(()) == "structure: nothing to do"


def test_the_dry_run_names_close_and_reopen():
    actions = (ReopenMilestone("a"), CloseMilestone("b"))
    assert render_structure_plan(actions).splitlines()[1:] == [
        '~ milestone "a": reopen',
        '~ milestone "b": close',
    ]


def test_the_summary_of_a_run():
    assert render_structure_applied(StructureApplied(2, 1, 0, 7, 2)) == (
        "milestones: 2 created, 1 closed, 0 reopened; 7 issues assigned; 2 checklists written"
    )
    assert render_structure_applied(StructureApplied()) == "structure: nothing to do"


def test_the_stories_are_listed_in_story_order_not_text_order():
    epic = _epic(1)
    stories = [_story(1, n) for n in (10, 2, 1)]
    issues = (_remote(epic, 1), *(_remote(s, 2 + i) for i, s in enumerate(stories)))
    actions = plan_structure(SPRINT, (epic, *stories), issues, (), options=StructureOptions(milestones=False))
    lines = [line for line in actions[0].description.splitlines() if line.startswith("- [")]
    assert [line.split(":")[0] for line in lines] == [
        "- [ ] Story 1.1",
        "- [ ] Story 1.2",
        "- [ ] Story 1.10",
    ]
