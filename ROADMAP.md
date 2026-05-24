# IssueOps — Production Roadmap

> From v1.0 (working Marketplace Action) to v2.0 (enterprise-grade triage platform).
> Each phase is independently shippable. Track items with `[ ]` → `[x]`.

---

## Phase 0 — Foundations (Current State Audit)

**Goal:** Lock down what exists before extending it.

- [x] Generate a real coverage report (`pytest --cov=app --cov-report=html`) and identify modules below 80%. _(67.65% overall; cache 33%, reporter 0%, triage 55%, github_service 67%)_
- [x] Add a `CHANGELOG.md` at repo root following Keep-a-Changelog format. Backfill v1.0.0.
- [x] Add `SECURITY.md` with vulnerability disclosure process (GitHub Security Advisories + email fallback).
- [x] Add `CONTRIBUTING.md` covering: dev setup, test commands, PR checklist, release process.
- [ ] Tag the current state as `v1.0.1` after these meta-files land (no code changes). _(deferred — needs explicit user approval to tag/push)_

**Acceptance:** Repo passes a basic open-source-project hygiene checklist (LICENSE, README, CHANGELOG, SECURITY, CONTRIBUTING, CI badge, coverage badge).

---

## Phase 1 — Reliability Hardening (v1.1)

**Goal:** Make the existing pipeline fail-safe and idempotent. Zero new features.

### 1.1 Idempotency

- [x] Add `processed_signatures: Dict[str, str]` to `CacheManager` keyed by `f"{repo}#{issue_number}"` → `sha256(body)`.
- [x] In the Action entrypoint, skip triage if `current_sha == cached_sha` AND `last_run_within(24h)`.
- [x] Add `--force` flag to `action` command to bypass idempotency. _(extended to `--force` on Action; scan command has implicit force behavior)_

**Files:** `app/services/cache.py`, `app/cli/main.py`, new `tests/test_idempotency.py`.

### 1.2 Comment Deduplication

- [ ] In `GitHubService`, add `find_bot_comment(owner, repo, issue_number, marker: str) -> Optional[int]`.
- [ ] Add `update_comment(owner, repo, comment_id, body) -> bool`.
- [ ] Embed a hidden HTML marker in every bot comment: `<!-- issueops:triage -->`.
- [ ] Triage flow: search for existing marker, update if present, else create.

**Files:** `app/services/github_service.py`, `tests/test_github_service.py`.

### 1.3 Label Diff Apply

- [ ] Extend `TriageAction` schema: add `labels_to_remove: List[str] = []`.
- [ ] Add `GitHubService.remove_label(owner, repo, issue_number, label)`.
- [ ] Triage flow: compute `(current_labels, desired_labels)`, diff, apply only the delta.
- [ ] Never remove labels not owned by IssueOps — maintain a `MANAGED_LABELS` whitelist derived from the config file.

**Files:** `app/models/schemas.py`, `app/services/triage.py`, `app/services/github_service.py`.

### 1.4 Human Override Lock

- [x] If issue has label `triage/locked` or `triage/override`, skip triage entirely. Log skip reason.
- [ ] Document in README under "Escape Hatches" section.

**Files:** `app/cli/main.py` (Action entrypoint), README.md.

### 1.5 Circuit Breaker for LLM

- [ ] Wrap `ExtractorService._generate_and_parse` in a circuit breaker (consecutive failure count, open after 5, half-open after 60s).
- [ ] When circuit is open, fall back to a deterministic rules-only path: regex-based crash detection on raw text.
- [ ] Add `extraction_mode: Literal["llm", "fallback"]` field to `IssueMetadata`. Confidence forced to 0.5 in fallback mode → routes to `triage/low-confidence` by default.

**Files:** new `app/core/circuit_breaker.py`, `app/services/extractor.py`, `app/models/schemas.py`.

### 1.6 Global Rate Limiter

- [ ] Add a token-bucket limiter in `GitHubService` that caps mutating calls (POST/PATCH) at 1 req/sec.
- [ ] Reads (GET) limited only by GitHub's own rate limit + existing exponential backoff.

**Files:** `app/services/github_service.py`, new `app/core/rate_limiter.py`.

**Acceptance:** Running the Action twice on the same issue produces zero duplicate comments, zero label thrash, and one (cached) LLM call.

---

## Phase 2 — Observability (v1.2)

**Goal:** You can answer "what happened and why" for any triaged issue without re-running.

### 2.1 Structured Audit Log

