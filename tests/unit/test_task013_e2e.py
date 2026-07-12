"""
Task 013 — Full End-to-End Audit.

Two things are validated here, both via the real CommandDispatcher (not by
calling cmd_* handlers directly) so the actual chain is exercised:

    Telegram (CommandContext) -> CommandDispatcher -> ConversationManager
    -> ConversationStore (SQLite) -> AI Guard -> AIRouter -> AI Provider
    -> response text

1. TestFullCommandSet — every command from Задача 4 (/start /help /ask
   /memory /reset /health /status /repo /issues) works end-to-end with a
   fully wired container (mock AI provider, fake GitHub client, real
   SQLite-backed ConversationManager, real AIGuard).
2. TestErrorScenarios — every scenario from Задача 5, confirming the
   system degrades to a friendly message instead of raising.

No real network calls anywhere (MockAIProvider, FakeGitHubClient).
"""
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

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
    AIProviderTimeoutError,
    GitHubAuthenticationError,
)

from .conftest import MockAIProvider

pytestmark = pytest.mark.integration


class FakeGitHubClient:
    """Mock GitHub client — no network calls. Mirrors GitHubClient's public surface."""

    def __init__(self, should_fail: Exception = None) -> None:
        self._should_fail = should_fail

    async def get_repository(self) -> Dict[str, Any]:
        if self._should_fail:
            raise self._should_fail
        return {
            "name": "phoenix-core",
            "owner": {"login": "octocat"},
            "default_branch": "main",
            "private": False,
            "stargazers_count": 1,
            "forks_count": 0,
            "open_issues_count": 2,
        }

    async def list_issues(self, state: str = "open", per_page: int = 5, page: int = 1) -> List[Dict[str, Any]]:
        if self._should_fail:
            raise self._should_fail
        return [{"number": 1, "title": "Sample issue", "state": "open", "user": {"login": "octocat"}}]

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "configured"}


class FakeApplication:
    """Mock PhoenixApplication — aggregates health_check() from a fixed component set,
    exactly like the real PhoenixApplication.health_check() does from self._components."""

    def __init__(self, components: Dict[str, Any]) -> None:
        self._components = components

    async def health_check(self) -> Dict[str, Any]:
        health = {"status": "healthy", "components": {}}
        for name, component in self._components.items():
            if hasattr(component, "health_check"):
                health["components"][name] = await component.health_check()
        return health


def build_full_dispatcher() -> CommandDispatcher:
    """Register every V1+Task010+Task011 command, exactly like TelegramBot._register_commands."""
    dispatcher = CommandDispatcher()
    dispatcher.register("start", commands.cmd_start, "start")
    dispatcher.register("help", commands.cmd_help, "help")
    dispatcher.register("version", commands.cmd_version, "version")
    dispatcher.register("status", commands.cmd_status, "status")
    dispatcher.register("health", commands.cmd_health, "health")
    dispatcher.register("repo", commands.cmd_repo, "repo")
    dispatcher.register("issues", commands.cmd_issues, "issues")
    dispatcher.register("plugins", commands.cmd_plugins, "plugins")
    dispatcher.register("ai", commands.cmd_ai, "ai")
    dispatcher.register("ask", commands.cmd_ask, "ask")
    dispatcher.register("reset", commands.cmd_reset, "reset")
    dispatcher.register("memory", commands.cmd_memory, "memory")
    return dispatcher


def build_full_container(tmp_path, ai_response: str = "Здравей от Phoenix.") -> Container:
    """A fully wired container — the same set of services PhoenixApplication registers."""
    container = Container()
    container.register("settings", SimpleNamespace(ai_max_prompt_length=4000))

    router = AIRouter(providers=[], default_provider="mock")
    router.register_provider("mock", MockAIProvider(response_content=ai_response))
    container.register("ai_router", router)

    conversation_manager = ConversationManager(max_messages=20, db_path=str(tmp_path / "e2e.db"))
    container.register("conversation_manager", conversation_manager)
    container.register("context_builder", ContextBuilder(max_context_chars=8000))

    ai_guard = AIGuard(
        rate_limiter=RateLimiter(max_requests=10, window_seconds=60),
        cost_guard=CostGuard(max_prompt_chars=4000, max_context_chars=12000),
        retry_policy=RetryPolicy(max_retries=2),
        sanitizer=OutputSanitizer(),
    )
    container.register("ai_guard", ai_guard)

    github_client = FakeGitHubClient()
    container.register("github_client", github_client)

    dispatcher = build_full_dispatcher()
    container.register("command_dispatcher", dispatcher)

    application = FakeApplication({
        "AIRouter": router,
        "ConversationManager": conversation_manager,
        "AIGuard": ai_guard,
        "GitHubClient": github_client,
    })
    container.register("application", application)

    return container


