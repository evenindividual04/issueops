import logging
from typing import Optional
from app.services.extractor import ExtractorService
from app.services.github_service import GitHubService
from app.models.schemas import DuplicateResult
from app.core.config import settings

logger = logging.getLogger(__name__)

class DuplicateService:
    """
    Orchestrates the Duplicate Detection pipeline.
    1. Keyword Extraction (LLM)
    2. Candidate Search (GitHub)
    3. Semantic Verification (LLM)
    """

    def __init__(self, github_service: GitHubService, extractor_service: ExtractorService):
        self.gh = github_service
        self.extractor = extractor_service

    async def check_duplicate(self, owner: str, repo: str, title: str, body: str, current_issue_id: int) -> DuplicateResult:
        full_text = f"{title}\n{body}"
        
        # 1. Generate Keywords
        try:
            keywords = await self.extractor.generate_search_keywords(full_text)
            logger.info(f"Generated Search Keywords: {keywords}")
        except Exception as e:
            logger.warning(f"Keyword generation failed: {e}")
            return DuplicateResult(confidence=0.0, reasoning="Keyword gen failed")

        if not keywords:
            return DuplicateResult(confidence=0.0, reasoning="No keywords found")

        # 2. Search GitHub
        try:
            candidates = await self.gh.search_issues(owner, repo, keywords)
            # Filter out self
            candidates = [c for c in candidates if c['number'] != current_issue_id]
            logger.info(f"Found {len(candidates)} candidates (excluding self).")

        except Exception as e:
           logger.warning(f"Search failed: {e}")
           return DuplicateResult(confidence=0.0, reasoning="Search API failed")

        if not candidates:
             return DuplicateResult(confidence=0.0, reasoning="No candidates found")

        # 3. Verify
        try:
            result = await self.extractor.find_semantic_duplicate(full_text, candidates)
            
            # Enrich with state if match found
            if result.duplicate_number:
                # Find the candidate that matched
                matched_candidate = next((c for c in candidates if c['number'] == result.duplicate_number), None)
                if matched_candidate:
                    result.matched_issue_state = matched_candidate['state']
            
            logger.info(f"Duplicate result: ID={result.duplicate_number} State={result.matched_issue_state} Conf={result.confidence}")
            return result
        except Exception as e:
             logger.error(f"Verification failed: {e}")
             return DuplicateResult(confidence=0.0, reasoning="Verification failed")