- [ ] Define `TriageAuditRecord` Pydantic model: `timestamp, repo, issue_number, body_sha, extraction_confidence, extraction_mode, matched_rule, labels_applied, labels_removed, duplicate_of, latency_ms, llm_tokens_used`.
- [ ] Every Action run writes `triage-audit.jsonl` (append) as a workflow artifact.
- [ ] Add `issueops audit-log <path>` CLI subcommand that pretty-prints the JSONL.

**Files:** new `app/models/audit.py`, `app/cli/main.py`, `app/services/triage.py`.

### 2.2 Metrics Command

- [ ] New CLI: `issueops stats owner/repo --since 7d`.
- [ ] Reads audit logs (local or from GitHub artifacts), produces a Rich table:
  - Total triaged
  - Confidence histogram (5 buckets)
  - Top 5 matched rules
  - Duplicate detection hit rate
  - LLM cache hit rate
  - p50 / p95 latency
- [ ] Emit JSON output flag (`--json`) for piping into dashboards.

**Files:** new `app/cli/stats.py`, `app/services/metrics.py`.

### 2.3 Structured Logging

- [ ] Replace `logging.info(f"...")` calls with a structured logger (`structlog` or stdlib + custom formatter).
- [ ] Every log line includes `repo`, `issue_number`, `run_id` (UUID per Action invocation).
- [ ] `--log-format json` flag emits JSON-L for ingestion into log aggregators.

**Files:** new `app/core/logging.py`, all services.

### 2.4 Optional OpenTelemetry Export

- [ ] Behind a feature flag (`OTEL_EXPORTER_OTLP_ENDPOINT` env var).
- [ ] Emit spans for: `extract`, `duplicate_search`, `rules_evaluate`, `apply_labels`.
- [ ] Document in README under "Enterprise Observability".

**Files:** `app/core/telemetry.py`, optional dependency in `pyproject.toml` (`[project.optional-dependencies] otel = [...]`).

**Acceptance:** After a week of running, you can answer "what's our false-positive rate on `critical` labels?" from audit logs alone.

---

## Phase 3 — Intelligence Upgrade (v1.3)

**Goal:** Better extraction, better duplicates, better rules.

### 3.1 Smart Text Truncation

