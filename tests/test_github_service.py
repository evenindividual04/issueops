from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.github_service import GitHubIssue, GitHubService


def _make_async_client(mock_get=None, mock_post=None, mock_patch=None):
    """Build a mock httpx.AsyncClient context manager."""
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    if mock_get:
        client.get = mock_get
    if mock_post:
        client.post = mock_post
    if mock_patch:
        client.patch = mock_patch
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


# ── find_comment_by_marker / update_comment / upsert_comment ──────────────────

@pytest.mark.asyncio
async def test_find_comment_by_marker_hit():
    comments_payload = [
        {"id": 1, "body": "regular human comment"},
        {"id": 2, "body": "bot wrote this <!-- issueops:triage -->"},
    ]
    resp = _make_response(200, comments_payload)
    mock_get = AsyncMock(return_value=resp)
    client = _make_async_client(mock_get=mock_get)

    svc = GitHubService(github_token="t")
    with patch("app.services.github_service.httpx.AsyncClient", return_value=client):
        cid = await svc.find_comment_by_marker("o", "r", 1, "<!-- issueops:triage -->")
    assert cid == 2


@pytest.mark.asyncio
async def test_find_comment_by_marker_miss_returns_none():
    resp = _make_response(200, [{"id": 1, "body": "unrelated"}])
    client = _make_async_client(mock_get=AsyncMock(return_value=resp))

    svc = GitHubService(github_token="t")
    with patch("app.services.github_service.httpx.AsyncClient", return_value=client):
        cid = await svc.find_comment_by_marker("o", "r", 1, "<!-- issueops:triage -->")
    assert cid is None


@pytest.mark.asyncio
async def test_find_comment_by_marker_swallows_errors():
    mock_get = AsyncMock(side_effect=Exception("boom"))
    client = _make_async_client(mock_get=mock_get)

    svc = GitHubService(github_token="t")
    with patch("app.services.github_service.httpx.AsyncClient", return_value=client):
        cid = await svc.find_comment_by_marker("o", "r", 1, "marker")
    assert cid is None


@pytest.mark.asyncio
async def test_update_comment_success():
    resp = _make_response(200, {"id": 42, "body": "new body"})
    mock_patch_call = AsyncMock(return_value=resp)
    client = _make_async_client(mock_patch=mock_patch_call)

    svc = GitHubService(github_token="t")
    with patch("app.services.github_service.httpx.AsyncClient", return_value=client):
        ok = await svc.update_comment("o", "r", 42, "new body")
    assert ok is True


@pytest.mark.asyncio
async def test_update_comment_failure_returns_false():
    mock_patch_call = AsyncMock(side_effect=Exception("network"))
    client = _make_async_client(mock_patch=mock_patch_call)

    svc = GitHubService(github_token="t")
    with patch("app.services.github_service.httpx.AsyncClient", return_value=client):
        ok = await svc.update_comment("o", "r", 42, "x")
    assert ok is False


@pytest.mark.asyncio
async def test_upsert_comment_creates_when_no_existing(monkeypatch):
    svc = GitHubService(github_token="t")

    async def _no_existing(*_a, **_kw):
        return None

    posted = {}

    async def _post(owner, repo, num, body):
        posted["body"] = body
        return True

    monkeypatch.setattr(svc, "find_comment_by_marker", _no_existing)
    monkeypatch.setattr(svc, "post_comment", _post)

    ok = await svc.upsert_comment("o", "r", 1, "hello", "<!-- m -->")
    assert ok is True
    assert "hello" in posted["body"] and "<!-- m -->" in posted["body"]


@pytest.mark.asyncio
async def test_upsert_comment_updates_when_existing(monkeypatch):
    svc = GitHubService(github_token="t")

    async def _existing(*_a, **_kw):
        return 99

    updated = {}

    async def _update(owner, repo, cid, body):
        updated["id"] = cid
        updated["body"] = body
        return True

    monkeypatch.setattr(svc, "find_comment_by_marker", _existing)
    monkeypatch.setattr(svc, "update_comment", _update)

    ok = await svc.upsert_comment("o", "r", 1, "hello", "<!-- m -->")
    assert ok is True
    assert updated["id"] == 99
    assert "hello" in updated["body"] and "<!-- m -->" in updated["body"]


