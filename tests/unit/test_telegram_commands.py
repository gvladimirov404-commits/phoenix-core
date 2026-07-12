"""Unit tests for phoenix_core.telegram.commands handlers.

All external services (GitHubClient, AIRouter, PluginRegistry, PhoenixApplication,
ConversationManager) are mocked or lightweight test doubles — no real HTTP
requests are made.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

from phoenix_core._version import __version__ as PHOENIX_VERSION
from phoenix_core.ai.router import AIRouter
from phoenix_core.core.container import Container
from phoenix_core.guard.cost_guard import CostGuard
from phoenix_core.guard.guard import AIGuard
from phoenix_core.guard.rate_limiter import RateLimiter
from phoenix_core.guard.retry import RetryPolicy
from phoenix_core.guard.sanitizer import OutputSanitizer
from phoenix_core.memory.context_builder import ContextBuilder
from phoenix_core.memory.manager import ConversationManager
from phoenix_core.telegram import commands
from phoenix_core.telegram.context import CommandContext
from phoenix_core.telegram.dispatcher import CommandDispatcher
from phoenix_core.utils.exceptions import (
    GitHubAuthenticationError,
    GitHubNotFoundError,
    GitHubRateLimitError,
)

from .conftest import MockAIProvider


def make_context(user_id: int = 1, chat_id: int = 1) -> CommandContext:
    return CommandContext(user_id=user_id, chat_id=chat_id)


def make_guard(max_requests=10, window=60, max_prompt=4000, max_context=12000, max_retries=2) -> AIGuard:
    return AIGuard(
        rate_limiter=RateLimiter(max_requests=max_requests, window_seconds=window),
        cost_guard=CostGuard(max_prompt_chars=max_prompt, max_context_chars=max_context),
        retry_policy=RetryPolicy(max_retries=max_retries),
        sanitizer=OutputSanitizer(),
    )


class TestVersionCommand:
    async def test_reports_version_from_version_module_only(self) -> None:
        container = Container()
        result = await commands.cmd_version([], make_context(), container)
        assert PHOENIX_VERSION in result


class TestStartCommand:
    async def test_includes_version_and_help_pointer(self) -> None:
        container = Container()
        result = await commands.cmd_start([], make_context(), container)
        assert PHOENIX_VERSION in result
        assert "/help" in result


class TestHelpCommand:
    async def test_lists_all_registered_commands(self) -> None:
        container = Container()
        dispatcher = CommandDispatcher()
        dispatcher.register("start", commands.cmd_start, "Greeting")
        dispatcher.register("version", commands.cmd_version, "Version info")
        container.register("command_dispatcher", dispatcher)

        result = await commands.cmd_help([], make_context(), container)

        assert "/start" in result
        assert "/version" in result

    async def test_missing_dispatcher_shows_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_help([], make_context(), container)
        assert "не е наличен" in result


class TestStatusCommand:
    async def test_missing_application_shows_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_status([], make_context(), container)
        assert "не е наличен" in result

    async def test_reports_components_and_overall_status(self) -> None:
        container = Container()
        fake_app = SimpleNamespace(
            health_check=AsyncMock(
                return_value={
                    "status": "healthy",
                    "components": {
                        "AIRouter": {"status": "healthy"},
                        "GitHubClient": {"status": "configured"},
                        "ConversationManager": {"status": "healthy"},
                        "AIGuard": {"status": "healthy"},
                    },
                }
            )
        )
        container.register("application", fake_app)

        result = await commands.cmd_status([], make_context(), container)

        assert "AI слой" in result
        assert "GitHub" in result
        assert "Памет на разговора" in result
        assert "AI Guard Layer" in result
        assert "healthy" in result


class TestHealthCommand:
    async def test_missing_application_shows_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_health([], make_context(), container)
        assert "не е наличен" in result

    async def test_reports_overall_status(self) -> None:
        container = Container()
        fake_app = SimpleNamespace(
            health_check=AsyncMock(return_value={"status": "unhealthy", "components": {}})
        )
        container.register("application", fake_app)

        result = await commands.cmd_health([], make_context(), container)

        assert "unhealthy" in result


class TestRepoCommand:
    async def test_missing_client_shows_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_repo([], make_context(), container)
        assert "не е конфигуриран" in result

    async def test_formats_repository_info(self) -> None:
        container = Container()
        fake_client = SimpleNamespace(
            get_repository=AsyncMock(
                return_value={
                    "name": "phoenix-core",
                    "owner": {"login": "octocat"},
                    "default_branch": "main",
                    "private": False,
                    "stargazers_count": 42,
                    "forks_count": 7,
                    "open_issues_count": 3,
                }
            )
        )
        container.register("github_client", fake_client)

        result = await commands.cmd_repo([], make_context(), container)

        assert "phoenix-core" in result
        assert "octocat" in result
        assert "main" in result
        assert "42" in result
        assert "7" in result
        assert "3" in result

    async def test_authentication_error_shows_friendly_message(self) -> None:
        container = Container()
        fake_client = SimpleNamespace(
            get_repository=AsyncMock(side_effect=GitHubAuthenticationError("bad token"))
        )
        container.register("github_client", fake_client)

        result = await commands.cmd_repo([], make_context(), container)

        assert "автентикацията" in result
        assert "bad token" not in result

    async def test_not_found_shows_friendly_message(self) -> None:
        container = Container()
        fake_client = SimpleNamespace(
            get_repository=AsyncMock(side_effect=GitHubNotFoundError("nope"))
        )
        container.register("github_client", fake_client)

        result = await commands.cmd_repo([], make_context(), container)

        assert "не е намерено" in result


class TestIssuesCommand:
    async def test_missing_client_shows_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_issues([], make_context(), container)
        assert "не е конфигуриран" in result

    async def test_formats_issue_list(self) -> None:
        container = Container()
        fake_client = SimpleNamespace(
            list_issues=AsyncMock(
                return_value=[
                    {"number": 1, "title": "Bug A", "state": "open", "user": {"login": "alice"}},
                    {"number": 2, "title": "Bug B", "state": "open", "user": {"login": "bob"}},
                ]
            )
        )
        container.register("github_client", fake_client)

        result = await commands.cmd_issues([], make_context(), container)

        assert "#1 Bug A" in result
        assert "@alice" in result
        assert "#2 Bug B" in result
        assert "@bob" in result

    async def test_empty_issue_list_shows_friendly_message(self) -> None:
        container = Container()
        fake_client = SimpleNamespace(list_issues=AsyncMock(return_value=[]))
        container.register("github_client", fake_client)

        result = await commands.cmd_issues([], make_context(), container)

        assert "Няма отворени issues" in result

    async def test_rate_limit_shows_friendly_message(self) -> None:
        container = Container()
        fake_client = SimpleNamespace(
            list_issues=AsyncMock(side_effect=GitHubRateLimitError("boom"))
        )
        container.register("github_client", fake_client)

        result = await commands.cmd_issues([], make_context(), container)

        assert "rate limit" in result


class TestPluginsCommand:
    async def test_missing_registry_shows_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_plugins([], make_context(), container)
        assert "не е наличен" in result

    async def test_stub_registry_shows_health_detail(self) -> None:
        container = Container()

        def raise_not_implemented():
            raise NotImplementedError("stub")

        fake_registry = SimpleNamespace(
            list_plugins=raise_not_implemented,
            health_check=AsyncMock(return_value={"status": "unknown", "detail": "V1 stub"}),
        )
        container.register("plugin_registry", fake_registry)

        result = await commands.cmd_plugins([], make_context(), container)

        assert "unknown" in result
        assert "V1 stub" in result


class TestAiCommand:
    async def test_missing_router_shows_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_ai([], make_context(), container)
        assert "не е наличен" in result

    async def test_lists_configured_provider_with_default_marker(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        router.register_provider("mock", MockAIProvider())
        container = Container()
        container.register("ai_router", router)

        result = await commands.cmd_ai([], make_context(), container)

        assert "mock: configured" in result
        assert "по подразбиране" in result

    async def test_no_providers_shows_friendly_message(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        container = Container()
        container.register("ai_router", router)

        result = await commands.cmd_ai([], make_context(), container)

        assert "Няма конфигуриран AI provider" in result


class TestFormatAiResponse:
    def test_wraps_content_with_header_and_provider_footer(self) -> None:
        from phoenix_core.ai.base import AIResponse

        response = AIResponse(content="42 е отговорът.", provider="deepseek", model="deepseek-chat")

        result = commands._format_ai_response(response)

        assert result.startswith("🤖 Phoenix AI\n\n")
        assert "42 е отговорът." in result
        assert result.endswith("Provider: deepseek")


class TestAskCommand:
    async def test_empty_ask_returns_helpful_message(self) -> None:
        container = Container()
        result = await commands.cmd_ask([], make_context(), container)
        assert "въпрос" in result

    async def test_successful_ask_returns_formatted_ai_response(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        router.register_provider("mock", MockAIProvider(response_content="Python е готин."))
        container = Container()
        container.register("ai_router", router)

        result = await commands.cmd_ask(["Какво", "е", "Python?"], make_context(), container)

        assert "🤖 Phoenix AI" in result
        assert "Python е готин." in result
        assert "Provider: mock" in result

    async def test_missing_ai_router_shows_unavailable_message(self) -> None:
        container = Container()
        result = await commands.cmd_ask(["hi"], make_context(), container)
        assert "не е наличен" in result

    async def test_prompt_over_configured_limit_is_rejected(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        provider = MockAIProvider()
        router.register_provider("mock", provider)
        container = Container()
        container.register("ai_router", router)
        container.register("settings", SimpleNamespace(ai_max_prompt_length=10))

        result = await commands.cmd_ask(["a", "much", "too", "long", "question", "here"], make_context(), container)

        assert "твърде дълга" in result
        assert provider.calls == []  # the provider must never be called

    async def test_prompt_within_default_limit_when_settings_missing(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        router.register_provider("mock", MockAIProvider(response_content="ok"))
        container = Container()
        container.register("ai_router", router)
        # No "settings" registered — falls back to the default limit, request still succeeds.

        result = await commands.cmd_ask(["hi"], make_context(), container)

        assert "ok" in result

    async def test_works_without_conversation_manager_registered(self) -> None:
        """Graceful degradation: /ask still works if Memory isn't wired up."""
        router = AIRouter(providers=[], default_provider="mock")
        router.register_provider("mock", MockAIProvider(response_content="ok"))
        container = Container()
        container.register("ai_router", router)

        result = await commands.cmd_ask(["hi"], make_context(), container)

        assert "ok" in result

    async def test_second_ask_includes_prior_turn_in_ai_request(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        provider = MockAIProvider(response_content="втори отговор")
        router.register_provider("mock", provider)
        container = Container()
        container.register("ai_router", router)
        container.register("conversation_manager", ConversationManager(max_messages=20))
        container.register("context_builder", ContextBuilder(max_context_chars=8000))
        ctx = make_context(user_id=7)

        await commands.cmd_ask(["първи", "въпрос"], ctx, container)
        await commands.cmd_ask(["втори", "въпрос"], ctx, container)

        second_call_messages = provider.calls[-1]["messages"]
        assert len(second_call_messages) == 3  # user1, assistant1, user2
        assert second_call_messages[0]["content"] == "първи въпрос"
        assert second_call_messages[1]["role"] == "assistant"
        assert second_call_messages[2]["content"] == "втори въпрос"

    async def test_different_users_get_independent_conversations(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        provider = MockAIProvider(response_content="ok")
        router.register_provider("mock", provider)
        container = Container()
        container.register("ai_router", router)
        manager = ConversationManager(max_messages=20)
        container.register("conversation_manager", manager)
        container.register("context_builder", ContextBuilder(max_context_chars=8000))

        await commands.cmd_ask(["hi", "from", "alice"], make_context(user_id=1), container)
        await commands.cmd_ask(["hi", "from", "bob"], make_context(user_id=2), container)

        assert manager.get_stats(1)["message_count"] == 2
        assert manager.get_stats(2)["message_count"] == 2
        assert manager.active_conversations == 2


class TestResetCommand:
    async def test_missing_conversation_manager_shows_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_reset([], make_context(), container)
        assert "не е налична" in result

    async def test_reset_existing_conversation(self) -> None:
        manager = ConversationManager(max_messages=20)
        manager.add_message(1, "user", "hi")
        container = Container()
        container.register("conversation_manager", manager)

        result = await commands.cmd_reset([], make_context(user_id=1), container)

        assert "изтрит" in result
        assert manager.get_stats(1) is None

    async def test_reset_with_no_existing_conversation(self) -> None:
        manager = ConversationManager(max_messages=20)
        container = Container()
        container.register("conversation_manager", manager)

        result = await commands.cmd_reset([], make_context(user_id=1), container)

        assert "Нямаше активен разговор" in result


class TestMemoryCommand:
    async def test_missing_conversation_manager_shows_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_memory([], make_context(), container)
        assert "не е налична" in result

    async def test_no_conversation_shows_empty_message(self) -> None:
        manager = ConversationManager(max_messages=20)
        container = Container()
        container.register("conversation_manager", manager)

        result = await commands.cmd_memory([], make_context(user_id=1), container)

        assert "Няма активен разговор" in result

    async def test_shows_stats_without_leaking_content(self) -> None:
        manager = ConversationManager(max_messages=20)
        manager.add_message(1, "user", "тайно съобщение")
        manager.add_message(1, "assistant", "друго тайно съобщение")
        container = Container()
        container.register("conversation_manager", manager)

        result = await commands.cmd_memory([], make_context(user_id=1), container)

        assert "Съобщения: 2" in result
        assert "тайно съобщение" not in result


class TestAskCommandWithGuard:
    """Task 011: AI Guard Layer integration with cmd_ask."""

    async def test_works_without_guard_registered(self) -> None:
        """Graceful degradation: /ask still works if the Guard Layer isn't wired up."""
        router = AIRouter(providers=[], default_provider="mock")
        router.register_provider("mock", MockAIProvider(response_content="ok"))
        container = Container()
        container.register("ai_router", router)

        result = await commands.cmd_ask(["hi"], make_context(), container)

        assert "ok" in result

    async def test_rate_limit_blocks_request_without_calling_provider(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        provider = MockAIProvider(response_content="ok")
        router.register_provider("mock", provider)
        container = Container()
        container.register("ai_router", router)
        container.register("ai_guard", make_guard(max_requests=1))

        await commands.cmd_ask(["first"], make_context(user_id=1), container)
        result = await commands.cmd_ask(["second"], make_context(user_id=1), container)

        assert "Твърде много заявки" in result
        assert len(provider.calls) == 1  # second request never reached the provider

    async def test_rate_limit_is_per_user(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        provider = MockAIProvider(response_content="ok")
        router.register_provider("mock", provider)
        container = Container()
        container.register("ai_router", router)
        container.register("ai_guard", make_guard(max_requests=1))

        result_a = await commands.cmd_ask(["hi"], make_context(user_id=1), container)
        result_b = await commands.cmd_ask(["hi"], make_context(user_id=2), container)

        assert "ok" in result_a
        assert "ok" in result_b

    async def test_oversized_context_rejected_without_calling_provider(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        provider = MockAIProvider(response_content="ok")
        router.register_provider("mock", provider)
        container = Container()
        container.register("ai_router", router)
        container.register("ai_guard", make_guard(max_prompt=100000, max_context=5))

        result = await commands.cmd_ask(["hello", "world"], make_context(), container)

        assert "твърде голям" in result
        assert provider.calls == []

    async def test_successful_ask_through_guard_is_sanitized_and_formatted(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        router.register_provider("mock", MockAIProvider(response_content="балансиран *отговор"))
        container = Container()
        container.register("ai_router", router)
        container.register("ai_guard", make_guard())

        result = await commands.cmd_ask(["hi"], make_context(), container)

        assert "🤖 Phoenix AI" in result
        assert result.count("*") % 2 == 0  # unbalanced token from the AI closed by the sanitizer
        assert "Provider: mock" in result

    async def test_guard_retries_transient_provider_errors(self, monkeypatch) -> None:
        async def fake_sleep(seconds):
            return None
        monkeypatch.setattr("phoenix_core.guard.retry.asyncio.sleep", fake_sleep)

        from phoenix_core.utils.exceptions import AIProviderTimeoutError

        router = AIRouter(providers=[], default_provider="mock")
        provider = MockAIProvider(response_content="ok")
        original_chat = provider.chat
        state = {"count": 0}

        async def flaky_chat(*args, **kwargs):
            state["count"] += 1
            if state["count"] < 2:
                raise AIProviderTimeoutError("timeout")
            return await original_chat(*args, **kwargs)

        provider.chat = flaky_chat
        router.register_provider("mock", provider)
        container = Container()
        container.register("ai_router", router)
        container.register("ai_guard", make_guard(max_retries=2))

        result = await commands.cmd_ask(["hi"], make_context(), container)

        assert "ok" in result
        assert state["count"] == 2

    async def test_guard_gives_up_after_exhausting_retries(self, monkeypatch) -> None:
        async def fake_sleep(seconds):
            return None
        monkeypatch.setattr("phoenix_core.guard.retry.asyncio.sleep", fake_sleep)

        from phoenix_core.utils.exceptions import AIProviderTimeoutError

        router = AIRouter(providers=[], default_provider="mock")
        provider = MockAIProvider()

        async def always_times_out(*args, **kwargs):
            raise AIProviderTimeoutError("timeout")

        provider.chat = always_times_out
        router.register_provider("mock", provider)
        container = Container()
        container.register("ai_router", router)
        container.register("ai_guard", make_guard(max_retries=1))

        result = await commands.cmd_ask(["hi"], make_context(), container)

        assert "твърде дълго време" in result


class TestOutputSanitizationWithoutGuard:
    """Task 011: sanitization must still run even if no AIGuard is registered."""

    async def test_response_is_sanitized_even_without_guard(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        router.register_provider("mock", MockAIProvider(response_content="незатворено *bold"))
        container = Container()
        container.register("ai_router", router)

        result = await commands.cmd_ask(["hi"], make_context(), container)

        assert result.count("*") % 2 == 0

