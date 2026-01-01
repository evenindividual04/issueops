from app.services.triage import TriageService
from app.models.schemas import IssueMetadata

def main():
    print("--- Verifying Phase 2: Rules Engine ---")
    
    triage = TriageService("rules.yaml")
    
    # 1. Test Critical Crash
    print("\nTest Case 1: Critical Crash")
    crash_issue = IssueMetadata(
        has_reproduction_steps=True,
        has_stacktrace=True,
        has_logs=True,
        is_crash=True,          # <--- Should trigger "Critical Crash"
        is_security_issue=False,
        is_blocker=False,
        extraction_confidence=0.9,
        environment="production",
        operating_system="linux",
        primary_area="backend"
    )
    
    action = triage.evaluate(crash_issue)
    print(f"Action: Priority {action.priority_score} | Labels: {action.labels}")
    print(f"Reason: {action.reasoning}")
    
    assert action.priority_score == 5, "Crash should be Priority 5"
    assert "critical" in action.labels, "Crash should have 'critical' label"

    # 2. Test Low Confidence
    print("\nTest Case 2: Low Confidence")
    confused_issue = IssueMetadata(
        has_reproduction_steps=False,
        has_stacktrace=False,
        has_logs=False,
        is_crash=False,
        is_security_issue=False,
        is_blocker=False,
        extraction_confidence=0.4, # <--- Should trigger "Low Confidence"
        environment="unknown",
        operating_system="web",
        primary_area="unknown"
    )
    
    action = triage.evaluate(confused_issue)
    print(f"Action: Priority {action.priority_score} | Labels: {action.labels}")
    print(f"Reason: {action.reasoning}")

    assert action.priority_score == 3
    assert "triage/manual-review" in action.labels

    print("\n✅ Rules Engine Verified")

if __name__ == "__main__":
    main()
