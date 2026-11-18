"""Tests for the plan module."""

from __future__ import annotations

import hashlib

import pytest

from bmad_gitlab.model import (
    Item,
    build_items,
    read_epics,
    read_status,
)
from bmad_gitlab.plan import (
    CreateIssue,
    CreateLabel,
    RemoteIssue,
    UpdateIssue,
    issue_title,
    item_labels,
    label_color,
    parse_marker,
    plan,
    render_description,
)

# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------


def _item(
    kind: str,
    key: str,
    epic: int,
    status: str,
    title: str,
    body: str = "",
) -> Item:
    story: int | None = None
    if kind == "story":
        parts = key.split("-", 2)
        if len(parts) == 3:
            story = int(parts[1])
    return Item(kind, key, epic, story, status, title, body)


def _remote(
    iid: int,
    title: str,
    description: str,
    labels: tuple[str, ...] = (),
    state: str = "opened",
) -> RemoteIssue:
    return RemoteIssue(iid, title, description, labels, state)


# ---------------------------------------------------------------------------
# issue_title
# ---------------------------------------------------------------------------


class TestIssueTitle:
    def test_epic(self):
        item = _item("epic", "epic-1", 1, "backlog", "First Epic")
        assert issue_title(item) == "Epic 1: First Epic"

    def test_story(self):
        item = _item("story", "1-1-some-key", 1, "backlog", "A Story")
        assert issue_title(item) == "Story 1.1: A Story"


# ---------------------------------------------------------------------------
# item_labels
# ---------------------------------------------------------------------------


class TestItemLabels:
    def test_epic_labels_order(self):
        item = _item("epic", "epic-1", 1, "backlog", "E")
        lbls = item_labels("orbit", item)
        assert lbls == (
            "type:epic",
            "status:backlog",
            "prd:orbit",
            "epic:orbit:1",
        )

    def test_story_labels_order(self):
        item = _item("story", "1-1-x", 1, "done", "S")
        lbls = item_labels("orbit", item)
        assert lbls == (
            "type:story",
            "status:done",
            "prd:orbit",
            "epic:orbit:1",
        )


# ---------------------------------------------------------------------------
# render_description
# ---------------------------------------------------------------------------


class TestRenderDescription:
    def test_with_body(self):
        item = _item("epic", "epic-1", 1, "backlog", "T", "Hello world")
        desc = render_description("orbit", item)
        title = issue_title(item)
        h = hashlib.sha256((title + "\n" + "Hello world").encode()).hexdigest()[:12]
        assert desc == f"Hello world\n\n---\n<!-- bmad:v1 sprint=orbit key=epic-1 hash={h} -->"

    def test_without_body(self):
        item = _item("epic", "epic-1", 1, "backlog", "T", "")
        desc = render_description("orbit", item)
        title = issue_title(item)
        h = hashlib.sha256((title + "\n").encode()).hexdigest()[:12]
        assert desc == f"---\n<!-- bmad:v1 sprint=orbit key=epic-1 hash={h} -->"

    def test_hash_stability(self):
        item = _item("epic", "epic-1", 1, "backlog", "T", "Body")
        d1 = render_description("orbit", item)
        d2 = render_description("orbit", item)
        assert d1 == d2

    def test_body_change_changes_hash(self):
        item = _item("epic", "epic-1", 1, "backlog", "T", "Body")
        item2 = _item("epic", "epic-1", 1, "backlog", "T", "Body2")
        d1 = render_description("orbit", item)
        d2 = render_description("orbit", item2)
        assert d1 != d2


# ---------------------------------------------------------------------------
# parse_marker
# ---------------------------------------------------------------------------


class TestParseMarker:
    def test_none(self):
        assert parse_marker("no marker here") is None

    def test_one(self):
        desc = "---\n<!-- bmad:v1 sprint=x key=k1 hash=abcdef012345 -->"
        m = parse_marker(desc)
        assert m is not None
        assert m.sprint == "x"
        assert m.key == "k1"
        assert m.digest == "abcdef012345"

    def test_two_returns_last(self):
        desc = (
            "---\n"
            "<!-- bmad:v1 sprint=a key=k1 hash=111111111111 -->\n"
            "text\n"
            "<!-- bmad:v1 sprint=b key=k2 hash=222222222222 -->"
        )
        m = parse_marker(desc)
        assert m is not None
        assert m.sprint == "b"
        assert m.key == "k2"
        assert m.digest == "222222222222"

    def test_accents_in_key(self):
        desc = "---\n<!-- bmad:v1 sprint=sprint1 key=1-1-déclarer hash=abcdef012345 -->"
        m = parse_marker(desc)
        assert m is not None
        assert m.key == "1-1-déclarer"


