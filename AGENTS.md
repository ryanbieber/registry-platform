# AGENTS.md

Repository workflow rules:

- Use `uv` for Python dependency management and execution.
- Run the relevant test suite before handoff, at minimum `uv run pytest -q` from `backend/`.
- Run `pre-commit run --all-files` when a `.pre-commit-config.yaml` is present.
- Keep changes on a feature branch.
- Land completed work with a squash merge so feature history stays easy to read.

Implementation notes:

- Prefer the repo's existing patterns over new abstractions.
- Keep validation focused on end-to-end behavior when adding user-facing workflows.
