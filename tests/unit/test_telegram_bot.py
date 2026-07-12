"""Unit tests for TelegramBot (Task 008: dispatcher-based routing; Task 010: CommandContext).

No real Telegram API calls are made — Update/Context objects are lightweight
fakes, and the python-telegram-bot Application/polling is never started.
Individual command *behavior* (start/help/version/status/repo/issues/
plugins/ai/ask/reset/memory) is covered in test_telegram_commands.py; this
file covers the bot's registration, dispatch, and CommandContext-building
plumbing.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from phoenix_core.core.container import Container
from phoenix_core.telegram.bot import TelegramBot
from phoenix_core.utils.exceptions import ConfigurationError


def make_update_and_context(text: str, args=None, user_id: int = 123, chat_id: int = 456, username=None):
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    effective_user = SimpleNamespace(id=user_id, username=username, language_code="bg")
    effective_chat = SimpleNamespace(id=chat_id)
    update = SimpleNamespace(message=message, effective_user=effective_user, effective_chat=effective_chat)
    context = SimpleNamespace(args=args or [])
    return update, context


def make_bot(token: str = "fake-token-not-used") -> TelegramBot:
    container = Container()
    return TelegramBot(token=token, settings=SimpleNamespace(), container=container)


class TestCommandRegistration:
    def test_registers_all_v1_commands(self) -> None:
        bot = make_bot()
        names = {name for name, _description in bot._dispatcher.list_commands()}
        assert names == {
            "start", "help", "version", "status", "health",
            "repo", "issues", "plugins", "ai", "ask", "reset", "memory",
        }

    def test_exposes_dispatcher_via_container(self) -> None:
        bot = make_bot()
        assert bot.container.resolve("command_dispatcher") is bot._dispatcher


class TestHandleDispatch:
    async def test_handle_routes_to_version_and_replies(self) -> None:
        bot = make_bot()
        update, context = make_update_and_context("/version")

        await bot._handle(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Phoenix Core" in text

    async def test_handle_strips_bot_username_suffix(self) -> None:
        bot = make_bot()
        update, context = make_update_and_context("/version@SomeBot")

        await bot._handle(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Phoenix Core" in text

    async def test_handle_passes_args_through(self) -> None:
        bot = make_bot()
        update, context = make_update_and_context("/ask hi there", args=["hi", "there"])

        await bot._handle(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "не е наличен" in text  # no ai_router registered in this bot's container

    async def test_handle_unknown_command_replies_with_friendly_message(self) -> None:
        bot = make_bot()
        update, context = make_update_and_context("/does_not_exist")

        await bot._handle(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Непозната команда" in text

    async def test_handle_ignores_messages_without_text(self) -> None:
        bot = make_bot()
        message = SimpleNamespace(text=None, reply_text=AsyncMock())
        update = SimpleNamespace(message=message, effective_user=None, effective_chat=None)
        context = SimpleNamespace(args=[])

        await bot._handle(update, context)

        message.reply_text.assert_not_called()

    async def test_handle_ignores_updates_without_effective_user(self) -> None:
        bot = make_bot()
        message = SimpleNamespace(text="/version", reply_text=AsyncMock())
        update = SimpleNamespace(message=message, effective_user=None, effective_chat=None)
        context = SimpleNamespace(args=[])

        await bot._handle(update, context)

        message.reply_text.assert_not_called()

    async def test_handle_builds_context_with_caller_user_id(self) -> None:
        bot = make_bot()

        seen = {}

        async def spy_handler(args, cmd_context, container):
            seen["user_id"] = cmd_context.user_id
            seen["chat_id"] = cmd_context.chat_id
            seen["command"] = cmd_context.command
            return "ok"

        bot._dispatcher.register("whoami", spy_handler, "test")
        update, context = make_update_and_context("/whoami", user_id=999, chat_id=888)

        await bot._handle(update, context)

        assert seen == {"user_id": 999, "chat_id": 888, "command": "whoami"}


class TestLifecycle:
    async def test_start_without_token_raises_configuration_error(self) -> None:
        bot = make_bot(token="")
        with pytest.raises(ConfigurationError):
            await bot.start()

    async def test_health_check_reports_not_started_before_start(self) -> None:
        bot = make_bot()
        health = await bot.health_check()
        assert health["status"] == "not_started"
