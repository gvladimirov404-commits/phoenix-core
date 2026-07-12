"""
Central Telegram command dispatcher — V1 MVP (Task 008), now context-aware
(Task 010 API correction).

Every Telegram command goes through this dispatcher: it holds the
name -> handler registry, resolves a handler by name, calls it with
validated arguments plus a CommandContext, turns any *unexpected*
exception into a friendly, non-leaking error message, and logs the
command lifecycle (received / completed / failed) without ever logging
sensitive data.

Handlers themselves contain no Telegram-specific code: they receive a list
of plain string arguments, a CommandContext (who is calling), and the DI
Container, and return a plain response string. Known/expected failure
modes (e.g. a specific service being unavailable) are the handler's own
responsibility to turn into a friendly message — see
phoenix_core.telegram.commands. The dispatcher's blanket except is only a
safety net for genuinely unexpected errors.
"""
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Tuple

from phoenix_core.core.container import Container
from phoenix_core.telegram.context import CommandContext
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

CommandHandler = Callable[[List[str], CommandContext, Container], Awaitable[str]]

_MSG_UNKNOWN_COMMAND = "❓ Непозната команда. Използвай /help за списък с командите."
_MSG_INTERNAL_ERROR = "⚠️ Възникна вътрешна грешка. Опитай отново по-късно."


@dataclass(frozen=True)
class _Registration:
    """Internal record pairing a command handler with its /help description."""
    handler: CommandHandler
    description: str


class CommandDispatcher:
    """Routes Telegram commands to their handlers and standardizes error handling."""

    def __init__(self) -> None:
        """Create an empty dispatcher with no commands registered yet."""
        self._commands: Dict[str, _Registration] = {}

    def register(self, name: str, handler: CommandHandler, description: str) -> None:
        """Register a command handler.

        Args:
            name: Command name without the leading slash (e.g. "start").
            handler: Async callable `(args, context, container) -> response_text`.
            description: Short, human-readable description shown by /help.
        """
        self._commands[name] = _Registration(handler=handler, description=description)

    def list_commands(self) -> List[Tuple[str, str]]:
        """Return (name, description) pairs for every registered command, sorted by name."""
        return sorted((name, reg.description) for name, reg in self._commands.items())

    async def dispatch(
        self, name: str, args: List[str], context: CommandContext, container: Container
    ) -> str:
        """Look up and run the handler for `name`, returning a safe response text.

        Unknown commands, and any exception a handler doesn't handle itself,
        are turned into a short, friendly message — never a stack trace or
        internal detail.

        Args:
            name: Command name without the leading slash.
            args: Plain string arguments following the command.
            context: CommandContext describing who issued the command.
            container: DI Container the handler may resolve services from.
        """
        logger.info("Telegram command received", command=name, user_id=context.user_id)
        registration = self._commands.get(name)
        if registration is None:
            logger.warning("Telegram command unknown", command=name)
            return _MSG_UNKNOWN_COMMAND

        try:
            response = await registration.handler(args, context, container)
        except Exception as e:
            logger.error("Telegram command failed", command=name, error_type=type(e).__name__)
            return _MSG_INTERNAL_ERROR

        logger.info("Telegram command completed", command=name)
        return response
