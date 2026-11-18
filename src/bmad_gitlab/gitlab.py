"""Thin client that talks to GitLab through the ``glab api`` command."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from bmad_gitlab.model import RemoteIssue


@dataclass(frozen=True)
class Reply:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str], str | None], Reply]


PAGE_SIZE = 100
MAX_PAGES = 1000  # a proxy that ignores ``page=`` would otherwise be walked for ever


class GitLabError(RuntimeError):
    """A call to GitLab failed or answered something unreadable."""


def _cut(text: str, maxlen: int = 300) -> str:
    """Cut *text* to *maxlen* characters."""
    return text if len(text) <= maxlen else text[:maxlen]


def run_glab(args: Sequence[str], stdin: str | None) -> Reply:
    """The real runner: ``subprocess.run(["glab", *args])``, no shell, text mode, a 60 second timeout."""
    # glab is the command of the user, found by name: it holds the authentication this module relies on.
    try:
        result = subprocess.run(  # noqa: S603
            ["glab", *args],  # noqa: S607  # nosec B607
            input=stdin,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return Reply(returncode=124, stdout="", stderr="timeout after 60 seconds")
    except OSError as exc:  # glab is not installed or cannot be started
        return Reply(returncode=127, stdout="", stderr=f"cannot run glab: {exc}")
    stderr = result.stderr or ""
    if result.returncode == 124:
        stderr = "timeout after 60 seconds"
    return Reply(
        returncode=result.returncode,
        stdout=result.stdout or "",
        stderr=stderr,
    )


class Client:
    """Talk to GitLab through ``glab api``."""

    def __init__(
        self,
        project: str,
        run: Runner = run_glab,
        hostname: str | None = None,
    ) -> None:
        self._project = quote(project, safe="")
        self._run = run
        self._hostname = hostname

    def _args(self, path: str, *, method: str = "GET") -> list[str]:
        args: list[str] = ["api"]
        if self._hostname:
            args.extend(["--hostname", self._hostname])
        if method != "GET":
            args.extend(["--method", method, "--input", "-", "-H", "Content-Type: application/json"])
        args.append(f"projects/{self._project}/{path}")
        return args

    def _get(self, path: str, page: int) -> Reply:
        """GET one page; glab takes a single path argument, so the query string is part of it."""
        separator = "&" if "?" in path else "?"
        return self._run(self._args(f"{path}{separator}per_page={PAGE_SIZE}&page={page}"), None)

    def _post(self, path: str, body: dict[str, Any]) -> Reply:
        return self._run(self._args(path, method="POST"), json.dumps(body))

    def _put(self, path: str, body: dict[str, Any]) -> Reply:
        return self._run(self._args(path, method="PUT"), json.dumps(body))

    def _check(self, reply: Reply, call: str) -> object:
        if reply.returncode != 0:
            raise GitLabError(
                f"{call}: non-zero return code {reply.returncode}; stderr: {_cut(reply.stderr)}"
            )
        try:
            return json.loads(reply.stdout)
        except (json.JSONDecodeError, ValueError) as exc:
            raise GitLabError(f"{call}: not valid JSON: {exc}") from exc

    def _pages(self, path: str, what: str) -> Iterator[tuple[str, list[Any]]]:
        """Each page of a list, with the call that made it; the last page is shorter than a full one."""
        for page in range(1, MAX_PAGES + 1):
            call = f"GET projects/{self._project}/{what} page {page}"
            data = self._list_of(self._check(self._get(path, page), call), call)
            yield call, data
            if len(data) < PAGE_SIZE:
                return
        raise GitLabError(f"GET projects/{self._project}/{what}: more than {MAX_PAGES} pages")

    def labels(self) -> dict[str, int]:
        """Label name -> id, every page."""
        result: dict[str, int] = {}
        for call, data in self._pages("labels", "labels"):
            for item in data:
                if not isinstance(item, dict) or "id" not in item or "name" not in item:
                    raise GitLabError(f"{call}: missing field (id or name)")
                if not isinstance(item["name"], str):
                    raise GitLabError(f"{call}: name is not a string")
                result[item["name"]] = self._int_field(item, "id", call)
        return result

    def issues(self) -> tuple[RemoteIssue, ...]:
        """Every issue, opened and closed, every page."""
        result: list[RemoteIssue] = []
        for call, data in self._pages("issues?state=all", "issues"):
            result.extend(self._remote_issue(item, call) for item in data)
        return tuple(result)

    def _remote_issue(self, item: object, call: str) -> RemoteIssue:
        """One issue of a page, or a ``GitLabError`` naming what is wrong with it."""
        if not isinstance(item, dict):
            raise GitLabError(f"{call}: expected a dict, got {type(item).__name__}")
        if item.get("iid") is None or item.get("title") is None:
            raise GitLabError(f"{call}: missing field (iid or title)")
        raw_labels = item.get("labels", [])
        if not isinstance(raw_labels, list):
            raise GitLabError(f"{call}: labels is not a list")
        state = item.get("state")
        if state not in ("opened", "closed"):
            raise GitLabError(f"{call}: unknown state {state!r}")
        description = item.get("description")
        if description is not None and not isinstance(description, str):
            raise GitLabError(f"{call}: description is not a string")
        return RemoteIssue(
            iid=self._int_field(item, "iid", call),
            title=str(item["title"]),
            description=description or "",
            labels=tuple(str(label) for label in raw_labels),
            state=state,
        )

    def create_label(self, name: str, color: str) -> int:
        """Create a label; its id."""
        call = f"POST projects/{self._project}/labels"
        reply = self._post("labels", {"name": name, "color": color})
        return self._integer(self._check(reply, call), call, "id")

    def create_issue(self, title: str, description: str, labels: Sequence[str]) -> int:
        """Create an issue with these labels; its iid."""
        call = f"POST projects/{self._project}/issues"
        body = {"title": title, "description": description, "labels": ",".join(labels)}
        reply = self._post("issues", body)
        return self._integer(self._check(reply, call), call, "iid")

    def update_issue(
        self,
        iid: int,
        *,
        title: str | None = None,
        description: str | None = None,
        add_labels: Sequence[str] = (),
        remove_labels: Sequence[str] = (),
        state_event: str | None = None,
    ) -> None:
        """Change what is given of issue ``iid``; labels are added and removed, never replaced."""
        if state_event is not None and state_event not in ("close", "reopen"):
            raise ValueError(f"invalid state_event {state_event!r}")
        body: dict[str, object] = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if add_labels:
            body["add_labels"] = ",".join(add_labels)  # "labels" would REPLACE every label of the issue
        if remove_labels:
            body["remove_labels"] = ",".join(remove_labels)
        if state_event is not None:
            body["state_event"] = state_event
        if not body:
            raise ValueError("no fields given")
        call = f"PUT projects/{self._project}/issues/{iid}"
        data = self._check(self._put(f"issues/{iid}", body), call)
        if not isinstance(data, dict):
            raise GitLabError(f"{call}: expected an object, got {type(data).__name__}")

    def _object(self, data: object, call: str, *fields: str) -> dict[str, Any]:
        """``data`` as an object holding ``fields``, or a ``GitLabError``."""
        if not isinstance(data, dict):
            raise GitLabError(f"{call}: expected an object, got {type(data).__name__}")
        missing = [name for name in fields if name not in data]
        if missing:
            raise GitLabError(f"{call}: missing field ({' or '.join(missing)})")
        return data

    @staticmethod
    def _int_field(item: Mapping[str, Any], field: str, call: str) -> int:
        """The integer ``field`` of an item of a list (an id is never a boolean), or a ``GitLabError``."""
        value = item[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise GitLabError(f"{call}: {field} is not an integer")
        return value

    def _integer(self, data: object, call: str, field: str) -> int:
        """The integer ``field`` of an answer that is an object, or a ``GitLabError``."""
        return self._int_field(self._object(data, call, field), field, call)

    def _list_of(self, data: object, call: str) -> list[Any]:
        if not isinstance(data, list):
            raise GitLabError(f"{call}: expected a list, got {type(data).__name__}")
        return data

    def _board(self, name: str) -> tuple[int, bool]:
        """The id of the board called ``name`` and whether it had to be created."""
        for call, boards in self._pages("boards", "boards"):
            for board in boards:
                if isinstance(board, dict) and board.get("name") == name:
                    return self._int_field(board, "id", call), False
        call = f"POST projects/{self._project}/boards"
        created = self._object(self._check(self._post("boards", {"name": name}), call), call, "id")
        return self._int_field(created, "id", call), True

    def _board_label_ids(self, board_id: int) -> set[int]:
        """The ids of the labels that already have a list on the board."""
        ids: set[int] = set()
        for call, lists in self._pages(f"boards/{board_id}/lists", f"boards/{board_id}/lists"):
            for entry in lists:
                if isinstance(entry, dict) and isinstance(entry.get("label"), dict):
                    ids.add(self._int_field(entry["label"], "id", call))
        return ids

    def ensure_board(self, name: str, label_names: Sequence[str]) -> bool:
        """Give the board ``name`` one list per label of ``label_names``; True if something was created."""
        known = self.labels()
        unknown = [label for label in label_names if label not in known]
        if unknown:
            raise GitLabError(f"ensure_board: unknown label {unknown[0]!r}")
        board_id, created = self._board(name)
        existing = self._board_label_ids(board_id)
        missing = [known[label] for label in label_names if known[label] not in existing]
        call = f"POST projects/{self._project}/boards/{board_id}/lists"
        for label_id in missing:
            reply = self._post(f"boards/{board_id}/lists", {"label_id": label_id})
            self._object(self._check(reply, call), call, "id")
        return created or bool(missing)
