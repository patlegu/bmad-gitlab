# Changelog

## 0.3.0

- `sync --apply` makes a milestone for each epic (named like its issue, holding the issues of its stories, closed when the epic is done) and writes in the issue of each epic a checklist of its stories (`- [x] Story 4.1: … (#12)`): the progress by epic that GitLab Premium gets from epics, on the free tier. Planned from what GitLab holds, so a second run changes nothing. `--no-milestones` and `--no-checklists` turn each off; a refusal of GitLab is a warning, not a failure.

## 0.2.0

- `sync --apply` makes four saved views by status in the Work items tab (`BMAD: Backlog`, `In progress`, `Review`, `Done`), created or corrected by name and never duplicated. `--no-views` turns them off. A refusal of GitLab (for example the limit of five views per person) is a warning, not a failure: the issues and the board are done.

## 0.1.7

- A story numbered 0 ("Story 2.0", a prerequisite of its epic) is read: the key `2-0-name` was refused as "must be 1 or more" while the epics file already accepted the heading, so a project that has one could not be mirrored at all. An epic numbered 0 is still refused.

## 0.1.6

First public release.

A BMAD module and a command-line engine that mirror the sprint tracking of a BMAD project
(`sprint-status.yaml` and the epics file) into GitLab issues, labels and one board.

- Deterministic engine: it plans first, writes nothing without `--apply`, and is idempotent.
- Reads both layouts of the BMAD epics file (epics and stories at level 2 or 3 and one or two levels under).
- Several sprints in one project, told apart by their name (any `project_name` is turned into a sprint name).
- Every list of GitLab is read page by page; every identifier is checked.
- Installs as a BMAD custom module: a skill with `sync`, `status` and `setup`, and an `on_complete` hook for
  sprint planning that never writes without an explicit yes unless `auto_apply` is on.
- Authentication stays in `glab`; no token is stored.
