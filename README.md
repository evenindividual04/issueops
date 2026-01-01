# IssueOps ⚡

[![Marketplace](https://img.shields.io/badge/Marketplace-v1.0.0-blue.svg)](https://github.com/marketplace/actions/issueops)
[![Tests](https://github.com/actions/toolkit/actions/workflows/main.yml/badge.svg)](https://github.com/actions/toolkit/actions/workflows/main.yml)

**Governance as Code for GitHub Issues.**

IssueOps treats your issue tracker like a production pipeline. It uses a deterministic AI engine to triage bugs, detect semantic duplicates, and curate "Good First Issues" for contributors—all defined in a simple YAML config.

## 🚀 Key Features

*   **Smart Caching ("The Wallet Saver"):** 
    Uses SHA-256 content addressing to skip re-analysis of unchanged issues, reducing LLM costs by ~90%.
*   **Semantic Duplicate Detection:** 
    Uses a "Stateless" approach (LLM + GitHub Search) to identify duplicates without expensive Vector Databases.
*   **Contributor Portal:** 
    Auto-generates a static `job_board.html` and `feed.xml` (RSS) to attract new contributors to "Good First Issues".
*   **Rules Engine:** 
    Configurable JSON-Logic rules (`rules.yaml`) to define custom triage policies.

## Usage

Create `.github/workflows/triage.yml` in your repository:

```yaml
name: Triage Issues
on:
  issues:
    types: [opened]

permissions:
  issues: write

jobs:
  triage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
          
      - name: Install Dependencies
        run: |
          pip install -r requirements.txt
          
      - name: Run Triage
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          # Run the triage tool on the current issue
          python main.py run ${{ github.repository }} ${{ github.event.issue.number }} --apply --yes
```

## Local Development (CLI)

You can also run this tool locally to debug prompts or rules.

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure .env
cp .env.example .env

# 3. Run
python main.py run owner/repo issue_id
```

## Configuration (`rules.yaml`)

Define your triage logic in `rules.yaml`.

```yaml
- name: "Critical Crash"
  condition:
    "or":
      - "==": [{ "var": "is_crash" }, true]
      - "==": [{ "var": "is_blocker" }, true]
  action:
    priority_score: 5
    labels: ["bug", "critical"]
    reasoning: "System crash detected."
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for details on the ETL pipeline design.

## 📊 The "Job Board" (Contributor Portal)

Turn your issue tracker into a recruiting tool. The `report` command generates a static HTML site listing "Good First Issues".

**[View Example Job Board](./job_board.html)** (Generated Artifact)

## 🛡️ Operational "Failure Modes"

We value transparency. Here is how the system handles edge cases:

### 1. Rate Limits (429 Errors)
The system respects GitHub and Google Gemini rate limits.
*   **Behavior**: If a limit is hit, the tool waits (exponential backoff) and retries up to 3 times.
*   **Outcome**: If all retries fail, it logs the error and exits gracefully (skipping that specific issue).

### 2. Hallucinations (AI Drift)
The AI is probabilistic. To mitigate risk:
*   **Strict Schema**: We force the AI to output strictly typed JSON.
*   **Confidence Gating**: Low-confidence predictions (e.g., "unknown" difficulty) are flagged for human review.
*   **Audit**: Use `main.py audit` to generate a CSV and compare AI predictions vs. reality.

### 3. Security & Privacy
*   **No Code Leaks**: The tool **only reads issue text** (titles, bodies, comments). It does NOT read your source code.
*   **Stateless**: No data is stored globally. Credentials live in your ephemeral CI environment.

## 🔧 Troubleshooting

| Error | Cause | Fix |
| :--- | :--- | :--- |
| `ValidationError` in `rules.yaml` | Typo in config | The tool automatically falls back to safe defaults. Check logs. |
| `Quota exceeded` (Gemini) | Free tier limit | Use `main.py report --limit 5` or wait for quota reset. |
| `GitHub API 403` | Token permissions | Ensure `GITHUB_TOKEN` has `issues: write` permission. |
