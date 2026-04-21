"""Tests for the GitHub API clients using httpx mock transport."""
from __future__ import annotations

import json

import httpx
import pytest

from devpulse.client import (
    AsyncGitHubClient,
    GitHubAPIError,
    GitHubClient,
    RateLimitWarning,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_USER = {"login": "tomfynes", "id": 12345}
MOCK_REPO = {
    "full_name": "astral-sh/uv",
    "description": "Fast Python package manager",
    "stargazers_count": 9999,
    "forks_count": 400,
    "open_issues_count": 35,
    "language": "Rust",
}
MOCK_PRS = [
    {
        "number": 100,
        "title": "Fix something",
        "user": {"login": "contributor"},
        "labels": [],
        "created_at": "2026-05-01T12:00:00Z",
    }
]
MOCK_RUNS = {
    "workflow_runs": [
        {
            "name": "CI",
            "head_branch": "main",
            "conclusion": "success",
            "status": "completed",
            "created_at": "2026-05-10T08:00:00Z",
        }
    ]
}


def make_response(data: dict, status: int = 200, headers: dict | None = None) -> httpx.Response:
    h = {"X-RateLimit-Remaining": "500", "X-RateLimit-Reset": "1234567890"}
    if headers:
        h.update(headers)
    return httpx.Response(status, json=data, headers=h)


class MockTransport(httpx.BaseTransport):
    def __init__(self, routes: dict[str, dict]):
        self._routes = routes

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in self._routes:
            return self._routes[path]
        return httpx.Response(404, json={"message": "Not Found"})


class AsyncMockTransport(httpx.AsyncBaseTransport):
    def __init__(self, routes: dict[str, httpx.Response]):
        self._routes = routes

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in self._routes:
            return self._routes[path]
        return httpx.Response(404, json={"message": "Not Found"})


# ---------------------------------------------------------------------------
# Sync client tests
# ---------------------------------------------------------------------------

def make_sync_client(routes: dict) -> GitHubClient:
    client = GitHubClient.__new__(GitHubClient)
    client._client = httpx.Client(transport=MockTransport(routes), base_url="https://api.github.com")
    return client


def test_sync_validate_token():
    client = make_sync_client({"/user": make_response(MOCK_USER)})
    user = client.validate_token()
    assert user["login"] == "tomfynes"


def test_sync_get_repo():
    client = make_sync_client({"/repos/astral-sh/uv": make_response(MOCK_REPO)})
    repo = client.get_repo("astral-sh/uv")
    assert repo["full_name"] == "astral-sh/uv"


def test_sync_get_open_prs():
    client = make_sync_client({"/repos/astral-sh/uv/pulls": make_response(MOCK_PRS)})
    prs = client.get_open_prs("astral-sh/uv")
    assert len(prs) == 1
    assert prs[0]["number"] == 100


def test_sync_404_raises_api_error():
    client = make_sync_client({})
    with pytest.raises(GitHubAPIError, match="Not found"):
        client.get_repo("does/notexist")


def test_sync_rate_limit_warning():
    response = make_response(MOCK_REPO, headers={"X-RateLimit-Remaining": "5"})
    client = make_sync_client({"/repos/astral-sh/uv": response})
    with pytest.raises(RateLimitWarning):
        client.get_repo("astral-sh/uv")


# ---------------------------------------------------------------------------
# Async client tests
# ---------------------------------------------------------------------------

def make_async_client(routes: dict) -> AsyncGitHubClient:
    client = AsyncGitHubClient.__new__(AsyncGitHubClient)
    client._client = httpx.AsyncClient(
        transport=AsyncMockTransport(routes),
        base_url="https://api.github.com",
    )
    return client


@pytest.mark.asyncio
async def test_async_get_repo():
    client = make_async_client({"/repos/astral-sh/uv": make_response(MOCK_REPO)})
    repo = await client.get_repo("astral-sh/uv")
    assert repo["language"] == "Rust"
    await client.close()


@pytest.mark.asyncio
async def test_async_get_prs():
    client = make_async_client({"/repos/astral-sh/uv/pulls": make_response(MOCK_PRS)})
    prs = await client.get_open_prs("astral-sh/uv")
    assert prs[0]["title"] == "Fix something"
    await client.close()


@pytest.mark.asyncio
async def test_async_get_workflow_runs():
    client = make_async_client({"/repos/astral-sh/uv/actions/runs": make_response(MOCK_RUNS)})
    runs = await client.get_workflow_runs("astral-sh/uv")
    assert runs[0]["conclusion"] == "success"
    await client.close()


@pytest.mark.asyncio
async def test_async_rate_limit_warning():
    response = make_response(MOCK_REPO, headers={"X-RateLimit-Remaining": "3"})
    client = make_async_client({"/repos/astral-sh/uv": response})
    with pytest.raises(RateLimitWarning):
        await client.get_repo("astral-sh/uv")
    await client.close()
