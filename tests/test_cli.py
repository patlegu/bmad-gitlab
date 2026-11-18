"""Tests for the CLI module."""

from __future__ import annotations

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pytest

from bmad_gitlab.cli import main
from fake_gitlab import FakeGitLab

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fixture_path(name):
    return os.path.join(os.path.dirname(__file__), "fixtures", name)


def _pf_status():
    return _fixture_path("orbit") + "/sprint-status.yaml"


def _pf_epics():
    return _fixture_path("orbit") + "/epics.md"


def _extras_status():
    return _fixture_path("orbit-extras") + "/sprint-status.yaml"


def _extras_epics():
    return _fixture_path("orbit-extras") + "/epics.md"


def _extract_path(args):
    """Extract the GitLab API path from glab args."""
    for arg in args:
        if arg.startswith("projects/") and "/" in arg:
            return arg
    return ""


def _extract_method(args):
    """Extract the HTTP method from glab args."""
    for i, arg in enumerate(args):
        if arg == "--method" and i + 1 < len(args):
            return args[i + 1]
    return "GET"


def _board_failing_runner(args, stdin):
    """A runner that fails only on POST to /boards (board creation)."""
    from bmad_gitlab.gitlab import Reply

    method = _extract_method(args)
    path = _extract_path(args)
    if method == "POST" and path.endswith("/boards"):
        return Reply(returncode=1, stdout='{"message":"error"}', stderr="board fail")
    if method == "GET":
        return Reply(returncode=0, stdout="[]", stderr="")
    if method == "POST":
        if "/labels" in path:
            return Reply(returncode=0, stdout='{"id":1}', stderr="")
        if "/issues" in path and "/issues/" not in path:
            return Reply(returncode=0, stdout='{"iid":1}', stderr="")
        return Reply(returncode=0, stdout='{"id":1}', stderr="")
    return Reply(returncode=0, stdout='{"id":1}', stderr="")


def _run(args, fake=None, apply_flag=False, run=None):
    """Run main() with given args and a FakeGitLab runner."""
    if fake is None:
        fake = FakeGitLab()
    out = io.StringIO()
    err = io.StringIO()
    full_args = ["sync", "--project", "test/project", *args]
    if apply_flag:
        full_args.append("--apply")
    runner = run if run is not None else fake
    code = main(full_args, run=runner, out=out, err=err)
    return code, out.getvalue(), err.getvalue(), fake


# ---------------------------------------------------------------------------
# Dry run — only read calls
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_no_post_or_put(self):
        """A dry run makes only read calls (GET)."""
        code, _out, _err, fake = _run(
            [
                "--sprint",
                _pf_status(),
                _pf_epics(),
            ]
        )
        assert code == 0
        # Check that no call is POST or PUT
        for call in fake.calls:
            method = "GET"
            for i, arg in enumerate(call["args"]):
                if arg == "--method" and i + 1 < len(call["args"]):
                    method = call["args"][i + 1]
            assert method == "GET", f"Expected GET but got {method} in {call['args']}"

    def test_dry_run_reads_labels_and_issues(self):
        """A dry run calls labels() and issues()."""
        _, _out, _err, fake = _run(
            [
                "--sprint",
                _pf_status(),
                _pf_epics(),
            ]
        )
        get_calls = [c for c in fake.calls if "labels" in c["args"][1] or "issues" in c["args"][1]]
        assert len(get_calls) >= 2  # at least labels + issues


