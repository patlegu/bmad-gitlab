---
name: bmad-gitlab
description: Mirrors the BMAD sprint (sprint-status.yaml and the epics file) into GitLab issues, labels and a board. Use when the user says "sync the sprint to GitLab", "mirror the sprint into GitLab", "show the GitLab sprint status", "set up bmad-gitlab", or when sprint planning ends and its on_complete hook runs this skill.
---

# bmad-gitlab

You keep the GitLab project in step with the BMAD sprint. The sprint files stay the master copy; GitLab shows one
issue per epic and per story, the status as a label, and one board. The work is done by a deterministic engine
that sits in `scripts/`: you do not decide what to create or change, you run it, show the user what it found, and
ask before anything is written. The user is a developer who wants to see the plan before GitLab changes.

## Resolution rules

- `{skill-root}` is this skill's installed directory; `{project-root}` is the project working directory.
- Every command below is run from `{project-root}`.

## On Activation

Detect the intent from the request. If none is clear, ask whether to sync, show the status, or set up.

| Intent | When | Do |
| --- | --- | --- |
| **sync** | "sync", "mirror", the `on_complete` hook | the flow below |
| **status** | "what differs", "show the GitLab status" | `uv run {skill-root}/scripts/gl_run.py --project-root {project-root} status`, then say in words what the plan holds; write nothing |
| **setup** | "set up", "configure", or the first run finds `modules.bgl` unset | load `references/setup.md` |

`--headless` / `-H` means do not ask: see Headless.

## Sync

1. Run `uv run {skill-root}/scripts/gl_run.py --project-root {project-root} sync`. Without `--apply` this only
   plans; nothing is written to GitLab.
2. Say what it found in a few lines: labels and issues to create, to change, to close, and any problem it names.
   Do not paste the whole listing unless the user asks for it.
3. Ask once: apply these changes to `<the project>`? Only on a clear yes, run the same command with `--apply`.
4. Report the counts the engine prints at the end, and stop. The engine is idempotent: running it again changes
   nothing.

## Trust

The launcher reads the configuration by running `_bmad/scripts/resolve_config.py` of the project, and the project's
team file sets `gitlab_project` and `auto_apply`. Run the skill only in a project whose files you trust.

## When it fails

- **Exit 5**: the configuration or a prerequisite is wrong (`uv`, `glab`, its sign-in, a missing sprint file, an
  unset project). The message on stderr already says the one command to run; give it, and stop. Never work around
  it by calling GitLab yourself.
- **Exit 3**: the epics file and the sprint status disagree (a key with no section, a section with no key). List
  the problems and ask the user to fix the files; do not write around them.
- **Exit 4 or 2**: show the engine's message as it is.

## Headless

When invoked headless (the `on_complete` of sprint planning), do not ask: run
`uv run {skill-root}/scripts/gl_run.py --project-root {project-root} --headless sync`. It writes to GitLab only
when the module setting `auto_apply` is true, which is off by default. Report in two sentences: what the plan
holds, and whether it was applied. If it was not, say that running this skill applies it.
