import json
import logging
import re

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.core.config import settings
from app.models.schemas import DuplicateResult, IssueMetadata
from app.services.cache import CacheManager

logger = logging.getLogger(__name__)

_CRASH_PATTERNS = re.compile(
    r"\b(panic|segfault|sigsegv|stack overflow|core dumped|fatal error|"
    r"unrecoverable|nullpointerexception|crash(?:ed|es|ing)?)\b",
    re.IGNORECASE,
)
_SECURITY_PATTERNS = re.compile(
    r"\b(cve-\d{4}-\d+|xss|csrf|sql injection|rce|"
    r"unauthorized|privilege escalation|vulnerab)",
    re.IGNORECASE,
)
_STACKTRACE_PATTERNS = re.compile(
    r"(traceback \(most recent call last\)|^\s+at [\w.$]+\(.*?\)|^\s+File \".*?\", line \d+)",
    re.IGNORECASE | re.MULTILINE,
)


def _fallback_extract(text: str) -> IssueMetadata:
    """
    Deterministic regex-based extraction. Used when the LLM circuit is open.
    Returns confidence 0.5 so the confidence gate routes the issue to
    'triage/low-confidence' rather than acting on the regex output.
    """
    return IssueMetadata(
        has_reproduction_steps=False,
        has_stacktrace=bool(_STACKTRACE_PATTERNS.search(text)),
        has_logs=False,
        is_crash=bool(_CRASH_PATTERNS.search(text)),
        is_security_issue=bool(_SECURITY_PATTERNS.search(text)),
        is_blocker=False,
        operating_system=None,
        environment="unknown",
        summary=text.strip().splitlines()[0][:200] if text.strip() else "(empty)",
        difficulty="unknown",
        required_skills=[],
        primary_area="unknown",
        verification_hint=None,
        related_closed_issue_id=None,
        extraction_confidence=0.5,
        extraction_mode="fallback",
    )


class ExtractorService:
    """
    AI-powered extraction engine.
    Converts unstructured issue text into strict JSON metadata.
    Wrapped in a circuit breaker — on sustained LLM failure, falls back to
    a deterministic regex extractor with low confidence.
    """

    def __init__(self, use_cache: bool = True):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set")

        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.LLM_MODEL
        self.cache = CacheManager() if use_cache else None
        self.breaker = CircuitBreaker(failure_threshold=5, recovery_seconds=60.0)

    def _build_prompt(self, text: str) -> str:
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
4. For 'summary': A single, simple sentence describing the goal.

SCHEMA REFERENCE:
- has_reproduction_steps, has_stacktrace, has_logs (bool)
- is_crash, is_security_issue, is_blocker (bool)
- operating_system (str|null), environment (str)
- summary (str): Non-technical summary.
- difficulty (str): "easy", "medium", "hard", "unknown"
- required_skills (List[str]): e.g. ["python", "docker"]
- primary_area (str): "frontend", "backend" etc.
- verification_hint (str|null): A single shell command to verify the fix. Infer from file paths/stacktrace.
- extraction_confidence (float): 0.0 to 1.0

ISSUE TEXT:
{text[:10000]}
"""

    async def extract(self, text: str) -> IssueMetadata:
        """Extract metadata from issue text. Retries once on JSON failure."""
        if self.cache:
            cached = self.cache.get(text)
            if cached:
                logger.info("Cache hit — skipping LLM call.")
                return cached

        prompt = self._build_prompt(text)

        try:
            result = await self.breaker.call(self._generate_and_parse, prompt)
            if self.cache:
                self.cache.set(text, result)
                self.cache.save()
            return result
        except CircuitOpenError as e:
            logger.warning(f"LLM circuit open — using fallback extractor: {e}")
            return _fallback_extract(text)
        except Exception as first_error:
            logger.warning(f"Extraction attempt 1 failed: {first_error}. Retrying...")
            retry_prompt = prompt + "\n\nError: Invalid JSON returned. Output ONLY standard JSON."
            try:
                return await self.breaker.call(self._generate_and_parse, retry_prompt)
            except CircuitOpenError:
                return _fallback_extract(text)
            except Exception as e:
                logger.error(f"Extraction failed permanently: {e}")
                # Last-resort: degrade rather than fail the Action entirely.
                return _fallback_extract(text)

    async def _generate_and_parse(self, prompt: str) -> IssueMetadata:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0),
        )

        if not response.text:
            raise ValueError("Empty response from LLM")

        clean_json = response.text.replace("```json", "").replace("```", "").strip()

        try:
            data = json.loads(clean_json)
            return IssueMetadata(**data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e
        except ValidationError as e:
            raise ValueError(f"Schema validation failed: {e}") from e

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
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return (response.text or "").strip().replace('"', '')

    async def find_semantic_duplicate(self, new_issue_text: str, candidates: list) -> DuplicateResult:
        """Compare new issue against candidates to find semantic match."""
        if not candidates:
            return DuplicateResult(duplicate_number=None, matched_issue_state=None, confidence=0.0, reasoning="No candidates found.")

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
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            clean = (response.text or "").replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            return DuplicateResult(**data)
        except Exception:
            return DuplicateResult(duplicate_number=None, matched_issue_state=None, confidence=0.0, reasoning="Analysis failed.")