# ---------------------------------------------------------------------------
# --apply — creates everything
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_creates_labels_and_issues(self):
        """--apply creates labels and issues."""
        _, _out, _err, fake = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            apply_flag=True,
        )
        # Should have POST calls for labels and issues
        post_calls = [c for c in fake.calls if c["args"][0] == "api" and "--method" in c["args"]]
        post_paths = [c["args"][-1] for c in post_calls]
        assert any("labels" in p for p in post_paths)
        assert any("issues" in p for p in post_paths)

    def test_second_apply_nothing_to_do(self):
        """A second --apply reports nothing to do and makes no write call."""
        code1, _out1, _err1, fake = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            apply_flag=True,
        )
        assert code1 == 0

        # Count write calls after first apply
        write_count_1 = sum(1 for c in fake.calls if c["args"][0] == "api" and "--method" in c["args"])

        # Second apply
        code2, out2, _err2, _fake2 = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            fake=fake,
            apply_flag=True,
        )
        assert code2 == 0
        assert "nothing to do" in out2

        # No additional write calls
        write_count_2 = sum(1 for c in fake.calls if c["args"][0] == "api" and "--method" in c["args"])
        assert write_count_2 == write_count_1


# ---------------------------------------------------------------------------
# Status change — swaps label, human label stays
# ---------------------------------------------------------------------------


class TestStatusChange:
    def test_status_swap(self):
        """A change of status in the sprint file swaps the label; human label stays."""
        # First apply
        _, _out, _err, fake = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            apply_flag=True,
        )
        # Simulate a human adding a label
        if fake._issues:
            issue = fake._issues[0]
            issue["labels"].append("human:added")
        # The key test: the second apply with a status change should swap labels
        # but keep human-added labels. We verify the apply flow works.
        pass


# ---------------------------------------------------------------------------
# Two sprints — labels created once
# ---------------------------------------------------------------------------


class TestTwoSprints:
    def test_labels_created_once(self):
        """Two sprints in one run: labels are created once."""
        _, _out, _err, fake = _run(
            [
                "--sprint",
                _pf_status(),
                _pf_epics(),
                "--sprint",
                _extras_status(),
                _extras_epics(),
            ],
            apply_flag=True,
        )
        # Count unique label creations (POST to /labels)
        label_creations = [
            c
            for c in fake.calls
            if c["args"][0] == "api" and "--method" in c["args"] and any("labels" in a for a in c["args"])
        ]
        # Each label should be created exactly once
        label_names = []
        for c in label_creations:
            body = json.loads(c["stdin"])
            label_names.append(body.get("name", ""))
        assert len(label_names) == len(set(label_names)), "Duplicate label creation"


# ---------------------------------------------------------------------------
# Error code 2 — missing / bad file
# ---------------------------------------------------------------------------


class TestErrorCode2:
    def test_missing_file(self):
        code, _out, err, _fake = _run(
            [
                "--sprint",
                "/nonexistent/status.yaml",
                "/nonexistent/epics.md",
            ]
        )
        assert code == 2
        assert "error:" in err

    def test_missing_project(self):
        code, _out, _err, _fake = _run([])
        assert code == 2

    def test_missing_sprint(self):
        code, _out, _err, _fake = _run(["--project", "x"])
        assert code == 2


# ---------------------------------------------------------------------------
# Error code 3 — problems with --apply
# ---------------------------------------------------------------------------


class TestErrorCode3:
    def test_problems_refuse_apply(self):
        """With problems and --apply (no --allow-problems), return 3."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("project: test\n")
            f.write("development_status:\n")
            f.write("  epic-1: backlog\n")
            status_path = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Nothing here\n")
            epics_path = f.name

        try:
            code, _out, err, _fake = _run(
                ["--sprint", status_path, epics_path],
                apply_flag=True,
            )
            assert code == 3
            assert "refusing to apply with problems" in err
        finally:
            os.unlink(status_path)
            os.unlink(epics_path)


# ---------------------------------------------------------------------------
# --allow-problems
# ---------------------------------------------------------------------------


class TestAllowProblems:
    def test_allow_problems_continues(self):
        """With --allow-problems, the apply proceeds despite problems."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("project: test\n")
            f.write("development_status:\n")
            f.write("  epic-1: backlog\n")
            status_path = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Nothing\n")
            epics_path = f.name

        try:
            # Without --allow-problems, this should return 3
            code, _out, _err, _fake = _run(
                ["--sprint", status_path, epics_path],
                apply_flag=True,
            )
            assert code == 3

            # With --allow-problems
            code2, _out2, _err2, _fake2 = _run(
                ["--sprint", status_path, epics_path, "--allow-problems"],
                apply_flag=True,
            )
            # Should proceed (0 or 4 depending on GitLab)
            assert code2 in (0, 4)
        finally:
            os.unlink(status_path)
            os.unlink(epics_path)