# ---------------------------------------------------------------------------
# plan — helpers
# ---------------------------------------------------------------------------


def _apply_create_label(lab: set[str], action: CreateLabel) -> set[str]:
    """Apply a CreateLabel action to a label set."""
    lab.add(action.name)
    return lab


def _apply_create_issue(
    iss: list[RemoteIssue],
    next_iid_ref: list[int],
    action: CreateIssue,
) -> list[RemoteIssue]:
    """Apply a CreateIssue action to the issue list."""
    next_iid_ref[0] += 1
    iss.append(
        RemoteIssue(
            iid=next_iid_ref[0],
            title=action.title,
            description=action.description,
            labels=action.labels,
            state="closed" if action.close else "opened",
        )
    )
    return iss


def _apply_update_issue(
    iss: list[RemoteIssue],
    action: UpdateIssue,
) -> list[RemoteIssue]:
    """Apply an UpdateIssue action to the issue list."""
    for i, issue in enumerate(iss):
        if issue.iid == action.iid:
            new_title = action.title if action.title is not None else issue.title
            new_desc = action.description if action.description is not None else issue.description
            new_labels = list(issue.labels)
            for lbl in action.add_labels:
                if lbl not in new_labels:
                    new_labels.append(lbl)
            for lbl in action.remove_labels:
                if lbl in new_labels:
                    new_labels.remove(lbl)
            new_state = issue.state
            if action.state_event == "close":
                new_state = "closed"
            elif action.state_event == "reopen":
                new_state = "opened"
            iss[i] = RemoteIssue(
                iid=issue.iid,
                title=new_title,
                description=new_desc,
                labels=tuple(new_labels),
                state=new_state,
            )
    return iss


def _apply_plan(
    sprint: str,
    items: tuple[Item, ...],
    labels: frozenset[str],
    issues: tuple[RemoteIssue, ...],
    prefix: str = "",
) -> tuple[frozenset[str], list[RemoteIssue]]:
    """Apply a plan to simulated remote state. Returns (labels, issues)."""
    lab = set(labels)
    iss: list[RemoteIssue] = list(issues)
    next_iid_ref: list[int] = [max((i.iid for i in iss), default=0) + 1]
    for action in plan(sprint, items, labels, issues, prefix).actions:
        if isinstance(action, CreateLabel):
            lab = _apply_create_label(lab, action)
        elif isinstance(action, CreateIssue):
            iss = _apply_create_issue(iss, next_iid_ref, action)
        elif isinstance(action, UpdateIssue):
            iss = _apply_update_issue(iss, action)
    return (frozenset(lab), iss)


# ---------------------------------------------------------------------------
# plan — label creation
# ---------------------------------------------------------------------------


class TestPlanLabels:
    def test_labels_created_once(self):
        items = (
            _item("epic", "epic-1", 1, "backlog", "E1"),
            _item("epic", "epic-2", 2, "backlog", "E2"),
        )
        p = plan("orbit", items, frozenset(), ())
        label_names = [a.name for a in p.actions if isinstance(a, CreateLabel)]
        assert len(label_names) == len(set(label_names))

    def test_labels_before_issues(self):
        items = (_item("epic", "epic-1", 1, "backlog", "E"),)
        p = plan("orbit", items, frozenset(), ())
        label_i = None
        issue_i = None
        for i, a in enumerate(p.actions):
            if isinstance(a, CreateLabel) and label_i is None:
                label_i = i
            if isinstance(a, CreateIssue) and issue_i is None:
                issue_i = i
        assert label_i is not None and issue_i is not None
        assert label_i < issue_i


# ---------------------------------------------------------------------------
# plan — new issue
# ---------------------------------------------------------------------------


