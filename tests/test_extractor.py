from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.extractor import ExtractorService


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


VALID_JSON = """{
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
}"""

EASY_JSON = """{
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
}"""


def _patch_client(side_effect=None, return_value=None):
    """Patch google.genai.Client used inside ExtractorService."""
    mock_client = MagicMock()
    if side_effect:
        mock_client.aio.models.generate_content = AsyncMock(side_effect=side_effect)
    else:
        mock_client.aio.models.generate_content = AsyncMock(return_value=return_value)
    return patch("app.services.extractor.genai.Client", return_value=mock_client), mock_client


@pytest.mark.asyncio
async def test_extract_happy_path():
    patcher, mock_client = _patch_client(return_value=_mock_response(VALID_JSON))
    with patcher:
        svc = ExtractorService(use_cache=False)
        metadata = await svc.extract("Some issue text")

    assert metadata.is_crash is True
    assert metadata.difficulty == "medium"
    assert "python" in metadata.required_skills
    assert metadata.primary_area == "backend"


@pytest.mark.asyncio
async def test_extract_strips_markdown_fences():
    fenced = f"```json\n{VALID_JSON}\n```"
    patcher, _ = _patch_client(return_value=_mock_response(fenced))
    with patcher:
        svc = ExtractorService(use_cache=False)
        metadata = await svc.extract("Issue text")

    assert metadata.extraction_confidence == 0.95


@pytest.mark.asyncio
async def test_extract_retries_on_bad_json():
    patcher, mock_client = _patch_client(side_effect=[
        _mock_response("This is not json"),
        _mock_response(EASY_JSON),
    ])
    with patcher:
        svc = ExtractorService(use_cache=False)
        metadata = await svc.extract("Retry me")

    assert metadata.primary_area == "documentation"
    assert mock_client.aio.models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_extract_raises_after_two_failures():
    patcher, mock_client = _patch_client(return_value=_mock_response("not json"))
    with patcher:
        svc = ExtractorService(use_cache=False)
        with pytest.raises(ValueError, match="Failed to extract"):
            await svc.extract("Bad input")

    assert mock_client.aio.models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_extract_raises_on_empty_response():
    patcher, _ = _patch_client(return_value=_mock_response(""))
    with patcher:
        svc = ExtractorService(use_cache=False)
        with pytest.raises(ValueError):
            await svc.extract("Some text")


@pytest.mark.asyncio
async def test_cache_hit_skips_llm():
    """Same text twice → LLM called only once."""
    patcher, mock_client = _patch_client(return_value=_mock_response(VALID_JSON))
    with patcher:
        with patch("app.services.extractor.CacheManager") as MockCache:
            cache_instance = MockCache.return_value
            cache_instance.get.side_effect = [None, MagicMock()]
            cache_instance.save = MagicMock()

            svc = ExtractorService(use_cache=True)
            await svc.extract("Some issue text")
            await svc.extract("Some issue text")

    assert mock_client.aio.models.generate_content.call_count == 1