class TestFullCommandSet:
    """Task 013, Задача 4 — every listed command, end-to-end, through the real dispatcher."""

    async def test_start(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        dispatcher = container.resolve("command_dispatcher")
        result = await dispatcher.dispatch(
            "start", [], CommandContext(user_id=1, chat_id=1), container
        )
        assert "Phoenix Core" in result

    async def test_help_lists_registered_commands(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        dispatcher = container.resolve("command_dispatcher")
        result = await dispatcher.dispatch("help", [], CommandContext(user_id=1, chat_id=1), container)
        assert "/ask" in result
        assert "/reset" in result
        assert "/memory" in result

    async def test_ask(self, tmp_path) -> None:
        container = build_full_container(tmp_path, ai_response="Тест отговор.")
        dispatcher = container.resolve("command_dispatcher")
        result = await dispatcher.dispatch(
            "ask", ["Какво", "е", "Phoenix?"], CommandContext(user_id=1, chat_id=1), container
        )
        assert "Тест отговор." in result
        assert "🤖 Phoenix AI" in result

    async def test_memory_after_ask(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        dispatcher = container.resolve("command_dispatcher")
        context = CommandContext(user_id=1, chat_id=1)
        await dispatcher.dispatch("ask", ["hi"], context, container)

        result = await dispatcher.dispatch("memory", [], context, container)
        assert "Съобщения: 2" in result

    async def test_reset(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        dispatcher = container.resolve("command_dispatcher")
        context = CommandContext(user_id=1, chat_id=1)
        await dispatcher.dispatch("ask", ["hi"], context, container)

        result = await dispatcher.dispatch("reset", [], context, container)
        assert "изтрит" in result

        stats_after = await dispatcher.dispatch("memory", [], context, container)
        assert "Няма активен разговор" in stats_after

    async def test_health(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        dispatcher = container.resolve("command_dispatcher")
        result = await dispatcher.dispatch("health", [], CommandContext(user_id=1, chat_id=1), container)
        assert "healthy" in result

    async def test_status(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        dispatcher = container.resolve("command_dispatcher")
        result = await dispatcher.dispatch("status", [], CommandContext(user_id=1, chat_id=1), container)
        assert "AI слой" in result
        assert "Памет на разговора" in result
        assert "AI Guard Layer" in result
        assert "GitHub" in result

    async def test_repo(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        dispatcher = container.resolve("command_dispatcher")
        result = await dispatcher.dispatch("repo", [], CommandContext(user_id=1, chat_id=1), container)
        assert "phoenix-core" in result
        assert "octocat" in result

    async def test_issues(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        dispatcher = container.resolve("command_dispatcher")
        result = await dispatcher.dispatch("issues", [], CommandContext(user_id=1, chat_id=1), container)
        assert "Sample issue" in result


class TestRestartValidation:
    """Task 013, Задача 3 — restart, conversation persistence, and health_check after restart."""

    async def test_health_check_reflects_persisted_state_after_restart(self, tmp_path) -> None:
        db_path = str(tmp_path / "restart_validation.db")

        # --- session 1 ---
        container_1 = build_full_container(tmp_path, ai_response="сесия 1")
        # override with the shared db_path so both "sessions" use the same file
        manager_1 = ConversationManager(max_messages=20, db_path=db_path)
        container_1.register("conversation_manager", manager_1)
        dispatcher_1 = container_1.resolve("command_dispatcher")
        context = CommandContext(user_id=1, chat_id=1)
        await dispatcher_1.dispatch("ask", ["преди", "рестарт"], context, container_1)
        await manager_1.stop()

        # --- simulated restart: brand new manager, same db file ---
        manager_2 = ConversationManager(max_messages=20, db_path=db_path)
        container_2 = build_full_container(tmp_path, ai_response="сесия 2")
        container_2.register("conversation_manager", manager_2)
        dispatcher_2 = container_2.resolve("command_dispatcher")

        # health_check must reflect what was persisted before the restart,
        # without any new /ask being made yet in this session.
        result = await dispatcher_2.dispatch("status", [], context, container_2)
        assert "Памет на разговора" in result

        memory_result = await dispatcher_2.dispatch("memory", [], context, container_2)
        assert "Съобщения: 2" in memory_result  # user + assistant from session 1

    async def test_conversation_continues_seamlessly_after_restart(self, tmp_path) -> None:
        db_path = str(tmp_path / "restart_continue.db")
        context = CommandContext(user_id=1, chat_id=1)

        container_1 = build_full_container(tmp_path)
        manager_1 = ConversationManager(max_messages=20, db_path=db_path)
        container_1.register("conversation_manager", manager_1)
        await container_1.resolve("command_dispatcher").dispatch(
            "ask", ["първо", "съобщение"], context, container_1
        )
        await manager_1.stop()

        container_2 = build_full_container(tmp_path)
        manager_2 = ConversationManager(max_messages=20, db_path=db_path)
        container_2.register("conversation_manager", manager_2)
        router_2 = container_2.resolve("ai_router")
        provider_2 = router_2.get_provider("mock")
        await container_2.resolve("command_dispatcher").dispatch(
            "ask", ["второ", "съобщение"], context, container_2
        )

        # The AI request after "restart" should carry forward history from before it.
        last_messages = provider_2.calls[-1]["messages"]
        assert any(m["content"] == "първо съобщение" for m in last_messages)


class TestErrorScenarios:
    """Task 013, Задача 5 — every scenario must degrade to a friendly message, never raise."""

    async def test_missing_ai_provider(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        container.register("ai_router", AIRouter(providers=[], default_provider="mock"))  # no provider registered
        dispatcher = container.resolve("command_dispatcher")

        result = await dispatcher.dispatch("ask", ["hi"], CommandContext(user_id=1, chat_id=1), container)

        assert "⚠️" in result or "не е" in result.lower()

    async def test_missing_github_token(self, tmp_path) -> None:
        wired_container = build_full_container(tmp_path)
        dispatcher = wired_container.resolve("command_dispatcher")

        # Simulates PhoenixApplication never registering github_client because
        # PHOENIX_GITHUB_TOKEN was empty — a fresh container with no github_client.
        container = Container()
        container.register("settings", SimpleNamespace(ai_max_prompt_length=4000))

        result = await dispatcher.dispatch("repo", [], CommandContext(user_id=1, chat_id=1), container)

        assert "не е конфигуриран" in result

    async def test_github_authentication_failure(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        container.register("github_client", FakeGitHubClient(should_fail=GitHubAuthenticationError("bad token")))
        dispatcher = container.resolve("command_dispatcher")

        result = await dispatcher.dispatch("repo", [], CommandContext(user_id=1, chat_id=1), container)

        assert "автентикацията" in result
        assert "bad token" not in result  # no internal detail leaked

    async def test_empty_conversation(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        dispatcher = container.resolve("command_dispatcher")

        result = await dispatcher.dispatch("memory", [], CommandContext(user_id=999, chat_id=999), container)

        assert "Няма активен разговор" in result

    async def test_oversized_prompt(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        container.register("settings", SimpleNamespace(ai_max_prompt_length=10))
        dispatcher = container.resolve("command_dispatcher")

        result = await dispatcher.dispatch(
            "ask", ["this", "is", "way", "too", "long", "for", "the", "limit"],
            CommandContext(user_id=1, chat_id=1), container,
        )

        assert "твърде дълга" in result

    async def test_rate_limit(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        container.register(
            "ai_guard",
            AIGuard(
                rate_limiter=RateLimiter(max_requests=1, window_seconds=60),
                cost_guard=CostGuard(max_prompt_chars=4000, max_context_chars=12000),
                retry_policy=RetryPolicy(max_retries=1),
                sanitizer=OutputSanitizer(),
            ),
        )
        dispatcher = container.resolve("command_dispatcher")
        context = CommandContext(user_id=1, chat_id=1)

        await dispatcher.dispatch("ask", ["first"], context, container)
        result = await dispatcher.dispatch("ask", ["second"], context, container)

        assert "Твърде много заявки" in result

    async def test_retry_exhausted(self, tmp_path, monkeypatch) -> None:
        async def fake_sleep(seconds):
            return None
        monkeypatch.setattr("phoenix_core.guard.retry.asyncio.sleep", fake_sleep)

        container = build_full_container(tmp_path)
        router = AIRouter(providers=[], default_provider="mock")
        provider = MockAIProvider()

        async def always_times_out(*args, **kwargs):
            raise AIProviderTimeoutError("timeout")

        provider.chat = always_times_out
        router.register_provider("mock", provider)
        container.register("ai_router", router)
        dispatcher = container.resolve("command_dispatcher")

        result = await dispatcher.dispatch("ask", ["hi"], CommandContext(user_id=1, chat_id=1), container)

        assert "твърде дълго време" in result

    async def test_unknown_command_never_raises(self, tmp_path) -> None:
        container = build_full_container(tmp_path)
        dispatcher = container.resolve("command_dispatcher")

        result = await dispatcher.dispatch(
            "not_a_real_command", [], CommandContext(user_id=1, chat_id=1), container
        )

        assert "Непозната команда" in result
