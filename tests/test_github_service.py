from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.github_service import GitHubIssue, GitHubService


def _make_async_client(mock_get=None, mock_post=None):
    """Build a mock httpx.AsyncClient context manager."""
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    if mock_get:
        client.get = mock_get
    if mock_post:
        client.post = mock_post
    return client


def _make_response(status_code: int, body=None, headers: dict = {}):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers
    if isinstance(body, (dict, list)):
        resp.json.return_value = body
        resp.text = str(body)
    else:
        resp.json.side_effect = ValueError("not json")
        resp.text = body or ""
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ── fetch_issue ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_issue_returns_structured_data():
    issue_payload = {
        "number": 42,
        "title": "App crashes on null input",
        "body": "Steps: pass null to login()",
        "html_url": "https://github.com/owner/repo/issues/42",
        "state": "open",
        "labels": [{"name": "bug"}, {"name": "critical"}],
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-02T00:00:00Z",
        "user": {"login": "alice"},
        "reactions": {},
    }
    comments_payload = [{"body": "Confirmed on macOS too."}]

    issue_resp = _make_response(200, issue_payload, {"X-RateLimit-Remaining": "59"})
    comments_resp = _make_response(200, comments_payload)

    mock_get = AsyncMock(side_effect=[issue_resp, comments_resp])
    mock_client = _make_async_client(mock_get=mock_get)

    with patch("app.services.github_service.httpx.AsyncClient", return_value=mock_client):
        svc = GitHubService(github_token="fake-token")
        issue = await svc.fetch_issue("owner", "repo", 42)

    assert isinstance(issue, GitHubIssue)
    assert issue.number == 42
    assert issue.title == "App crashes on null input"
    assert issue.labels == ["bug", "critical"]
    assert issue.comments == ["Confirmed on macOS too."]


@pytest.mark.asyncio
async def test_fetch_issue_404_raises_value_error():
    resp = _make_response(404, "Not Found")
    resp.raise_for_status.side_effect = None

    import httpx
    http_err = httpx.HTTPStatusError("404", request=MagicMock(), response=resp)
    resp.raise_for_status.side_effect = http_err

    mock_get = AsyncMock(side_effect=http_err)
    mock_client = _make_async_client(mock_get=mock_get)

    with patch("app.services.github_service.httpx.AsyncClient", return_value=mock_client):
        svc = GitHubService()
        with pytest.raises(Exception):
            await svc.fetch_issue("owner", "repo", 9999)


# ── apply_labels ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_apply_labels_success():
    resp = _make_response(200, [{"name": "bug"}])
    mock_post = AsyncMock(return_value=resp)
    mock_client = _make_async_client(mock_post=mock_post)

    with patch("app.services.github_service.httpx.AsyncClient", return_value=mock_client):
        svc = GitHubService(github_token="fake-token")
        result = await svc.apply_labels("owner", "repo", 1, ["bug", "critical"])

    assert result is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"] == {"labels": ["bug", "critical"]}


@pytest.mark.asyncio
async def test_apply_labels_empty_list_skips_api():
    mock_post = AsyncMock()
    mock_client = _make_async_client(mock_post=mock_post)

    with patch("app.services.github_service.httpx.AsyncClient", return_value=mock_client):
        svc = GitHubService(github_token="fake-token")
        result = await svc.apply_labels("owner", "repo", 1, [])

    assert result is True
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_apply_labels_api_failure_returns_false():
    mock_post = AsyncMock(side_effect=Exception("network error"))
    mock_client = _make_async_client(mock_post=mock_post)

    with patch("app.services.github_service.httpx.AsyncClient", return_value=mock_client):
        svc = GitHubService(github_token="fake-token")
        result = await svc.apply_labels("owner", "repo", 1, ["bug"])

    assert result is False


# ── search_issues (rate limit backoff) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_search_issues_returns_candidates():
    payload = {
        "items": [
            {"number": 10, "title": "Auth crash", "state": "open", "body": "Details here"},
            {"number": 11, "title": "Login null pointer", "state": "closed", "body": None},
        ]
    }
    resp = _make_response(200, payload)
    mock_get = AsyncMock(return_value=resp)
    mock_client = _make_async_client(mock_get=mock_get)

    with patch("app.services.github_service.httpx.AsyncClient", return_value=mock_client):
        svc = GitHubService(github_token="fake-token")
        results = await svc.search_issues("owner", "repo", "auth crash null")

    assert len(results) == 2
    assert results[0]["number"] == 10
    assert results[1]["body_snippet"] == ""


@pytest.mark.asyncio
async def test_search_issues_retries_on_rate_limit():
    rate_limit_resp = _make_response(429, "Rate limited", {"Retry-After": "0"})
    success_resp = _make_response(200, {"items": [{"number": 5, "title": "Test", "state": "open", "body": "b"}]})

    mock_get = AsyncMock(side_effect=[rate_limit_resp, success_resp])
    mock_client = _make_async_client(mock_get=mock_get)

    with patch("app.services.github_service.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.github_service.asyncio.sleep", new_callable=AsyncMock):
            svc = GitHubService(github_token="fake-token", max_retries=3)
            results = await svc.search_issues("owner", "repo", "crash")

    assert len(results) == 1
    assert results[0]["number"] == 5
    assert mock_get.call_count == 2


# ── post_comment ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_comment_success():
    resp = _make_response(201, {"id": 99})
    mock_post = AsyncMock(return_value=resp)
    mock_client = _make_async_client(mock_post=mock_post)

    with patch("app.services.github_service.httpx.AsyncClient", return_value=mock_client):
        svc = GitHubService(github_token="fake-token")
        result = await svc.post_comment("owner", "repo", 1, "Marked as duplicate.")

    assert result is True


# ── parse_github_url ──────────────────────────────────────────────────────────

def test_parse_github_url_valid():
    svc = GitHubService()
    owner, repo = svc.parse_github_url("https://github.com/acme/my-repo")
    assert owner == "acme"
    assert repo == "my-repo"


def test_parse_github_url_strips_git_suffix():
    svc = GitHubService()
    owner, repo = svc.parse_github_url("https://github.com/acme/my-repo.git")
    assert repo == "my-repo"


def test_parse_github_url_invalid_raises():
    svc = GitHubService()
    with pytest.raises(ValueError):
        svc.parse_github_url("not-a-url")


# ── auth header ───────────────────────────────────────────────────────────────

def test_auth_header_present_when_token_given():
    svc = GitHubService(github_token="ghp_test123")
    assert svc.headers["Authorization"] == "token ghp_test123"


def test_no_auth_header_when_no_token():
    svc = GitHubService()
    assert "Authorization" not in svc.headers