- [ ] Replace `text[:10000]` with `app/core/text.py:summarize_for_llm(text, max_chars=10000)`:
  - First 2000 chars (the user's framing)
  - Last 2000 chars (often stack trace)
  - All lines matching `Error|Exception|Traceback|panic|SIGSEGV|FATAL`
  - Deduplicated, joined with section markers
- [ ] Unit tests confirming stack traces near the end of long bodies survive truncation.

**Files:** new `app/core/text.py`, `app/services/extractor.py`, `tests/test_text.py`.

### 3.2 Embedding-Based Duplicate Detection

- [ ] Add `gemini-embedding-001` calls via `client.aio.models.embed_content`.
- [ ] Maintain a local FAISS index at `.issueops/embeddings.faiss` (or sqlite-vec for zero-dep).
- [ ] On each new issue: embed → top-K similarity search → feed candidates into existing semantic verifier.
- [ ] Fall back to keyword search if embedding fails (current behavior).
- [ ] Add `issueops index-rebuild owner/repo` CLI command for backfill.

**Files:** new `app/services/embedding_service.py`, `app/services/duplicate_service.py`, optional dep `faiss-cpu` or `sqlite-vec`.

### 3.3 Derived Fields in Rules Context

- [ ] In `TriageService.evaluate`, always inject:
  - `days_since_created`
  - `days_since_updated`
  - `comment_count`
  - `reaction_count`
  - `is_first_time_contributor` (from GitHub API)
  - `body_length`
- [ ] Document available variables in a `CONFIG.md` reference.

**Files:** `app/services/triage.py`, `app/services/github_service.py` (add `get_contributor_history`), `CONFIG.md`.

### 3.4 Schema Versioning

- [ ] Add `schema_version: "v1"` at top of `issueops.yaml`.
- [ ] Validate on load — warn if missing, error if unknown.
- [ ] Add a migration registry (`app/core/migrations.py`) for future schema changes.

**Files:** `app/services/config_loader.py` (extract from current location), `app/cli/templates.py`.

### 3.5 Rules Engine Expansion

- [ ] Add operators: `contains`, `matches` (regex), `between`, `count`, `any`, `all`.
- [ ] Add unit tests for each new operator.
- [ ] Document operator semantics in `CONFIG.md`.

**Files:** `app/services/logic.py`, `tests/test_logic.py`, `CONFIG.md`.

**Acceptance:** Duplicate detection recall improves measurably on a hand-labeled test set (target: 80% → 90%).

---

## Phase 4 — Multi-Tenant Governance (v1.4)

**Goal:** Org admins can govern triage policy across many repos from one place.

### 4.1 Org-Level Config Inheritance

- [ ] If `.github` repo exists in the org and contains `.github/issueops.yaml`, load it as the base config.
- [ ] Per-repo `.github/issueops.yaml` extends/overrides org config.
- [ ] Inheritance model: org rules run first, repo rules can override by `name:`.
- [ ] Add `issueops validate owner/repo` to dry-run-check the merged config.

**Files:** new `app/services/config_loader.py`, `app/cli/main.py`.

### 4.2 Policy Locks

- [ ] Org admins can mark rules as `locked: true` — repos cannot override or disable them.
- [ ] Useful for security rules ("always flag CVE mentions") and compliance.
- [ ] Validate locks at config-merge time, fail loudly.

**Files:** `app/services/config_loader.py`, `app/models/schemas.py`.

### 4.3 Scheduled Sweeps

- [ ] New workflow: `triage-sweep.yml` triggered on `schedule:` (e.g., daily 09:00 UTC).
- [ ] New CLI: `issueops sweep owner/repo --apply` — fetches all open issues, re-triages those whose `days_since_updated` crossed a threshold defined in any rule.
- [ ] Surfaces stale issues without spamming maintainers.

**Files:** new `app/cli/sweep.py`, `templates/triage-sweep.yml`.

### 4.4 Assignment Routing

- [ ] New action field: `assign_to_team: List[str]` or `request_reviewer: str`.
- [ ] Optional `contributor_match: skill_overlap` mode — match `required_skills` against contributors' historical PR areas.
- [ ] Behind a feature flag — needs careful design to avoid spamming.

**Files:** `app/models/schemas.py`, `app/services/github_service.py`, `app/services/contributor_matcher.py` (new).

**Acceptance:** An org with 20 repos can enforce a single security-labeling policy from `.github/issueops.yaml` without touching individual repo configs.

---

## Phase 5 — Architecture Refactor (v1.5)

**Goal:** Codebase becomes idiomatic enough to pass a CodeAnt scan with high marks.

### 5.1 Layered Architecture

- [ ] Split `main.py` into:
  - `app/cli/commands/` (one file per command: `scan.py`, `report.py`, `test.py`, etc.)
  - `app/cli/presenters/` (Rich formatting)
  - `app/services/triage_runner.py` (single orchestration function called by both CLI and Action)
- [ ] Both CLI and Action call the same `run_triage(issue, config, options) -> TriageResult` entry point.

**Files:** restructure `app/cli/`.

### 5.2 Dependency Injection for Settings

- [ ] Replace `from app.core.config import settings` module-singleton with constructor injection.
- [ ] Tests construct `Settings(...)` explicitly. No more `monkeypatch.setenv`.

**Files:** all services, all tests.

### 5.3 Split DuplicateService

- [ ] `KeywordExtractor` (LLM-based)
- [ ] `CandidateSearcher` (GitHub API)
- [ ] `SemanticVerifier` (LLM-based)
- [ ] `EmbeddingMatcher` (FAISS)
- [ ] `DuplicateOrchestrator` — thin coordinator, holds the four above.

**Files:** `app/services/duplicate/` (new package).

### 5.4 Result Type Refinement

- [ ] Replace `TriageResult.matched: bool` with `TriageResult.outcome: Literal["matched", "no_match", "low_confidence", "skipped_locked", "fallback"]`.
- [ ] Downstream code switches on the enum instead of inferring from multiple fields.

**Files:** `app/models/schemas.py`, all callers.

### 5.5 Coverage Targets

- [ ] Raise `--cov-fail-under` from 70 → 85.
- [ ] 95%+ on: `logic.py`, `triage.py`, `extractor.py`, `duplicate/*`.
- [ ] Remove `templates.py` exclusion — it's tiny, just include it.

**Files:** `pyproject.toml`, tests.

**Acceptance:** Repo passes a static analysis pass with no function >50 lines, no file >400 lines, and 85%+ coverage.

---

## Phase 6 — Quality & Evaluation Framework (v1.6)

**Goal:** Prove the AI is actually accurate. Numbers, not vibes.

### 6.1 Golden Test Set

- [ ] Curate 50 real GitHub issues from popular OSS repos covering: crashes, security, good-first-issues, duplicates, vague reports.
- [ ] Hand-label each with expected `IssueMetadata` and expected `TriageAction`.
- [ ] Store at `tests/fixtures/golden/{slug}.json`.

**Files:** new `tests/fixtures/golden/`, new `tests/test_golden.py`.

### 6.2 Evaluation Script

- [ ] `issueops eval` runs the full pipeline against the golden set and emits:
  - Per-field extraction accuracy
  - Confusion matrix on `difficulty`, `primary_area`
  - Confidence calibration plot (is 0.8 confidence actually 80% right?)
  - Duplicate detection precision/recall
- [ ] Gate releases: regressions on golden set block CI.

**Files:** new `app/cli/eval.py`, `.github/workflows/eval.yml`.

### 6.3 Shadow Mode

- [ ] New flag: `--shadow` runs triage without applying labels. Writes audit log only.
- [ ] Lets teams validate IssueOps against their backlog before going live.
- [ ] Document a recommended rollout path in README: shadow → low-confidence-only → full apply.

**Files:** `app/cli/main.py`, README.md.

### 6.4 A/B Prompt Testing

- [ ] Prompt versions live in `app/prompts/v1.py`, `v2.py`, ...
- [ ] `issueops eval --prompt-version v2` runs golden set against alternate prompt.
- [ ] Lets you iterate on the extraction prompt with empirical feedback.

**Files:** new `app/prompts/`, `app/services/extractor.py`.

**Acceptance:** Every prompt change is gated by a golden-set evaluation showing non-regression.

---

## Phase 7 — Enterprise Distribution (v2.0)

**Goal:** Optional SaaS layer for teams that don't want to self-host the cache and audit logs.

### 7.1 Stateful Backend (Optional)

- [ ] Add `--backend remote --backend-url https://...` mode.
- [ ] Backend is a simple FastAPI service holding: cache, audit logs, embeddings index.
- [ ] Open-source the backend — anyone can self-host.

**Files:** new `backend/` subdirectory, separate `pyproject.toml`.

### 7.2 Web Dashboard

- [ ] Read-only dashboard showing per-repo metrics (the `stats` command, as HTML).
- [ ] Authenticated via GitHub OAuth.
- [ ] Deployable to Vercel/Fly.io.

**Files:** new `dashboard/` subdirectory (Next.js or simple Flask/Jinja).

### 7.3 Webhook-Based Triggering (Alternative to Action)

- [ ] Support running as a GitHub App (webhook receiver) instead of an Action.
- [ ] Lower latency, no Action minutes consumed, central control plane.
- [ ] Document trade-offs vs. Action mode.

**Files:** `backend/webhooks.py`, new docs page.

### 7.4 Compliance Features

- [ ] Audit log export in SOC2-friendly format (immutable, signed).
- [ ] PII redaction on logs (issue bodies sometimes contain emails, customer data).
- [ ] Configurable data retention.

**Files:** `app/core/redaction.py`, `backend/audit_export.py`.

**Acceptance:** A 1,000-engineer organization can run IssueOps with a single config file, central dashboard, and SOC2-compliant audit trail.

---

## Cross-Cutting Improvements (Continuous)

These don't belong to a single phase — pick them up as you go.

### Documentation

- [ ] `docs/architecture.md` — sequence diagrams of each pipeline path.
- [ ] `docs/configuration.md` — full reference for `issueops.yaml`.
- [ ] `docs/recipes/` — common patterns (security triage, GFI routing, staleness sweeps).
- [ ] `docs/troubleshooting.md` — common failures and fixes.

### Developer Experience

- [ ] `make dev` / `make test` / `make lint` shortcuts.
- [ ] Devcontainer config (`.devcontainer/devcontainer.json`).
- [ ] VS Code workspace settings for ruff + mypy.

### Release Process

- [ ] Release-please or semantic-release for automated versioning + changelog.
- [ ] `v1`, `v1.1`, `v1.1.0` tag aliases (matches Actions Marketplace convention).
- [ ] Release notes auto-generated from conventional commits.

### Security

- [ ] CodeQL scanning workflow.
- [ ] `pip-audit` in CI.
- [ ] Dependabot config for weekly dep updates.
- [ ] SLSA Level 2+ provenance on releases.

---

## Suggested Execution Order

If you have **1 week** before showing this to CodeAnt:
- Phase 0 (1 day)
- Phase 1.1, 1.2, 1.3, 1.5 (3 days) — the visible reliability wins
- Phase 2.1, 2.2 (2 days) — the metrics story
- Phase 6.1, 6.3 (1 day) — proves rigor

If you have **1 month**:
- All of Phases 0–3
- Phase 5 selectively (the architecture refactor)
- Phase 6.1–6.3 (eval framework + golden set)

If you have **1 quarter**:
- Phases 0–6 fully
- Begin Phase 7.1 (backend) if there's external interest

---

## Definition of Done (Per Phase)

A phase is done when:
1. All checkboxes ticked.
2. CI is green on main.
3. CHANGELOG entry written.
4. Tagged release pushed.
5. README updated to reflect new capabilities.
6. Acceptance criterion for the phase is demonstrably met (with evidence — screenshots, logs, or test output).
