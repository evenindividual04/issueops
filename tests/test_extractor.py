import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.extractor import ExtractorService


def _mock_async_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


VALID_JSON = """
{
    "has_reproduction_steps": true,
    "has_stacktrace": false,
    "has_logs": false,
    "operating_system": "linux",
    "environment": "production",
    "is_crash": true,
    "is_security_issue": false,
    "is_blocker": false,
    "summary": "Fix validation error in login",
    "difficulty": "medium",
    "required_skills": ["python", "fastapi"],
    "primary_area": "backend",
    "extraction_confidence": 0.95
}
"""

EASY_JSON = """
{
    "has_reproduction_steps": false,
    "has_stacktrace": false,
    "has_logs": false,
    "operating_system": "other",
    "environment": "unknown",
    "is_crash": false,
    "is_security_issue": false,
    "is_blocker": false,
    "summary": "Docs are outdated",
    "difficulty": "easy",
    "required_skills": ["markdown"],
    "primary_area": "documentation",
    "extraction_confidence": 1.0
}
"""


@pytest.mark.asyncio
async def test_extract_happy_path():
    with patch("google.generativeai.GenerativeModel") as MockModel:
        instance = MockModel.return_value
        instance.generate_content_async = AsyncMock(
            return_value=_mock_async_response(VALID_JSON)
        )

        service = ExtractorService(use_cache=False)
        metadata = await service.extract("Some issue text")

    assert metadata.is_crash is True
    assert metadata.difficulty == "medium"
    assert "python" in metadata.required_skills
    assert metadata.primary_area == "backend"


@pytest.mark.asyncio
async def test_extract_with_markdown_fences():
    """Models sometimes wrap JSON in ```json``` — the extractor must strip it."""
    fenced = f"```json\n{VALID_JSON}\n```"

    with patch("google.generativeai.GenerativeModel") as MockModel:
        instance = MockModel.return_value
        instance.generate_content_async = AsyncMock(
            return_value=_mock_async_response(fenced)
        )

        service = ExtractorService(use_cache=False)
        metadata = await service.extract("Issue text")

    assert metadata.extraction_confidence == 0.95


@pytest.mark.asyncio
async def test_extract_retries_on_bad_json():
    """First call returns invalid JSON; second call returns valid JSON."""
    with patch("google.generativeai.GenerativeModel") as MockModel:
        instance = MockModel.return_value
        instance.generate_content_async = AsyncMock(side_effect=[
            _mock_async_response("This is not json"),
            _mock_async_response(EASY_JSON),
        ])

        service = ExtractorService(use_cache=False)
        metadata = await service.extract("Retry me")

    assert metadata.primary_area == "documentation"
    assert metadata.difficulty == "easy"
    assert instance.generate_content_async.call_count == 2


@pytest.mark.asyncio
async def test_extract_raises_after_two_failures():
    """Both attempts return bad JSON → ValueError must propagate."""
    with patch("google.generativeai.GenerativeModel") as MockModel:
        instance = MockModel.return_value
        instance.generate_content_async = AsyncMock(
            return_value=_mock_async_response("not json at all")
        )

        service = ExtractorService(use_cache=False)
        with pytest.raises(ValueError, match="Failed to extract"):
            await service.extract("Bad input")

    assert instance.generate_content_async.call_count == 2


@pytest.mark.asyncio
async def test_extract_raises_on_empty_response():
    with patch("google.generativeai.GenerativeModel") as MockModel:
        instance = MockModel.return_value
        instance.generate_content_async = AsyncMock(
            return_value=_mock_async_response("")
        )

        service = ExtractorService(use_cache=False)
        with pytest.raises(ValueError):
            await service.extract("Some text")


@pytest.mark.asyncio
async def test_cache_is_used_on_second_call():
    """Same text twice → LLM called only once."""
    with patch("google.generativeai.GenerativeModel") as MockModel:
        instance = MockModel.return_value
        instance.generate_content_async = AsyncMock(
            return_value=_mock_async_response(VALID_JSON)
        )
        with patch("app.services.extractor.CacheManager") as MockCache:
            cache_instance = MockCache.return_value
            # First call: miss; second call: hit
            cache_instance.get.side_effect = [None, MagicMock()]
            cache_instance.save = MagicMock()

            service = ExtractorService(use_cache=True)
            await service.extract("Some issue text")
            await service.extract("Some issue text")

    assert instance.generate_content_async.call_count == 1
