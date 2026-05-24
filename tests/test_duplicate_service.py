import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.duplicate_service import DuplicateService
from app.models.schemas import DuplicateResult


def _make_services(keywords="auth crash", candidates=None, dup_result=None):
    """Build mocked GitHubService and ExtractorService."""
    gh = MagicMock()
    extractor = MagicMock()

    extractor.generate_search_keywords = AsyncMock(return_value=keywords)

    default_candidates = candidates if candidates is not None else [
        {"number": 5, "title": "Login crash", "state": "open", "body_snippet": "crash on login"},
    ]
    gh.search_issues = AsyncMock(return_value=default_candidates)

    default_result = dup_result or DuplicateResult(
        duplicate_number=5,
        matched_issue_state="open",
        confidence=0.95,
        reasoning="Identical stack trace.",
    )
    extractor.find_semantic_duplicate = AsyncMock(return_value=default_result)

    return gh, extractor


# ── happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_detects_open_duplicate():
    gh, extractor = _make_services()
    svc = DuplicateService(gh, extractor)

    result = await svc.check_duplicate("owner", "repo", "Auth crash", "Steps to repro", 99)

    assert result.duplicate_number == 5
    assert result.matched_issue_state == "open"
    assert result.confidence >= 0.9


@pytest.mark.asyncio
async def test_detects_closed_prior_art():
    closed_candidate = [{"number": 3, "title": "Old crash", "state": "closed", "body_snippet": "same error"}]
    prior_art = DuplicateResult(
        duplicate_number=3,
        matched_issue_state="closed",
        confidence=0.92,
        reasoning="Same root cause, resolved in #3.",
    )
    gh, extractor = _make_services(candidates=closed_candidate, dup_result=prior_art)
    svc = DuplicateService(gh, extractor)

    result = await svc.check_duplicate("owner", "repo", "Crash again", "Body", 99)

    assert result.duplicate_number == 3
    assert result.matched_issue_state == "closed"


@pytest.mark.asyncio
async def test_self_is_excluded_from_candidates():
    """Current issue must never be its own duplicate."""
    self_candidate = [{"number": 99, "title": "Same issue", "state": "open", "body_snippet": "..."}]
    gh, extractor = _make_services(candidates=self_candidate)
    # After self-filter, candidates will be empty → no_candidates path
    no_match = DuplicateResult(confidence=0.0, reasoning="No candidates found")
    extractor.find_semantic_duplicate = AsyncMock(return_value=no_match)

    svc = DuplicateService(gh, extractor)
    result = await svc.check_duplicate("owner", "repo", "Title", "Body", 99)

    assert result.duplicate_number is None
    assert result.confidence == 0.0


# ── degraded paths ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_returns_no_match_when_keywords_empty():
    gh, extractor = _make_services(keywords="")
    svc = DuplicateService(gh, extractor)

    result = await svc.check_duplicate("owner", "repo", "Title", "Body", 1)

    assert result.confidence == 0.0
    assert "keyword" in result.reasoning.lower() or "No keywords" in result.reasoning
    gh.search_issues.assert_not_called()


@pytest.mark.asyncio
async def test_returns_no_match_when_keyword_generation_fails():
    gh, extractor = _make_services()
    extractor.generate_search_keywords = AsyncMock(side_effect=RuntimeError("LLM timeout"))

    svc = DuplicateService(gh, extractor)
    result = await svc.check_duplicate("owner", "repo", "Title", "Body", 1)

    assert result.confidence == 0.0
    gh.search_issues.assert_not_called()


@pytest.mark.asyncio
async def test_returns_no_match_when_search_returns_empty():
    gh, extractor = _make_services(candidates=[])
    svc = DuplicateService(gh, extractor)

    result = await svc.check_duplicate("owner", "repo", "Title", "Body", 1)

    assert result.confidence == 0.0
    extractor.find_semantic_duplicate.assert_not_called()


@pytest.mark.asyncio
async def test_returns_no_match_when_search_fails():
    gh, extractor = _make_services()
    gh.search_issues = AsyncMock(side_effect=Exception("API down"))

    svc = DuplicateService(gh, extractor)
    result = await svc.check_duplicate("owner", "repo", "Title", "Body", 1)

    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_returns_no_match_when_verification_fails():
    gh, extractor = _make_services()
    extractor.find_semantic_duplicate = AsyncMock(side_effect=Exception("LLM crash"))

    svc = DuplicateService(gh, extractor)
    result = await svc.check_duplicate("owner", "repo", "Title", "Body", 1)

    assert result.confidence == 0.0


# ── matched state enrichment ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_matched_state_is_enriched_from_candidate():
    candidates = [{"number": 7, "title": "Crash", "state": "open", "body_snippet": "..."}]
    raw_result = DuplicateResult(duplicate_number=7, confidence=0.91, reasoning="Match.")
    gh, extractor = _make_services(candidates=candidates, dup_result=raw_result)

    svc = DuplicateService(gh, extractor)
    result = await svc.check_duplicate("owner", "repo", "Title", "Body", 1)

    assert result.matched_issue_state == "open"
