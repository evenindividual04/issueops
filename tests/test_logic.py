import pytest
from app.services.logic import apply


# ── basic operators ───────────────────────────────────────────────────────────

def test_equality():
    assert apply({"==": [{"var": "x"}, 5]}, {"x": 5}) is True
    assert apply({"==": [{"var": "x"}, 5]}, {"x": 6}) is False


def test_inequality():
    assert apply({"!=": [{"var": "x"}, 5]}, {"x": 6}) is True
    assert apply({"!=": [{"var": "x"}, 5]}, {"x": 5}) is False


def test_comparison_operators():
    assert apply({">": [{"var": "n"}, 3]}, {"n": 4}) is True
    assert apply({"<": [{"var": "n"}, 3]}, {"n": 2}) is True
    assert apply({">=": [{"var": "n"}, 3]}, {"n": 3}) is True
    assert apply({"<=": [{"var": "n"}, 3]}, {"n": 4}) is False


def test_and_short_circuits():
    assert apply({"and": [True, True]}, {}) is True
    assert apply({"and": [True, False]}, {}) is False


def test_or():
    assert apply({"or": [False, True]}, {}) is True
    assert apply({"or": [False, False]}, {}) is False


# ── "in" operator (was missing, now added) ────────────────────────────────────

def test_in_value_present_in_list():
    data = {"labels": ["bug", "waiting-for-info", "help-wanted"]}
    rule = {"in": ["waiting-for-info", {"var": "labels"}]}
    assert apply(rule, data) is True


def test_in_value_absent_from_list():
    data = {"labels": ["bug"]}
    rule = {"in": ["waiting-for-info", {"var": "labels"}]}
    assert apply(rule, data) is False


def test_in_empty_list():
    assert apply({"in": ["x", []]}, {}) is False


def test_in_string_substring():
    assert apply({"in": ["crash", "app crashes on startup"]}, {}) is True


def test_in_non_iterable_returns_false():
    assert apply({"in": ["x", 42]}, {}) is False


# ── staleness rule (real template rule) ───────────────────────────────────────

def test_staleness_rule_fires_when_label_present():
    """Replicates the golden config staleness rule."""
    rule = {
        "and": [
            {">": [{"var": "days_since_update"}, 14]},
            {"in": ["waiting-for-info", {"var": "labels"}]},
        ]
    }
    data = {"days_since_update": 20, "labels": ["waiting-for-info"]}
    assert apply(rule, data) is True


def test_staleness_rule_does_not_fire_when_fresh():
    rule = {
        "and": [
            {">": [{"var": "days_since_update"}, 14]},
            {"in": ["waiting-for-info", {"var": "labels"}]},
        ]
    }
    data = {"days_since_update": 5, "labels": ["waiting-for-info"]}
    assert apply(rule, data) is False


def test_staleness_rule_does_not_fire_without_label():
    rule = {
        "and": [
            {">": [{"var": "days_since_update"}, 14]},
            {"in": ["waiting-for-info", {"var": "labels"}]},
        ]
    }
    data = {"days_since_update": 30, "labels": ["bug"]}
    assert apply(rule, data) is False


# ── var lookup ────────────────────────────────────────────────────────────────

def test_var_nested_path():
    data = {"issue": {"state": "open"}}
    assert apply({"var": "issue.state"}, data) == "open"


def test_var_missing_key_returns_default():
    assert apply({"var": ["missing_key", "default"]}, {}) == "default"


def test_literal_passthrough():
    assert apply(42, {}) == 42
    assert apply("hello", {}) == "hello"
    assert apply(True, {}) is True
