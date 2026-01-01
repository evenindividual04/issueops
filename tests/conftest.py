import pytest
import os
import sys

# Ensure app modules are importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from app.models.schemas import IssueMetadata

@pytest.fixture
def crash_metadata():
    """Metadata for a critical crash."""
    return IssueMetadata(
        has_reproduction_steps=True,
        has_stacktrace=True,
        has_logs=True,
        is_crash=True,
        is_security_issue=False,
        is_blocker=True,
        operating_system="linux",
        environment="production",
        summary="Application crashes on startup when config is missing",
        difficulty="hard",
        required_skills=["python", "systems"],
        primary_area="backend",
        extraction_confidence=0.95
    )

@pytest.fixture
def feature_metadata():
    """Metadata for a feature request (simulated)."""
    return IssueMetadata(
        has_reproduction_steps=False,
        has_stacktrace=False,
        has_logs=False,
        is_crash=False,
        is_security_issue=False,
        is_blocker=False,
        operating_system="web",
        environment="development",
        summary="Add dark mode toggle to settings",
        difficulty="medium",
        required_skills=["css", "react"],
        primary_area="frontend",
        extraction_confidence=0.90
    )

@pytest.fixture
def empty_metadata():
    """Metadata for a confusing/empty issue."""
    return IssueMetadata(
        has_reproduction_steps=False,
        has_stacktrace=False,
        has_logs=False,
        is_crash=False,
        is_security_issue=False,
        is_blocker=False,
        operating_system=None,
        environment="unknown",
        summary="User reports 'it does not work'",
        difficulty="unknown",
        required_skills=[],
        primary_area="unknown",
        extraction_confidence=0.2
    )
