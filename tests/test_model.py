"""Tests for the sprint reading model."""

from pathlib import Path

import pytest

from bmad_gitlab.model import (
    Entry,
    Epics,
    SprintError,
    build_items,
    read_epics,
    read_status,
    sprint_name,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _pf_status() -> str:
    return (FIXTURES / "orbit" / "sprint-status.yaml").read_text()


def _pf_epics() -> str:
    return (FIXTURES / "orbit" / "epics.md").read_text()


def _extras_status() -> str:
    return (FIXTURES / "orbit-extras" / "sprint-status.yaml").read_text()


def _extras_epics() -> str:
    return (FIXTURES / "orbit-extras" / "epics.md").read_text()


# ── read_status ──────────────────────────────────────────────────────


class TestReadStatusOk:
    def test_orbit(self):
        project, entries = read_status(_pf_status())
        assert project == "orbit"
        kinds = [e.kind for e in entries]
        assert kinds.count("epic") == 7
        assert kinds.count("story") == 24
        assert kinds.count("retrospective") == 7

    def test_extras(self):
        project, entries = read_status(_extras_status())
        assert project == "orbit-extras"
        kinds = [e.kind for e in entries]
        assert kinds.count("epic") == 3
        assert kinds.count("story") == 8
        assert kinds.count("retrospective") == 3

    def test_file_order_preserved(self):
        _, entries = read_status(_pf_status())
        keys = [e.key for e in entries]
        assert keys[0] == "epic-1"
        assert keys[1] == "1-1-plan-a-café-stop"

    def test_retrospective_key(self):
        _, entries = read_status(_pf_status())
        retro = [e for e in entries if e.kind == "retrospective"]
        assert retro[0].key == "epic-1-retrospective"
        assert retro[0].story is None
        assert retro[0].status == "optional"

    def test_story_key_keeps_accents(self):
        _, entries = read_status(_pf_status())
        story = [e for e in entries if e.key == "1-1-plan-a-café-stop"]
        assert len(story) == 1
        assert story[0].epic == 1
        assert story[0].story == 1


class TestReadStatusErrors:
    def test_invalid_yaml(self):
        with pytest.raises(SprintError, match="invalid YAML"):
            read_status("{{not yaml")

    def test_top_level_not_mapping(self):
        with pytest.raises(SprintError, match="top level is not a mapping"):
            read_status("- item")

    def test_no_development_status(self):
        with pytest.raises(SprintError, match="no development_status mapping"):
            read_status("project: foo")

    def test_development_status_not_mapping(self):
        with pytest.raises(SprintError, match="development_status is not a mapping"):
            read_status("project: foo\ndevelopment_status: [a]")

    def test_no_project_string(self):
        with pytest.raises(SprintError, match="no project string"):
            read_status("development_status: {}")

    def test_unknown_key(self):
        with pytest.raises(SprintError, match="unknown key shape"):
            read_status("project: x\ndevelopment_status:\n  bad: backlog")

    def test_story_key_no_slug(self):
        with pytest.raises(SprintError, match="unknown key shape"):
            read_status("project: x\ndevelopment_status:\n  1-1: backlog")

    def test_bad_epic_status(self):
        with pytest.raises(SprintError, match="invalid status"):
            read_status("project: x\ndevelopment_status:\n  epic-1: broken")

    def test_bad_story_status(self):
        with pytest.raises(SprintError, match="invalid status"):
            read_status("project: x\ndevelopment_status:\n  1-1-slug: broken")

    def test_bad_retro_status(self):
        with pytest.raises(SprintError, match="invalid status"):
            read_status("project: x\ndevelopment_status:\n  epic-1-retrospective: broken")

    def test_non_integer_epic_number(self):
        with pytest.raises(SprintError, match="do not parse as integers"):
            read_status("project: x\ndevelopment_status:\n  epic-abc: backlog")

    def test_non_integer_story_numbers(self):
        with pytest.raises(SprintError, match="do not parse as integers"):
            read_status("project: x\ndevelopment_status:\n  1-abc-slug: backlog")


# ── read_epics ───────────────────────────────────────────────────────


class TestReadEpicsOk:
    def test_orbit(self):
        epics = read_epics(_pf_epics())
        assert len(epics.epic_titles) == 7
        assert len(epics.story_titles) == 24

    def test_extras(self):
        epics = read_epics(_extras_epics())
        assert len(epics.epic_titles) == 3
        assert len(epics.story_titles) == 8

    def test_story_1_1_title(self):
        epics = read_epics(_pf_epics())
        assert epics.story_titles[(1, 1)] == "Plan a café stop"

    def test_story_1_1_body_starts_with_the_user_story(self):
        epics = read_epics(_pf_epics())
        body = epics.story_bodies[(1, 1)]
        assert body.startswith("**As a** traveller,")

    def test_story_1_1_body_contains_ac1(self):
        epics = read_epics(_pf_epics())
        body = epics.story_bodies[(1, 1)]
        assert "AC-1" in body

    def test_empty_text(self):
        epics = read_epics("")
        assert isinstance(epics, Epics)
        assert epics.epic_titles == {}

    def test_no_epic_headings(self):
        epics = read_epics("# Just a title\n\nSome text.")
        assert epics.epic_titles == {}

    def test_fenced_code_block_heading_ignored(self):
        text = "## Épique 1 : Title\n\n```\n### Story 9.9 : fake\n```\n\n### Story 1.1 : Real\n\nBody.\n"
        epics = read_epics(text)
        assert (1, 1) in epics.story_titles
        assert (9, 9) not in epics.story_titles

    def test_epic_without_space_before_colon(self):
        text = "## Epic 4: Title\n\nBody.\n"
        epics = read_epics(text)
        assert 4 in epics.epic_titles
        assert epics.epic_titles[4] == "Title"

    def test_other_heading_ends_section(self):
        text = "## Épique 1 : Title\n\nEpic body.\n\n## Dettes ouvertes\n\nOther.\n"
        epics = read_epics(text)
        assert epics.epic_bodies[1] == "Epic body."


# ── build_items ──────────────────────────────────────────────────────


class TestBuildItemsOk:
    def test_orbit_integration(self):
        _, entries = read_status(_pf_status())
        epics = read_epics(_pf_epics())
        items, problems = build_items(entries, epics)
        assert len(problems) == 0
        kinds = [i.kind for i in items]
        assert kinds.count("epic") == 7
        assert kinds.count("story") == 24
        assert kinds.count("retrospective") == 7

    def test_extras_integration(self):
        _, entries = read_status(_extras_status())
        epics = read_epics(_extras_epics())
        items, problems = build_items(entries, epics)
        assert len(problems) == 0
        assert items[0].title == "Detect and build the manifest"

    def test_story_1_1_item(self):
        _, entries = read_status(_pf_status())
        epics = read_epics(_pf_epics())
        items, _ = build_items(entries, epics)
        story = next(i for i in items if i.key == "1-1-plan-a-café-stop")
        assert story.title == "Plan a café stop"
        assert story.body.startswith("**As a** traveller,")
        assert "AC-1" in story.body

    def test_retrospective_defaults(self):
        entries = (Entry("retrospective", "epic-1-retrospective", 1, None, "optional"),)
        epics = Epics.empty()
        items, _ = build_items(entries, epics)
        assert items[0].title == "Retrospective: Epic 1"
        assert items[0].body == ""

    def test_epic_key_format(self):
        _, entries = read_status(_pf_status())
        epics = read_epics(_pf_epics())
        items, _ = build_items(entries, epics)
        epic = next(i for i in items if i.kind == "epic" and i.epic == 1)
        assert epic.key == "epic-1"
        assert epic.story is None


class TestBuildItemsProblems:
    def test_story_missing_section(self):
        entries = (Entry("story", "1-1-missing", 1, 1, "backlog"),)
        epics = Epics.empty()
        items, problems = build_items(entries, epics)
        assert len(problems) == 1
        assert "story 1-1-missing has no section in epics.md" in problems
        assert items[0].title == "Missing"

    def test_epic_missing_section(self):
        entries = (Entry("epic", "epic-99", 99, None, "backlog"),)
        epics = read_epics(_pf_epics())
        _items, problems = build_items(entries, epics)
        assert "epic-99 has no section in epics.md" in problems

    def test_epic_section_no_entry(self):
        entries = tuple()
        epics = read_epics(_pf_epics())
        _, problems = build_items(entries, epics)
        assert any("epic 1" in p and "no entry" in p for p in problems)

    def test_story_section_no_entry(self):
        text_epics = (
            "## Épique 1 : Title\n\n### Story 1.1 : A\n\nBody A.\n### Story 1.5 : Extra\n\nBody Extra.\n"
        )
        entries = (Entry("story", "1-1-a", 1, 1, "backlog"),)
        epics = read_epics(text_epics)
        _, problems = build_items(entries, epics)
        assert any("epics.md has story 1.5 with no entry" in p for p in problems)

    def test_duplicate_story_in_epics(self):
        text_epics = "## Épique 1 : Title\n\n### Story 1.1 : A\n\nBody A.\n### Story 1.1 : B\n\nBody B.\n"
        entries = (Entry("story", "1-1-a", 1, 1, "backlog"),)
        epics = read_epics(text_epics)
        _, problems = build_items(entries, epics)
        assert any("epics.md has duplicate story 1.1" in p for p in problems)

    def test_problems_in_file_order(self):
        epics = read_epics(_pf_epics())
        entries = (
            Entry("story", "1-99-missing", 1, 99, "backlog"),
            Entry("epic", "epic-99", 99, None, "backlog"),
        )
        _, problems = build_items(entries, epics)
        assert problems[0] == "story 1-99-missing has no section in epics.md"
        assert problems[1] == "epic-99 has no section in epics.md"


# ── keys of an odd shape, the empty reading, the fallback title ──────


class TestOddInputs:
    def test_a_key_that_is_not_a_string_is_refused_by_name(self):
        text = "project: p\ndevelopment_status:\n  1: backlog\n"
        with pytest.raises(SprintError, match="unknown key shape: 1"):
            read_status(text)

    def test_a_story_key_with_an_empty_slug_is_not_a_story_key(self):
        text = "project: p\ndevelopment_status:\n  1-1-: backlog\n"
        with pytest.raises(SprintError, match="unknown key shape: '1-1-'"):
            read_status(text)

    def test_an_epics_text_without_any_epic_reads_as_four_empty_mappings(self):
        epics = read_epics("just some text\n")
        assert epics.epic_titles == {} and epics.epic_bodies == {}
        assert epics.story_titles == {} and epics.story_bodies == {}
        assert epics.duplicate_stories == ()

    def test_the_fallback_title_of_a_missing_story_is_the_slug_with_a_capital(self):
        _, entries = read_status("project: p\ndevelopment_status:\n  1-1-declare-a-host: backlog\n")
        items, problems = build_items(entries, Epics.empty())
        assert items[0].title == "Declare a host"
        assert problems == ("story 1-1-declare-a-host has no section in epics.md",)


class TestStatusesAndHeadings:
    @pytest.mark.parametrize("status", ["backlog", "ready-for-dev", "in-progress", "review", "done"])
    def test_every_story_status_is_accepted(self, status):
        _, entries = read_status(f"project: p\ndevelopment_status:\n  1-1-x: {status}\n")
        assert entries[0].status == status

    @pytest.mark.parametrize("status", ["ready-for-dev", "review", "optional"])
    def test_an_epic_refuses_the_statuses_of_a_story(self, status):
        with pytest.raises(SprintError, match="invalid status"):
            read_status(f"project: p\ndevelopment_status:\n  epic-1: {status}\n")

    @pytest.mark.parametrize("status", ["backlog", "in-progress", "review"])
    def test_a_retrospective_is_optional_or_done_only(self, status):
        with pytest.raises(SprintError, match="invalid status"):
            read_status(f"project: p\ndevelopment_status:\n  epic-1-retrospective: {status}\n")

    def test_an_epic_heading_without_its_colon_is_not_an_epic(self):
        epics = read_epics("## Epic 4 Title without colon\n\ntext\n")
        assert epics.epic_titles == {}

    def test_the_body_of_an_epic_stops_at_its_first_story_heading(self):
        epics = read_epics("## Epic 1: Title\n\nIntro of the epic.\n\n### Story 1.1: First\n\nStory text.\n")
        assert epics.epic_bodies[1] == "Intro of the epic."
        assert epics.story_bodies[(1, 1)] == "Story text."

    def test_the_body_of_the_last_story_stops_at_the_next_second_level_heading(self):
        text = "## Epic 1: T\n\n### Story 1.1: S\n\nIn the story.\n\n## Open questions\n\nNot in the story.\n"
        assert read_epics(text).story_bodies[(1, 1)] == "In the story."


# ── the layout BMAD writes by default: an epic list, then the details with the stories one level deeper ─────


def _orbit() -> tuple[str, str]:
    folder = FIXTURES / "default-layout"
    return (folder / "sprint-status.yaml").read_text(), (folder / "epics.md").read_text()


class TestDefaultLayout:
    def test_epics_and_stories_are_found_at_their_levels(self):
        epics = read_epics(_orbit()[1])
        assert epics.epic_titles == {1: "Catalogue of planets", 2: "Trip booking"}
        assert epics.story_titles == {
            (1, 1): "List the planets",
            (1, 2): "Show one planet",
            (2, 1): "Book a trip",
        }
        assert epics.duplicate_stories == ()

    def test_a_listed_epic_keeps_its_summary_and_not_the_empty_text_of_its_details(self):
        epics = read_epics(_orbit()[1])
        assert epics.epic_bodies[1] == "The user can browse the planets of a system.\n\n**FRs covered:** FR1"
        assert epics.epic_bodies[2].startswith("The user can book and cancel a trip.")

    def test_a_sub_heading_inside_a_story_stays_in_its_text(self):
        body = read_epics(_orbit()[1]).story_bodies[(1, 1)]
        assert "##### Acceptance details" in body
        assert "The list is sorted by distance." in body
        assert "Then** its planets appear." in body

    def test_a_heading_as_high_as_the_stories_ends_the_last_story(self):
        body = read_epics(_orbit()[1]).story_bodies[(2, 1)]
        assert body.endswith("So that I can travel.")
        assert "These notes" not in body

    def test_a_requirements_heading_does_not_end_up_in_a_story(self):
        epics = read_epics(_orbit()[1])
        for body in (*epics.story_bodies.values(), *epics.epic_bodies.values()):
            assert "Functional Requirements" not in body
            assert "FR1: A user" not in body

    def test_every_item_has_its_section_and_nothing_is_reported(self):
        status, text = _orbit()
        _, entries = read_status(status)
        items, problems = build_items(entries, read_epics(text))
        assert problems == ()
        assert [i.title for i in items if i.kind != "retrospective"] == [
            "Catalogue of planets",
            "List the planets",
            "Show one planet",
            "Trip booking",
            "Book a trip",
        ]

    def test_the_flat_layout_is_read_as_before(self):
        epics = read_epics(_pf_epics())
        assert len(epics.epic_titles) == 7
        assert epics.story_bodies[(1, 1)].startswith("**As a** traveller,")


# ── names that a marker or a list of labels cannot carry ──────────────────────────────────────────────


def _status(project: str, extra: str = "") -> str:
    return f"project: {project!r}\ndevelopment_status:\n  epic-1: backlog\n{extra}"


class TestNamesInMarkersAndLabels:
    @pytest.mark.parametrize(
        ("raw", "name"),
        [
            ("orbit", "orbit"),
            ("orbit-extras", "orbit-extras"),
            ("v1.2_beta", "v1.2_beta"),
            ("my project", "my-project"),
            ("  Orbit  ", "Orbit"),
            ("a, b", "a-b"),
            ("a=b key=c", "a-b-key-c"),
            ("x --> y", "x----y"),
            ("team:app", "team-app"),
            ("Électrique v2", "Électrique-v2"),
        ],
    )
    def test_a_project_name_gives_a_sprint_name_a_marker_can_carry(self, raw, name):
        assert sprint_name(raw) == name

    @pytest.mark.parametrize("raw", ["", " ", " , ", "---"])
    def test_a_name_with_nothing_to_keep_is_refused(self, raw):
        with pytest.raises(SprintError, match="holds no letter or digit"):
            sprint_name(raw)

    def test_read_status_gives_the_name_as_written(self):
        assert read_status(_status("my project"))[0] == "my project"

    def test_a_key_with_a_space_is_not_a_key(self):
        with pytest.raises(SprintError, match="unknown key shape"):
            read_status(_status("orbit", "  1-1-a b: backlog\n"))

    def test_a_key_with_a_tab_is_not_a_key(self):
        with pytest.raises(SprintError, match="unknown key shape"):
            read_status(_status("orbit", '  "1-1-a\tb": backlog\n'))


class TestFences:
    def test_a_heading_inside_a_tilde_block_is_not_a_heading(self):
        text = "## Epic 1: T\n\n~~~\n### Story 9.9: fake\n~~~\n\n### Story 1.1: Real\n\nBody.\n"
        assert read_epics(text).story_titles == {(1, 1): "Real"}

    def test_a_block_is_closed_by_its_own_marker_only(self):
        text = "## Epic 1: T\n\n```\n~~~\n### Story 9.9: still code\n```\n\n### Story 1.1: Real\n\nBody.\n"
        assert read_epics(text).story_titles == {(1, 1): "Real"}

    def test_a_tilde_marker_inside_a_backtick_block_does_not_close_it(self):
        text = "## Epic 1: T\n\n~~~\n```\n### Story 9.9: still code\n~~~\n\n### Story 1.1: Real\n\nBody.\n"
        assert read_epics(text).story_titles == {(1, 1): "Real"}


class TestEpicNumbers:
    @pytest.mark.parametrize("key", ["epic-0", "0-1-first-story", "epic-0-retrospective"])
    def test_an_epic_below_one_is_refused(self, key):
        with pytest.raises(SprintError, match="must be 1 or more"):
            read_status(f"project: p\ndevelopment_status:\n  {key}: backlog\n")

    def test_epic_one_is_accepted(self):
        _, entries = read_status("project: p\ndevelopment_status:\n  epic-1: backlog\n")
        assert entries[0].epic == 1

    def test_an_epic_listed_without_text_takes_the_text_of_its_details(self):
        text = "## Epic 1: Orbit\n\n## Epic Details\n\n## Epic 1: Orbit\n\nThe real text.\n"
        assert read_epics(text).epic_bodies[1] == "The real text."

    def test_an_epic_listed_with_a_text_keeps_it(self):
        text = "## Epic 1: Orbit\n\nThe summary.\n\n## Epic Details\n\n## Epic 1: Orbit\n\nThe details.\n"
        assert read_epics(text).epic_bodies[1] == "The summary."


class TestKeysAndHeadings:
    @pytest.mark.parametrize(
        "key",
        [
            "epic-+1",
            "epic-1_0",
            "epic-٣",
            "1-+0-first",
            "1-\u0660-first",
            "epic-1-retrospective-retrospective",
        ],
    )
    def test_a_key_that_int_would_take_but_is_not_a_number_is_refused(self, key):
        with pytest.raises(SprintError):
            read_status(f"project: p\ndevelopment_status:\n  {key}: backlog\n")

    def test_two_keys_for_the_same_epic_or_story_are_a_problem(self):
        keys = ["epic-1", "epic-01", "1-1-a", "1-01-b"]
        text = "project: p\ndevelopment_status:\n" + "".join(f"  {key}: backlog\n" for key in keys)
        _, entries = read_status(text)
        _, problems = build_items(entries, Epics.empty())
        assert "the sprint status has two keys for epic 1: epic-1 and epic-01" in problems
        assert "the sprint status has two keys for story 1.1: 1-1-a and 1-01-b" in problems

    def test_a_retrospective_does_not_stand_for_its_epic(self):
        _, entries = read_status("project: p\ndevelopment_status:\n  epic-2-retrospective: optional\n")
        _, problems = build_items(entries, read_epics("## Epic 2: Two\n"))
        assert problems == ("epics.md has epic 2 with no entry in the sprint status",)

    def test_a_heading_with_an_enormous_number_is_not_a_heading(self):
        epics = read_epics("## Epic 1: One\n\ntext\n\n## Epic " + "9" * 5000 + ": Huge\n")
        assert list(epics.epic_titles) == [1]

    def test_the_text_right_under_a_heading_is_kept(self):
        epics = read_epics("## Epic 1: One\nSummary line\n### Story 1.1: S\nStory line\n")
        assert epics.epic_bodies[1] == "Summary line"
        assert epics.story_bodies[(1, 1)] == "Story line"

    def test_a_sub_heading_stays_in_an_epic_written_at_level_two(self):
        epics = read_epics("## Epic 1: One\n\nBefore\n\n### Details\n\nAfter\n")
        assert epics.epic_bodies[1] == "Before\n\n### Details\n\nAfter"


class TestFencesLikeCommonMark:
    def _epics(self, text):
        return read_epics(text)

    def test_a_longer_fence_is_not_closed_by_a_shorter_one(self):
        text = "## Epic 1: One\n\n````\n```\n### Story 1.1: fake\n```\n````\n\n### Story 1.2: real\n\nText\n"
        epics = self._epics(text)
        assert list(epics.story_titles) == [(1, 2)]
        assert "### Story 1.1: fake" in epics.epic_bodies[1]

    def test_a_fence_in_a_line_with_text_is_not_a_block(self):
        text = "## Epic 1: One\n\n```x``` is code in a line\n\n### Story 1.1: Real\n\nText\n"
        assert list(self._epics(text).story_titles) == [(1, 1)]

    def test_a_backtick_fence_with_an_info_string_opens_a_block(self):
        text = "## Epic 1: One\n\n```python\n### Story 1.1: fake\n```\n\n### Story 1.2: real\n"
        assert list(self._epics(text).story_titles) == [(1, 2)]

    def test_a_line_with_an_info_string_does_not_close_the_block(self):
        text = "## Epic 1: One\n\n```\n```python\n### Story 1.1: fake\n```\n\n### Story 1.2: real\n"
        assert list(self._epics(text).story_titles) == [(1, 2)]

    def test_tildes_and_backticks_do_not_close_each_other(self):
        text = "## Epic 1: One\n\n~~~\n```\n### Story 1.1: fake\n~~~\n\n### Story 1.2: real\n"
        assert list(self._epics(text).story_titles) == [(1, 2)]

    def test_a_fence_indented_by_up_to_three_spaces_is_a_fence(self):
        text = "## Epic 1: One\n\n   ```\n### Story 1.1: fake\n   ```\n\n### Story 1.2: real\n"
        assert list(self._epics(text).story_titles) == [(1, 2)]


class TestStrictNumbers:
    def test_a_key_of_thousands_of_digits_is_a_sprint_error_and_not_a_traceback(self):
        with pytest.raises(SprintError, match="do not parse as integers"):
            read_status("project: p\ndevelopment_status:\n  ? epic-" + "9" * 5000 + "\n  : backlog\n")

    def test_a_number_of_seven_digits_is_refused(self):
        with pytest.raises(SprintError, match="1 to 6 digits"):
            read_status("project: p\ndevelopment_status:\n  epic-1234567: backlog\n")

    def test_a_heading_with_a_non_ascii_digit_is_not_a_heading(self):
        assert read_epics("## Epic ٣: x\n").epic_titles == {}

    def test_a_key_that_would_end_the_hidden_marker_is_refused(self):
        with pytest.raises(SprintError, match="unknown key shape"):
            read_status("project: p\ndevelopment_status:\n  1-1-a-->b: backlog\n")


def test_the_data_classes_are_frozen():
    import dataclasses

    from bmad_gitlab.model import Item
    from bmad_gitlab.plan import Applied, Plan

    for instance, field in (
        (Entry("epic", "epic-1", 1, None, "backlog"), "status"),
        (Item("epic", "epic-1", 1, None, "backlog", "t", "b"), "title"),
        (Plan((), ()), "actions"),
        (Applied(0, 0, 0, 0, 0), "labels_created"),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field, None)


class TestStoryZero:
    """A story numbered 0 is a prerequisite of its epic ("Story 2.0"): hephaistos has one."""

    STATUS = "project: p\ndevelopment_status:\n  epic-2: in-progress\n  2-0-lock: done\n  2-1-agent: review\n"
    EPICS = (
        "## Epic 2: Agents\n\n### Story 2.0: Lock and deadlines\n\nThe lock.\n\n"
        "### Story 2.1: Agent\n\nThe agent.\n"
    )

    def test_a_key_with_story_number_zero_is_read(self):
        _, entries = read_status(self.STATUS)
        zero = next(e for e in entries if e.key == "2-0-lock")
        assert (zero.kind, zero.epic, zero.story) == ("story", 2, 0)

    def test_a_heading_of_story_zero_is_read(self):
        assert read_epics(self.EPICS).story_titles == {(2, 0): "Lock and deadlines", (2, 1): "Agent"}

    def test_the_story_zero_gets_its_title_and_its_text_and_there_is_no_problem(self):
        _, entries = read_status(self.STATUS)
        items, problems = build_items(entries, read_epics(self.EPICS))
        assert problems == ()
        zero = next(i for i in items if i.key == "2-0-lock")
        assert (zero.story, zero.title, zero.body) == (0, "Lock and deadlines", "The lock.")

    def test_a_story_zero_without_its_section_is_a_problem_like_any_other(self):
        _, entries = read_status(self.STATUS)
        _, problems = build_items(entries, read_epics("## Epic 2: Agents\n\n### Story 2.1: Agent\n\nx\n"))
        assert problems == ("story 2-0-lock has no section in epics.md",)

    def test_story_zero_and_story_one_are_two_stories(self):
        _, entries = read_status(self.STATUS)
        assert [e.story for e in entries if e.story is not None] == [0, 1]

    def test_epic_zero_is_still_refused(self):
        with pytest.raises(SprintError, match="must be 1 or more"):
            read_status("project: p\ndevelopment_status:\n  0-0-first: backlog\n")
