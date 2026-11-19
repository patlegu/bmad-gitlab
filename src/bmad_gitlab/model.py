"""Read a BMAD sprint into items."""

from __future__ import annotations

import re
from collections.abc import Hashable, Iterator
from dataclasses import dataclass
from typing import Literal, TypeVar

import yaml

Kind = Literal["epic", "story", "retrospective"]
_MAX_DIGITS = 6  # an epic or a story has no more digits than this; int() refuses 4300
_K = TypeVar("_K", bound=Hashable)

EPIC_STATUSES = ("backlog", "in-progress", "done")
STORY_STATUSES = ("backlog", "ready-for-dev", "in-progress", "review", "done")
RETROSPECTIVE_STATUSES = ("optional", "done")

# BMAD writes an epic at level 2 or 3 and a story one or two levels under it, depending on whether the epics
# file has an "Epic Details" part: both layouts are read.
_EPIC_RE = re.compile(r"^(#{2,4})\s+(Épique|Epic)\s+([0-9]{1,6})\s*:\s*(.+)$")
_STORY_RE = re.compile(r"^(#{2,5})\s+Story\s+([0-9]{1,6})\.([0-9]{1,6})\s*:\s*(.+)$")


class SprintError(ValueError):
    """The sprint files cannot be read; the message says which key or heading and why."""


@dataclass(frozen=True)
class Entry:
    """One key of ``sprint-status.yaml``: what it is, its numbers and its status."""

    kind: Kind
    key: str
    epic: int
    story: int | None
    status: str


@dataclass(frozen=True)
class Item:
    """An entry of the sprint with the title and the text of its section of ``epics.md``."""

    kind: Kind
    key: str
    epic: int
    story: int | None
    status: str
    title: str
    body: str


@dataclass(frozen=True)
class RemoteIssue:
    """What GitLab holds, as the caller read it."""

    iid: int
    title: str
    description: str
    labels: tuple[str, ...]
    state: Literal["opened", "closed"]


@dataclass(frozen=True)
class Epics:
    """Parsed epics.md: titles and bodies by number."""

    epic_titles: dict[int, str]
    epic_bodies: dict[int, str]
    story_titles: dict[tuple[int, int], str]
    story_bodies: dict[tuple[int, int], str]
    duplicate_stories: tuple[tuple[int, int], ...] = ()

    @classmethod
    def empty(cls) -> Epics:
        return cls({}, {}, {}, {})


_OTHER_HEADING_RE = re.compile(r"^(#{2,6})\s+(.+)$")
_NOT_IN_A_NAME = re.compile(r"[^\w.-]+")


@dataclass(frozen=True)
class _Heading:
    """A heading of epics.md; ``epic`` is None when it is neither an epic nor a story."""

    line: int
    level: int
    epic: int | None
    story: int | None
    title: str


def _parse_heading(line: str, number: int) -> _Heading | None:
    if match := _EPIC_RE.match(line):
        return _Heading(number, len(match.group(1)), int(match.group(3)), None, match.group(4).strip())
    if match := _STORY_RE.match(line):
        epic, story = int(match.group(2)), int(match.group(3))
        return _Heading(number, len(match.group(1)), epic, story, match.group(4).strip())
    if match := _OTHER_HEADING_RE.match(line):
        return _Heading(number, len(match.group(1)), None, None, match.group(2).strip())
    return None


def _split_body(text: str) -> str:
    lines = text.split("\n")
    start = 0
    end = len(lines)
    while start < end and lines[start].strip() == "":
        start += 1
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    return "\n".join(lines[start:end])


