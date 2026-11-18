# AGENTS.md

Rules for anyone, human or agent, who changes this repository.

- Python 3.11+, run with `uv`. Checks, from the repository root: `uv run pytest -q`, `uv run ruff check .`.
- Code and commits in English. Commits: `type(scope): what changes`, no issue numbers in the subject.
- The engine is deterministic: no function guesses, a failed lookup is an error and not an empty result,
  an unknown state is never "ok". Every function of the package has a McCabe complexity of 10 or less and
  at most six parameters (the ruff configuration enforces both; never change it to silence a check).
- Calls to GitLab go through one small client that takes the command runner as a parameter, so that tests
  use a fake runner and never reach the network. A change to the client is also exercised once against a
  real project before it is merged.
- A test must fail when the behaviour it names is removed. Do not edit a test to make code pass.
- Never write a token, a host name or an internal address in a file, a commit or an issue.