@pytest.mark.asyncio
async def test_remove_label_success():
    resp = _make_response(200, {})
    mock_delete = AsyncMock(return_value=resp)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.delete = mock_delete

    svc = GitHubService(github_token="t")
    with patch("app.services.github_service.httpx.AsyncClient", return_value=client):
        ok = await svc.remove_label("o", "r", 1, "stale")
    assert ok is True


@pytest.mark.asyncio
async def test_remove_label_404_is_success():
    """Removing a non-existent label should not be treated as an error."""
    resp = _make_response(404, "")
    resp.raise_for_status.side_effect = None  # 404 path returns early
    mock_delete = AsyncMock(return_value=resp)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.delete = mock_delete

    svc = GitHubService(github_token="t")
    with patch("app.services.github_service.httpx.AsyncClient", return_value=client):
        ok = await svc.remove_label("o", "r", 1, "ghost")
    assert ok is True


@pytest.mark.asyncio
async def test_remove_label_failure():
    mock_delete = AsyncMock(side_effect=Exception("network"))
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.delete = mock_delete

    svc = GitHubService(github_token="t")
    with patch("app.services.github_service.httpx.AsyncClient", return_value=client):
        ok = await svc.remove_label("o", "r", 1, "x")
    assert ok is False


@pytest.mark.asyncio
async def test_sync_labels_only_adds_missing(monkeypatch):
    svc = GitHubService(github_token="t")
    calls = {"add": None, "remove": []}

    async def _apply(owner, repo, num, labels):
        calls["add"] = labels
        return True

    async def _remove(owner, repo, num, label):
        calls["remove"].append(label)
        return True

    monkeypatch.setattr(svc, "apply_labels", _apply)
    monkeypatch.setattr(svc, "remove_label", _remove)

    ok = await svc.sync_labels(
        "o", "r", 1,
        current_labels=["bug"],
        desired_labels=["bug", "critical"],
    )
    assert ok is True
    assert calls["add"] == ["critical"]
    assert calls["remove"] == []


@pytest.mark.asyncio
async def test_sync_labels_respects_managed_whitelist(monkeypatch):
    """labels_to_remove must be intersected with managed_labels."""
    svc = GitHubService(github_token="t")
    removed: list[str] = []

    async def _apply(*_a, **_kw):
        return True

    async def _remove(owner, repo, num, label):
        removed.append(label)
        return True

    monkeypatch.setattr(svc, "apply_labels", _apply)
    monkeypatch.setattr(svc, "remove_label", _remove)

    await svc.sync_labels(
        "o", "r", 1,
        current_labels=["triage/low-confidence", "user-added"],
        desired_labels=["critical"],
        labels_to_remove=["triage/low-confidence", "user-added"],
        managed_labels=["triage/low-confidence", "critical"],
    )
    assert removed == ["triage/low-confidence"]


@pytest.mark.asyncio
async def test_sync_labels_noop_when_already_in_sync(monkeypatch):
    svc = GitHubService(github_token="t")
    calls = {"add": 0, "remove": 0}

    async def _apply(*_a, **_kw):
        calls["add"] += 1
        return True

    async def _remove(*_a, **_kw):
        calls["remove"] += 1
        return True

    monkeypatch.setattr(svc, "apply_labels", _apply)
    monkeypatch.setattr(svc, "remove_label", _remove)

    await svc.sync_labels(
        "o", "r", 1,
        current_labels=["bug", "critical"],
        desired_labels=["bug", "critical"],
    )
    assert calls == {"add": 0, "remove": 0}


@pytest.mark.asyncio
async def test_upsert_does_not_double_marker(monkeypatch):
    """If body already contains the marker, don't append it again."""
    svc = GitHubService(github_token="t")

    async def _no_existing(*_a, **_kw):
        return None

    posted = {}

    async def _post(owner, repo, num, body):
        posted["body"] = body
        return True

    monkeypatch.setattr(svc, "find_comment_by_marker", _no_existing)
    monkeypatch.setattr(svc, "post_comment", _post)

    body_with_marker = "hello <!-- m -->"
    await svc.upsert_comment("o", "r", 1, body_with_marker, "<!-- m -->")
    assert posted["body"].count("<!-- m -->") == 1
