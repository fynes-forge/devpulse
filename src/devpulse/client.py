"""GitHub API clients — synchronous (Typer) and async (Textual)."""
from __future__ import annotations

import httpx

GITHUB_API = "https://api.github.com"
RATE_LIMIT_WARNING_THRESHOLD = 20


class RateLimitWarning(Exception):
    """Raised when the GitHub API rate limit is getting critically low."""
    pass


class GitHubAPIError(Exception):
    """Raised on non-2xx responses from the GitHub API."""
    pass


def _build_headers(token: str) -> dict[str, str]:
    """Shared auth headers for both sync and async clients."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _check_rate_limit(response: httpx.Response) -> None:
    """Warn if the remaining API call budget is low."""
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining is not None and int(remaining) < RATE_LIMIT_WARNING_THRESHOLD:
        raise RateLimitWarning(
            f"GitHub API rate limit low: {remaining} requests remaining. "
            f"Resets at: {response.headers.get('X-RateLimit-Reset', 'unknown')}"
        )


# ---------------------------------------------------------------------------
# Synchronous client — used by Typer CLI commands
# ---------------------------------------------------------------------------

class GitHubClient:
    """Synchronous GitHub API client. Use as a context manager."""

    def __init__(self, token: str) -> None:
        self._client = httpx.Client(
            base_url=GITHUB_API,
            headers=_build_headers(token),
            timeout=15.0,
        )

    def _get(self, path: str, **params) -> httpx.Response:
        response = self._client.get(path, params=params or None)
        if response.status_code == 404:
            raise GitHubAPIError(f"Not found: {path}")
        if response.status_code == 401:
            raise GitHubAPIError("Authentication failed. Run `devpulse login` to refresh your token.")
        response.raise_for_status()
        _check_rate_limit(response)
        return response

    def validate_token(self) -> dict:
        """Validate the token by fetching the authenticated user."""
        return self._get("/user").json()

    def get_repo(self, repo: str) -> dict:
        """Fetch basic repository metadata."""
        return self._get(f"/repos/{repo}").json()

    def get_open_prs(self, repo: str) -> list[dict]:
        """Fetch open pull requests for a repository (up to 50)."""
        return self._get(f"/repos/{repo}/pulls", state="open", per_page=50).json()

    def get_workflow_runs(self, repo: str) -> list[dict]:
        """Fetch recent workflow runs."""
        return self._get(f"/repos/{repo}/actions/runs", per_page=10).json().get("workflow_runs", [])

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Async client — used by the Textual TUI
# ---------------------------------------------------------------------------

class AsyncGitHubClient:
    """Async GitHub API client. Use as an async context manager."""

    def __init__(self, token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API,
            headers=_build_headers(token),
            timeout=15.0,
        )

    async def _get(self, path: str, **params) -> httpx.Response:
        response = await self._client.get(path, params=params or None)
        if response.status_code == 404:
            raise GitHubAPIError(f"Not found: {path}")
        if response.status_code == 401:
            raise GitHubAPIError("Authentication failed. Run `devpulse login` to refresh your token.")
        response.raise_for_status()
        _check_rate_limit(response)
        return response

    async def validate_token(self) -> dict:
        return (await self._get("/user")).json()

    async def get_repo(self, repo: str) -> dict:
        return (await self._get(f"/repos/{repo}")).json()

    async def get_open_prs(self, repo: str) -> list[dict]:
        return (await self._get(f"/repos/{repo}/pulls", state="open", per_page=50)).json()

    async def get_workflow_runs(self, repo: str) -> list[dict]:
        return (await self._get(f"/repos/{repo}/actions/runs", per_page=10)).json().get("workflow_runs", [])

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncGitHubClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()
