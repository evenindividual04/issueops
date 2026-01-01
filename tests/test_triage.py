import pytest
from app.services.triage import TriageService
from app.models.schemas import TriageAction, IssueMetadata

def test_critical_crash_rule(crash_metadata):
    """Verify that a crash triggers P5 (Maintainer Fire)."""
    service = TriageService(rules_path="rules.yaml")
    action = service.evaluate(crash_metadata)
    
    assert action.priority_score == 5
    assert "critical" in action.labels
    assert "Critical System Crash" in action.reasoning or "crash" in action.reasoning.lower()

def test_good_first_issue_rule():
    """Verify that an easy doc task triggers P1 (Contributor Gold)."""
    # Construct an "Easy Doc" issue
    easy_issue = IssueMetadata(
        has_reproduction_steps=False,
        has_stacktrace=False,
        has_logs=False,
        operating_system=None,
        environment="unknown",
        is_crash=False,
        is_security_issue=False,
        is_blocker=False,
        summary="Fix typo in README",
        difficulty="easy",
        required_skills=["markdown"],
        primary_area="documentation",
        extraction_confidence=0.95
    )
    
    service = TriageService(rules_path="rules.yaml")
    action = service.evaluate(easy_issue)
    
    assert action.priority_score == 1
    assert "good-first-issue" in action.labels

def test_help_wanted_rule(feature_metadata):
    """
    Verify that a medium feature request triggers P2 (Contributor Silver).
    Fixture is set to 'medium' difficulty.
    """
    service = TriageService(rules_path="rules.yaml")
    action = service.evaluate(feature_metadata)
    
    assert action.priority_score == 2
    assert "help-wanted" in action.labels

def test_fallback_rule(empty_metadata):
    """Verify low confidence falls back to manual."""
    service = TriageService(rules_path="rules.yaml")
    action = service.evaluate(empty_metadata)
    
    assert action.priority_score == 3
    assert "triage/manual" in action.labels
