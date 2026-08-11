"""TelegramNotificationService — thin adapter over the existing
TelegramBot.send_message() (TASK-023 Phase G). Not a new Telegram client:
it wraps the bot instance already managed by PhoenixApplication's
component lifecycle.

Known limitation (explicitly accepted for this phase, per architecture
sign-off): assumes user_id == chat_id, which holds for today's
personal-DM bot usage but would break if the bot were ever used in a
group chat context. Revisit if/when group-chat support is added.
"""
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)


class TelegramNotificationService:
    """Delivers alert text to a user via the existing TelegramBot instance."""

    def __init__(self, telegram_bot) -> None:
        self._telegram_bot = telegram_bot

    async def send(self, user_id: int, text: str) -> bool:
        """Send `text` to `user_id` (treated as chat_id — see module docstring).
        Never raises: any exception from the underlying bot is caught, logged,
        and reported as a False return so callers can continue with other users."""
        try:
            await self._telegram_bot.send_message(chat_id=user_id, text=text)
            return True
        except Exception as e:
            logger.warning(
                "Notification delivery failed",
                user_id=user_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False
