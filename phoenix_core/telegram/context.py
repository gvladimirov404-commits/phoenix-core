"""
CommandContext — request-scoped caller context for the command layer.

Introduced as a small correction to the public API surface (see Task 010
discussion): CommandDispatcher and command handlers originally received
only `(args, container)`, with no representation of *who* issued the
command. That worked while no command needed caller identity, but the
Conversation Memory Engine (Task 010) needs a stable per-caller key
(`user_id`) to keep separate conversations separate.

Rather than growing handler signatures with one positional parameter per
new piece of caller info (user_id, then chat_id, then username, ...),
every handler now receives a single immutable CommandContext alongside
args and the Container. Handlers that don't need it simply ignore it.

CommandContext is intentionally Telegram-agnostic: it is built once by
the interface layer (currently phoenix_core.telegram.bot.TelegramBot)
from whatever transport-specific object triggered the command, and
everything below that point (CommandDispatcher, command handlers,
ConversationManager) depends only on this plain dataclass. This is what
lets the same command layer be reused by a future CLI, REST API, or
another chat platform without touching dispatcher or handler code.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class CommandContext:
    """Immutable per-request context describing who issued a command.

    Attributes:
        user_id: Stable identifier for the caller (e.g. Telegram user id).
            This is the key used by ConversationManager to keep per-user
            conversations separate — it is the one field every current
            handler that needs identity relies on.
        chat_id: Identifier of the chat/channel the command was sent from.
            May equal user_id for private chats; kept separate because it
            differs in group chats and on other transports.
        username: Caller's display/username, if the transport provides one.
        language_code: Caller's client-reported language code, if any.
        command: Name of the command being handled, without the leading
            slash (e.g. "ask"). Included so a handler doesn't need it
            passed separately if it ever needs to know its own name.
    """

    user_id: int
    chat_id: int
    username: Optional[str] = None
    language_code: Optional[str] = None
    command: str = ""
