from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class IssueMetadata(BaseModel):
    """
    Unified metadata schema for both Maintainers (Technical) and Contributors (Accessibility).
    """
    model_config = ConfigDict(extra="forbid")

    # --- MAINTAINER SIGNALS (Technical Severity) ---
    has_reproduction_steps: bool = Field(..., description="True if reproduction steps/code are provided.")
    has_stacktrace: bool = Field(..., description="True if a stacktrace or error log is present.")
    has_logs: bool = Field(..., description="True if application/server logs are pasted.")

    is_crash: bool = Field(False, description="True if system crash/panic/segfault.")
    is_security_issue: bool = Field(False, description="True if security vulnerability/CVE.")
    is_blocker: bool = Field(False, description="True if prevents build/deploy/startup.")

    # --- ENVIRONMENT CONTEXT ---
    operating_system: Optional[str] = Field(None, description="Detected OS (e.g., Linux, Windows, macOS).")
    environment: str = Field(
        "unknown",
        description="The environment where the issue was observed (e.g. production, staging)."
    )

    # --- CONTRIBUTOR SIGNALS (Accessibility) ---
    summary: str = Field(..., description="A 1-sentence non-technical summary for new contributors.")

    difficulty: Literal["easy", "medium", "hard", "unknown"] = Field(
        ...,
        description="Estimated complexity. 'easy' = docs/typos, 'hard' = architecture/race-conditions."
    )

    required_skills: List[str] = Field(
        default_factory=list,
        description="List of skills needed (e.g., ['python', 'css', 'docker', 'sql'])."
    )

    # --- CLASSIFICATION ---
    primary_area: Literal["frontend", "backend", "database", "devops", "documentation", "unknown"] = Field(
        "unknown",
        description="Architectural component."
    )

    # --- TEST COMPANION & PRIOR ART ---
    verification_hint: Optional[str] = Field(None, description="A suggested terminal command to verify a fix.")
    related_closed_issue_id: Optional[int] = Field(None, description="ID of a similar closed issue as solution blueprint.")

    extraction_confidence: float = Field(..., ge=0.0, le=1.0)
    extraction_mode: Literal["llm", "fallback"] = Field(
        "llm",
        description="'llm' = Gemini call; 'fallback' = circuit-breaker regex path.",
    )


class TriageAction(BaseModel):
    """The decision output from the Rules Engine."""
    priority_score: int = Field(..., ge=1, le=5)
    labels: List[str] = Field(
        default_factory=list,
        description="Labels to ensure are present on the issue.",
    )
    labels_to_remove: List[str] = Field(
        default_factory=list,
        description="Labels to remove from the issue if currently present.",
    )
    reasoning: str = Field(..., description="Human-readable explanation of why this rule fired.")


class RuleDefinition(BaseModel):
    """Strict definition of a single Rule in rules.yaml."""
    name: str = Field(..., min_length=1, description="Unique name for the rule.")
    condition: Dict[str, Any] = Field(..., description="Valid JSON-Logic logical condition.")
    action: TriageAction = Field(..., description="Action to take if condition is true.")


class DuplicateResult(BaseModel):
    """Result of semantic duplicate verification."""
    duplicate_number: Optional[int] = Field(None, description="Issue number of duplicate, or null.")
    matched_issue_state: Optional[str] = Field(None, description="State of the matched issue: 'open' or 'closed'.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    reasoning: str = Field(..., description="Why it is or isn't a duplicate.")


class RuleResult(BaseModel):
    """Result of a single rule evaluation trace."""
    rule_name: str
    matched: bool
    action: Optional[TriageAction] = None
    evaluation_data: Optional[Dict[str, Any]] = None