def read_status(text: str) -> tuple[str, tuple[Entry, ...]]:
    """(project, entries in file order) of a sprint-status.yaml text."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SprintError(f"invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise SprintError("top level is not a mapping")

    if "development_status" not in data:
        raise SprintError("no development_status mapping")

    dev = data["development_status"]
    if not isinstance(dev, dict):
        raise SprintError("development_status is not a mapping")

    if not isinstance(data.get("project"), str):
        raise SprintError("no project string")

    entries: list[Entry] = []
    for key, status in dev.items():
        kind = _classify_key(key)
        if kind is None:
            raise SprintError(f"unknown key shape: {key!r}")
        epic_num, story_num = _parse_key_numbers(key, kind)
        if epic_num < 1:
            raise SprintError(f"the epic number of key {key!r} must be 1 or more")
        valid = _valid_statuses(kind)
        if status not in valid:
            raise SprintError(f"invalid status {status!r} for {kind} {key!r}")
        entries.append(Entry(kind, key, epic_num, story_num, status))

    return (data["project"], tuple(entries))


def sprint_name(project: str) -> str:
    """The sprint name written in the labels and in the hidden marker of an issue, from the project name.

    A name is cut at a space in a marker and at a comma in a list of labels, so every run of characters
    other than letters, digits, ``_``, ``.`` and ``-`` becomes one dash (``My project`` gives ``My-project``).
    A name that already holds only those is unchanged, and so are the issues made from it. This is the one
    rule that turns any ``project_name`` of BMAD into a sprint name; two names that give the same sprint are
    refused by the caller."""
    name = _NOT_IN_A_NAME.sub("-", project).strip("-")
    if not name:
        raise SprintError(f"the project name {project!r} holds no letter or digit")
    return name


def _classify_key(key: object) -> Kind | None:
    if not isinstance(key, str) or any(char.isspace() for char in key) or "-->" in key:
        return (
            None  # a key is written in the hidden marker of an issue, which ends at the first space or `-->`
        )
    if key.startswith("epic-") and key.endswith("-retrospective"):
        return "retrospective"
    if key.startswith("epic-"):
        return "epic"
    parts = key.split("-", 2)
    if len(parts) == 3 and parts[2]:
        return "story"
    return None


def _number(text: str, key: str) -> int:
    """The number written in ``text``: ASCII digits only (``int`` alone also takes ``+1``, ``1_0``, ``٣``)."""
    if not (text.isascii() and text.isdigit()) or len(text) > _MAX_DIGITS:
        raise SprintError(
            f"numbers in key {key!r} do not parse as integers (1 to {_MAX_DIGITS} digits): {text!r}"
        )
    return int(text)


def _parse_key_numbers(key: str, kind: Kind) -> tuple[int, int | None]:
    if kind == "epic":
        return (_number(key.removeprefix("epic-"), key), None)
    if kind == "retrospective":
        return (_number(key.removeprefix("epic-").removesuffix("-retrospective"), key), None)
    parts = key.split("-", 2)
    # a story may be numbered 0: a prerequisite of its epic ("Story 2.0")
    return (_number(parts[0], key), _number(parts[1], key))


def _valid_statuses(kind: Kind) -> tuple[str, ...]:
    if kind == "epic":
        return EPIC_STATUSES
    if kind == "story":
        return STORY_STATUSES
    return RETROSPECTIVE_STATUSES


def read_epics(text: str) -> Epics:
    """Parse an epics.md text into structured data."""
    lines = text.split("\n")
    epic_titles: dict[int, str] = {}
    epic_bodies: dict[int, str] = {}
    story_titles: dict[tuple[int, int], str] = {}
    story_bodies: dict[tuple[int, int], str] = {}
    duplicates: list[tuple[int, int]] = []
    for heading, epic, body in _sections(lines, _extract_headings(lines)):
        if heading.story is None:
            _keep_epic(epic_titles, epic_bodies, epic, heading.title, _split_body(body))
            continue
        number = (epic, heading.story)
        if number in story_titles:
            duplicates.append(number)
        story_titles[number] = heading.title
        story_bodies[number] = _split_body(body)
    return Epics(epic_titles, epic_bodies, story_titles, story_bodies, tuple(duplicates))


def _keep_epic(titles: dict[int, str], bodies: dict[int, str], epic: int, title: str, body: str) -> None:
    """Record an epic; one listed first and detailed later keeps its first title and its first text."""
    if epic not in titles:
        titles[epic] = title
        bodies[epic] = body
    elif not bodies[epic]:
        bodies[epic] = body


_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def _opens(line: str) -> str:
    """The run of backticks or tildes that opens a block of code on ``line``, or an empty string.

    As in CommonMark, the text after a backtick fence holds no backtick: three backticks around a word in a
    line of text are code in that line, not a block."""
    match = _FENCE_RE.match(line)
    if match is None or (match.group(1)[0] == "`" and "`" in match.group(2)):
        return ""
    return match.group(1)


def _closes(line: str, fence: str) -> bool:
    """True when ``line`` closes the block opened by ``fence``: the same character, as long, nothing after."""
    stripped = line.strip()
    return len(stripped) >= len(fence) and stripped == stripped[0] * len(stripped) and stripped[0] == fence[0]


def _extract_headings(lines: list[str]) -> list[_Heading]:
    """The headings that matter, in order; whatever is inside a fenced code block is not a heading.

    A heading that is neither an epic nor a story ends a section only when it is as high as the deepest epic
    or story heading of the file: a sub-heading inside a story belongs to the story."""
    found: list[_Heading] = []
    fence = ""  # the run of backticks or tildes that opened the block of code we are in
    for number, line in enumerate(lines):
        if fence:
            fence = "" if _closes(line, fence) else fence
        elif opening := _opens(line):
            fence = opening
        elif (heading := _parse_heading(line, number)) is not None:
            found.append(heading)
    deepest = max((h.level for h in found if h.epic is not None), default=3)
    return [h for h in found if h.epic is not None or h.level <= deepest]


def _sections(lines: list[str], headings: list[_Heading]) -> Iterator[tuple[_Heading, int, str]]:
    """Each epic and each story, with its epic number and its text up to the next heading of any kind."""
    for index, heading in enumerate(headings):
        if heading.epic is None:
            continue
        end = headings[index + 1].line if index + 1 < len(headings) else len(lines)
        yield heading, heading.epic, "\n".join(lines[heading.line + 1 : end])


def _section_of(entry: Entry, epics: Epics, problems: list[str]) -> tuple[str, str]:
    """The title and body of the section of ``entry`` in epics.md; a note in ``problems`` if there is none."""
    if entry.kind == "retrospective":
        return f"Retrospective: Epic {entry.epic}", ""
    if entry.story is not None:
        number = (entry.epic, entry.story)
        if number in epics.story_titles:
            return epics.story_titles[number], epics.story_bodies[number]
        problems.append(f"story {entry.key} has no section in epics.md")
        return entry.key.split("-", 2)[2].replace("-", " ").capitalize(), ""
    if entry.epic in epics.epic_titles:
        return epics.epic_titles[entry.epic], epics.epic_bodies[entry.epic]
    problems.append(f"epic-{entry.epic} has no section in epics.md")
    return f"Epic {entry.epic}", ""


def _make_item(entry: Entry, epics: Epics, problems: list[str]) -> Item:
    title, body = _section_of(entry, epics, problems)
    return Item(entry.kind, entry.key, entry.epic, entry.story, entry.status, title, body)


def _remember(found: dict[_K, Entry], number: _K, entry: Entry, what: str, problems: list[str]) -> None:
    """Record the entry of an epic or a story; a second key for the same number is a problem."""
    if number in found:
        problems.append(f"the sprint status has two keys for {what}: {found[number].key} and {entry.key}")
    found[number] = entry


def build_items(
    project_entries: tuple[Entry, ...],
    epics: Epics,
) -> tuple[tuple[Item, ...], tuple[str, ...]]:
    """The items in file order, and the problems found."""
    problems: list[str] = []
    entry_by_epic: dict[int, Entry] = {}
    entry_by_story: dict[tuple[int, int], Entry] = {}
    for entry in project_entries:
        if entry.kind == "retrospective":
            continue
        if entry.story is None:
            _remember(entry_by_epic, entry.epic, entry, f"epic {entry.epic}", problems)
        else:
            what = f"story {entry.epic}.{entry.story}"
            _remember(entry_by_story, (entry.epic, entry.story), entry, what, problems)

    items = [_make_item(e, epics, problems) for e in project_entries]

    for ep in epics.epic_titles:
        if ep not in entry_by_epic:
            problems.append(f"epics.md has epic {ep} with no entry in the sprint status")

    for ep, st in epics.story_titles:
        if (ep, st) not in entry_by_story:
            problems.append(f"epics.md has story {ep}.{st} with no entry in the sprint status")

    for ep, st in epics.duplicate_stories:
        problems.append(f"epics.md has duplicate story {ep}.{st}")

    return (tuple(items), tuple(problems))