class TestPlanNewIssue:
    def test_creates_issue(self):
        items = (_item("epic", "epic-1", 1, "backlog", "E"),)
        p = plan("orbit", items, frozenset(), ())
        creates = [a for a in p.actions if isinstance(a, CreateIssue)]
        assert len(creates) == 1
        assert creates[0].key == "epic-1"
        assert creates[0].close is False

    def test_done_item_close_true(self):
        items = (_item("epic", "epic-1", 1, "done", "Done Epic"),)
        p = plan("orbit", items, frozenset(), ())
        creates = [a for a in p.actions if isinstance(a, CreateIssue)]
        assert len(creates) == 1
        assert creates[0].close is True


# ---------------------------------------------------------------------------
# plan — update: unchanged
# ---------------------------------------------------------------------------


class TestPlanUnchanged:
    def test_no_action_when_unchanged(self):
        title = "Epic 1: E"
        body = "Body"
        h = hashlib.sha256((title + "\n" + body).encode()).hexdigest()[:12]
        desc = f"Body\n\n---\n<!-- bmad:v1 sprint=orbit key=epic-1 hash={h} -->"
        item = _item("epic", "epic-1", 1, "backlog", "E", body)
        labels = ("type:epic", "status:backlog", "prd:orbit", "epic:orbit:1")
        issues = (_remote(1, title, desc, labels, "opened"),)
        p = plan("orbit", (item,), frozenset(labels), issues)
        assert p.actions == ()
        assert p.warnings == ()


# ---------------------------------------------------------------------------
# plan — update: changed title only
# ---------------------------------------------------------------------------


class TestPlanChangedTitle:
    def test_title_change(self):
        title = "Epic 1: E"
        body = "Body"
        h = hashlib.sha256((title + "\n" + body).encode()).hexdigest()[:12]
        desc = f"Body\n\n---\n<!-- bmad:v1 sprint=orbit key=epic-1 hash={h} -->"
        item = _item("epic", "epic-1", 1, "backlog", "E", body)
        labels = ("type:epic", "status:backlog", "prd:orbit", "epic:orbit:1")
        issues = (_remote(1, "Old Title", desc, labels, "opened"),)
        p = plan("orbit", (item,), frozenset(labels), issues)
        updates = [a for a in p.actions if isinstance(a, UpdateIssue)]
        assert len(updates) == 1
        assert updates[0].title == "Epic 1: E"
        assert updates[0].description is None


# ---------------------------------------------------------------------------
# plan — update: changed source → new description
# ---------------------------------------------------------------------------


class TestPlanChangedBody:
    def test_body_change_changes_description(self):
        title = "Epic 1: E"
        body1 = "Body1"
        h1 = hashlib.sha256((title + "\n" + body1).encode()).hexdigest()[:12]
        desc1 = f"Body1\n\n---\n<!-- bmad:v1 sprint=orbit key=epic-1 hash={h1} -->"
        item = _item("epic", "epic-1", 1, "backlog", "E", "Body2")
        labels = ("type:epic", "status:backlog", "prd:orbit", "epic:orbit:1")
        issues = (_remote(1, title, desc1, labels, "opened"),)
        p = plan("orbit", (item,), frozenset(labels), issues)
        updates = [a for a in p.actions if isinstance(a, UpdateIssue)]
        assert len(updates) == 1
        assert updates[0].description is not None


# ---------------------------------------------------------------------------
# plan — update: status swap
# ---------------------------------------------------------------------------


class TestPlanStatusSwap:
    def test_status_label_swap(self):
        title = "Epic 1: E"
        body = "Body"
        h = hashlib.sha256((title + "\n" + body).encode()).hexdigest()[:12]
        desc = f"Body\n\n---\n<!-- bmad:v1 sprint=orbit key=epic-1 hash={h} -->"
        item = _item("epic", "epic-1", 1, "in-progress", "E", body)
        existing_labels = ("type:epic", "status:backlog", "prd:orbit", "epic:orbit:1")
        issues = (_remote(1, title, desc, existing_labels, "opened"),)
        p = plan("orbit", (item,), frozenset(existing_labels), issues)
        updates = [a for a in p.actions if isinstance(a, UpdateIssue)]
        assert len(updates) == 1
        assert updates[0].remove_labels == ("status:backlog",)
        assert updates[0].add_labels == ("status:in-progress",)
        assert updates[0].title is None
        assert updates[0].description is None

    def test_no_other_label_touched(self):
        title = "Epic 1: E"
        body = "Body"
        h = hashlib.sha256((title + "\n" + body).encode()).hexdigest()[:12]
        desc = f"Body\n\n---\n<!-- bmad:v1 sprint=orbit key=epic-1 hash={h} -->"
        item = _item("epic", "epic-1", 1, "in-progress", "E", body)
        # Human added a custom label
        existing_labels = (
            "type:epic",
            "status:backlog",
            "prd:orbit",
            "epic:orbit:1",
            "human-added",
        )
        issues = (_remote(1, title, desc, existing_labels, "opened"),)
        p = plan("orbit", (item,), frozenset(existing_labels), issues)
        updates = [a for a in p.actions if isinstance(a, UpdateIssue)]
        assert len(updates) == 1
        assert "human-added" not in updates[0].remove_labels


