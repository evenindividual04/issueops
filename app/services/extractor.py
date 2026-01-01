import json
import logging
import google.generativeai as genai
from pydantic import ValidationError

from app.core.config import settings
from app.models.schemas import IssueMetadata, DuplicateResult
from app.services.cache import CacheManager

logger = logging.getLogger(__name__)

class ExtractorService:
    """
    AI-powered extraction engine.
    Converts unstructured issue text into strict JSON metadata.
    """

    def __init__(self, use_cache: bool = True):
        # Initialize Gemini
        if not settings.GEMINI_API_KEY:
             raise ValueError("GEMINI_API_KEY is not set")
        
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(settings.LLM_MODEL)
        self.cache = CacheManager() if use_cache else None
    
    def _build_prompt(self, text: str) -> str:
        """Construct the extraction prompt with strict schema definition."""
        return f"""You are a technical screener for an Open Source Project.
Your job is to analyze the GitHub Issue below and extract structured metadata for two audiences:
1. MAINTAINERS: Who need to know if it's a critical crash or security risk.
2. CONTRIBUTORS: Who need to know if it's a "Good First Issue" (easy, clear skills).

STRICT INSTRUCTIONS:
1. Output ONLY valid JSON.
2. For 'difficulty':
   - "easy": Typos, documentation, simple CSS/Text changes.
   - "medium": isolated bug fix, single function change.
   - "hard": Architectural change, race conditions, core logic.
3. For 'required_skills': specific languages or tools (e.g. "python", "react", "sql"). Lowercase only.
4. For 'summary': A single, simple sentence describing the goal (e.g. "Fix crash when clicking login button").

SCHEMA REFERENCE:
- has_reproduction_steps, has_stacktrace, has_logs (bool)
- is_crash, is_security_issue, is_blocker (bool)
- operating_system (str|null), environment (str)
- summary (str): Non-technical summary.
- difficulty (str): "easy", "medium", "hard", "unknown"
- required_skills (List[str]): e.g. ["python", "docker"]
- primary_area (str): "frontend", "backend" etc.
- extraction_confidence (float): 0.0 to 1.0

ISSUE TEXT:
{text[:10000]}
"""

    async def extract(self, text: str) -> IssueMetadata:
        """
        Extract metadata from issue text.
        Retries once on JSON failure.
        """
        # 1. Check Cache
        if self.cache:
            cached = self.cache.get(text)
            if cached:
                logger.info("⚡️ Cache Hit: Skipping AI analysis.")
                return cached

        prompt = self._build_prompt(text)
        
        try:
            result = await self._generate_and_parse(prompt)
            # 2. Update Cache
            if self.cache:
                self.cache.set(text, result)
                self.cache.save()
            return result
        except Exception as first_error:
            logger.warning(f"Extraction failed (attempt 1): {first_error}. Retrying...")
            try:
                # Retry with explicit JSON instruction appended
                retry_prompt = prompt + "\n\nError: Invalid JSON returned. Please fix and output ONLY standard JSON."
                return await self._generate_and_parse(retry_prompt)
            except Exception as e:
                logger.error(f"Extraction failed permanently: {e}")
                raise ValueError(f"Failed to extract metadata: {e}")

    async def _generate_and_parse(self, prompt: str) -> IssueMetadata:
        """Helper to call LLM and validate Pydantic model."""
        # Note: Using synchronous generate_content because async support is limited in some versions
        # wrapping in simple awaitable if needed, but for CLI tool synchronous is fine or we can use ThreadPool
        # For this phase, we will call it directly since `main.py` will likely be async or we just accept the blocking call
        
        response = self.model.generate_content(
            prompt,
            generation_config={"temperature": 0.0}
        )
        
        if not response.text:
            raise ValueError("Empty response from LLM")

        # Clean response (sometimes models add markdown blocks despite instructions)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        
        try:
            data = json.loads(clean_json)
            return IssueMetadata(**data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
        except ValidationError as e:
            raise ValueError(f"Schema Validation Failed: {e}")

    async def generate_search_keywords(self, text: str) -> str:
        """Extract high-signal keywords for GitHub Search."""
        prompt = f"""You are a search query optimizer. 
Extract 3-5 unique technical keywords from the issue below to find duplicates.
PRIORITY:
1. Hex codes, Error Constants, Exception Names.
2. Distinctive terms (deadlock, race condition).
3. EXCLUDE generic words (bug, error, help, crash).

Output ONLY the space-separated keywords string.

ISSUE:
{text[:2000]}
"""
        response = await self.model.generate_content_async(prompt)
        return response.text.strip().replace('"', '')

    async def find_semantic_duplicate(self, new_issue_text: str, candidates: list) -> DuplicateResult:
        """Compare new issue against candidates to find semantic match."""
        if not candidates:
            return DuplicateResult(duplicate_number=None, confidence=0.0, reasoning="No candidates found.")

        candidates_text = "\n".join([
            f"Candidate #{c['number']} ({c['state']}): {c['title']}\n{c['body_snippet']}..." 
            for c in candidates
        ])

        prompt = f"""You are a Senior QA Engineer. Compare the NEW ISSUE to CANDIDATES.
Identify if any candidate describes the EXACT SAME root cause.

SCORING:
- 1.0: Identical stack trace / error code.
- 0.8: Strong match (same behavior, different words).
- <0.5: Vague similarity.

STRICT JSON OUTPUT:
{{
  "duplicate_number": <int|null>,
  "confidence": <float 0.0-1.0>,
  "reasoning": "<string>"
}}

NEW ISSUE:
{new_issue_text[:3000]}

CANDIDATES:
{candidates_text}
"""
        try:
            # Use _generate_and_parse logic inline but adapted for DuplicateResult
            response = await self.model.generate_content_async(prompt)
            clean = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            return DuplicateResult(**data)
        except Exception:
            return DuplicateResult(duplicate_number=None, confidence=0.0, reasoning="Analysis Failed")
