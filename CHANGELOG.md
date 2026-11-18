# Changelog

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
