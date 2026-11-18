# Setup

Register the module in this project: where the issues go, and what runs after sprint planning. The settings are
written to `_bmad/custom/config.toml` (the team file: no secret in it, it is meant to be committed) and the hook to
`_bmad/custom/bmad-sprint-planning.toml`. Authentication stays in `glab`; no token is ever asked for or written.

## Ask, all together, with the defaults shown

- **GitLab project** (`GROUP/PROJECT`), required. Offer a default from `git remote get-url origin` when it is a
  GitLab address; never guess when there is none.
- **GitLab host**, default `gitlab.com`; ask only when the remote is on another host.
- **More sprints**: look in `{implementation_artifacts}` for other `sprint-status*.yaml` files and their epics
  files. For each one the user wants mirrored: the two paths, and a title prefix when its numbers repeat those of
  the main sprint (for example `app-extras=[extras]`, where the left side is the `project:` line of that status file).
- **Apply without asking when run by the hook** (`auto_apply`), default **no**. Say what it means: with yes, the
  end of sprint planning creates and changes issues on GitLab by itself.

## Then

1. Run `uv run {skill-root}/scripts/gl_setup.py --project-root {project-root} --project <GROUP/PROJECT>` with
   `--hostname`, `--auto-apply`, `--extra-sprint STATUS=EPICS` and `--prefix SPRINT=TEXT` for what was chosen.
2. It prints what it wrote. If the hook file already existed and is not the module's, it is kept and the line to
   add is given: show that line to the user, do not edit the file.
3. Check the whole chain without writing anything: run the **status** intent. If it fails with exit 5, give the
   command it names.
4. Tell the user what will happen after the next sprint planning: the plan is shown, and nothing is written to
   GitLab unless they apply it (or `auto_apply` is on).
