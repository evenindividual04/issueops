# Contributing to IssueOps

Thanks for your interest in improving IssueOps. This guide covers how to set up the project, run the quality gates, and submit changes.

## Development Setup

```bash
git clone https://github.com/evenindividual04/issueops
cd issueops

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -e ".[dev]"
cp .env.example .env              # add your GEMINI_API_KEY
pre-commit install                # enable formatting/lint hooks
```

## Quality Gates

Every PR must pass the same checks CI runs:

```bash
# Lint
ruff check app/ tests/

# Format check
ruff format --check app/ tests/

# Type check
mypy app/

# Tests + coverage (floor: 70%)
pytest --cov=app --cov-fail-under=70
```

A pre-commit hook runs `ruff` and secret detection automatically on `git commit`.

## Project Layout

```
app/
├── cli/        # Typer commands + golden config templates
├── core/       # Settings, env-only config
├── models/     # Pydantic schemas (single source of truth)
└── services/   # extractor, triage, duplicate, github, cache, logic, reporter
tests/          # mirrors app/ structure
```

See [ROADMAP.md](./ROADMAP.md) for upcoming phases — each phase has discrete checkboxes you can pick up.

## Pull Request Workflow

1. Fork → branch → commit using conventional prefixes (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`).
2. Add or update tests for any behavior change.
3. Update `CHANGELOG.md` under `[Unreleased]`.
4. Update `README.md` if the change affects public-facing behavior or config.
5. Ensure CI is green and coverage hasn't dropped.
6. Open a PR with a description that explains the **why**, not just the **what**.

## Issue Triage

Bug reports should include:
- IssueOps version (`issueops --version`).
- Python version (`python --version`).
- A minimal `issueops.yaml` that reproduces the problem.
- The full Action log or CLI output (redact secrets first).

Feature requests should reference the roadmap phase they fit into, or propose a new phase.

## Code of Conduct

This project follows the [Contributor Covenant](./CODE_OF_CONDUCT.md).

## Security

Do **not** open public issues for vulnerabilities. See [SECURITY.md](./SECURITY.md) for the private disclosure process.

## Releasing (Maintainers)

1. Bump version in `pyproject.toml`.
2. Move `[Unreleased]` entries in `CHANGELOG.md` under the new version with today's date.
3. Tag: `git tag -a v1.x.y -m "Release v1.x.y"` and push.
4. The Marketplace tag (`v1`) is fast-forwarded to the latest minor release.