# ---------------------------------------------------------------------------
# plan — close and reopen
# ---------------------------------------------------------------------------


class TestPlanCloseReopen:
    def test_done_closes_opened(self):
        title = "Epic 1: E"
        body = "Body"
        h = hashlib.sha256((title + "\n" + body).encode()).hexdigest()[:12]
        desc = f"Body\n\n---\n<!-- bmad:v1 sprint=orbit key=epic-1 hash={h} -->"
        item = _item("epic", "epic-1", 1, "done", "E", body)
        labels = ("type:epic", "status:backlog", "prd:orbit", "epic:orbit:1")
        issues = (_remote(1, title, desc, labels, "opened"),)
        p = plan("orbit", (item,), frozenset(labels), issues)
        updates = [a for a in p.actions if isinstance(a, UpdateIssue)]
        assert len(updates) == 1
        assert updates[0].state_event == "close"

    def test_reopen_closed_not_done(self):
        title = "Epic 1: E"
        body = "Body"
        h = hashlib.sha256((title + "\n" + body).encode()).hexdigest()[:12]
        desc = f"Body\n\n---\n<!-- bmad:v1 sprint=orbit key=epic-1 hash={h} -->"
        item = _item("epic", "epic-1", 1, "backlog", "E", body)
        labels = ("type:epic", "status:backlog", "prd:orbit", "epic:orbit:1")
        issues = (_remote(1, title, desc, labels, "closed"),)
        p = plan("orbit", (item,), frozenset(labels), issues)
        updates = [a for a in p.actions if isinstance(a, UpdateIssue)]
        assert len(updates) == 1
        assert updates[0].state_event == "reopen"


# ---------------------------------------------------------------------------
# plan — duplicate issue warning
# ---------------------------------------------------------------------------


class TestPlanDuplicate:
    def test_two_issues_warning(self):
        title = "Epic 1: E"
        body = "Body"
        h = hashlib.sha256((title + "\n" + body).encode()).hexdigest()[:12]
        desc = f"Body\n\n---\n<!-- bmad:v1 sprint=orbit key=epic-1 hash={h} -->"
        labels = ("type:epic", "status:backlog", "prd:orbit", "epic:orbit:1")
        issues = (
            _remote(1, title, desc, labels, "opened"),
            _remote(2, title, desc, labels, "opened"),
        )
        item = _item("epic", "epic-1", 1, "backlog", "E", body)
        p = plan("orbit", (item,), frozenset(labels), issues)
        assert p.actions == ()
        assert len(p.warnings) == 1
        assert "key epic-1 has 2 issues: #1, #2" in p.warnings[0]


# ---------------------------------------------------------------------------
# plan — orphan issue
# ---------------------------------------------------------------------------


class TestPlanOrphan:
    def test_orphan_issue_warning(self):
        title = "Epic 1: E"
        body = "Body"
        h = hashlib.sha256((title + "\n" + body).encode()).hexdigest()[:12]
        desc = f"Body\n\n---\n<!-- bmad:v1 sprint=orbit key=epic-99 hash={h} -->"
        issues = (_remote(5, title, desc, (), "opened"),)
        items = (_item("epic", "epic-1", 1, "backlog", "E", "B"),)
        p = plan("orbit", items, frozenset(), issues)
        assert len(p.warnings) == 1
        assert "issue #5 (key epic-99) has no entry in the sprint status" in p.warnings[0]


# ---------------------------------------------------------------------------
# plan — another sprint ignored
# ---------------------------------------------------------------------------


