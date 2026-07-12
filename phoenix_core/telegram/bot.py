"""
Telegram bot — V1 MVP, now with a Command Dispatcher (Task 008) and
per-request CommandContext (Task 010 API correction).

Polling-based bot. Every command is registered with a CommandDispatcher and
routed through a single generic PTB callback (_handle) — there is no
per-command Telegram-specific logic here. _handle builds a CommandContext
from the incoming Update (caller identity/chat) and hands it to the
dispatcher alongside the plain args list. Command *behavior* lives in
phoenix_core.telegram.commands as plain `(args, context, container) -> str`
functions, reusing the existing AIRouter / ConversationManager /
GitHubClient / PluginRegistry / PhoenixApplication services via the
Container. See Task 004 for the original MVP scope, Task 008 for the
dispatcher/commands split, and Task 010 for the CommandContext addition
and Conversation Memory Engine.
"""
from typing import Any, Dict, Optional

from telegram import Message, Update
from telegram.ext import Application, CommandHandler as PTBCommandHandler, ContextTypes

from phoenix_core.config.settings import TelegramConfig
from phoenix_core.core.container import Container
from phoenix_core.telegram import commands as telegram_commands
from phoenix_core.telegram.context import CommandContext
from phoenix_core.telegram.dispatcher import CommandDispatcher
from phoenix_core.utils.exceptions import ConfigurationError
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)


class TelegramBot:
    """Telegram control interface (polling-based V1 MVP)."""

    def __init__(self, token: str, settings: TelegramConfig, container: Container):
        """Create the bot and register all built-in commands (does not start polling).

        Args:
            token: Telegram bot API token (may be empty; start() will raise if so).
            settings: TelegramConfig for this bot.
            container: DI container used by command handlers to resolve services
                ("settings", "ai_router", "conversation_manager", "context_builder",
                "github_client", "plugin_registry", "application") at
                command-handling time.
        """
        self.token = token
        self.settings = settings
        self.container = container
        self._application: Optional[Application] = None
        self._dispatcher = CommandDispatcher()
        self._register_commands()

    def _register_commands(self) -> None:
        """Register every built-in command handler with the dispatcher (Task 008)."""
        self._dispatcher.register("start", telegram_commands.cmd_start, "Приветствие и версия")
        self._dispatcher.register("help", telegram_commands.cmd_help, "Списък с всички команди")
        self._dispatcher.register("version", telegram_commands.cmd_version, "Версията на Phoenix Core")
        self._dispatcher.register("status", telegram_commands.cmd_status, "Обобщен статус на всички компоненти")
        self._dispatcher.register("health", telegram_commands.cmd_health, "Кратка проверка на здравето")
        self._dispatcher.register("repo", telegram_commands.cmd_repo, "Информация за конфигурирания GitHub repository")
        self._dispatcher.register("issues", telegram_commands.cmd_issues, "Последните 5 отворени issues")
        self._dispatcher.register("plugins", telegram_commands.cmd_plugins, "Статус на Plugin Registry")
        self._dispatcher.register("ai", telegram_commands.cmd_ai, "Конфигурираните AI доставчици и статус")
        self._dispatcher.register("ask", telegram_commands.cmd_ask, "Задай въпрос на AI-я (помни разговора)")
        self._dispatcher.register("reset", telegram_commands.cmd_reset, "Изтрива текущия разговор с AI-я")
        self._dispatcher.register("memory", telegram_commands.cmd_memory, "Статистика за текущия разговор")
        # Exposed via the container so cmd_help can list all commands without
        # this module needing to duplicate the registry.
        self.container.register("command_dispatcher", self._dispatcher)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Build the underlying Application, wire every registered command, and start polling."""
        if not self.token:
            raise ConfigurationError("Telegram bot_token is not configured")

        self._application = Application.builder().token(self.token).build()
        for name, _description in self._dispatcher.list_commands():
            self._application.add_handler(PTBCommandHandler(name, self._handle))

        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling()
        logger.info("TelegramBot started", mode="polling")

    async def stop(self) -> None:
        """Stop polling and shut down the underlying Application, if started."""
        if self._application is None:
            return
        logger.info("Stopping TelegramBot...")
        try:
            updater = self._application.updater
            if updater is not None and updater.running:
                await updater.stop()
            await self._application.stop()
            await self._application.shutdown()
        finally:
            self._application = None
        logger.info("TelegramBot stopped")

    async def health_check(self) -> Dict[str, Any]:
        """Report whether the bot's polling Application has been started."""
        return {
            "status": "healthy" if self._application is not None else "not_started",
            "detail": "Telegram bot polling" if self._application else "Telegram bot not started",
        }

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Message:
        """Send a message via the bot. Requires start() to have been called."""
        if self._application is None:
            raise ConfigurationError("Telegram bot is not started")
        return await self._application.bot.send_message(chat_id=chat_id, text=text, **kwargs)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def _handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Single PTB entrypoint for every registered command.

        Extracts the command name from the message text (since multiple
        CommandHandler registrations share this one callback), builds a
        CommandContext from the update's sender/chat info, delegates to the
        CommandDispatcher, and replies with whatever text it returns.
        """
        message = update.message
        if message is None or not message.text:
            return

        telegram_user = getattr(update, "effective_user", None)
        if telegram_user is None:
            # No identifiable sender (should not normally happen for a command
            # message) — nothing we can build a CommandContext for.
            return

        telegram_chat = getattr(update, "effective_chat", None)
        chat_id = telegram_chat.id if telegram_chat is not None else telegram_user.id

        command_name = message.text.split()[0].lstrip("/").split("@")[0]
        args = list(context.args or [])
        command_context = CommandContext(
            user_id=telegram_user.id,
            chat_id=chat_id,
            username=getattr(telegram_user, "username", None),
            language_code=getattr(telegram_user, "language_code", None),
            command=command_name,
        )
        response = await self._dispatcher.dispatch(command_name, args, command_context, self.container)
        await message.reply_text(response)
