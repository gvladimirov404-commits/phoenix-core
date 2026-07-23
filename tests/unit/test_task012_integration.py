"""
Integration test for Task 012: Telegram -> CommandDispatcher -> ConversationManager
(SQLite-backed) -> AIRouter (mock provider) -> response, then verifies the
conversation actually persisted to disk and survives a simulated restart.

No real Telegram Update objects and no real HTTP calls — CommandContext
already stands in for "the Telegram layer" here, exactly as in
test_command_dispatcher.py and test_telegram_bot.py; MockAIProvider stands
in for a real AI provider (no network access).
"""
import pytest

from phoenix_core.ai.router import AIRouter
from phoenix_core.core.container import Container
from phoenix_core.memory.context_builder import ContextBuilder
from phoenix_core.memory.manager import ConversationManager
from phoenix_core.telegram import commands
from phoenix_core.telegram.context import CommandContext
from phoenix_core.telegram.dispatcher import CommandDispatcher

from .conftest import MockAIProvider

pytestmark = pytest.mark.integration


def build_dispatcher() -> CommandDispatcher:
    dispatcher = CommandDispatcher()
    dispatcher.register("ask", commands.cmd_ask, "Ask the AI")
    dispatcher.register("reset", commands.cmd_reset, "Reset conversation")
    dispatcher.register("memory", commands.cmd_memory, "Conversation stats")
    return dispatcher


class TestFullFlowThroughSQLite:
    async def test_ask_flows_through_dispatcher_into_sqlite_and_back(self, tmp_path) -> None:
        db_path = str(tmp_path / "integration.db")

        container = Container()
        router = AIRouter(providers=[], default_provider="mock")
        provider = MockAIProvider(response_content="Отговорът на Phoenix.")
        router.register_provider("mock", provider)
        container.register("ai_router", router)

        conversation_manager = ConversationManager(max_messages=20, db_path=db_path)
        try:
            container.register("conversation_manager", conversation_manager)
            container.register("context_builder", ContextBuilder(max_context_chars=8000))

            dispatcher = build_dispatcher()
            context = CommandContext(user_id=100, chat_id=100, command="ask")

            response_text = await dispatcher.dispatch("ask", ["Какво", "е", "Phoenix?"], context, container)

            assert "🤖 Phoenix AI" in response_text
            assert "Отговорът на Phoenix." in response_text
            assert len(provider.calls) == 1

            # Verify it actually landed in SQLite, not just in the in-process object.
            stats = conversation_manager.get_stats(100)
            assert stats["message_count"] == 2  # user question + assistant answer
        finally:
            await conversation_manager.stop()

    async def test_second_ask_in_same_flow_carries_history_from_sqlite(self, tmp_path) -> None:
        db_path = str(tmp_path / "integration_history.db")

        container = Container()
        router = AIRouter(providers=[], default_provider="mock")
        provider = MockAIProvider(response_content="втори отговор")
        router.register_provider("mock", provider)
        container.register("ai_router", router)

        conversation_manager = ConversationManager(max_messages=20, db_path=db_path)
        try:
            container.register("conversation_manager", conversation_manager)
            container.register("context_builder", ContextBuilder(max_context_chars=8000))

            dispatcher = build_dispatcher()
            context = CommandContext(user_id=200, chat_id=200, command="ask")

            await dispatcher.dispatch("ask", ["първи", "въпрос"], context, container)
            await dispatcher.dispatch("ask", ["втори", "въпрос"], context, container)

            second_call_messages = provider.calls[-1]["messages"]
            assert len(second_call_messages) == 3  # user1, assistant1, user2 — loaded back from SQLite
            assert second_call_messages[0]["content"] == "първи въпрос"
        finally:
            await conversation_manager.stop()

    async def test_reset_and_memory_commands_work_through_the_dispatcher(self, tmp_path) -> None:
        db_path = str(tmp_path / "integration_reset.db")

        container = Container()
        router = AIRouter(providers=[], default_provider="mock")
        router.register_provider("mock", MockAIProvider(response_content="ok"))
        container.register("ai_router", router)

        conversation_manager = ConversationManager(max_messages=20, db_path=db_path)
        try:
            container.register("conversation_manager", conversation_manager)
            container.register("context_builder", ContextBuilder(max_context_chars=8000))

            dispatcher = build_dispatcher()
            context = CommandContext(user_id=300, chat_id=300)

            await dispatcher.dispatch("ask", ["hi"], context, container)
            memory_text = await dispatcher.dispatch("memory", [], context, container)
            assert "Съобщения: 2" in memory_text
            reset_text = await dispatcher.dispatch("reset", [], context, container)
            assert "изтрит" in reset_text

            memory_after_reset = await dispatcher.dispatch("memory", [], context, container)
            assert "Няма активен разговор" in memory_after_reset
        finally:
            await conversation_manager.stop()

    async def test_conversation_survives_a_simulated_restart_mid_flow(self, tmp_path) -> None:
        """The exact Task 012 scenario: data must outlive the ConversationManager instance."""
        db_path = str(tmp_path / "integration_restart.db")

        # --- "session 1": app starts, user asks something, app stops ---
        container_1 = Container()
        router_1 = AIRouter(providers=[], default_provider="mock")
        router_1.register_provider("mock", MockAIProvider(response_content="сесия 1"))
        container_1.register("ai_router", router_1)
        manager_1 = ConversationManager(max_messages=20, db_path=db_path)
        container_1.register("conversation_manager", manager_1)
        container_1.register("context_builder", ContextBuilder(max_context_chars=8000))

        dispatcher_1 = build_dispatcher()
        context = CommandContext(user_id=400, chat_id=400)
        await dispatcher_1.dispatch("ask", ["преди", "рестарт"], context, container_1)
        await manager_1.stop()

        # --- "session 2": brand new app instance, same database file ---
        container_2 = Container()
        router_2 = AIRouter(providers=[], default_provider="mock")
        provider_2 = MockAIProvider(response_content="сесия 2")
        router_2.register_provider("mock", provider_2)
        container_2.register("ai_router", router_2)
        manager_2 = ConversationManager(max_messages=20, db_path=db_path)
        container_2.register("conversation_manager", manager_2)
        container_2.register("context_builder", ContextBuilder(max_context_chars=8000))

        dispatcher_2 = build_dispatcher()
        try:
            await dispatcher_2.dispatch("ask", ["след", "рестарт"], context, container_2)

            second_session_messages = provider_2.calls[-1]["messages"]
            # The AI request in session 2 should include what was said in session 1.
            assert any(m["content"] == "преди рестарт" for m in second_session_messages)
            assert manager_2.get_stats(400)["message_count"] == 4
        finally:
            await manager_2.stop()