class TestPlanSprintScoping:
    def test_other_sprint_ignored(self):
        """An issue of another sprint is not matched and generates no warning."""
        title = "Epic 1: E"
        body = "Body"
        h = hashlib.sha256((title + "\n" + body).encode()).hexdigest()[:12]
        desc = f"Body\n\n---\n<!-- bmad:v1 sprint=other-sprint key=epic-1 hash={h} -->"
        labels = ("type:epic", "status:backlog", "prd:other-sprint", "epic:other-sprint:1")
        issues = (_remote(1, title, desc, labels, "opened"),)
        item = _item("epic", "epic-1", 1, "backlog", "E", body)
        p = plan("orbit", (item,), frozenset(), issues)
        # The other-sprint issue is ignored: no warning, no update for it
        assert p.warnings == ()
        # But we still create labels + issue for our sprint (since none exist)
        creates = [a for a in p.actions if isinstance(a, CreateIssue)]
        assert len(creates) == 1
        assert creates[0].key == "epic-1"


# ---------------------------------------------------------------------------
# plan — retrospective ignored
# ---------------------------------------------------------------------------


class TestPlanRetrospective:
    def test_retrospective_ignored(self):
        items = (_item("retrospective", "epic-1-retrospective", 1, "optional", "R"),)
        p = plan("orbit", items, frozenset(), ())
        assert p.actions == ()
        assert p.warnings == ()


# ---------------------------------------------------------------------------
# plan — two sprints same epic number no collision
# ---------------------------------------------------------------------------


class TestPlanSprintCollision:
    def test_two_sprints_same_epic(self):
        items_a = (_item("epic", "epic-1", 1, "backlog", "E", "B"),)
        items_b = (_item("epic", "epic-1", 1, "backlog", "E", "B"),)
        # Both sprints have no issues yet
        p_a = plan("orbit", items_a, frozenset(), ())
        p_b = plan("orbit-extras", items_b, frozenset(), ())
        # Each should create its own issue (labels + issue)
        creates_a = [a for a in p_a.actions if isinstance(a, CreateIssue)]
        creates_b = [a for a in p_b.actions if isinstance(a, CreateIssue)]
        assert len(creates_a) == 1
        assert len(creates_b) == 1
        # Descriptions must have different sprint markers
        assert "sprint=orbit" in creates_a[0].description
        assert "sprint=orbit-extras" in creates_b[0].description


# ---------------------------------------------------------------------------
# Idempotency — apply plan, re-plan gives empty
# ---------------------------------------------------------------------------


class TestIdempotency:
    def _load_fixture(self, name: str) -> tuple[str, tuple[Item, ...], frozenset[str]]:
        with open(f"tests/fixtures/{name}/sprint-status.yaml") as f:
            status_text = f.read()
        with open(f"tests/fixtures/{name}/epics.md") as f:
            epics_text = f.read()
        project, entries = read_status(status_text)
        epics = read_epics(epics_text)
        items, _ = build_items(entries, epics)
        # Collect all needed labels
        all_labels: set[str] = set()
        for item in items:
            if item.kind == "retrospective":
                continue
            all_labels.update(item_labels(project, item))
        return (project, items, frozenset(all_labels))

    def test_orbit_idempotent(self):
        project, items, labels = self._load_fixture("orbit")
        _, issues = _apply_plan(project, items, labels, ())
        p2 = plan(project, items, labels, tuple(issues))
        assert p2.actions == ()
        assert p2.warnings == ()

    def test_extras_idempotent(self):
        project, items, labels = self._load_fixture("orbit-extras")
        _, issues = _apply_plan(project, items, labels, ())
        p2 = plan(project, items, labels, tuple(issues))
        assert p2.actions == ()
        assert p2.warnings == ()

    def test_both_sprints_together(self):
        pf_project, pf_items, pf_labels = self._load_fixture("orbit")
        extras_project, extras_items, extras_labels = self._load_fixture("orbit-extras")
        # Apply orbit
        _, pf_issues = _apply_plan(pf_project, pf_items, pf_labels, ())
        # Apply extras
        _, extras_issues = _apply_plan(extras_project, extras_items, extras_labels, ())
        # Re-plan both
        p1 = plan(pf_project, pf_items, pf_labels, tuple(pf_issues))
        p2 = plan(extras_project, extras_items, extras_labels, tuple(extras_issues))
        assert p1.actions == ()
        assert p1.warnings == ()
        assert p2.actions == ()
        assert p2.warnings == ()

    def test_human_change_still_empty(self):
        """After a human adds a label or edits description (keeping marker), plan is still empty."""
        project, items, labels = self._load_fixture("orbit")
        _, issues = _apply_plan(project, items, labels, ())
        # Human adds a label to the first issue
        if issues:
            issue = issues[0]
            human_labels = (*issue.labels, "human-added")
            issues[0] = RemoteIssue(
                iid=issue.iid,
                title=issue.title,
                description=issue.description,
                labels=human_labels,
                state=issue.state,
            )
        p2 = plan(project, items, labels, tuple(issues))
        assert p2.actions == ()
        assert p2.warnings == ()

    def test_human_edit_description_keeps_marker(self):
        """Human edits body text but keeps the marker line — plan stays empty."""
        project, items, labels = self._load_fixture("orbit")
        _, issues = _apply_plan(project, items, labels, ())
        if issues:
            issue = issues[0]
            # Insert extra text before the marker (which starts with ---)
            lines = issue.description.split("\n")
            # Find the --- line
            marker_idx = None
            for i, line in enumerate(lines):
                if line.strip() == "---":
                    marker_idx = i
                    break
            if marker_idx is not None:
                new_desc = "\n".join(lines[:marker_idx]) + "\nHuman edited\n" + "\n".join(lines[marker_idx:])
                issues[0] = RemoteIssue(
                    iid=issue.iid,
                    title=issue.title,
                    description=new_desc,
                    labels=issue.labels,
                    state=issue.state,
                )
        p2 = plan(project, items, labels, tuple(issues))
        assert p2.actions == ()
        assert p2.warnings == ()


