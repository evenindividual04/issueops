import pytest
from unittest.mock import MagicMock, patch
from app.services.extractor import ExtractorService

@pytest.mark.asyncio
async def test_extract_happy_path():
    """Test extracting valid JSON from LLM response."""
    
    # Mock Response Text (Strict Schema)
    mock_json = """
    ```json
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
    ```
    """
    
    # Patch the GenerativeModel
    with patch("google.generativeai.GenerativeModel") as MockModel:
        instance = MockModel.return_value
        instance.generate_content.return_value.text = mock_json
        
        service = ExtractorService()
        metadata = await service.extract("Some issue text")
        
        assert metadata.is_crash is True
        assert metadata.difficulty == "medium"
        assert "python" in metadata.required_skills
        assert metadata.primary_area == "backend"

@pytest.mark.asyncio
async def test_extract_retry_logic():
    """Test that it retries on bad JSON."""
    
    bad_json = "This is not json"
    good_json = """
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
    
    with patch("google.generativeai.GenerativeModel") as MockModel:
        instance = MockModel.return_value
        
        mock_bad = MagicMock()
        mock_bad.text = bad_json
        
        mock_good = MagicMock()
        mock_good.text = good_json
        
        instance.generate_content.side_effect = [mock_bad, mock_good]
        
        service = ExtractorService()
        metadata = await service.extract("Retry me")
        
        assert metadata.primary_area == "documentation"
        assert metadata.difficulty == "easy"
        # Verify it was called twice
        assert instance.generate_content.call_count == 2
