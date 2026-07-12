"""
GitHub client — V1 MVP (Task 005).

Implements a minimal, real client against the official GitHub REST API,
using the existing Settings system (phoenix_core.config.settings.GitHubConfig)
for configuration. Only the following operations are supported:

- check_repository_access() — verify the token can access the configured repo
- get_repository()          — fetch repository info
- get_current_user()        — fetch info for the authenticated user
- create_issue()            — create an issue
- list_issues()             — list issues

No Pull Requests, branches, releases, commits, or Actions/workflow
management — out of scope for Task 005.
"""
from typing import Any, Dict, List, Optional

import httpx

from phoenix_core.config.settings import GitHubConfig
from phoenix_core.utils.exceptions import (
    GitHubAuthenticationError,
    GitHubConfigurationError,
    GitHubConnectionError,
    GitHubError,
    GitHubForbiddenError,
    GitHubInvalidResponseError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubTimeoutError,
)
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://api.github.com"
DEFAULT_API_VERSION = "2022-11-28"
DEFAULT_TIMEOUT = 30


class GitHubClient:
    """Minimal GitHub REST API client (V1 MVP, Task 005).

    Configuration (token, owner, repo) comes exclusively from
    phoenix_core.config.settings.GitHubConfig, populated via environment
    variables (PHOENIX_GITHUB_TOKEN / PHOENIX_GITHUB_OWNER / PHOENIX_GITHUB_REPO).
    """

    def __init__(
        self,
        token: str,
        settings: GitHubConfig,
        base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Create a client bound to a single repository.

        Args:
            token: GitHub personal access token (may be empty; operations
                that require it will raise GitHubConfigurationError).
            settings: GitHubConfig providing owner/repo.
            base_url: Override for the GitHub API base URL (mainly for tests).
            timeout: Request timeout in seconds.
        """
        self.token = token
        self.settings = settings
        self.base_url = base_url or DEFAULT_BASE_URL
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Lifecycle hook. No network calls are made on start."""
        logger.debug("GitHubClient.start() called")

    async def stop(self) -> None:
        """Lifecycle hook: closes the underlying HTTP client."""
        await self.close()
        logger.debug("GitHubClient.stop() called")

    async def close(self) -> None:
        """Close the underlying HTTP client, if one was created."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": DEFAULT_API_VERSION,
                },
            )
        return self._client

    # ------------------------------------------------------------------
    # Health check (Задача 4 — local validation only, no network request)
    # ------------------------------------------------------------------

    async def health_check(self) -> Dict[str, Any]:
        """Validate local configuration only (token, owner, repo present).

        Does NOT send any request to GitHub.
        """
        issues = []
        if not self.token:
            issues.append("token is not set")

        owner = getattr(self.settings, "owner", "") or ""
        if not owner:
            issues.append("owner is not set")

        repo = getattr(self.settings, "repo", "") or ""
        if not repo:
            issues.append("repo is not set")

        return {
            "status": "configured" if not issues else "misconfigured",
            "owner": owner or None,
            "repo": repo or None,
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # Public operations (Задача 2)
    # ------------------------------------------------------------------

    async def check_repository_access(self) -> bool:
        """Check that the configured token can access the configured repository."""
        owner = self._require_owner()
        repo = self._require_repo()
        logger.info("Checking GitHub repository access", owner=owner, repo=repo)
        await self._request("GET", f"/repos/{owner}/{repo}")
        return True

    async def get_repository(self) -> Dict[str, Any]:
        """Get information about the configured repository."""
        owner = self._require_owner()
        repo = self._require_repo()
        logger.info("Fetching GitHub repository info", owner=owner, repo=repo)
        return await self._request("GET", f"/repos/{owner}/{repo}")

    async def get_current_user(self) -> Dict[str, Any]:
        """Get information about the currently authenticated user."""
        logger.info("Fetching current GitHub user")
        return await self._request("GET", "/user")

    async def create_issue(
        self,
        title: str,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create an issue in the configured repository."""
        owner = self._require_owner()
        repo = self._require_repo()

        payload: Dict[str, Any] = {"title": title}
        if body is not None:
            payload["body"] = body
        if labels:
            payload["labels"] = labels

        logger.info("Creating GitHub issue", owner=owner, repo=repo)
        return await self._request("POST", f"/repos/{owner}/{repo}/issues", json_body=payload)

    async def list_issues(
        self,
        state: str = "open",
        per_page: int = 30,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """List issues in the configured repository."""
        owner = self._require_owner()
        repo = self._require_repo()

        params = {"state": state, "per_page": per_page, "page": page}
        logger.info("Listing GitHub issues", owner=owner, repo=repo, state=state)
        return await self._request("GET", f"/repos/{owner}/{repo}/issues", params=params)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_owner(self) -> str:
        owner = getattr(self.settings, "owner", "") or ""
        if not owner:
            raise GitHubConfigurationError("GitHub owner is not configured")
        return owner

    def _require_repo(self) -> str:
        repo = getattr(self.settings, "repo", "") or ""
        if not repo:
            raise GitHubConfigurationError("GitHub repo is not configured")
        return repo

    async def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Perform a single GitHub API request and map errors to standardized exceptions.

        Никога не логва GitHub token или Authorization header (Задача 5).
        """
        if not self.token:
            raise GitHubConfigurationError("GitHub token is not configured")

        client = self._get_client()
        try:
            response = await client.request(method, path, json=json_body, params=params)
        except httpx.TimeoutException as e:
            raise GitHubTimeoutError(f"GitHub request timed out: {e}") from e
        except httpx.TransportError as e:
            raise GitHubConnectionError(f"GitHub connection failed: {e}") from e

        if response.status_code in (200, 201):
            try:
                return response.json()
            except ValueError as e:
                raise GitHubInvalidResponseError(
                    f"GitHub returned a non-JSON response: {e}"
                ) from e

        await self._raise_for_status(response)
        # _raise_for_status always raises; this satisfies type checkers.
        raise GitHubError(f"GitHub request failed (HTTP {response.status_code})")

    async def _raise_for_status(self, response: httpx.Response) -> None:
        """Raise the standardized exception matching the response's status code."""
        status = response.status_code
        try:
            body = response.json()
            message = body.get("message", response.text)
        except ValueError:
            message = response.text

        if status == 401:
            raise GitHubAuthenticationError(f"GitHub authentication failed (HTTP 401): {message}")
        if status == 403:
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                raise GitHubRateLimitError(f"GitHub rate limit exceeded: {message}")
            raise GitHubForbiddenError(f"GitHub access forbidden (HTTP 403): {message}")
        if status == 404:
            raise GitHubNotFoundError(f"GitHub repository or resource not found (HTTP 404): {message}")
        if status == 429:
            raise GitHubRateLimitError(f"GitHub rate limit exceeded (HTTP 429): {message}")
        raise GitHubError(f"GitHub request failed (HTTP {status}): {message}")
