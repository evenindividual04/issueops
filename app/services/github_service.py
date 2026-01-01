import httpx
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from urllib.parse import quote

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
        """Apply labels to an issue."""
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

    async def fetch_issues(self, owner: str, repo: str, state: str = "open", limit: int = 10) -> List[GitHubIssue]:
        """Fetch multiple issues using Search API to exclude PRs."""
        url = f"{self.base_url}/search/issues"
        query = f"repo:{owner}/{repo} is:issue state:{state}"
        params = {"q": query, "per_page": limit}
        
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
                        labels=[l["name"] for l in item.get("labels", [])],
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

    async def search_issues(self, owner: str, repo: str, keywords: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for duplicate candidates using GitHub Search API.
        Returns lightweight dicts: number, title, body_snippet, state.
        """
        query = f"repo:{owner}/{repo} is:issue sort:relevance {keywords}"
        encoded_query = quote(query)
        url = f"{self.base_url}/search/issues?q={encoded_query}&per_page={limit}"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=self.headers)
                if response.status_code == 200:
                    items = response.json().get("items", [])
                    candidates = []
                    for item in items:
                        body = item.get("body") or ""
                        candidates.append({
                            "number": item["number"],
                            "title": item["title"],
                            "state": item["state"],
                            "body_snippet": body[:500]
                        })
                    return candidates
                else:
                    logger.error(f"Search failed: {response.text}")
                    return []
            except Exception as e:
                logger.error(f"Search error: {e}")
                return []
