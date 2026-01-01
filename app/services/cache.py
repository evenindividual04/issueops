import json
import hashlib
import os
import logging
from typing import Dict, Optional, Any
from app.models.schemas import IssueMetadata

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Manages a simple JSON-based cache to avoid re-analyzing unchanged issues.
    Key: SHA-256(issue_text)
    Value: Serialized IssueMetadata
    """
    
    def __init__(self, cache_path: str = ".triage_cache.json"):
        self.cache_path = cache_path
        self.cache: Dict[str, Any] = {}
        self.load()

    def _compute_hash(self, text: str) -> str:
        """Generate a deterministic hash for the content."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def load(self):
        """Load cache from disk."""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r") as f:
                    self.cache = json.load(f)
                logger.info(f"Loaded {len(self.cache)} cached items from {self.cache_path}")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}. Starting fresh.")
                self.cache = {}
        else:
            self.cache = {}

    def save(self):
        """Persist cache to disk."""
        try:
            with open(self.cache_path, "w") as f:
                json.dump(self.cache, f)
            logger.info(f"Saved cache to {self.cache_path}")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def get(self, text: str) -> Optional[IssueMetadata]:
        """Retrieve metadata if text matches cache."""
        key = self._compute_hash(text)
        data = self.cache.get(key)
        if data:
            try:
                # Deserialize back to Pydantic model
                return IssueMetadata(**data)
            except Exception:
                return None
        return None

    def set(self, text: str, metadata: IssueMetadata):
        """Store metadata in cache."""
        key = self._compute_hash(text)
        self.cache[key] = metadata.model_dump()
