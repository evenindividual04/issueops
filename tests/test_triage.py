from app.models.schemas import IssueMetadata
from app.services.triage import TriageService


def test_critical_crash_rule(crash_metadata):
    svc = TriageService(rules_path="rules.yaml")
    action = svc.evaluate(crash_metadata)

    assert action.priority_score == 5
    assert "critical" in action.labels


def test_good_first_issue_rule():
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
        extraction_confidence=0.95,
    )
    svc = TriageService(rules_path="rules.yaml")
    action = svc.evaluate(easy_issue)

    assert action.priority_score == 1
    assert "good-first-issue" in action.labels


def test_help_wanted_rule(feature_metadata):
    svc = TriageService(rules_path="rules.yaml")
    action = svc.evaluate(feature_metadata)

    assert action.priority_score == 2
    assert "help-wanted" in action.labels


def test_confidence_gate_blocks_auto_labeling():
    """Low-confidence extraction must not apply domain labels."""
    low_conf = IssueMetadata(
        has_reproduction_steps=False,
        has_stacktrace=False,
        has_logs=False,
        is_crash=True,  # would normally trigger P5
        is_security_issue=False,
        is_blocker=False,
        operating_system=None,
        environment="unknown",
        summary="Something broken",
        difficulty="unknown",
        required_skills=[],
        primary_area="unknown",
        extraction_confidence=0.4,  # below 0.75 threshold
    )
    svc = TriageService(rules_path="rules.yaml")
    action = svc.evaluate(low_conf, min_confidence=0.75)

    assert "triage/low-confidence" in action.labels
    assert "critical" not in action.labels


def test_confidence_gate_bypassed_with_lower_threshold():
    """Setting a lower threshold allows the rules engine to run."""
    low_conf = IssueMetadata(
        has_reproduction_steps=True,
        has_stacktrace=True,
        has_logs=False,
        is_crash=True,
        is_security_issue=False,
        is_blocker=False,
        operating_system=None,
        environment="production",
        summary="Crash on startup",
        difficulty="hard",
        required_skills=["python"],
        primary_area="backend",
        extraction_confidence=0.5,
    )
    svc = TriageService(rules_path="rules.yaml")
    action = svc.evaluate(low_conf, min_confidence=0.3)

    assert action.priority_score == 5
    assert "critical" in action.labels


def test_default_fallback_no_rules_match(empty_metadata):
    svc = TriageService(rules_path="rules.yaml")
    # empty_metadata has confidence 0.2 — use min_confidence=0.0 to test fallback path
    action = svc.evaluate(empty_metadata, min_confidence=0.0)

    assert action.priority_score == 3
    assert action.priority_score == 3


def test_trace_returns_full_decision_record(crash_metadata):
    svc = TriageService(rules_path="rules.yaml")
    results = svc.trace(crash_metadata)
    assert len(results) >= 1
    matched_results = [r for r in results if r.matched]
    assert len(matched_results) >= 1
    assert matched_results[0].action is not None


def test_trace_low_confidence_short_circuits():
    low_conf = IssueMetadata(
        has_reproduction_steps=False,
        has_stacktrace=False,
        has_logs=False,
        is_crash=False,
        is_security_issue=False,
        is_blocker=False,
        operating_system=None,
        environment="unknown",
        summary="vague",
        difficulty="unknown",
        required_skills=[],
        primary_area="unknown",
        extraction_confidence=0.2,
    )
    svc = TriageService(rules_path="rules.yaml")
    results = svc.trace(low_conf)
    assert len(results) == 1
    assert results[0].rule_name == "confidence-gate"
    assert results[0].matched is True


def test_missing_rules_file_falls_back_to_default(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    svc = TriageService(rules_path=str(missing))
    # Falls back to root rules.yaml — should still load rules
    assert len(svc.rules) > 0


def test_missing_default_rules_yields_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no rules.yaml anywhere
    svc = TriageService(rules_path="nowhere.yaml")
    assert svc.rules == []


def test_invalid_yaml_falls_back_gracefully(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("this is: not [valid: yaml")
    svc = TriageService(rules_path=str(bad))
    # Falls back to project rules.yaml
    assert isinstance(svc.rules, list)


def test_evaluate_context_overrides_metadata(crash_metadata):
    svc = TriageService(rules_path="rules.yaml")
    # Add context — should merge into evaluation data without crashing
    action = svc.evaluate(crash_metadata, context={"days_since_update": 5})
    assert action.priority_score == 5