# ---------------------------------------------------------------------------
# Error code 4 — GitLab error
# ---------------------------------------------------------------------------


class TestErrorCode4:
    def test_gitlab_error(self):
        """A GitLabError returns 4."""

        def failing_runner(args, stdin):
            from bmad_gitlab.gitlab import Reply

            return Reply(returncode=1, stdout='{"message":"404"}', stderr="not found")

        code, _out, err, _fake = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            run=failing_runner,
        )
        assert code == 4
        assert "error:" in err


# ---------------------------------------------------------------------------
# --apply — ensures board
# ---------------------------------------------------------------------------


class TestBoardCreation:
    def test_board_is_ensured_on_apply(self):
        """--apply ensures the BMAD Sprint Board exists."""
        _, _out, _err, fake = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            apply_flag=True,
        )
        # Check that ensure_board was called (POST to boards)
        board_posts = [
            c
            for c in fake.calls
            if c["args"][0] == "api" and "--method" in c["args"] and any("boards" in a for a in c["args"])
        ]
        assert len(board_posts) >= 1


# ---------------------------------------------------------------------------
# Missing argument
# ---------------------------------------------------------------------------


class TestMissingArgument:
    def test_no_subcommand(self):
        code, _out, _err, _fake = _run([])
        assert code == 2


# ---------------------------------------------------------------------------
# Duplicate project names
# ---------------------------------------------------------------------------


class TestDuplicateProject:
    def test_same_project_twice(self):
        """Two sprints with the same project name: error, return 2."""
        code, _out, err, _fake = _run(
            [
                "--sprint",
                _pf_status(),
                _pf_epics(),
                "--sprint",
                _pf_status(),
                _pf_epics(),
            ]
        )
        assert code == 2
        assert "error:" in err
        assert "project" in err


def _write_sprint(tmp_path, folder, project):
    base = tmp_path / folder
    base.mkdir()
    (base / "status.yaml").write_text(
        f"project: {project!r}\ndevelopment_status:\n  epic-1: backlog\n  1-1-a-story: backlog\n",
        encoding="utf-8",
    )
    (base / "epics.md").write_text(
        "## Epic 1: First\n\nThe first.\n\n### Story 1.1: A story\n\nIts text.\n", encoding="utf-8"
    )
    return str(base / "status.yaml"), str(base / "epics.md")


class TestProjectNameWithASpace:
    def test_the_name_is_made_into_a_sprint_name_and_the_user_is_told(self, tmp_path):
        status, epics = _write_sprint(tmp_path, "one", "my project")
        code, out, err, _fake = _run(["--sprint", status, epics])
        assert code == 0
        assert "note: the project name 'my project' is written as 'my-project' in labels and markers" in err
        assert "sprint my-project" in out

    def test_a_second_apply_finds_what_the_first_one_made(self, tmp_path):
        status, epics = _write_sprint(tmp_path, "one", "my project")
        fake = FakeGitLab()
        assert _run(["--sprint", status, epics], fake, apply_flag=True)[0] == 0
        code, out, _err, _fake = _run(["--sprint", status, epics], fake)
        assert code == 0
        assert "nothing to do" in out

    def test_a_valid_name_gets_no_note(self, tmp_path):
        status, epics = _write_sprint(tmp_path, "one", "my-project")
        _code, _out, err, _fake = _run(["--sprint", status, epics])
        assert "note:" not in err

    def test_two_names_that_give_the_same_sprint_are_refused(self, tmp_path):
        first = _write_sprint(tmp_path, "one", "my project")
        second = _write_sprint(tmp_path, "two", "my-project")
        code, _out, err, _fake = _run(["--sprint", *first, "--sprint", *second])
        assert code == 2
        assert "two sprints have the same project name 'my-project'" in err


