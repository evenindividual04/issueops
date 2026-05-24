import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from app.models.schemas import IssueMetadata

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Two-tier persistence:
      1. `cache`: SHA-256(issue_text) → IssueMetadata payload.
         Skips LLM re-analysis when body content is unchanged.
      2. `processed_signatures`: f"{owner}/{repo}#{issue_number}" → {sha, ts}.
         Skips full triage rerun (labels, comments) when body sha + recent run
         indicate a duplicate Action invocation (e.g. workflow retry).

    Both layers persist to a single JSON file under separate top-level keys.
    """

    SCHEMA_VERSION = 2
    DEFAULT_IDEMPOTENCY_WINDOW_S = 24 * 60 * 60  # 24h

    def __init__(self, cache_path: str = ".triage_cache.json"):
        self.cache_path = cache_path
        self.cache: Dict[str, Any] = {}
        self.processed_signatures: Dict[str, Dict[str, Any]] = {}
        self.load()

    def _compute_hash(self, text: str) -> str:
        """Generate a deterministic hash for the content."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def load(self) -> None:
        """Load cache from disk. Supports v1 (flat dict) and v2 (wrapped) layouts."""
        if not os.path.exists(self.cache_path):
            return
        try:
            with open(self.cache_path) as f:
                raw = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}. Starting fresh.")
            return

        if isinstance(raw, dict) and raw.get("_schema_version") == self.SCHEMA_VERSION:
            self.cache = raw.get("cache", {})
            self.processed_signatures = raw.get("processed_signatures", {})
        else:
            # Legacy v1 file: a flat dict of sha → metadata.
            self.cache = raw if isinstance(raw, dict) else {}
            self.processed_signatures = {}

        logger.info(
            f"Loaded {len(self.cache)} cached extractions, "
            f"{len(self.processed_signatures)} processed signatures."
        )

    def save(self) -> None:
        """Persist both caches under the v2 envelope."""
        payload = {
            "_schema_version": self.SCHEMA_VERSION,
            "cache": self.cache,
            "processed_signatures": self.processed_signatures,
        }
        try:
            with open(self.cache_path, "w") as f:
                json.dump(payload, f)
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

    def set(self, text: str, metadata: IssueMetadata) -> None:
        """Store metadata in cache."""
        key = self._compute_hash(text)
        self.cache[key] = metadata.model_dump()

    @staticmethod
    def _signature_key(owner: str, repo: str, issue_number: int) -> str:
        return f"{owner}/{repo}#{issue_number}"

    def is_recently_processed(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
        window_seconds: int = DEFAULT_IDEMPOTENCY_WINDOW_S,
    ) -> bool:
        """
        True if (owner/repo#number) was processed with the same body sha within
        the idempotency window. Callers should short-circuit triage in that case.
        """
        key = self._signature_key(owner, repo, issue_number)
        prior = self.processed_signatures.get(key)
        if not prior:
            return False
        if prior.get("sha") != self._compute_hash(body):
            return False
        age = time.time() - float(prior.get("ts", 0))
        return age < window_seconds

    def mark_processed(self, owner: str, repo: str, issue_number: int, body: str) -> None:
        """Record that this issue+body was fully triaged at the current time."""
        key = self._signature_key(owner, repo, issue_number)
        self.processed_signatures[key] = {
            "sha": self._compute_hash(body),
            "ts": time.time(),
        }
