# Changelog

All notable changes to **IssueOps** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

See [ROADMAP.md](./ROADMAP.md) for upcoming phases.

## [1.0.1] - 2026-05-24

### Added
- `SECURITY.md` describing private vulnerability reporting and response timelines.
- `ROADMAP.md` outlining phases v1.1 → v2.0.
- Expanded `CONTRIBUTING.md` with the full dev / lint / type-check / test workflow.

### Changed
- `CHANGELOG.md` restructured to Keep-a-Changelog with an `[Unreleased]` section.

### Fixed
- Coverage gate now enforced at 70% via `--cov-fail-under` (CI green).

## [1.0.0] - 2026-05-24 — GitHub Marketplace release

### Added
- **Confidence gating:** Extractions below `MIN_CONFIDENCE` (default 0.75) are routed to `triage/low-confidence` instead of auto-labeled.
- **JSON-Logic `in` and `!` operators:** Enables staleness rules like `"in": ["waiting-for-info", {"var": "labels"}]`.
- **Rate-limit backoff** on GitHub Search API with exponential retry.
- **CI pipeline** (`.github/workflows/ci.yml`) running ruff, mypy, and pytest with coverage gating.
- **Pre-commit hooks** for ruff format + secret detection.
- **Test coverage:** 50 tests across extractor, triage, logic, duplicate, and github services.

### Changed
- **SDK migration:** `google-generativeai` (deprecated) → `google-genai` 2.5+, fully async via `client.aio.models.generate_content`.
- **Pydantic v2:** `class Config` → `model_config = ConfigDict(extra="forbid")`.
- **Config cleanup:** Removed dead legacy fields (Redis, FastAPI server, CORS) from `app/core/config.py`.
- **README rewrite:** ASCII architecture diagram, features table, accurate `action.yml` example, schema reference, design decisions section.

### Fixed
- `app/cli/main.py` runtime crash from missing `Optional, List` imports.
- mypy strict compliance: explicit `None` defaults on `DuplicateResult`, `cast(Literal[...])` on user input.
- `response.text` null guards in extractor.
- ruff E741 ambiguous variable `l` in list comprehensions.

## [0.x] - Pre-release

Earlier iterations: FastAPI/Streamlit prototype → CLI-only pivot → ETL pipeline → Marketplace-ready packaging. See git history for details.
