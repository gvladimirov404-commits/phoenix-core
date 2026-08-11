"""Unit tests for TelegramNotificationService (TASK-023 Phase G)."""
import pytest

from phoenix_core.services.notifications.telegram_notification import TelegramNotificationService


class FakeTelegramBot:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.sent = []

    async def send_message(self, chat_id: int, text: str) -> None:
        if self.should_fail:
            raise RuntimeError("simulated Telegram failure")
        self.sent.append((chat_id, text))


class TestTelegramNotificationService:
    @pytest.mark.asyncio
    async def test_send_success_returns_true(self) -> None:
        bot = FakeTelegramBot()
        service = TelegramNotificationService(bot)

        result = await service.send(123, "hello")

        assert result is True
        assert bot.sent == [(123, "hello")]

    @pytest.mark.asyncio
    async def test_send_failure_returns_false_not_raises(self) -> None:
        bot = FakeTelegramBot(should_fail=True)
        service = TelegramNotificationService(bot)

        result = await service.send(123, "hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_user_id_used_as_chat_id(self) -> None:
        bot = FakeTelegramBot()
        service = TelegramNotificationService(bot)

        await service.send(999, "msg")

        assert bot.sent[0][0] == 999