class TestAnySprintName:
    def test_a_sprint_with_any_name_gets_its_labels_created(self):
        epic = _item("epic", "epic-1", 1, "backlog", "First")
        story = _item("story", "1-1-a-story", 1, "review", "A story")
        result = plan("some-other-project", (epic, story), frozenset(), ())
        created = {a.name: a.color for a in result.actions if isinstance(a, CreateLabel)}
        assert created["prd:some-other-project"] == "#6C757D"
        assert created["epic:some-other-project:1"] == "#428BCA"
        assert set(created) == {
            "type:epic",
            "type:story",
            "status:backlog",
            "status:review",
            "prd:some-other-project",
            "epic:some-other-project:1",
        }


class TestLabelColours:
    @pytest.mark.parametrize("name", ["priority:high", "epic:x:0", "epic:x:abc", "epic:x:", "status"])
    def test_an_unknown_family_or_a_bad_epic_number_has_no_colour(self, name):
        with pytest.raises(ValueError, match="no colour for label"):
            label_color(name)

    def test_the_epic_palette_wraps_after_ten(self):
        assert label_color("epic:p:1") == label_color("epic:p:11") == "#428BCA"
        assert label_color("epic:p:10") == "#E67E22"


class TestTitlePrefix:
    EPIC = _item("epic", "epic-1", 1, "backlog", "First")
    STORY = _item("story", "1-1-a-story", 1, "backlog", "A story", "Body.")

    def test_the_prefix_goes_in_front_of_an_epic_and_a_story_title(self):
        assert issue_title(self.EPIC, "[extras]") == "[extras] Epic 1: First"
        assert issue_title(self.STORY, "[extras]") == "[extras] Story 1.1: A story"

    def test_without_a_prefix_the_titles_are_unchanged(self):
        assert issue_title(self.EPIC) == issue_title(self.EPIC, "") == "Epic 1: First"

    def test_the_prefix_is_part_of_the_hash_of_the_source(self):
        assert render_description("p", self.STORY, "[extras]") != render_description("p", self.STORY)
        assert render_description("p", self.STORY, "[extras]") == render_description(
            "p", self.STORY, "[extras]"
        )

    def test_a_new_issue_is_created_with_the_prefixed_title(self):
        created = [
            a
            for a in plan("p", (self.EPIC, self.STORY), frozenset(), (), "[extras]").actions
            if isinstance(a, CreateIssue)
        ]
        assert [a.title for a in created] == ["[extras] Epic 1: First", "[extras] Story 1.1: A story"]

    def test_planning_again_after_applying_with_a_prefix_gives_nothing(self):
        labels, issues = _apply_plan("p", (self.EPIC, self.STORY), frozenset(), (), "[extras]")
        again = plan("p", (self.EPIC, self.STORY), labels, tuple(issues), "[extras]")
        assert again.actions == () and again.warnings == ()

    def test_adding_a_prefix_renames_the_existing_issues_and_changes_nothing_else(self):
        labels, issues = _apply_plan("p", (self.EPIC, self.STORY), frozenset(), ())
        renamed = plan("p", (self.EPIC, self.STORY), labels, tuple(issues), "[extras]")
        assert [(a.title, a.add_labels, a.remove_labels, a.state_event) for a in renamed.actions] == [
            ("[extras] Epic 1: First", (), (), None),
            ("[extras] Story 1.1: A story", (), (), None),
        ]
        assert all(
            a.description is not None for a in renamed.actions
        )  # the hash in the marker follows the title

    def test_removing_the_prefix_renames_them_back(self):
        labels, issues = _apply_plan("p", (self.EPIC, self.STORY), frozenset(), (), "[extras]")
        back = plan("p", (self.EPIC, self.STORY), labels, tuple(issues))
        assert [a.title for a in back.actions] == ["Epic 1: First", "Story 1.1: A story"]

    def test_planning_again_after_the_rename_gives_nothing(self):
        labels, issues = _apply_plan("p", (self.EPIC, self.STORY), frozenset(), ())
        labels, issues = _apply_plan("p", (self.EPIC, self.STORY), labels, tuple(issues), "[extras]")
        again = plan("p", (self.EPIC, self.STORY), labels, tuple(issues), "[extras]")
        assert again.actions == () and again.warnings == ()  # the marker follows the new title


