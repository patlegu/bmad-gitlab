# bmad-gitlab

A [BMAD](https://github.com/bmad-code-org/BMAD-METHOD) module that mirrors a project's sprint tracking
(`sprint-status.yaml`, epics, stories) into GitLab issues, so that the progress of a BMAD sprint is visible and
shared in the tracker.

**Status:** implemented. The tool is tested with ≥ 95 % coverage and exercised against a real GitLab project.

## Usage

```console
$ bmad-gitlab sync --project GROUP/PROJECT \
    --sprint sprint-status.yaml epics.md \
    --sprint next-sprint.yaml next-epics.md
```

Dry-run by default — prints the plan without writing anything. Add `--apply` to actually create labels, issues, and the board on GitLab:

```console
$ bmad-gitlab sync --project GROUP/PROJECT \
    --sprint sprint-status.yaml epics.md \
    --apply
```

### Options

| Flag | Meaning |
|---|---|
| `--project GROUP/PROJECT` | GitLab project (required) |
| `--sprint STATUS EPICS` | A sprint pair; repeat for multiple sprints (required) |
| `--prefix SPRINT=TEXT` | Put TEXT in front of every issue title of the sprint named SPRINT (its `project` in `sprint-status.yaml`), to tell apart sprints that share numbers, for example `--prefix 'orbit-extras=[extras]'`. Adding or removing it later renames the existing issues |
| `--hostname HOST` | Custom GitLab hostname (default: gitlab.com) |
| `--apply` | Actually write to GitLab |
| `--allow-problems` | Proceed even when the files disagree (a key with no section, a section with no key, two keys for one epic or story) |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 2 | Argument or file read error |
| 3 | Problems found with `--apply` (use `--allow-problems` to override) |
| 4 | GitLab API error |

### As a BMAD module

Install the module into a BMAD project with the BMAD installer, from this repository:

```console
$ npx bmad-method install --directory . --custom-source /path/to/bmad-gitlab --tools claude-code
```

It asks for the GitLab project, the host and whether the hook may apply without asking, and installs the
`bmad-gitlab` skill (the engine is carried inside it, nothing else to install). Authentication stays in `glab`
(`glab auth login`); no token is stored anywhere.

The skill has three intents: **sync** (plan, ask, then apply), **status** (what differs, nothing written) and
**setup** (the project, more sprints, title prefixes, and the hook). The hook is the `on_complete` instruction of
`bmad-sprint-planning`, written by `setup` into `_bmad/custom/bmad-sprint-planning.toml`: after sprint planning the
plan is shown, and **nothing is written to GitLab unless you apply it**, or you turned `auto_apply` on. The
settings live in `[modules.bgl]` of the team configuration (`_bmad/custom/config.toml`).

The engine inside the skill is a copy of `src/bmad_gitlab/`; after changing the engine run
`python scripts/vendor.py` (a test fails when the copy differs).

## Design

- **A deterministic engine, a thin skill around it.** The synchronisation is a Python command-line tool run
  with `uv`, tested with pytest and exercised against a real GitLab project. A BMAD skill and a module package
  it: the skill tells the agent when to run the tool (the `on_complete` hook of `bmad-sprint-planning` is the
  trigger), the module installs both. The agent writes text where language is needed; it never carries the logic.
- **File to GitLab first.** `sprint-status.yaml` stays the master copy; the tool projects it into issues. The
  keys and markers are those a later move to "the tracker is the source of truth" needs, for when several
  people work on the same sprint in parallel.
- **GitLab without Premium.** Plain labels (`type:epic|story`, `status:backlog|ready-for-dev|in-progress|review|done`,
  `epic:<sprint>:N`, `prd:<sprint>`), one issue board per project, issues and merge requests only. No epics, no scoped labels, no iterations.
- **Idempotent.** Each issue carries a hidden marker with its sprint, its BMAD key and a hash of its text
  (`<!-- bmad:v1 sprint=… key=1-1-… hash=… -->`); nothing is
  stored in `sprint-status.yaml`, which BMAD regenerates. Running the tool twice changes nothing.
- **Dry run by default.** Creating or changing anything on GitLab needs an explicit option.

## Rules the engine follows

- A lookup that fails is a failure, never "nothing to do".
- An unknown issue state is an error, never "opened" or "closed" by default.
- A `status:` label is the tool's only when it is one of the five it writes (`status:backlog`, `status:ready-for-dev`,
  `status:in-progress`, `status:review`, `status:done`): any other label, whatever its name, is left alone.
- The tool reads the BMAD configuration of the project it is run in, which runs `_bmad/scripts/resolve_config.py`
  of that project: run it in a project you trust.
- Every call to the `glab` command line is exercised against a real project before it is merged.
- Titles follow one format per artefact: `Epic {n}: {title}`, `Story {epic}.{story}: {title}`.
- The project name (`project:` of `sprint-status.yaml`, BMAD's `project_name`) is written in labels and in the hidden marker of each
  issue, so every run of characters other than letters, digits, `_`, `.` and `-` becomes one dash (`My project` gives
  `My-project`). A name that is already made of those is unchanged. The sync says so when it renames, and refuses two
  sprints that end up with the same name.

## Tested on

A real GitLab project with seven epics, twenty-four stories and a second sprint that reuses the same numbers (the
`--prefix` option exists for that), and on a project whose epics file uses the BMAD default layout (an epic list, then
the details with the stories one level deeper). The test fixtures are invented (`tests/fixtures/orbit*`).

## Language

The module is written in English: code, documentation, commits, issues and the text it publishes to GitLab. It reads
planning files written in any language; the headings of the epics files are recognised in English (`## Epic N: Title`)
and in French (`## Épique N : Titre`).

## License

MIT, see [LICENSE](LICENSE).
