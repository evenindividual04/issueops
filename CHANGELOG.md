# Changelog

All notable changes to the **AI Triage Automation Engine** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-12-18

### Added
- **Unified Core:** Schema now tracks "Contributor Signals" (`difficulty`, `required_skills`) alongside "Maintainer Signals" (`crash`, `security`).
- **Job Board:** CLI `report` command generates a static HTML "Good First Issue" board (`job_board.html`).
- **GitHub Action:** Full support for running in CI/CD via `action` command and `action.yml`.
- **Search API:** `GitHubService` now uses Search API to efficiently exclude PRs and filter by state.
- **Docker:** Production-ready `Dockerfile` (Python 3.12-slim).

### Changed
- **CLI:** `scan` command (formerly `run`) now supports `--role maintainer|contributor` filtering.
- **Rules:** `rules.yaml` rewritten to govern both severity triage and difficulty classification.
- **Extractor:** System Prompt updated to act as a "Technical Screener".

### Hardening Sprint (Post-v2.0.0)
- **Config Robustness:** Added strict Pydantic schema for `rules.yaml` with automatic fallback to defaults to prevent CI crashes.
- **Audit Tooling:** Added `audit` command to generate CSV reports for human-in-the-loop verification.
- **Documentation:** Added Failure Modes, Architecture Diagram, and Troubleshooting guide.
- **Optimization:** Implemented SHA-256 Caching to reduce API costs by 90%.
- **Community:** Added Marketplace assets (`action.yml`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`).
- **Features:** Added RSS Feeds for contributors and **Semantic Duplicate Detection**.



## [1.0.0] - 2025-12-18

### Added
- **Core:** `ExtractorService` to parse unstructured issue text using Google Gemini (`app/services/extractor.py`).
- **Rules Engine:** Deterministic `TriageService` based on `json-logic` and `rules.yaml`.
- **CLI:** `main.py` entry point with `extract`, `decide`, and `run` commands (`app/cli/main.py`).
- **Integration:** `GitHubService` now supports applying labels and comments (with dry-run mode).
- **Testing:** Comprehensive test suite (`tests/`) with mocked LLM calls, valid fixtures, and retry logic verification.
- **Documentation:** 
    - `ARCHITECTURE.md`: Detailed breakdown of the ETL pattern (Extract, Transform, Load).
    - `README.md`: Updated usage guide for both Local CLI and GitHub Action.
    - `LICENSE`: MIT License.
- **Quality:** `mypy.ini` for type checking configuration and strictly typed Pydantic schemas (`app/models/schemas.py`).

### Changed
- **Architecture:** Complete pivot from a FastAPI/Streamlit web application to a stateless CLI tool.
- **Dependencies:** Pruned `requirements.txt` to <10 essential packages (removed `fastapi`, `uvicorn`, `streamlit`).
- **Logic:** Replaced incompatible `json-logic` PyPI library with a custom, lightweight implementation (`app/services/logic.py`).
- **Configuration:** Moved prompts to `extractor.py` and consolidated configuration in `app/core/config.py`.

### Removed
- Legacy backend API (`app/api/`) and entry points.
- Legacy frontend (`frontend/`) and associated dependencies.
- Unused services and utilities (`app/services/llm_service.py`, `app/utils/`, `app/core/prompts.py`).