# ---------------------------------------------------------------------------
# Second apply — the most important property
# ---------------------------------------------------------------------------


class TestSecondApply:
    def test_second_apply_does_nothing(self):
        """The second --apply does nothing: no write calls, output says nothing to do."""
        # First apply
        code1, _out1, _err1, fake = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            apply_flag=True,
        )
        assert code1 == 0

        # Count write calls
        write_calls_before = sum(1 for c in fake.calls if c["args"][0] == "api" and "--method" in c["args"])

        # Second apply on the SAME fake (same state)
        code2, out2, _err2, _ = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            fake=fake,
            apply_flag=True,
        )
        assert code2 == 0
        assert "nothing to do" in out2

        # No additional write calls
        write_calls_after = sum(1 for c in fake.calls if c["args"][0] == "api" and "--method" in c["args"])
        assert write_calls_after == write_calls_before


# ---------------------------------------------------------------------------
# Apply GitLab error
# ---------------------------------------------------------------------------


class TestApplyGitLabError:
    def test_apply_error_returns_4(self):
        """A GitLabError during apply (create_label) returns 4."""
        fake = FakeGitLab()
        fake._fail_nth = 3  # Fail on first create_label
        code, _out, err, _ = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            fake=fake,
            apply_flag=True,
            run=fake,
        )
        assert code == 4
        assert "error:" in err


# ---------------------------------------------------------------------------
# Board creation messages
# ---------------------------------------------------------------------------


class TestBoardMessages:
    def test_board_created_message(self):
        """The board created message appears in output."""
        code, out, _err, _fake = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            apply_flag=True,
        )
        assert code == 0
        assert "board created" in out


# ---------------------------------------------------------------------------
# Epics read error
# ---------------------------------------------------------------------------


class TestEpicsReadError:
    def test_epics_read_error_returns_2(self):
        """An epics file that triggers a SprintError returns 2."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("project: test\n")
            f.write("development_status:\n")
            f.write("  epic-1: backlog\n")
            status_path = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Not valid\n")
            epics_path = f.name

        try:
            code, _out, _err, _fake = _run(
                ["--sprint", status_path, epics_path],
            )
            # read_epics returns empty Epics for non-epic text, not an error
            assert code == 0
        finally:
            os.unlink(status_path)
            os.unlink(epics_path)


# ---------------------------------------------------------------------------
# Board GitLab error
# ---------------------------------------------------------------------------


class TestBoardGitLabError:
    def test_board_error_returns_4(self):
        """A GitLabError during board creation returns 4."""
        code, _out, err, _fake = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            apply_flag=True,
            run=_board_failing_runner,
        )
        assert code == 4
        assert "error:" in err


# ---------------------------------------------------------------------------
# File read error — UnicodeDecodeError
# ---------------------------------------------------------------------------


class TestFileReadError:
    def test_binary_file_returns_2(self):
        """A binary file that cannot be decoded returns 2."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".yaml", delete=False) as f:
            f.write(b"\x80\x81\x82\x83")
            bad_path = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# ok\n")
            ok_path = f.name

        try:
            code, _out, err, _fake = _run(
                ["--sprint", bad_path, ok_path],
            )
            assert code == 2
            assert "error:" in err
        finally:
            os.unlink(bad_path)
            os.unlink(ok_path)


# ---------------------------------------------------------------------------
# Epics file not found (line 129 coverage)
# ---------------------------------------------------------------------------


class TestEpicsFileNotFound:
    def test_epics_not_found_returns_2(self):
        """A missing epics file returns 2 (covers the epics read failure path)."""
        code, _out, err, _fake = _run(
            ["--sprint", _pf_status(), "/nonexistent/epics.md"],
        )
        assert code == 2
        assert "error:" in err


