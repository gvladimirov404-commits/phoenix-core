"""Unit tests for phoenix_core.github.client.GitHubClient.

All HTTP calls are mocked — no real network requests are made.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from phoenix_core.github.client import GitHubClient
from phoenix_core.utils.exceptions import (
    GitHubAuthenticationError,
    GitHubConfigurationError,
    GitHubConnectionError,
    GitHubForbiddenError,
    GitHubInvalidResponseError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubTimeoutError,
)


def make_settings(owner: str = "octocat", repo: str = "hello-world") -> SimpleNamespace:
    return SimpleNamespace(owner=owner, repo=repo)


def make_client(token: str = "gh-token", owner: str = "octocat", repo: str = "hello-world") -> GitHubClient:
    return GitHubClient(token=token, settings=make_settings(owner=owner, repo=repo))


def fake_response(status_code: int, json_data, headers=None) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    response.text = str(json_data)
    response.headers = headers or {}
    return response


class TestRepositoryAccessSuccess:
    async def test_check_repository_access_returns_true(self, monkeypatch) -> None:
        client = make_client()
        response = fake_response(200, {"full_name": "octocat/hello-world"})
        monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(return_value=response))

        result = await client.check_repository_access()

        assert result is True

    async def test_get_repository_returns_parsed_json(self, monkeypatch) -> None:
        client = make_client()
        response = fake_response(200, {"full_name": "octocat/hello-world", "private": False})
        monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(return_value=response))

        result = await client.get_repository()

        assert result["full_name"] == "octocat/hello-world"

    async def test_get_current_user_returns_parsed_json(self, monkeypatch) -> None:
        client = make_client()
        response = fake_response(200, {"login": "octocat"})
        monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(return_value=response))

        result = await client.get_current_user()

        assert result["login"] == "octocat"


class TestConfigurationErrors:
    async def test_missing_token_raises_configuration_error(self) -> None:
        client = make_client(token="")
        with pytest.raises(GitHubConfigurationError):
            await client.check_repository_access()

    async def test_missing_owner_raises_configuration_error(self) -> None:
        client = make_client(owner="")
        with pytest.raises(GitHubConfigurationError):
            await client.check_repository_access()

    async def test_missing_repo_raises_configuration_error(self) -> None:
        client = make_client(repo="")
        with pytest.raises(GitHubConfigurationError):
            await client.check_repository_access()


class TestHttpErrors:
    async def test_401_raises_authentication_error(self, monkeypatch) -> None:
        client = make_client()
        response = fake_response(401, {"message": "Bad credentials"})
        monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(return_value=response))
        with pytest.raises(GitHubAuthenticationError):
            await client.check_repository_access()

    async def test_403_without_rate_limit_headers_raises_forbidden_error(self, monkeypatch) -> None:
        client = make_client()
        response = fake_response(403, {"message": "Forbidden"}, headers={})
        monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(return_value=response))
        with pytest.raises(GitHubForbiddenError):
            await client.check_repository_access()

    async def test_403_with_exhausted_rate_limit_raises_rate_limit_error(self, monkeypatch) -> None:
        client = make_client()
        response = fake_response(
            403,
            {"message": "API rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0"},
        )
        monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(return_value=response))
        with pytest.raises(GitHubRateLimitError):
            await client.check_repository_access()

    async def test_404_raises_not_found_error(self, monkeypatch) -> None:
        client = make_client()
        response = fake_response(404, {"message": "Not Found"})
        monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(return_value=response))
        with pytest.raises(GitHubNotFoundError):
            await client.get_repository()

    async def test_429_raises_rate_limit_error(self, monkeypatch) -> None:
        client = make_client()
        response = fake_response(429, {"message": "Too Many Requests"})
        monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(return_value=response))
        with pytest.raises(GitHubRateLimitError):
            await client.get_repository()

    async def test_timeout_raises_timeout_error(self, monkeypatch) -> None:
        client = make_client()
        monkeypatch.setattr(
            httpx.AsyncClient,
            "request",
            AsyncMock(side_effect=httpx.TimeoutException("timed out")),
        )
        with pytest.raises(GitHubTimeoutError):
            await client.get_repository()

    async def test_connection_error_raises_connection_error(self, monkeypatch) -> None:
        client = make_client()
        monkeypatch.setattr(
            httpx.AsyncClient,
            "request",
            AsyncMock(side_effect=httpx.ConnectError("connection failed")),
        )
        with pytest.raises(GitHubConnectionError):
            await client.get_repository()

    async def test_malformed_response_raises_invalid_response_error(self, monkeypatch) -> None:
        client = make_client()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.json.side_effect = ValueError("not json")
        response.text = "not json"
        response.headers = {}
        monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(return_value=response))
        with pytest.raises(GitHubInvalidResponseError):
            await client.get_repository()


class TestIssues:
    async def test_create_issue_success(self, monkeypatch) -> None:
        client = make_client()
        response = fake_response(201, {"number": 1, "title": "Bug report"})
        mock_request = AsyncMock(return_value=response)
        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        result = await client.create_issue(title="Bug report", body="Details", labels=["bug"])

        assert result["number"] == 1
        _, kwargs = mock_request.call_args
        assert kwargs["json"]["title"] == "Bug report"
        assert kwargs["json"]["labels"] == ["bug"]

    async def test_list_issues_success(self, monkeypatch) -> None:
        client = make_client()
        response = fake_response(200, [{"number": 1}, {"number": 2}])
        monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(return_value=response))

        result = await client.list_issues(state="open")

        assert len(result) == 2


class TestHealthCheck:
    async def test_health_check_is_local_only_and_configured(self, monkeypatch) -> None:
        client = make_client()
        mock_request = AsyncMock()
        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        result = await client.health_check()

        assert result["status"] == "configured"
        assert result["owner"] == "octocat"
        assert result["issues"] == []
        mock_request.assert_not_called()

    async def test_health_check_reports_missing_token(self) -> None:
        client = make_client(token="")
        result = await client.health_check()
        assert result["status"] == "misconfigured"
        assert "token is not set" in result["issues"]
