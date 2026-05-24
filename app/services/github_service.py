import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


@dataclass
class GitHubIssue:
    """Structured GitHub issue data."""
    number: int
    title: str
    body: str
    comments: List[str]
    url: str
    state: str
    labels: List[str]
    created_at: str
    updated_at: str
    author: str
    reactions: Dict[str, int]


class GitHubService:
    """Service for interacting with GitHub API."""

    def __init__(
        self,
        github_token: Optional[str] = None,
        timeout: int = 10,
        max_retries: int = 3
    ):
        """
        Initialize GitHub service.

        Args:
            github_token: Optional GitHub personal access token
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
        """
        self.github_token = github_token
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = "https://api.github.com"
        self.headers = self._build_headers()

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers with authentication."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Issue-Analyzer/1.0"
        }
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
        return headers

    def parse_github_url(self, url: str) -> tuple[str, str]:
        """
        Parse GitHub URL to extract owner and repo.

        Args:
            url: GitHub repository URL

        Returns:
            Tuple of (owner, repo)

        Raises:
            ValueError: If URL format is invalid
        """
        try:
            # Handle various URL formats
            url = url.strip().rstrip('/')

            # Extract from https://github.com/owner/repo
            if "github.com" in url:
                parts = url.split('/')
                if len(parts) >= 2:
                    owner = parts[-2]
                    repo = parts[-1].replace('.git', '')
                    if owner and repo:
                        return owner, repo

            raise ValueError(f"Invalid GitHub URL format: {url}")
        except Exception as e:
            logger.error(f"Error parsing GitHub URL: {e}")
            raise ValueError(f"Invalid GitHub URL: {url}") from e

    async def fetch_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int
    ) -> GitHubIssue:
        """
        Fetch GitHub issue with comments.

        Args:
            owner: Repository owner
            repo: Repository name
            issue_number: Issue number

        Returns:
            GitHubIssue object with all data

        Raises:
            Exception: If API request fails
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Fetch issue
                issue_url = (
                    f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}"
                )
                issue_response = await client.get(
                    issue_url,
                    headers=self.headers
                )
                issue_response.raise_for_status()
                issue_data = issue_response.json()

                # Fetch comments
                comments = await self._fetch_comments(
                    client, owner, repo, issue_number
                )

                # Check rate limit
                rate_limit = issue_response.headers.get("X-RateLimit-Remaining")
                if rate_limit:
                    logger.info(f"GitHub API rate limit remaining: {rate_limit}")

                return GitHubIssue(
                    number=issue_data.get("number", 0),
                    title=issue_data.get("title", ""),
                    body=issue_data.get("body", ""),
                    comments=comments,
                    url=issue_data.get("html_url", ""),
                    state=issue_data.get("state", ""),
                    labels=[label["name"] for label in issue_data.get("labels", [])],
                    created_at=issue_data.get("created_at", ""),
                    updated_at=issue_data.get("updated_at", ""),
                    author=issue_data.get("user", {}).get("login", ""),
                    reactions=issue_data.get("reactions", {})
                )

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise ValueError(f"Issue #{issue_number} not found in {owner}/{repo}")
                elif e.response.status_code == 403:
                    msg = "GitHub API rate limit exceeded."
                    if not self.github_token:
                        msg += " Add a GITHUB_TOKEN to .env to increase limits."
                    raise ValueError(msg)
                else:
                    logger.error(f"GitHub API error: {e}")
                    raise

            except Exception as e:
                logger.error(f"Error fetching GitHub issue: {e}")
                raise

    async def _fetch_comments(
        self,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        issue_number: int,
        max_comments: int = 20
    ) -> List[str]:
        """
        Fetch issue comments from GitHub API.

        Args:
            client: HTTPX async client
            owner: Repository owner
            repo: Repository name
            issue_number: Issue number
            max_comments: Maximum comments to fetch

        Returns:
            List of comment texts
        """
        try:
            comments_url = (
                f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"
            )
            comments_response = await client.get(
                comments_url,
                headers=self.headers,
                params={"per_page": max_comments}
            )
            comments_response.raise_for_status()
            comments_data = comments_response.json()

            # Extract comment bodies
            comments = [
                comment.get("body", "")
                for comment in comments_data
                if comment.get("body")
            ]

            logger.info(f"Fetched {len(comments)} comments")
            return comments[:max_comments]

        except Exception as e:
            logger.warning(f"Error fetching comments: {e}")
            return []

    async def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current GitHub API rate limit status.

        Returns:
            Rate limit information
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/rate_limit",
                    headers=self.headers
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching rate limit: {e}")
            return {}

    async def validate_repository(
        self,
        owner: str,
        repo: str
    ) -> bool:
        """
        Validate that a repository exists and is accessible.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            True if repository exists and is accessible
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}",
                    headers=self.headers
                )
                return response.status_code == 200
        except Exception:
            return False

    async def apply_labels(self, owner: str, repo: str, issue_number: int, labels: List[str]) -> bool:
        """Apply labels to an issue (additive — GitHub merges, never removes)."""
        if not labels:
            return True

        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/labels"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json={"labels": labels}
                )
                response.raise_for_status()
                logger.info(f"Applied labels {labels} to {owner}/{repo}#{issue_number}")
                return True
            except Exception as e:
                logger.error(f"Failed to apply labels: {e}")
                return False

    async def remove_label(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        label: str,
    ) -> bool:
        """
        Remove a single label from an issue. Returns True on success or if the
        label was already absent (404 is treated as success).
        """
        encoded = quote(label, safe="")
        url = (
            f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}"
            f"/labels/{encoded}"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.delete(url, headers=self.headers)
                if resp.status_code == 404:
                    return True
                resp.raise_for_status()
                logger.info(f"Removed label {label!r} from {owner}/{repo}#{issue_number}")
                return True
            except Exception as e:
                logger.error(f"Failed to remove label {label!r}: {e}")
                return False

    async def sync_labels(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        current_labels: List[str],
        desired_labels: List[str],
        labels_to_remove: Optional[List[str]] = None,
        managed_labels: Optional[List[str]] = None,
    ) -> bool:
        """
        Idempotent diff-based label sync.

        Adds labels in `desired_labels` not yet present. Removes labels from
        `labels_to_remove`, restricted to `managed_labels` if provided
        (prevents removing labels owned by humans/other bots).
        """
        current = set(current_labels)
        desired = set(desired_labels)
        to_add = sorted(desired - current)

        remove_set: set[str] = set(labels_to_remove or [])
        if managed_labels is not None:
            remove_set &= set(managed_labels)
        to_remove = sorted(remove_set & current)

        ok = True
        if to_add:
            ok = await self.apply_labels(owner, repo, issue_number, to_add) and ok
        for label in to_remove:
            ok = await self.remove_label(owner, repo, issue_number, label) and ok
        return ok

    async def fetch_issues(self, owner: str, repo: str, state: str = "open", limit: int = 10) -> List[GitHubIssue]:
        """Fetch multiple issues using Search API to exclude PRs."""
        url = f"{self.base_url}/search/issues"
        query = f"repo:{owner}/{repo} is:issue state:{state}"
        params: dict[str, str] = {"q": query, "per_page": str(limit)}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()

                data = response.json()
                items = data.get("items", [])

                issues = []
                for item in items:
                    issues.append(GitHubIssue(
                        number=item.get("number", 0),
                        title=item.get("title", ""),
                        body=item.get("body", ""),
                        comments=[],
                        url=item.get("html_url", ""),
                        state=item.get("state", ""),
                        labels=[lbl["name"] for lbl in item.get("labels", [])],
                        created_at=item.get("created_at", ""),
                        updated_at=item.get("updated_at", ""),
                        author=item.get("user", {}).get("login", ""),
                        reactions=item.get("reactions", {})
                    ))
                return issues
            except Exception as e:
                logger.error(f"Failed to fetch issues: {e}")
                return []

    async def post_comment(self, owner: str, repo: str, issue_number: int, body: str) -> bool:
        """Post a comment on an issue."""
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json={"body": body}
                )
                response.raise_for_status()
                logger.info(f"Posted comment on {owner}/{repo}#{issue_number}")
                return True
            except Exception as e:
                logger.error(f"Failed to post comment: {e}")
                return False

    async def find_comment_by_marker(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        marker: str,
    ) -> Optional[int]:
        """
        Return the id of the first comment on `issue_number` whose body contains
        `marker`, or None if not found. Marker is typically an HTML comment like
        '<!-- issueops:triage -->' embedded in bot comments so they can be
        updated in-place across re-runs.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(url, headers=self.headers, params={"per_page": 100})
                resp.raise_for_status()
                for comment in resp.json():
                    if marker in (comment.get("body") or ""):
                        return int(comment["id"])
                return None
            except Exception as e:
                logger.warning(f"find_comment_by_marker failed: {e}")
                return None

    async def update_comment(
        self,
        owner: str,
        repo: str,
        comment_id: int,
        body: str,
    ) -> bool:
        """Edit an existing comment (PATCH /issues/comments/{id})."""
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/comments/{comment_id}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.patch(url, headers=self.headers, json={"body": body})
                resp.raise_for_status()
                logger.info(f"Updated comment {comment_id} on {owner}/{repo}")
                return True
            except Exception as e:
                logger.error(f"Failed to update comment {comment_id}: {e}")
                return False

    async def upsert_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
        marker: str,
    ) -> bool:
        """
        Idempotent comment: if a comment containing `marker` already exists,
        edit it. Otherwise post a new one. The marker is appended to the body
        on insert.
        """
        existing_id = await self.find_comment_by_marker(owner, repo, issue_number, marker)
        body_with_marker = body if marker in body else f"{body}\n\n{marker}"
        if existing_id is not None:
            return await self.update_comment(owner, repo, existing_id, body_with_marker)
        return await self.post_comment(owner, repo, issue_number, body_with_marker)

    async def search_issues(self, owner: str, repo: str, keywords: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for duplicate candidates using GitHub Search API.
        Returns lightweight dicts: number, title, body_snippet, state.
        Retries on rate limit (429/403) with exponential backoff.
        """
        query = f"repo:{owner}/{repo} is:issue sort:relevance {keywords}"
        encoded_query = quote(query)
        url = f"{self.base_url}/search/issues?q={encoded_query}&per_page={limit}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    response = await client.get(url, headers=self.headers)

                    if response.status_code in (429, 403):
                        retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
                        logger.warning(f"Rate limited (attempt {attempt + 1}). Retrying in {retry_after}s.")
                        await asyncio.sleep(retry_after)
                        continue

                    if response.status_code == 200:
                        items = response.json().get("items", [])
                        return [
                            {
                                "number": item["number"],
                                "title": item["title"],
                                "state": item["state"],
                                "body_snippet": (item.get("body") or "")[:500],
                            }
                            for item in items
                        ]

                    logger.error(f"Search failed ({response.status_code}): {response.text}")
                    return []

                except Exception as e:
                    logger.error(f"Search error (attempt {attempt + 1}): {e}")
                    if attempt == self.max_retries - 1:
                        return []
                    await asyncio.sleep(2 ** attempt)

        return []
