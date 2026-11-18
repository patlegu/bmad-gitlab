---
title: 'Module Plan'
status: 'built and installed through the BMAD installer'
module_name: 'bmad-gitlab'
module_code: 'bgl'
module_description: 'Mirrors the BMAD sprint (sprint-status.yaml and the epics file) into GitLab issues, labels and a board.'
architecture: 'one workflow skill around a deterministic engine'
standalone: true
expands_module: ''
skills_planned: ['bmad-gitlab']
config_variables: ['gitlab_project', 'gitlab_hostname', 'title_prefixes', 'extra_sprints', 'auto_apply']
created: '2026-11-18'
updated: '2026-11-18'
---

# Module Plan

## Vision

A BMAD project plans its work in files (`epics.md`, `sprint-status.yaml`). When a team, or one person with
agents, works from a GitLab project, the same work has to be visible there: one issue per epic and story, status
as a label, one board. The engine (`bmad-gitlab sync`, finished and exercised against a real GitLab project)
does that deterministically. The module is the missing half: it makes the sync happen **at the right moment, with
the right settings, without anyone typing the command**, and it never writes to GitLab without an explicit apply.

## Architecture

**One workflow skill, `bmad-gitlab`, around the engine; a standalone self-registering module** (the module builder
recommends this for a single skill: no separate `-setup` skill, the skill registers itself with `setup`).
The skill carries no logic: it checks the prerequisites, builds the command from the module configuration, runs the
engine, and reports. The agent writes text only where language is needed (the summary to the user).

### How the engine travels with the skill (decision to confirm)

**Recommended: vendor the engine inside the skill.** `skills/bmad-gitlab/scripts/` holds a built copy of the
`bmad_gitlab` package and a one-file launcher with inline dependencies (`pyyaml`), run as
`uv run {skill-root}/scripts/bmad_gitlab.py sync ...`. Installing the module is then copying one folder: no
network, no private-repository access, no version drift between the skill and the engine it calls.
`src/bmad_gitlab/` stays the single source; a `vendor` script copies it, and **a test fails when the vendored copy
differs from the source** (a copy that can drift without any alarm is a defect waiting).
Rejected: `uvx --from git+...` (needs the network and access to the repository at every run, and pins nothing);
a `pip install` step in `setup` (a second place where the version lives, a global install to maintain).

### The trigger

`bmad-sprint-planning` ends with `{workflow.on_complete}`, a scalar instruction read at its last step. Its own
`customize.toml` is overwritten on update, so the module never edits it: `setup` **writes
`{project-root}/_bmad/custom/bmad-sprint-planning.toml`** with
`[workflow] on_complete = "Run the bmad-gitlab skill in headless mode to mirror the sprint into GitLab."`
(and asks before touching an `on_complete` already set there: override wins, so it must not be silently replaced).
The skill is also callable by hand (`bmad-gitlab`, `status`, `setup`).

### Safety (the non-negotiable)

**Nothing is written to GitLab without an explicit apply.** Interactive: the skill shows the plan (what it would
create, change, close), then asks once. Headless: dry run and report, unless the module configuration says
`auto_apply: true` (default `false`). The visible change on a real project is the user's decision, not the hook's.

## Skills

### bmad-gitlab

**Type:** workflow

**Core Outcome:** after sprint planning, or on demand, the GitLab project shows exactly the epics and stories of
the sprint, with the right status labels, and the user knows what changed.

**The Non-Negotiable:** no write to GitLab without an explicit apply; a missing prerequisite (`glab`, its
authentication, `uv`) stops the run with one clear line saying what to do, never a half run.

**Capabilities:**

| Capability | Outcome | Inputs | Outputs |
| ---------- | ------- | ------ | ------- |
| sync | the plan, then (after approval or `auto_apply`) the issues, labels and board brought in line | module config, `sprint-status.yaml` + epics file of every configured sprint | the engine report: counts, problems, exit code |
| status | what differs between the sprint files and GitLab, nothing written | same | the dry-run plan, summarised in words |
| setup | the module registered, `on_complete` wired, `glab` checked | the user's answers | the `[modules.bgl]` table in `_bmad/custom/config.toml` (the team file the installer never touches), the `on_complete` override file |

Prerequisite check, in this order: `uv`, `glab`, `glab auth status` for the configured host. Each failure names the
command to run.

## Configuration variables

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `gitlab_project` | (asked) | `GROUP/PROJECT` the issues go to; required |
| `gitlab_hostname` | `gitlab.com` | for a self-hosted GitLab |
| `extra_sprints` | none | further pairs (status file, epics file) after the standard one, e.g. a second PRD |
| `title_prefixes` | none | `SPRINT=TEXT` pairs, to tell apart sprints that reuse the same numbers |
| `auto_apply` | `false` | apply without asking when run headless |

The standard pair is `{implementation_artifacts}/sprint-status.yaml` and `{planning_artifacts}/epics.md` from the
BMAD config (`modules.bmm`, read through the project's own `resolve_config.py`; this BMAD version keeps its
configuration in TOML layers, not in `config.yaml`). No token is ever stored: authentication stays in `glab`.

## Out of scope for 0.1

Reverse synchronisation (a card moved on the board is not written back to `sprint-status.yaml`); GitLab Premium
objects (epics, scoped labels, iterations); any other tracker.

## Build order (steps 1, 3 and a first real run are done: see the skill, `scripts/vendor.py`, and the tests)

1. Author the skill with the workflow builder, from this plan: `SKILL.md`, references `sync.md`, `status.md`,
   `headless.md`, the prerequisite check.
2. Package it with the module builder, standalone self-registering (`module.yaml`, `module-help.csv`,
   `marketplace.json`, the merge scripts).
3. The `vendor` script and its drift test; the one-file launcher; lint and types stay on `src/` only.
4. `setup` writes the `on_complete` override; test it on a throwaway BMAD project.
5. Real run: install it into a real BMAD project, run sprint planning, watch the hook produce the dry
   run, then apply with consent.
6. Validate the module with the module builder (VM); then the CQI audit of the repository; then the synthetic
   fixtures and a fresh history for the public release.

## Questions for the author

1. Module code `bgl`: fine, or another?
2. `auto_apply` defaults to `false`: confirm.
3. Vendored engine in the skill (recommended) rather than installed from the repository: confirm.

## What the build changed (2026-11-18)

- **Packaged by the installer, not by self-registration.** The module builder's standalone scaffold writes a
  `config.yaml` registration (`module-setup.md`, `merge-config.py`, `merge-help-csv.py`); the BMAD 6.12 installer
  keeps its configuration in TOML layers and registers a custom module itself from `assets/module.yaml` and
  `assets/module-help.csv`. A real install (`npx bmad-method install --custom-source`) into a throwaway project
  registered the module, put the three help entries in the catalogue, installed the skill with its vendored
  engine, and the installed skill ran `setup` then `status` against a real GitLab project ("nothing to do").
  The module builder's validator still reports the three legacy self-registration files as missing: they are left
  out on purpose, a second registration path would write a file nothing reads.
- **Known noise.** The installer prints two warnings that it cannot locate `module.yaml` for the module (it looks
  for `skills/<name>/module.yaml` or a `*-setup` skill, and reads the prompts from `assets/` of a standalone
  skill): the questions are asked and written, only the agent roster and user-scope keys are skipped, and this
  module has neither. A `module.yaml` at the other path loses the questions, so it stays in `assets/`.
- **Authors to decide before the public release:** `repository` and `homepage` of the marketplace manifest (the
  private GitLab address is there for now).
