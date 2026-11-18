"""Faithful in-memory double of GitLab for testing."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from urllib.parse import parse_qs

from bmad_gitlab.gitlab import Reply


class _GlabUsageError(Exception):
    """What the real `glab api` says when it is called with the wrong number of arguments."""


@dataclass
class FakeGitLab:
    """In-memory double of GitLab endpoints used by the client."""

    _labels: dict[str, int] = field(default_factory=dict, init=False)
    _next_label_id: int = field(default=1, init=False)

    _issues: list[dict] = field(default_factory=list, init=False)
    _next_issue_iid: int = field(default=1, init=False)

    _boards: list[dict] = field(default_factory=list, init=False)
    _next_board_id: int = field(default=1, init=False)

    _boards_lists: dict[int, list[dict]] = field(default_factory=dict, init=False)
    _next_list_id: int = field(default=1, init=False)

    calls: list[dict] = field(default_factory=list, init=False)

    # knobs for injecting failures
    _fail_nth: int | None = field(default=None, init=False)
    _fail_count: int = field(default=0, init=False)
    _fail_text: str | None = field(default=None, init=False)
    _fail_shape: str | None = field(default=None, init=False)

    # ------------------------------------------------------------------
    # Runner protocol
    # ------------------------------------------------------------------

    def __call__(self, args: Sequence[str], stdin: str | None) -> Reply:
        self.calls.append({"args": list(args), "stdin": stdin})

        # -- inject failure? -------------------------------------------------
        if self._fail_nth is not None and self._fail_count == self._fail_nth - 1:
            self._fail_count += 1
            if self._fail_text is not None:
                return Reply(returncode=0, stdout=self._fail_text, stderr="forced")
            if self._fail_shape == "list":
                return Reply(returncode=0, stdout="[]", stderr="")
            if self._fail_shape == "object":
                return Reply(returncode=0, stdout="{}", stderr="")
            return Reply(returncode=1, stdout='{"message":"404 Not Found"}', stderr="not found")
        self._fail_count += 1

        # -- parse -----------------------------------------------------------
        try:
            method, path, params = self._parse_args(args)
        except _GlabUsageError as exc:
            return Reply(returncode=1, stdout="", stderr=str(exc))

        # -- route -----------------------------------------------------------
        if path.startswith("projects/"):
            return self._handle_project(method, path, params, stdin)
        if path.startswith("boards/"):
            return self._handle_boards(method, path, params, stdin)
        return Reply(returncode=1, stdout='{"message":"404 Not Found"}', stderr="not found")

    # -- internal helpers --------------------------------------------------

    @staticmethod
    def _parse_args(args: Sequence[str]):
        """Return (method, path, params) from glab args."""
        method = "GET"
        i = 1
        while i < len(args):
            if args[i] == "--hostname" and i + 1 < len(args):
                i += 2
            elif args[i] == "--method" and i + 1 < len(args):
                method = args[i + 1]
                i += 2
            elif args[i] in ("--input", "-H"):
                i += 2
            else:
                break
        positional = list(args[i:])
        if len(positional) != 1:  # glab api takes exactly one path; query parameters belong in it
            raise _GlabUsageError(f"accepts 1 arg(s), received {len(positional)}")
        path, _, query = positional[0].partition("?")
        params = {k: v[-1] for k, v in parse_qs(query).items()}
        return method, path, params

    def _handle_project(self, method: str, path: str, params: dict, stdin: str | None) -> Reply:
        rest = path[len("projects/") :]
        slash = rest.find("/")
        if slash == -1:
            return Reply(returncode=1, stdout='{"message":"404 Not Found"}', stderr="not found")
        sub = rest[slash + 1 :].split("?", 1)[0]
        if sub == "labels":
            return self._route_labels(method, params, stdin)
        if sub == "issues":
            return self._route_issues(method, params, stdin)
        if sub.startswith("issues/"):
            return self._route_issue_iid(method, sub, stdin)
        if sub == "boards":
            return self._route_boards(method, stdin)
        if sub.startswith("boards/"):
            return self._route_board_lists(method, sub, stdin)
        return Reply(returncode=1, stdout='{"message":"404 Not Found"}', stderr="not found")

    def _route_labels(self, method: str, params: dict, stdin: str | None) -> Reply:
        if method == "GET":
            return self._get_labels(params)
        return self._post_label(stdin)

    def _route_issues(self, method: str, params: dict, stdin: str | None) -> Reply:
        if method == "GET":
            return self._get_issues(params)
        return self._post_issue(stdin)

    def _route_issue_iid(self, method: str, sub: str, stdin: str | None) -> Reply:
        if method == "PUT":
            iid = int(sub.split("/")[1])
            return self._put_issue(iid, stdin)
        return Reply(returncode=1, stdout='{"message":"404 Not Found"}', stderr="not found")

    def _route_boards(self, method: str, stdin: str | None) -> Reply:
        if method == "GET":
            return self._get_boards()
        return self._post_board(stdin)

    def _route_board_lists(self, method: str, sub: str, stdin: str | None) -> Reply:
        rest = sub[len("boards/") :]
        slash = rest.find("/")
        if slash == -1:
            return Reply(returncode=1, stdout='{"message":"404 Not Found"}', stderr="not found")
        board_id = int(rest[:slash])
        sub2 = rest[slash + 1 :]
        if sub2 == "lists":
            if method == "GET":
                return self._get_board_lists(board_id)
            return self._post_board_list(board_id, stdin)
        return Reply(returncode=1, stdout='{"message":"404 Not Found"}', stderr="not found")

    def _handle_boards(self, method: str, path: str, params: dict, stdin: str | None) -> Reply:
        rest = path[len("boards/") :]
        slash = rest.find("/")
        if slash == -1:
            return Reply(returncode=1, stdout='{"message":"404 Not Found"}', stderr="not found")
        board_id = int(rest[:slash])
        sub = rest[slash + 1 :]
        if sub == "lists":
            if method == "GET":
                return self._get_board_lists(board_id)
            if method == "POST":
                return self._post_board_list(board_id, stdin)
        return Reply(returncode=1, stdout='{"message":"404 Not Found"}', stderr="not found")

    # -- labels ------------------------------------------------------------

    def _get_labels(self, params: dict) -> Reply:
        page = int(params.get("page", "1"))
        per_page = int(params.get("per_page", "100"))
        items = sorted(self._labels.items(), key=lambda kv: kv[1])
        start = (page - 1) * per_page
        end = start + per_page
        page_data = [{"id": iid, "name": nm} for nm, iid in items[start:end]]
        return Reply(returncode=0, stdout=json.dumps(page_data), stderr="")

    def _post_label(self, stdin: str | None) -> Reply:
        if not stdin:
            return Reply(returncode=1, stdout='{"message":"400 Bad Request"}', stderr="bad request")
        try:
            body = json.loads(stdin)
        except (json.JSONDecodeError, ValueError):
            return Reply(returncode=1, stdout='{"message":"400 Bad Request"}', stderr="invalid JSON")
        name = body.get("name")
        if not name:
            return Reply(returncode=1, stdout='{"message":"400 Bad Request"}', stderr="missing name")
        if name in self._labels:
            return Reply(returncode=1, stdout='{"message":"409 Conflict"}', stderr="duplicate label")
        iid = self._next_label_id
        self._next_label_id += 1
        self._labels[name] = iid
        return Reply(returncode=0, stdout=json.dumps({"id": iid, "name": name}), stderr="")

    # -- issues ------------------------------------------------------------

    def _get_issues(self, params: dict) -> Reply:
        page = int(params.get("page", "1"))
        per_page = int(params.get("per_page", "100"))
        start = (page - 1) * per_page
        end = start + per_page
        page_data = self._issues[start:end]
        return Reply(returncode=0, stdout=json.dumps(page_data), stderr="")

    def _post_issue(self, stdin: str | None) -> Reply:
        if not stdin:
            return Reply(returncode=1, stdout='{"message":"400 Bad Request"}', stderr="bad request")
        try:
            body = json.loads(stdin)
        except (json.JSONDecodeError, ValueError):
            return Reply(returncode=1, stdout='{"message":"400 Bad Request"}', stderr="invalid JSON")
        iid = self._next_issue_iid
        self._next_issue_iid += 1
        self._issues.append(
            {
                "iid": iid,
                "title": body.get("title", ""),
                "description": body.get("description", ""),
                "labels": sorted(body.get("labels", "").split(",")) if body.get("labels") else [],
                "state": "opened",
            }
        )
        return Reply(returncode=0, stdout=json.dumps({"iid": iid}), stderr="")

    def _put_issue(self, iid: int, stdin: str | None) -> Reply:
        for issue in self._issues:
            if issue["iid"] == iid:
                body = self._load_json(stdin)
                if body is None:
                    return Reply(returncode=1, stdout='{"message":"400 Bad Request"}', stderr="invalid JSON")
                self._apply_issue_fields(issue, body)
                return Reply(returncode=0, stdout=json.dumps(issue), stderr="")
        return Reply(returncode=1, stdout='{"message":"404 Not Found"}', stderr="404 Issue Not Found")

    @staticmethod
    def _load_json(stdin: str | None) -> dict | None:
        if not stdin:
            return None
        try:
            return json.loads(stdin)
        except (json.JSONDecodeError, ValueError):
            return None

    def _apply_issue_fields(self, issue: dict, body: dict) -> None:
        if "title" in body:
            issue["title"] = body["title"]
        if "description" in body:
            issue["description"] = body["description"]
        if "labels" in body:  # replaces every label of the issue, as the real API does
            issue["labels"] = sorted(body["labels"].split(","))
        if "add_labels" in body:
            issue["labels"] = sorted(set(issue["labels"]) | set(body["add_labels"].split(",")))
        if "remove_labels" in body:
            to_remove = set(body["remove_labels"].split(","))
            issue["labels"] = [lbl for lbl in issue["labels"] if lbl not in to_remove]
        if "state_event" in body:
            if body["state_event"] == "close":
                issue["state"] = "closed"
            elif body["state_event"] == "reopen":
                issue["state"] = "opened"

    # -- boards ------------------------------------------------------------

    def _get_boards(self) -> Reply:
        return Reply(returncode=0, stdout=json.dumps(self._boards), stderr="")

    def _post_board(self, stdin: str | None) -> Reply:
        if not stdin:
            return Reply(returncode=1, stdout='{"message":"400 Bad Request"}', stderr="bad request")
        try:
            body = json.loads(stdin)
        except (json.JSONDecodeError, ValueError):
            return Reply(returncode=1, stdout='{"message":"400 Bad Request"}', stderr="invalid JSON")
        name = body.get("name", "")
        bid = self._next_board_id
        self._next_board_id += 1
        self._boards.append({"id": bid, "name": name})
        self._boards_lists[bid] = []
        return Reply(returncode=0, stdout=json.dumps({"id": bid, "name": name, "lists": []}), stderr="")

    def _list_object(self, entry: dict) -> dict:
        """A board list as GitLab shows it: the label is a nested object, not an id."""
        name = next(n for n, label_id in self._labels.items() if label_id == entry["label_id"])
        label = {"id": entry["label_id"], "name": name}
        return {"id": entry["id"], "label": label, "position": entry["position"]}

    def _get_board_lists(self, board_id: int) -> Reply:
        lists = [self._list_object(entry) for entry in self._boards_lists.get(board_id, [])]
        return Reply(returncode=0, stdout=json.dumps(lists), stderr="")

    def _post_board_list(self, board_id: int, stdin: str | None) -> Reply:
        if not stdin:
            return Reply(returncode=1, stdout='{"message":"400 Bad Request"}', stderr="bad request")
        try:
            body = json.loads(stdin)
        except (json.JSONDecodeError, ValueError):
            return Reply(returncode=1, stdout='{"message":"400 Bad Request"}', stderr="invalid JSON")
        label_id = body.get("label_id")
        if label_id not in self._labels.values():
            return Reply(returncode=1, stdout='{"message":"400 Bad request"}', stderr="unknown label")
        lists = self._boards_lists.setdefault(board_id, [])
        if any(entry["label_id"] == label_id for entry in lists):
            return Reply(returncode=1, stdout="", stderr="Label has already been taken")
        lid = self._next_list_id
        self._next_list_id += 1
        entry = {"id": lid, "label_id": label_id, "position": len(lists)}
        lists.append(entry)
        return Reply(returncode=0, stdout=json.dumps(self._list_object(entry)), stderr="")
