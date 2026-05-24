GOLDEN_CONFIG = """# IssueOps Configuration
# ======================
# This file defines the "Governance as Code" logic for your issue tracker.
# Rules are evaluated from top to bottom. The first matching rule wins.

rules:
  # --- 1. Safety Rules (High Priority) ---
  - name: "Block Critical Crashes"
    condition:
      "or":
        - "==": [{ "var": "is_crash" }, true]
        - "==": [{ "var": "is_blocker" }, true]
        - "==": [{ "var": "is_security_issue" }, true]
    action:
      priority_score: 5
      labels: ["bug", "critical", "security"]
      reasoning: "System stability or security risk detected."

  # --- 2. Contributor Rules (Community Growth) ---
  - name: "Label Good First Issues"
    condition:
      "and":
        - "==": [{ "var": "difficulty" }, "easy"]
        - "==": [{ "var": "has_reproduction_steps" }, true]
        # Ensure we don't accidentally mark crashes as 'easy'
        - "!=": [{ "var": "is_crash" }, true]
    action:
      priority_score: 1
      labels: ["good-first-issue", "help-wanted"]
      reasoning: "Issue is well-documented and low complexity, perfect for new contributors."

  # --- 3. Stale Rules (Housekeeping) ---
  # Note: Requires the 'days_since_update' context variable
  - name: "Close Stale Waiting Issues"
    condition:
      "and":
        - ">": [{ "var": "days_since_update" }, 14]
        - "in": ["waiting-for-info", { "var": "labels" }]
    action:
      priority_score: 3
      labels: ["stale", "closing-soon"]
      reasoning: "Issue has been waiting for author response for over 14 days."
"""