# ── the writer and the reader of the marker agree on every name ─────────────────────────────────────────


@pytest.mark.parametrize(
    "given", ["ok", "my project", "a, b", "a=b key=c", "x --> y", "team:app", "Électrique v2"]
)
def test_the_marker_written_for_a_project_is_read_back_whatever_it_is_called(given):
    from bmad_gitlab.model import Item, read_status, sprint_name

    raw, _ = read_status(f"project: {given!r}\ndevelopment_status:\n  epic-1: backlog\n")
    sprint = sprint_name(raw)
    item = Item("story", "1-1-a-story", 1, 1, "backlog", "A story", "its text")
    marker = parse_marker(render_description(sprint, item))
    assert marker is not None
    assert (marker.sprint, marker.key) == (sprint, "1-1-a-story")


class TestStateEventIsIdempotent:
    @pytest.mark.parametrize(
        ("status", "state", "event"),
        [
            ("done", "opened", "close"),
            ("done", "closed", None),
            ("backlog", "opened", None),
            ("backlog", "closed", "reopen"),
        ],
    )
    def test_the_event_follows_status_and_state(self, status, state, event):
        from bmad_gitlab.plan import _state_event

        item = _item("epic", "epic-1", 1, status, "E", "Body")
        assert _state_event(item, _remote(1, "Epic 1: E", "", (), state)) == event

    def test_a_done_item_whose_issue_is_closed_gives_nothing_to_do(self):
        title, body = "Epic 1: E", "Body"
        item = _item("epic", "epic-1", 1, "done", "E", body)
        labels = ("type:epic", "status:done", "prd:orbit", "epic:orbit:1")
        issues = (_remote(1, title, render_description("orbit", item), labels, "closed"),)
        actions = plan("orbit", (item,), frozenset(labels), issues).actions
        assert not [a for a in actions if isinstance(a, UpdateIssue)]


class TestLabelsOfTheTool:
    @pytest.mark.parametrize(
        ("name", "color"),
        [
            ("type:epic", "#6B5CE7"),
            ("type:story", "#428BCA"),
            ("status:done", "#44AD8E"),
            ("prd:x", "#6C757D"),
        ],
    )
    def test_the_colour_of_a_fixed_label(self, name, color):
        from bmad_gitlab.plan import label_color

        assert label_color(name) == color

    def test_a_status_label_a_person_added_is_left_alone(self):
        item = _item("epic", "epic-1", 1, "in-progress", "E", "Body")
        labels = ("type:epic", "status:backlog", "status:blocked", "prd:orbit", "epic:orbit:1")
        issues = (_remote(1, "Epic 1: E", render_description("orbit", item), labels, "opened"),)
        updates = [
            a for a in plan("orbit", (item,), frozenset(labels), issues).actions if isinstance(a, UpdateIssue)
        ]
        assert updates[0].remove_labels == ("status:backlog",)
        assert updates[0].add_labels == ("status:in-progress",)
