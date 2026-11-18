"""Tests for the GitLab client and its faithful double."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from bmad_gitlab.gitlab import Client, GitLabError, Reply, run_glab
from bmad_gitlab.plan import RemoteIssue

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_gitlab import FakeGitLab

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk(labels=None, issues=None, boards=None):
    """Build a FakeGitLab and attach it as the client runner."""
    fake = FakeGitLab()
    if labels:
        for nm in labels:
            fake._labels[nm] = fake._next_label_id
            fake._next_label_id += 1
    if issues:
        for iss in issues:
            iid = fake._next_issue_iid
            fake._next_issue_iid += 1
            fake._issues.append(
                {
                    "iid": iid,
                    "title": iss.get("title", ""),
                    "description": iss.get("description", ""),
                    "labels": iss.get("labels", []),
                    "state": iss.get("state", "opened"),
                }
            )
    if boards:
        for b in boards:
            bid = fake._next_board_id
            fake._next_board_id += 1
            fake._boards.append({"id": bid, "name": b["name"]})
            fake._boards_lists[bid] = b.get("lists", [])
    return Client("test-project", run=fake)


# ---------------------------------------------------------------------------
# run_glab
# ---------------------------------------------------------------------------


class TestRunGlab:
    def test_timeout_reply(self):
        """A subprocess timeout returns returncode 124 with a message."""
        with patch("bmad_gitlab.gitlab.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("glab", 60)
            reply = run_glab(["api", "test"], None)
            assert mock_run.called
        assert reply.returncode == 124
        assert "timeout" in reply.stderr

    def test_a_missing_glab_is_a_reply_and_not_a_traceback(self):
        """glab not installed: the answer is 127 with the reason, so the CLI ends in its own error code."""
        with patch("bmad_gitlab.gitlab.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError(2, "No such file or directory", "glab")
            reply = run_glab(["api", "test"], None)
        assert reply.returncode == 127
        assert "cannot run glab" in reply.stderr

    def test_normal_reply(self):
        """A successful call returns the subprocess result."""
        with patch("bmad_gitlab.gitlab.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["glab"], returncode=0, stdout="ok", stderr=""
            )
            reply = run_glab(["api", "test"], None)
        assert reply.returncode == 0
        assert reply.stdout == "ok"


# ---------------------------------------------------------------------------
# Argument construction
# ---------------------------------------------------------------------------


class TestArgsConstruction:
    def test_no_hostname(self):
        c = Client("my-project")
        fake = FakeGitLab()
        c._run = fake
        c.labels()
        call = fake.calls[0]
        assert call["args"][0] == "api"
        assert "--hostname" not in call["args"]
        assert "projects/my-project/labels?per_page=100&page=1" in call["args"]
        assert len(call["args"]) == 2  # glab api takes ONE path argument: the query string is part of it

    def test_with_hostname(self):
        c = Client("my-project", hostname="git.example.com")
        fake = FakeGitLab()
        c._run = fake
        c.labels()
        call = fake.calls[0]
        assert call["args"] == [
            "api",
            "--hostname",
            "git.example.com",
            "projects/my-project/labels?per_page=100&page=1",
        ]

    def test_url_encoding(self):
        c = Client("team/app")
        fake = FakeGitLab()
        c._run = fake
        c.labels()
        call = fake.calls[0]
        assert "projects/team%2Fapp/labels?per_page=100&page=1" in call["args"]

    def test_post_body_not_in_args(self):
        c = Client("my-project")
        fake = FakeGitLab()
        c._run = fake
        c.create_label("x", "#ff0000")
        call = fake.calls[0]
        assert "--method" in call["args"]
        assert "x" not in call["args"]
        assert '"name": "x"' in call["stdin"]

    def test_special_chars_in_title(self):
        """A title starting with -- or holding quotes/newlines travels only in the JSON body."""
        c = Client("my-project")
        fake = FakeGitLab()
        c._run = fake
        c.create_issue("--dangerous title", "desc\nwith\nnewlines", ["a"])
        call = fake.calls[0]
        assert "--dangerous" not in call["args"]
        body = json.loads(call["stdin"])
        assert body["title"] == "--dangerous title"
        assert body["description"] == "desc\nwith\nnewlines"

    def test_post_args_order(self):
        c = Client("my-project", hostname="git.example.com")
        fake = FakeGitLab()
        c._run = fake
        c.create_label("x", "#ff0000")
        call = fake.calls[0]
        args = call["args"]
        api_i = args.index("api")
        host_i = args.index("--hostname")
        method_i = args.index("--method")
        assert host_i == api_i + 1  # --hostname right after api
        assert method_i > host_i


# ---------------------------------------------------------------------------
# labels()
# ---------------------------------------------------------------------------


class TestLabels:
    def test_empty(self):
        c = _mk(labels=[])
        assert c.labels() == {}

    def test_single(self):
        c = _mk(labels=["bug", "feature"])
        result = c.labels()
        assert result == {"bug": 1, "feature": 2}

    def test_pagination(self):
        fake = FakeGitLab()
        for i in range(250):
            fake._labels[f"label{i}"] = fake._next_label_id
            fake._next_label_id += 1
        c = Client("test-project", run=fake)
        result = c.labels()
        assert len(result) == 250

    def test_exactly_100(self):
        fake = FakeGitLab()
        for i in range(100):
            fake._labels[f"label{i}"] = fake._next_label_id
            fake._next_label_id += 1
        c = Client("test-project", run=fake)
        result = c.labels()
        assert len(result) == 100

    def test_empty_second_page(self):
        fake = FakeGitLab()
        for i in range(100):
            fake._labels[f"label{i}"] = fake._next_label_id
            fake._next_label_id += 1
        c = Client("test-project", run=fake)
        result = c.labels()
        assert len(result) == 100
        assert fake.calls[-1]["args"][-1] == "projects/test-project/labels?per_page=100&page=2"


# ---------------------------------------------------------------------------
# issues()
# ---------------------------------------------------------------------------


class TestIssues:
    def test_empty(self):
        c = _mk(issues=[])
        assert c.issues() == ()

    def test_single(self):
        c = _mk(issues=[{"title": "T", "description": "D", "labels": ["a", "b"], "state": "opened"}])
        issues = c.issues()
        assert len(issues) == 1
        assert issues[0] == RemoteIssue(1, "T", "D", ("a", "b"), "opened")

    def test_pagination_250(self):
        fake = FakeGitLab()
        for i in range(250):
            fake._issues.append(
                {
                    "iid": fake._next_issue_iid,
                    "title": f"I{i}",
                    "description": f"D{i}",
                    "labels": [],
                    "state": "opened",
                }
            )
            fake._next_issue_iid += 1
        c = Client("test-project", run=fake)
        result = c.issues()
        assert len(result) == 250

    def test_pagination_exactly_100(self):
        fake = FakeGitLab()
        for i in range(100):
            fake._issues.append(
                {
                    "iid": fake._next_issue_iid,
                    "title": f"I{i}",
                    "description": f"D{i}",
                    "labels": [],
                    "state": "opened",
                }
            )
            fake._next_issue_iid += 1
        c = Client("test-project", run=fake)
        result = c.issues()
        assert len(result) == 100

    def test_closed_state(self):
        c = _mk(issues=[{"title": "T", "description": "D", "labels": [], "state": "closed"}])
        assert c.issues()[0].state == "closed"

    def test_missing_description(self):
        c = _mk(issues=[{"title": "T", "labels": [], "state": "opened"}])
        assert c.issues()[0].description == ""


# ---------------------------------------------------------------------------
# create_label / create_issue
# ---------------------------------------------------------------------------


class TestCreateLabel:
    def test_creates(self):
        c = _mk(labels=[])
        iid = c.create_label("new-label", "#aabbcc")
        assert iid == 1

    def test_duplicate_raises(self):
        c = _mk(labels=["dup"])
        with pytest.raises(GitLabError, match="duplicate"):
            c.create_label("dup", "#aabbcc")


class TestCreateIssue:
    def test_returns_iid(self):
        c = _mk(issues=[])
        iid = c.create_issue("T", "D", ["a", "b"])
        assert iid == 1

    def test_labels_comma_separated(self):
        c = _mk(issues=[])
        c.create_issue("T", "D", ["a", "b"])
        body = json.loads(c._run.calls[-1]["stdin"])
        assert body["labels"] == "a,b"


# ---------------------------------------------------------------------------
# update_issue
# ---------------------------------------------------------------------------


class TestUpdateIssue:
    def test_title_only(self):
        c = _mk(issues=[{"title": "old", "description": "D", "labels": [], "state": "opened"}])
        c.update_issue(1, title="new")
        fake = c._run
        body = json.loads(fake.calls[-1]["stdin"])
        assert body == {"title": "new"}

    def test_description_only(self):
        c = _mk(issues=[{"title": "T", "description": "old", "labels": [], "state": "opened"}])
        c.update_issue(1, description="new")
        body = json.loads(c._run.calls[-1]["stdin"])
        assert body == {"description": "new"}

    def test_add_labels_only(self):
        c = _mk(issues=[{"title": "T", "description": "D", "labels": ["a"], "state": "opened"}])
        c.update_issue(1, add_labels=["b"])
        body = json.loads(c._run.calls[-1]["stdin"])
        assert body == {"add_labels": "b"}  # "labels" would replace every label of the issue

    def test_remove_labels_only(self):
        c = _mk(issues=[{"title": "T", "description": "D", "labels": ["a"], "state": "opened"}])
        c.update_issue(1, remove_labels=["a"])
        body = json.loads(c._run.calls[-1]["stdin"])
        assert body == {"remove_labels": "a"}

    def test_state_event_close(self):
        c = _mk(issues=[{"title": "T", "description": "D", "labels": [], "state": "opened"}])
        c.update_issue(1, state_event="close")
        body = json.loads(c._run.calls[-1]["stdin"])
        assert body == {"state_event": "close"}

    def test_all_together(self):
        c = _mk(issues=[{"title": "T", "description": "D", "labels": ["a"], "state": "opened"}])
        c.update_issue(
            1, title="new", description="nd", add_labels=["b"], remove_labels=["a"], state_event="close"
        )
        body = json.loads(c._run.calls[-1]["stdin"])
        assert body == {
            "title": "new",
            "description": "nd",
            "add_labels": "b",
            "remove_labels": "a",
            "state_event": "close",
        }

    def test_no_fields_raises(self):
        c = _mk()
        with pytest.raises(ValueError, match="no fields"):
            c.update_issue(1)

    def test_invalid_state_event(self):
        c = _mk()
        with pytest.raises(ValueError, match="invalid state_event"):
            c.update_issue(1, state_event="invalid")


# ---------------------------------------------------------------------------
# ensure_board
# ---------------------------------------------------------------------------


class TestEnsureBoard:
    def test_nothing_exists(self):
        c = _mk(labels=["bug"], boards=[])
        assert c.ensure_board("MyBoard", ["bug"]) is True
        assert len(c._run._boards) == 1
        assert len(c._run._boards_lists[1]) == 1

    def test_board_exists_with_some_lists(self):
        fake = FakeGitLab()
        fake._labels["bug"] = 1
        fake._labels["other"] = 2
        bid = fake._next_board_id
        fake._next_board_id += 1
        fake._boards.append({"id": bid, "name": "MyBoard"})
        fake._boards_lists[bid] = [{"id": 1, "label_id": 2, "position": 0}]
        c = Client("test-project", run=fake)
        assert c.ensure_board("MyBoard", ["bug"]) is True

    def test_everything_exists(self):
        fake = FakeGitLab()
        fake._labels["bug"] = 1
        bid = fake._next_board_id
        fake._next_board_id += 1
        fake._boards.append({"id": bid, "name": "MyBoard"})
        fake._boards_lists[bid] = [{"id": 1, "label_id": 1, "position": 0}]
        c = Client("test-project", run=fake)
        assert c.ensure_board("MyBoard", ["bug"]) is False

    def test_unknown_label(self):
        c = _mk(labels=["bug"], boards=[])
        with pytest.raises(GitLabError, match="unknown label"):
            c.ensure_board("MyBoard", ["missing"])


# ---------------------------------------------------------------------------
# Error modes — rule 4
# ---------------------------------------------------------------------------


class TestErrorModes:
    def _client(self, fake):
        return Client("test-project", run=fake)

    def test_nonzero_returncode_labels(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_text = '{"message":"404 Not Found"}'
        c = self._client(fake)
        with pytest.raises(GitLabError, match="GET projects/test-project/labels page 1"):
            c.labels()

    def test_nonzero_returncode_issues(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_text = '{"message":"404 Not Found"}'
        c = self._client(fake)
        with pytest.raises(GitLabError, match="GET projects/test-project/issues page 1"):
            c.issues()

    def test_invalid_json(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_text = "not json at all"
        c = self._client(fake)
        with pytest.raises(GitLabError, match="not valid JSON"):
            c.labels()

    def test_wrong_shape_list_vs_object(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_shape = "object"
        c = self._client(fake)
        with pytest.raises(GitLabError, match="expected a list"):
            c.labels()

    def test_missing_field_labels(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_text = json.dumps([{"id": 1}])
        c = self._client(fake)
        with pytest.raises(GitLabError, match="missing field"):
            c.labels()

    def test_missing_field_issues_iid(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_text = json.dumps([{"title": "T"}])
        c = self._client(fake)
        with pytest.raises(GitLabError, match="missing field"):
            c.issues()

    def test_unknown_state_issues(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_text = json.dumps([{"iid": 1, "title": "T", "state": "unknown"}])
        c = self._client(fake)
        with pytest.raises(GitLabError, match="unknown state"):
            c.issues()

    def test_create_label_missing_id(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_text = json.dumps({"name": "x"})
        c = self._client(fake)
        with pytest.raises(GitLabError, match="missing field"):
            c.create_label("x", "#000")

    def test_create_issue_missing_iid(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_text = json.dumps({"title": "x"})
        c = self._client(fake)
        with pytest.raises(GitLabError, match="missing field"):
            c.create_issue("T", "D", [])

    def test_boards_wrong_shape(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_shape = "object"
        c = self._client(fake)
        with pytest.raises(GitLabError, match="expected a list"):
            c.ensure_board("B", [])

    def test_cut_stderr(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_text = "x" * 1000
        c = self._client(fake)
        with pytest.raises(GitLabError) as exc:
            c.labels()
        assert len(str(exc.value)) <= 400  # call name + stderr cut to 300

    def test_failed_page_stops_pagination(self):
        fake = FakeGitLab()
        for i in range(100):
            fake._labels[f"label{i}"] = fake._next_label_id
            fake._next_label_id += 1
        fake._fail_nth = 2
        fake._fail_text = '{"message":"error"}'
        c = self._client(fake)
        with pytest.raises(GitLabError):
            c.labels()

    def test_issues_labels_not_list(self):
        fake = FakeGitLab()
        fake._fail_nth = 1
        fake._fail_text = json.dumps([{"iid": 1, "title": "T", "labels": "not-a-list"}])
        c = self._client(fake)
        with pytest.raises(GitLabError, match="not a list"):
            c.issues()


# ---------------------------------------------------------------------------
# Idempotency — plan → client → plan again
# ---------------------------------------------------------------------------


class TestIdempotency:
    def _load_fixture(self, name):
        with open(f"tests/fixtures/{name}/sprint-status.yaml") as f:
            status_text = f.read()
        with open(f"tests/fixtures/{name}/epics.md") as f:
            epics_text = f.read()
        from bmad_gitlab.model import build_items, read_epics, read_status

        project, entries = read_status(status_text)
        epics = read_epics(epics_text)
        items, _ = build_items(entries, epics)
        from bmad_gitlab.plan import item_labels

        all_labels = set()
        for item in items:
            if item.kind == "retrospective":
                continue
            all_labels.update(item_labels(project, item))
        return project, items, frozenset(all_labels)

    def test_plan_apply_replan_empty(self):
        project, items, _labels = self._load_fixture("orbit")
        fake = FakeGitLab()
        c = Client(project, run=fake)

        from bmad_gitlab.plan import CreateIssue, CreateLabel, plan

        # Apply plan: create labels then issues (initial remote has none)
        p1 = plan(project, items, frozenset(), ())
        for action in p1.actions:
            if isinstance(action, CreateLabel):
                c.create_label(action.name, action.color)
            elif isinstance(action, CreateIssue):
                c.create_issue(action.title, action.description, action.labels)

        # Read back
        remote_labels = frozenset(c.labels().keys())
        remote_issues = c.issues()

        # Re-plan — should be empty
        p2 = plan(project, items, remote_labels, remote_issues)
        assert p2.actions == ()
        assert p2.warnings == ()


# ---------------------------------------------------------------------------
# Behaviours of the real API that the first version got wrong (checked on a real project)
# ---------------------------------------------------------------------------


class TestRealApiBehaviours:
    def test_a_failed_update_is_an_error_not_a_silent_success(self):
        c = _mk(issues=[{"title": "T", "labels": []}])
        c._run._fail_nth = 1
        with pytest.raises(GitLabError, match="PUT projects/test-project/issues/1"):
            c.update_issue(1, title="new")

    def test_updating_an_unknown_issue_is_an_error(self):
        c = _mk()
        with pytest.raises(GitLabError, match="404"):
            c.update_issue(99, title="new")

    def test_adding_and_removing_labels_leaves_the_labels_a_human_added(self):
        c = _mk(issues=[{"title": "T", "labels": ["human:keep", "status:backlog"]}])
        c.update_issue(1, add_labels=["status:review"], remove_labels=["status:backlog"])
        assert c.issues()[0].labels == ("human:keep", "status:review")

    def test_a_label_is_added_once_even_when_it_is_already_there(self):
        c = _mk(issues=[{"title": "T", "labels": ["status:review"]}])
        c.update_issue(1, add_labels=["status:review"])
        assert c.issues()[0].labels == ("status:review",)

    def test_the_lists_of_a_board_are_read_from_their_nested_label(self):
        c = _mk(labels=["status:backlog", "status:review"])
        assert c.ensure_board("B", ["status:backlog", "status:review"]) is True
        # nothing to add the second time
        assert c.ensure_board("B", ["status:backlog", "status:review"]) is False
        assert len(c._run._boards_lists[1]) == 2

    def test_a_refused_list_creation_is_an_error(self):
        c = _mk(labels=["status:backlog"], boards=[{"name": "B"}])
        c._run._fail_nth = 4  # the board lookup, the labels, the lists, then the creation of a list
        with pytest.raises(GitLabError, match="boards/1/lists"):
            c.ensure_board("B", ["status:backlog"])

    def test_the_double_refuses_a_second_argument_as_the_real_glab_does(self):
        fake = FakeGitLab()
        reply = fake(["api", "projects/p/labels", "per_page=100"], None)
        assert reply.returncode == 1 and "accepts 1 arg" in reply.stderr


class TestWrongShapeIsNeverAnEmptyResult:
    def test_an_object_where_the_issues_list_was_expected(self):
        c = _mk()
        c._run._fail_nth = 1
        c._run._fail_shape = "object"  # the answer is {}: iterating it would give "no issue"
        with pytest.raises(GitLabError, match="expected a list"):
            c.issues()

    def test_an_object_where_the_labels_list_was_expected(self):
        c = _mk()
        c._run._fail_nth = 1
        c._run._fail_shape = "object"
        with pytest.raises(GitLabError, match="expected a list"):
            c.labels()


class TestIntegerFields:
    @pytest.mark.parametrize("answer", ['{"id": "7"}', '{"id": true}', '{"id": null}', '{"iid": 3}'])
    def test_a_created_label_without_an_integer_id_is_an_error(self, answer):
        from bmad_gitlab.gitlab import Reply

        client = Client("p", run=lambda args, stdin: Reply(0, answer, ""))
        with pytest.raises(GitLabError, match="POST projects/p/labels"):
            client.create_label("a", "#000000")

    def test_a_created_issue_without_an_integer_iid_is_an_error(self):
        from bmad_gitlab.gitlab import Reply

        client = Client("p", run=lambda args, stdin: Reply(0, '{"iid": "3"}', ""))
        with pytest.raises(GitLabError, match="iid is not an integer"):
            client.create_issue("t", "d", ["l"])


# ── lists that GitLab pages, and the fields read from them ───────────────────────────────────────────


def _reply(payload):
    from bmad_gitlab.gitlab import Reply

    return Reply(returncode=0, stdout=json.dumps(payload), stderr="")


class _Pager:
    """A runner that answers every call with the same full page: a proxy that ignores ``page=``."""

    def __init__(self):
        self.calls = 0

    def __call__(self, args, stdin):
        self.calls += 1
        return _reply([{"id": self.calls * 1000 + n, "name": f"l{self.calls}-{n}"} for n in range(100)])


class TestPagedReads:
    def test_a_list_that_never_ends_is_an_error_and_not_a_loop(self):
        pager = _Pager()
        with pytest.raises(GitLabError, match="more than 1000 pages"):
            Client("p", run=pager).labels()
        assert pager.calls == 1000

    def test_every_page_is_read_until_a_short_one(self):
        pages = [[{"id": n, "name": f"a{n}"} for n in range(100)], [{"id": 500, "name": "last"}]]
        answers = iter(pages)
        labels = Client("p", run=lambda args, stdin: _reply(next(answers))).labels()
        assert len(labels) == 101 and labels["last"] == 500

    @pytest.mark.parametrize("bad", ["12", 1.5, True, None])
    def test_a_label_id_that_is_not_an_integer_is_refused(self, bad):
        client = Client("p", run=lambda args, stdin: _reply([{"id": bad, "name": "x"}]))
        with pytest.raises(GitLabError, match="id is not an integer"):
            client.labels()

    @pytest.mark.parametrize("bad", ["7", 7.0, False])
    def test_an_issue_iid_that_is_not_an_integer_is_refused(self, bad):
        item = {"iid": bad, "title": "t", "state": "opened", "labels": []}
        with pytest.raises(GitLabError, match="iid is not an integer"):
            Client("p", run=lambda args, stdin: _reply([item])).issues()

    def test_a_board_id_that_is_not_an_integer_is_refused(self):
        client = Client("p", run=lambda args, stdin: _reply([{"id": "3", "name": "B"}]))
        with pytest.raises(GitLabError, match="id is not an integer"):
            client._board("B")

    def test_a_list_label_id_that_is_not_an_integer_is_refused(self):
        client = Client("p", run=lambda args, stdin: _reply([{"label": {"id": "9"}}]))
        with pytest.raises(GitLabError, match="id is not an integer"):
            client._board_label_ids(1)

    def test_the_lists_of_a_board_are_read_past_the_first_page(self):
        full = [{"label": {"id": n}} for n in range(100)]
        answers = iter([full, [{"label": {"id": 777}}]])
        client = Client("p", run=lambda args, stdin: _reply(next(answers)))
        assert 777 in client._board_label_ids(1)

    def test_a_board_on_a_later_page_is_found(self):
        full = [{"id": n, "name": f"other{n}"} for n in range(100)]
        answers = iter([full, [{"id": 42, "name": "Mine"}]])
        client = Client("p", run=lambda args, stdin: _reply(next(answers)))
        assert client._board("Mine") == (42, False)


class TestWhatGitLabAnswersIsChecked:
    def test_a_label_name_that_is_not_a_string_is_an_error(self):
        client = Client("p", run=lambda args, stdin: _reply([{"id": 1, "name": 7}]))
        with pytest.raises(GitLabError, match="name is not a string"):
            client.labels()

    def test_a_description_that_is_not_a_string_is_an_error(self):
        issue = {"iid": 1, "title": "T", "description": 5, "labels": [], "state": "opened"}
        client = Client("p", run=lambda args, stdin: _reply([issue]))
        with pytest.raises(GitLabError, match="description is not a string"):
            client.issues()

    def test_a_null_description_is_an_empty_one(self):
        issue = {"iid": 1, "title": "T", "description": None, "labels": [], "state": "opened"}
        client = Client("p", run=lambda args, stdin: _reply([issue]))
        assert client.issues()[0].description == ""

    def test_a_board_is_not_created_when_a_label_is_unknown(self):
        fake = FakeGitLab()
        with pytest.raises(GitLabError, match="unknown label"):
            Client("p", run=fake).ensure_board("Board", ["status:backlog"])
        assert fake._boards == []

    def test_the_page_size_asked_is_the_page_size_that_ends_the_walk(self):
        from bmad_gitlab.gitlab import PAGE_SIZE

        fake = FakeGitLab()
        Client("p", run=fake).labels()
        assert f"per_page={PAGE_SIZE}&page=1" in fake.calls[0]["args"][-1]


class TestWhatIsSaidOfAFailure:
    def test_a_long_stderr_is_cut_and_a_short_one_is_whole(self):
        long_reply = Reply(returncode=1, stdout="", stderr="x" * 1000)
        with pytest.raises(GitLabError) as exc:
            Client("p", run=lambda args, stdin: long_reply).labels()
        assert "x" * 300 in str(exc.value)
        assert "x" * 301 not in str(exc.value)
        short_reply = Reply(returncode=1, stdout="", stderr="short")
        with pytest.raises(GitLabError, match=r"stderr: short$"):
            Client("p", run=lambda args, stdin: short_reply).labels()

    def test_a_label_that_is_not_an_object_is_an_error(self):
        client = Client("p", run=lambda args, stdin: _reply(["name"]))
        with pytest.raises(GitLabError, match="missing field"):
            client.labels()

    def test_an_issue_that_is_not_an_object_is_an_error(self):
        client = Client("p", run=lambda args, stdin: _reply(["issue"]))
        with pytest.raises(GitLabError, match="expected a dict"):
            client.issues()

    def test_an_update_answered_by_a_list_is_an_error(self):
        client = Client("p", run=lambda args, stdin: _reply([]))
        with pytest.raises(GitLabError, match="expected an object"):
            client.update_issue(1, title="T")

    def test_a_creation_answered_by_a_list_is_an_error(self):
        client = Client("p", run=lambda args, stdin: _reply([]))
        with pytest.raises(GitLabError, match="expected an object"):
            client.create_label("a", "#111111")


class TestTheContractWithGlab:
    def test_labels_are_joined_by_a_comma_and_sent_as_add_and_remove(self):
        fake = FakeGitLab()
        fake._issues.append({"iid": 1, "title": "T", "description": "", "labels": [], "state": "opened"})
        Client("p", run=fake).update_issue(1, add_labels=["a", "b"], remove_labels=["c", "d"])
        body = json.loads(fake.calls[-1]["stdin"])
        assert body == {"add_labels": "a,b", "remove_labels": "c,d"}

    def test_a_write_names_its_method_and_its_content_type_and_a_read_names_neither(self):
        fake = FakeGitLab()
        client = Client("p", run=fake)
        client.create_label("a", "#111111")
        assert json.loads(fake.calls[-1]["stdin"]) == {"name": "a", "color": "#111111"}
        args = fake.calls[-1]["args"]
        assert args[args.index("--method") + 1] == "POST"
        assert args[args.index("-H") + 1] == "Content-Type: application/json"
        client.labels()
        assert "-H" not in fake.calls[-1]["args"] and "--method" not in fake.calls[-1]["args"]

    def test_the_hostname_goes_before_the_path(self):
        fake = FakeGitLab()
        Client("g/p", run=fake, hostname="git.example").labels()
        args = fake.calls[-1]["args"]
        assert args[:3] == ["api", "--hostname", "git.example"]
        assert args[-1].startswith("projects/g%2Fp/labels?")

    def test_a_list_of_a_board_may_hold_things_that_are_not_labels(self):
        entries = [{"id": 1, "label": None}, "text", {"id": 2}, {"id": 3, "label": {"id": 5}}]
        client = Client("p", run=lambda args, stdin: _reply(entries))
        assert client._board_label_ids(9) == {5}


class TestTheRealRunner:
    def _done(self, code, stdout="", stderr=None):
        return subprocess.CompletedProcess(["glab"], code, stdout, stderr)

    def test_it_runs_glab_without_a_shell_in_text_mode_with_a_limit(self):
        with patch("bmad_gitlab.gitlab.subprocess.run", return_value=self._done(0, "{}")) as run:
            reply = run_glab(["api", "x"], "in")
        assert run.call_args.args == (["glab", "api", "x"],)
        assert run.call_args.kwargs == {"input": "in", "capture_output": True, "text": True, "timeout": 60}
        assert reply == Reply(0, "{}", "")  # a missing stderr is an empty string

    def test_the_stderr_of_a_command_is_given_as_it_is(self):
        with patch("bmad_gitlab.gitlab.subprocess.run", return_value=self._done(1, "", "boom")):
            assert run_glab(["api"], None).stderr == "boom"

    def test_an_exit_code_of_124_says_it_timed_out(self):
        with patch("bmad_gitlab.gitlab.subprocess.run", return_value=self._done(124, "", "other")):
            reply = run_glab(["api"], None)
        assert (reply.returncode, reply.stderr) == (124, "timeout after 60 seconds")