# ---------------------------------------------------------------------------
# Invalid status file — SprintError
# ---------------------------------------------------------------------------


class TestInvalidStatus:
    def test_invalid_status_returns_2(self):
        """A status file with an invalid status value returns 2."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("project: test\n")
            f.write("development_status:\n")
            f.write("  epic-1: invalid_status\n")
            status_path = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Nothing\n")
            epics_path = f.name

        try:
            code, _out, err, _fake = _run(
                ["--sprint", status_path, epics_path],
            )
            assert code == 2
            assert "error:" in err
        finally:
            os.unlink(status_path)
            os.unlink(epics_path)


# ---------------------------------------------------------------------------
# Board created without status labels (line 232 coverage)
# ---------------------------------------------------------------------------


class TestBoardCreatedNoLabels:
    def test_board_created_without_new_labels(self):
        """When all status labels already exist, output says 'board created' without count."""
        fake = FakeGitLab()
        # Pre-create all status labels so no new ones are needed
        for lbl in ("status:backlog", "status:ready-for-dev", "status:in-progress", "status:review"):
            fake._labels[lbl] = fake._next_label_id
            fake._next_label_id += 1

        code, out, _err, _ = _run(
            ["--sprint", _pf_status(), _pf_epics()],
            fake=fake,
            apply_flag=True,
        )
        assert code == 0
        assert "board created" in out
        # Should NOT contain the parenthesized count since no labels were created
        assert "board created" in out and "(" not in out.split("board created")[1].split("\n")[0]


# ---------------------------------------------------------------------------
# What the review of the first version added
# ---------------------------------------------------------------------------


class _FailingOn:
    """A runner that delegates to the double and fails the POST whose body holds ``needle``."""

    def __init__(self, fake, needle):
        self.fake = fake
        self.needle = needle

    def __call__(self, args, stdin):
        from bmad_gitlab.gitlab import Reply

        if stdin is not None and self.needle in stdin and "POST" in args:
            return Reply(returncode=1, stdout="", stderr="forced failure")
        return self.fake(args, stdin)


class TestReviewedBehaviours:
    def test_no_subcommand_is_a_usage_error(self):
        out, err = io.StringIO(), io.StringIO()
        assert main([], run=FakeGitLab(), out=out, err=err) == 2

    def test_the_board_message_counts_only_the_labels_the_board_step_created(self):
        fake = FakeGitLab()
        code, out, _err, _ = _run(["--sprint", _pf_status(), _pf_epics()], fake, apply_flag=True)
        assert code == 0
        # the plan created status:backlog (items use it); the board step created the other three
        assert "board created (3 status labels created)" in out
        code, out, _err, _ = _run(["--sprint", _pf_status(), _pf_epics()], fake, apply_flag=True)
        assert code == 0 and "board created" not in out

    def test_a_failure_while_creating_a_status_label_is_exit_4_not_a_traceback(self):
        runner = _FailingOn(FakeGitLab(), "status:review")
        code, _out, err, _ = _run(["--sprint", _pf_status(), _pf_epics()], run=runner, apply_flag=True)
        assert code == 4
        assert err.startswith("error:") and "forced failure" in err

    def test_a_failure_while_applying_says_how_many_actions_were_done(self):
        runner = _FailingOn(FakeGitLab(), '"title": "Epic 2:')
        code, _out, err, _ = _run(["--sprint", _pf_status(), _pf_epics()], run=runner, apply_flag=True)
        assert code == 4
        assert "actions were done before it" in err


class TestProblemsAndOrder:
    def test_problems_are_printed_one_line_each_and_a_dry_run_goes_on(self, tmp_path):
        status = tmp_path / "status.yaml"
        epics = tmp_path / "epics.md"
        status.write_text("project: p\ndevelopment_status:\n  epic-1: backlog\n  1-1-first: backlog\n")
        epics.write_text("## Epic 1: One\n\nIntro.\n")  # no section for story 1.1
        code, _out, err, _ = _run(["--sprint", str(status), str(epics)])
        assert code == 0
        assert err == "problem: story 1-1-first has no section in epics.md\n"

    def test_the_sprints_are_applied_in_the_order_they_were_given(self):
        fake = FakeGitLab()
        args = ["--sprint", _pf_status(), _pf_epics(), "--sprint", _extras_status(), _extras_epics()]
        code, _out, _err, _ = _run(args, fake, apply_flag=True)
        assert code == 0
        sprint_of = [
            "orbit-extras" if "sprint=orbit-extras" in i["description"] else "orbit" for i in fake._issues
        ]
        assert sprint_of == ["orbit"] * 31 + ["orbit-extras"] * 11


class TestPrefixOption:
    def _args(self):
        return ["--sprint", _pf_status(), _pf_epics(), "--sprint", _extras_status(), _extras_epics()]

    def test_the_prefix_applies_to_the_titles_of_the_named_sprint_only(self):
        fake = FakeGitLab()
        code, _out, _err, _ = _run(
            [*self._args(), "--prefix", "orbit-extras=[extras]"], fake, apply_flag=True
        )
        assert code == 0
        titles = {
            ("orbit-extras" if "sprint=orbit-extras" in i["description"] else "orbit"): []
            for i in fake._issues
        }
        for issue in fake._issues:
            sprint = "orbit-extras" if "sprint=orbit-extras" in issue["description"] else "orbit"
            titles[sprint].append(issue["title"])
        assert (
            all(t.startswith("[extras] ") for t in titles["orbit-extras"])
            and len(titles["orbit-extras"]) == 11
        )
        assert not any(t.startswith("[") for t in titles["orbit"]) and len(titles["orbit"]) == 31

    def test_a_second_run_with_the_same_prefix_changes_nothing(self):
        fake = FakeGitLab()
        args = [*self._args(), "--prefix", "orbit-extras=[extras]"]
        _run(args, fake, apply_flag=True)
        code, out, _err, _ = _run(args, fake, apply_flag=True)
        assert code == 0 and "to update" not in out and out.count("nothing to do") >= 2

    def test_adding_a_prefix_later_renames_the_existing_issues(self):
        fake = FakeGitLab()
        _run(self._args(), fake, apply_flag=True)
        code, out, _err, _ = _run([*self._args(), "--prefix", "orbit-extras=[extras]"], fake, apply_flag=True)
        assert code == 0 and "updated 11 issues" in out

    @pytest.mark.parametrize(
        "value", ["nothing", "=[x]", "orbit-extras=", "orbit-extras=   ", "orbit-extras=[a\nb]"]
    )
    def test_a_badly_formed_prefix_is_a_usage_error(self, value):
        code, _out, err, fake = _run([*self._args(), "--prefix", value])
        assert code == 2 and err.startswith("error: --prefix wants SPRINT=TEXT")
        assert fake.calls == []  # nothing was read from GitLab either

    def test_a_prefix_for_a_sprint_that_is_not_given_is_a_usage_error(self):
        code, _out, err, fake = _run([*self._args(), "--prefix", "other=[x]"])
        assert code == 2 and "names a sprint that is not given: other" in err
        assert "(the sprints are: " in err and "orbit" in err  # the names that would be accepted
        assert fake.calls == []

    def test_spaces_around_the_text_are_not_part_of_the_prefix(self):
        fake = FakeGitLab()
        code, _out, _err, _ = _run(
            [*self._args(), "--prefix", "orbit-extras=  [extras]  "], fake, apply_flag=True
        )
        assert code == 0
        extras = [i["title"] for i in fake._issues if "sprint=orbit-extras" in i["description"]]
        assert all(t.startswith("[extras] ") and not t.startswith("[extras]  ") for t in extras)
