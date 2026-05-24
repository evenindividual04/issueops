# IssueOps

[![CI](https://github.com/evenindividual04/issueops/actions/workflows/ci.yml/badge.svg)](https://github.com/evenindividual04/issueops/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-70%25%2B-brightgreen)](https://github.com/evenindividual04/issueops/actions/workflows/ci.yml)
[![Marketplace](https://img.shields.io/badge/GitHub%20Marketplace-v1.0.0-blue)](https://github.com/marketplace/actions/issueops)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)

**AI-powered issue triage as a GitHub Action. Governance as code.**

IssueOps treats your issue tracker like a production pipeline — the same discipline you apply to code review, applied to the issues that create the work. It uses a hybrid AI + rules engine to detect critical bugs, surface duplicate reports, and route "Good First Issues" to contributors automatically.

---

## How It Works

```
New Issue Filed
      │
      ▼
┌─────────────┐     Cache hit?    ┌──────────────┐
│  SHA-256    │ ──── yes ────────▶│  Load result │
│  Cache      │                   └──────┬───────┘
└──────┬──────┘                          │
       │ miss                            │
       ▼                                 ▼
┌─────────────┐    confidence < 0.75    ┌──────────────────┐
│  Gemini AI  │ ──── low confidence ───▶│ triage/low-conf  │
│  Extractor  │                         │ (human review)   │
└──────┬──────┘                         └──────────────────┘
       │ high confidence
       ▼
┌─────────────┐   open duplicate    ┌──────────────────┐
│  Duplicate  │ ──── found ────────▶│ Flag + comment   │
│  Detection  │                     └──────────────────┘
└──────┬──────┘   closed duplicate
       │ ──── found ────────▶ Link as Prior Art
       │ no match
       ▼
┌─────────────┐
│ Rules Engine│  ── YAML rules ──▶  Labels + Priority
│ (JSON-Logic)│
└─────────────┘
```

**Extract** — Gemini converts unstructured issue text into a typed schema (crash signals, difficulty, required skills, verification hints).

**Gate** — If extraction confidence is below the configurable threshold (default 0.75), the issue is flagged for manual review instead of being auto-labeled. Uncertain AI decisions don't silently pollute your backlog.

**Compare** — Semantic duplicate search using GitHub's Search API. No vector database required.

**Decide** — Deterministic JSON-Logic rules evaluate the structured data. Your rules, version-controlled alongside your code.

---

## Features

| Feature | Description |
|---|---|
| **Confidence Gating** | Auto-labeling only fires when extraction confidence ≥ threshold. Below it, issues get `triage/low-confidence` for human review. |
| **SHA-256 Caching** | Content-addressable cache skips LLM re-analysis of unchanged issues. ~90% cost reduction in practice. |
| **Duplicate Detection** | 3-step pipeline: keyword extraction → GitHub search → semantic verification. Distinguishes open duplicates (close it) from closed ones (link as prior art). |
| **Test Radar** | Infers the exact `pytest` command to verify a fix from stack traces and file paths. Surfaces as `verification_hint`. |
| **Prior Art Linker** | Closed duplicates become solution blueprints for contributors, not just noise. |
| **Contributor Job Board** | Generates a static HTML portal + RSS feed of Good First Issues. |
| **Governance as Code** | All triage logic lives in `.github/issueops.yaml`, versioned and reviewable in PRs. |

---

## Quick Start

### 1. Add the Action

```yaml
# .github/workflows/triage.yml
name: IssueOps Triage
on:
  issues:
    types: [opened, edited]

jobs:
  triage:
    runs-on: ubuntu-latest
    permissions:
      issues: write
    steps:
      - uses: actions/checkout@v4

      - name: Cache triage data
        uses: actions/cache@v4
        with:
          path: .triage_cache.json
          key: triage-${{ github.repository }}-${{ hashFiles('.github/issueops.yaml') }}
          restore-keys: triage-${{ github.repository }}-

      - uses: evenindividual04/issueops@v1.0.0
        with:
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

### 2. Scaffold Your Rules

```bash
pip install issueops
issueops init       # creates .github/issueops.yaml
issueops test       # verify your rules without a live API call
```

---

## Configuration

Rules live in `.github/issueops.yaml`. The `issueops init` command scaffolds a production-ready starter.

```yaml
rules:
  # Safety: flag crashes and security issues immediately
  - name: "Critical Crash"
    condition:
      "or":
        - "==": [{var: is_crash}, true]
        - "==": [{var: is_blocker}, true]
        - "==": [{var: is_security_issue}, true]
    action:
      priority_score: 5
      labels: ["bug", "critical", "security"]
      reasoning: "System stability or security risk detected."

  # Community: surface good first issues
  - name: "Good First Issue"
    condition:
      "and":
        - "==": [{var: difficulty}, "easy"]
        - "==": [{var: has_reproduction_steps}, true]
        - "!=": [{var: is_crash}, true]
    action:
      priority_score: 1
      labels: ["good-first-issue", "help-wanted"]
      reasoning: "Well-documented, low-complexity issue."

  # Staleness: nudge inactive issues
  - name: "Stale Waiting"
    condition:
      "and":
        - ">": [{var: days_since_update}, 14]
        - "in": ["waiting-for-info", {var: labels}]
    action:
      priority_score: 3
      labels: ["stale"]
      reasoning: "No response in 14 days."
```

### Extracted Fields

Every issue is analysed and returns a typed schema:

| Field | Type | Description |
|---|---|---|
| `is_crash` | bool | Crash/panic/segfault detected |
| `is_security_issue` | bool | CVE or security vulnerability |
| `is_blocker` | bool | Prevents build/deploy |
| `difficulty` | enum | `easy` / `medium` / `hard` / `unknown` |
| `required_skills` | list[str] | e.g. `["python", "docker"]` |
| `primary_area` | enum | `frontend` / `backend` / `database` / `devops` / `docs` |
| `verification_hint` | str | Suggested test command to verify a fix |
| `extraction_confidence` | float | 0.0–1.0. Below threshold → manual review. |

---

## CLI Reference

```bash
# Scaffold config
issueops init

# Test rules without live API
issueops test --is-crash --label waiting-for-info --days-since-update 20

# Test end-to-end with real issue text
issueops test --body "App crashes on startup with null pointer exception"

# Analyse a specific issue (dry run)
issueops scan owner/repo 42

# Apply labels
issueops scan owner/repo 42 --apply

# Batch scan + generate contributor job board
issueops report owner/repo --limit 20

# Export CSV for accuracy auditing
issueops audit owner/repo --limit 50
```

---

## Local Development

```bash
git clone https://github.com/evenindividual04/issueops
cd issueops

pip install -e ".[dev]"
cp .env.example .env   # add GEMINI_API_KEY

# Run tests
pytest tests/ -v --cov=app

# Lint
ruff check app/ tests/

# Type check
mypy app/
```

### Architecture

```
app/
├── cli/
│   ├── main.py          # Typer CLI commands
│   └── templates.py     # Golden config scaffold
├── core/
│   └── config.py        # Settings (env-based)
├── models/
│   └── schemas.py       # Pydantic models (IssueMetadata, TriageAction, …)
└── services/
    ├── extractor.py     # Gemini AI extraction
    ├── triage.py        # JSON-Logic rules engine + confidence gate
    ├── duplicate_service.py  # 3-step duplicate detection
    ├── github_service.py     # GitHub API (async, rate-limit backoff)
    ├── reporter.py      # HTML job board + RSS feed
    ├── cache.py         # SHA-256 content-addressable cache
    └── logic.py         # JSON-Logic evaluator
```

---

## Design Decisions

**Why a rules engine instead of pure AI?** AI is non-deterministic. Rules are auditable, version-controlled, and PR-reviewable. The AI handles the hard part (unstructured text → structured data); the rules engine handles the decisions. This gives you a system you can debug.

**Why confidence gating?** A 0.3-confidence extraction silently applying `critical` labels would be worse than doing nothing. The gate ensures AI uncertainty surfaces as a human task, not a wrong label.

**Why no vector database?** GitHub's Search API with keyword extraction covers 95% of real-world duplicate detection without the operational overhead of a vector store.

---

## License

MIT © [Anmol Sen](https://github.com/evenindividual04)
