"""
Built-in Telegram command handlers — V1 MVP (Task 008), now context-aware
with Conversation Memory (Task 010).

Every handler here has the same shape: `async def cmd_x(args, context, container) -> str`.
Handlers contain no Telegram-specific code (no Update/Context, no reply_text)
— they only resolve services from the Container, call their already-existing
public methods, and return a plain response string. CommandDispatcher takes
care of routing, unknown commands, logging, and the unexpected-error fallback.
`context` (a CommandContext) carries caller identity — currently only /ask,
/reset, and /memory use it (to key the caller's conversation); every other
handler ignores it.

No command here calls an AI model beyond what the user explicitly requested
via /ask, and no command performs a write operation beyond a user resetting
their own conversation via /reset — /repo, /issues, /ai, /plugins, /status,
/health, and /memory are all read-only introspection over already existing
services. All failures are turned into short, friendly Bulgarian text —
never a stack trace, never a token/secret, and never conversation content
(Задача 3, Задача 5, Task 010 Задача 7).
"""
from typing import List, Optional

from phoenix_core._version import __version__ as _PHOENIX_VERSION
from phoenix_core.ai.base import AIResponse
from phoenix_core.core.container import Container
from phoenix_core.guard.guard import AIGuard
from phoenix_core.guard.sanitizer import OutputSanitizer
from phoenix_core.memory.context_builder import ContextBuilder, DEFAULT_MAX_CONTEXT_CHARS
from phoenix_core.telegram.context import CommandContext
from phoenix_core.utils.exceptions import (
    AIProviderConnectionError,
    AIProviderError,
    AIProviderNotFoundError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    ConfigurationError,
    ContextTooLargeError,
    GitHubAuthenticationError,
    GitHubConfigurationError,
    GitHubConnectionError,
    GitHubError,
    GitHubForbiddenError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubTimeoutError,
    PromptTooLargeError,
    RateLimitExceededError,
    ValidationError,
)
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

# User-facing messages are intentionally short and never include stack traces
# or internal error details (Задача 3, Task 008).
_MSG_EMPTY_ASK = "Моля, въведи въпрос след /ask. Пример: /ask Какво е Python?"
_MSG_AI_NOT_CONFIGURED = "AI слоят не е конфигуриран (липсва API ключ)."
_MSG_AI_PROVIDER_NOT_FOUND = "Заявеният AI provider не е наличен."
_MSG_AI_TIMEOUT = "Заявката отне твърде дълго време. Опитай отново."
_MSG_AI_CONNECTION = "Проблем с връзката към AI услугата. Опитай по-късно."
_MSG_AI_RATE_LIMIT = "Твърде много заявки в момента. Опитай отново след малко."
_MSG_AI_GENERIC_ERROR = "AI услугата върна грешка. Опитай отново по-късно."
_MSG_INVALID_INPUT = "Невалидна заявка."
_MSG_AI_UNAVAILABLE = "AI слоят не е наличен в момента."
_MSG_RESET_DONE = "🗑️ Разговорът е изтрит. Следващият /ask ще започне нов разговор."
_MSG_RESET_NOTHING = "Нямаше активен разговор — /ask ще започне нов разговор."
_MSG_MEMORY_EMPTY = "🧠 Няма активен разговор. Използвай /ask, за да започнеш."
_MSG_MEMORY_UNAVAILABLE = "⚠️ Паметта на разговора не е налична в момента."
_MSG_CONTEXT_TOO_LARGE = "⚠️ Контекстът на разговора е твърде голям. Пробвай /reset и опитай отново."

# Fallback used only if "settings" isn't registered in the container (should not
# happen in the running app — Settings.ai_max_prompt_length is the real source).
_DEFAULT_MAX_PROMPT_LENGTH = 4000

_MSG_GITHUB_NOT_CONFIGURED = "⚠️ GitHub клиентът не е конфигуриран (липсва PHOENIX_GITHUB_TOKEN)."
_MSG_GITHUB_MISCONFIGURED = "⚠️ GitHub owner/repo не са конфигурирани."
_MSG_GITHUB_AUTH = "⚠️ GitHub автентикацията се провали (невалиден token)."
_MSG_GITHUB_NOT_FOUND = "⚠️ Repository-то не е намерено."
_MSG_GITHUB_FORBIDDEN = "⚠️ Достъпът до repository-то е забранен."
_MSG_GITHUB_RATE_LIMIT = "⚠️ GitHub rate limit достигнат. Опитай по-късно."
_MSG_GITHUB_CONNECTION = "⚠️ Проблем с връзката към GitHub. Опитай по-късно."
_MSG_GITHUB_GENERIC_ERROR = "⚠️ GitHub заявката се провали."

# Maps a health-check component key (the reporting class name) to a
# friendly Bulgarian label for /status.
_COMPONENT_LABELS = {
    "AIRouter": "AI слой",
    "TelegramBot": "Telegram",
    "GitHubClient": "GitHub",
    "PluginRegistry": "Plugin Registry",
    "ConversationManager": "Памет на разговора",
    "AIGuard": "AI Guard Layer",
}

_STATUS_ICONS = {"healthy": "✅", "unhealthy": "❌", "configured": "✅"}


def _status_icon(status: str) -> str:
    """Map a health-check status string to a display icon (❓ if unrecognized)."""
    return _STATUS_ICONS.get(status, "❓")


async def cmd_start(args: List[str], context: CommandContext, container: Container) -> str:
    """Greeting: version, short description, and a pointer to /help."""
    return (
        "👋 Здравей! Аз съм Phoenix Core.\n"
        f"Версия: {_PHOENIX_VERSION}\n\n"
        "Модулен AI framework с Telegram контрол, GitHub интеграция и AI слой.\n\n"
        "Използвай /help за списък с всички команди."
    )


async def cmd_help(args: List[str], context: CommandContext, container: Container) -> str:
    """List every registered command with its description."""
    try:
        dispatcher = container.resolve("command_dispatcher")
    except KeyError:
        return "⚠️ Списъкът с команди не е наличен."

    lines = ["📖 Налични команди:"]
    for name, description in dispatcher.list_commands():
        lines.append(f"/{name} — {description}")
    return "\n".join(lines)


async def cmd_version(args: List[str], context: CommandContext, container: Container) -> str:
    """Show the version, read only from phoenix_core._version.__version__."""
    return f"🔥 Phoenix Core v{_PHOENIX_VERSION}"


async def cmd_status(args: List[str], context: CommandContext, container: Container) -> str:
    """Show a per-component status overview via PhoenixApplication.health_check()."""
    try:
        app = container.resolve("application")
    except KeyError:
        return "⚠️ Статус не е наличен."

    health = await app.health_check()
    lines = ["📊 Статус на Phoenix Core:"]
    for component_name, component_health in health.get("components", {}).items():
        label = _COMPONENT_LABELS.get(component_name, component_name)
        component_status = component_health.get("status", "unknown")
        icon = _status_icon(component_status)
        lines.append(f"{icon} {label}: {component_status}")

    overall = health.get("status", "unknown")
    lines.append("")
    lines.append(f"Общо: {_status_icon(overall)} {overall}")
    return "\n".join(lines)


async def cmd_health(args: List[str], context: CommandContext, container: Container) -> str:
    """Concise health summary, via the same PhoenixApplication.health_check() service."""
    try:
        app = container.resolve("application")
    except KeyError:
        return "⚠️ Health service не е наличен."

    health = await app.health_check()
    overall = health.get("status", "unknown")
    return f"{_status_icon(overall)} Phoenix Core: {overall}"


async def cmd_repo(args: List[str], context: CommandContext, container: Container) -> str:
    """Show configured repository info via GitHubClient.get_repository()."""
    try:
        github_client = container.resolve("github_client")
    except KeyError:
        return _MSG_GITHUB_NOT_CONFIGURED

    try:
        repo = await github_client.get_repository()
    except GitHubConfigurationError:
        return _MSG_GITHUB_MISCONFIGURED
    except GitHubAuthenticationError:
        return _MSG_GITHUB_AUTH
    except GitHubNotFoundError:
        return _MSG_GITHUB_NOT_FOUND
    except GitHubForbiddenError:
        return _MSG_GITHUB_FORBIDDEN
    except GitHubRateLimitError:
        return _MSG_GITHUB_RATE_LIMIT
    except (GitHubTimeoutError, GitHubConnectionError):
        return _MSG_GITHUB_CONNECTION
    except GitHubError:
        return _MSG_GITHUB_GENERIC_ERROR

    owner_login = (repo.get("owner") or {}).get("login", "—")
    visibility = "private" if repo.get("private") else "public"
    lines = [
        "📦 Repository:",
        f"• Име: {repo.get('name', '—')}",
        f"• Owner: {owner_login}",
        f"• Default branch: {repo.get('default_branch', '—')}",
        f"• Видимост: {visibility}",
        f"• ⭐ Stars: {repo.get('stargazers_count', 0)}",
        f"• 🍴 Forks: {repo.get('forks_count', 0)}",
        f"• 🐛 Open issues: {repo.get('open_issues_count', 0)}",
    ]
    return "\n".join(lines)


async def cmd_issues(args: List[str], context: CommandContext, container: Container) -> str:
    """Show the 5 most recent open issues via GitHubClient.list_issues()."""
    try:
        github_client = container.resolve("github_client")
    except KeyError:
        return _MSG_GITHUB_NOT_CONFIGURED

    try:
        issues = await github_client.list_issues(state="open", per_page=5, page=1)
    except GitHubConfigurationError:
        return _MSG_GITHUB_MISCONFIGURED
    except GitHubAuthenticationError:
        return _MSG_GITHUB_AUTH
    except GitHubNotFoundError:
        return _MSG_GITHUB_NOT_FOUND
    except GitHubForbiddenError:
        return _MSG_GITHUB_FORBIDDEN
    except GitHubRateLimitError:
        return _MSG_GITHUB_RATE_LIMIT
    except (GitHubTimeoutError, GitHubConnectionError):
        return _MSG_GITHUB_CONNECTION
    except GitHubError:
        return _MSG_GITHUB_GENERIC_ERROR

    if not issues:
        return "📋 Няма отворени issues."

    lines = ["📋 Последни issues:"]
    for issue in issues[:5]:
        number = issue.get("number", "?")
        title = issue.get("title", "—")
        state = issue.get("state", "—")
        author = (issue.get("user") or {}).get("login", "—")
        lines.append(f"#{number} {title} [{state}] — @{author}")
    return "\n".join(lines)


async def cmd_plugins(args: List[str], context: CommandContext, container: Container) -> str:
    """Show Plugin Registry status (V1 stub — plugin discovery isn't implemented yet)."""
    try:
        plugin_registry = container.resolve("plugin_registry")
    except KeyError:
        return "⚠️ Plugin Registry не е наличен."

    try:
        plugins = plugin_registry.list_plugins()
    except NotImplementedError:
        health = await plugin_registry.health_check()
        return (
            "🧩 Plugin Registry:\n"
            f"• Статус: {health.get('status', 'unknown')}\n"
            f"• {health.get('detail', '')}"
        )

    if not plugins:
        return "🧩 Няма заредени плъгини."

    lines = ["🧩 Заредени плъгини:"]
    for plugin in plugins:
        lines.append(f"• {plugin.get('name', '—')} — {plugin.get('description', '')}")
    return "\n".join(lines)


async def cmd_ai(args: List[str], context: CommandContext, container: Container) -> str:
    """Show configured AI providers, the default one, and their status."""
    try:
        ai_router = container.resolve("ai_router")
    except KeyError:
        return _MSG_AI_UNAVAILABLE

    health = await ai_router.health_check()
    providers = health.get("providers", {})
    if not providers:
        return "🤖 Няма конфигуриран AI provider."

    default_provider = health.get("default_provider", "—")
    lines = ["🤖 AI Providers:"]
    for name, provider_health in providers.items():
        status = provider_health.get("status", "unknown")
        label = "configured" if status == "configured" else "unavailable"
        marker = " (по подразбиране)" if name == default_provider else ""
        lines.append(f"• {name}: {label}{marker}")
    return "\n".join(lines)


def _resolve_context_builder(container: Container) -> ContextBuilder:
    """Resolve the shared ContextBuilder from the container, or build a default one.

    Falls back to a builder with the module default budget if none is
    registered — mirrors the same "graceful degradation, never crash"
    pattern used for ai_max_prompt_length above.
    """
    try:
        return container.resolve("context_builder")
    except KeyError:
        return ContextBuilder(max_context_chars=DEFAULT_MAX_CONTEXT_CHARS)


async def cmd_ask(args: List[str], context: CommandContext, container: Container) -> str:
    """Ask the configured AI provider a question, using the caller's conversation history.

    Flow (Task 010 + Task 011 Guard Layer): load the caller's conversation ->
    build provider-shaped context from it -> append the new question ->
    AI Guard pre-checks (rate limit, prompt/context size) -> AIRouter.chat()
    through the Guard's retry policy -> on success, record both the
    question and the answer into the conversation, sanitize the response
    text, and return it. If Conversation Memory or the AI Guard Layer
    isn't available for any reason, /ask still works — it degrades to
    exactly the Task 010 (or Task 009) behavior rather than failing.
    """
    if not args:
        return _MSG_EMPTY_ASK

    question = " ".join(args)

    try:
        settings = container.resolve("settings")
        max_length = settings.ai_max_prompt_length
    except KeyError:
        max_length = _DEFAULT_MAX_PROMPT_LENGTH

    if len(question) > max_length:
        return f"⚠️ Заявката е твърде дълга (максимум {max_length} символа)."

    # Only length is logged — never the message content (Задача 4/5).
    logger.info("AI request started", command="ask", user_id=context.user_id, question_length=len(question))

    try:
        ai_router = container.resolve("ai_router")
    except KeyError:
        return _MSG_AI_UNAVAILABLE

    try:
        conversation_manager = container.resolve("conversation_manager")
    except KeyError:
        conversation_manager = None

    if conversation_manager is not None:
        conversation = conversation_manager.get_or_create(context.user_id)
        context_builder = _resolve_context_builder(container)
        messages = context_builder.build(conversation) + [{"role": "user", "content": question}]
    else:
        messages = [{"role": "user", "content": question}]

    try:
        ai_guard = container.resolve("ai_guard")
    except KeyError:
        ai_guard = None

    if ai_guard is not None:
        try:
            ai_guard.guard_request(context.user_id, question, messages)
        except RateLimitExceededError:
            return _MSG_AI_RATE_LIMIT
        except PromptTooLargeError:
            return f"⚠️ Заявката е твърде дълга (максимум {max_length} символа)."
        except ContextTooLargeError:
            return _MSG_CONTEXT_TOO_LARGE

    try:
        if ai_guard is not None:
            response = await ai_guard.call_provider(lambda: ai_router.chat(messages=messages))
        else:
            response = await ai_router.chat(messages=messages)
    except ConfigurationError:
        logger.warning("AI request failed: not configured", command="ask")
        return _MSG_AI_NOT_CONFIGURED
    except AIProviderNotFoundError:
        logger.warning("AI request failed: provider not found", command="ask")
        return _MSG_AI_PROVIDER_NOT_FOUND
    except AIProviderTimeoutError:
        logger.warning("AI request failed: timeout", command="ask")
        return _MSG_AI_TIMEOUT
    except AIProviderConnectionError:
        logger.warning("AI request failed: connection error", command="ask")
        return _MSG_AI_CONNECTION
    except AIProviderRateLimitError:
        logger.warning("AI request failed: rate limited", command="ask")
        return _MSG_AI_RATE_LIMIT
    except AIProviderError:
        logger.error("AI request failed: provider error", command="ask")
        return _MSG_AI_GENERIC_ERROR
    except ValidationError:
        logger.warning("AI request failed: invalid input", command="ask")
        return _MSG_INVALID_INPUT

    logger.info("AI request completed", command="ask", provider=response.provider)

    if conversation_manager is not None:
        conversation_manager.add_message(context.user_id, "user", question)
        conversation_manager.add_message(context.user_id, "assistant", response.content)

    return _format_ai_response(response, ai_guard)


async def cmd_reset(args: List[str], context: CommandContext, container: Container) -> str:
    """Delete the caller's current conversation (Task 010) so the next /ask starts fresh."""
    try:
        conversation_manager = container.resolve("conversation_manager")
    except KeyError:
        return _MSG_MEMORY_UNAVAILABLE

    existed = conversation_manager.reset(context.user_id)
    return _MSG_RESET_DONE if existed else _MSG_RESET_NOTHING


async def cmd_memory(args: List[str], context: CommandContext, container: Container) -> str:
    """Show conversation stats for the caller — never the conversation content itself."""
    try:
        conversation_manager = container.resolve("conversation_manager")
    except KeyError:
        return _MSG_MEMORY_UNAVAILABLE

    stats = conversation_manager.get_stats(context.user_id)
    if stats is None:
        return _MSG_MEMORY_EMPTY

    last_activity = stats["updated_at"].strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "🧠 Памет на разговора:",
        f"• ID: {stats['conversation_id']}",
        f"• Съобщения: {stats['message_count']}",
        f"• Използван контекст: {stats['context_chars']} символа",
        f"• Последна активност: {last_activity}",
    ]
    return "\n".join(lines)


def _format_ai_response(response: AIResponse, ai_guard: Optional[AIGuard] = None) -> str:
    """Unified Telegram formatting for every AI provider's response (Task 009).

    Sanitizes response.content before sending to Telegram (Task 011,
    Задача 5) — via the AI Guard Layer if available, otherwise via a
    default OutputSanitizer so this protection is never skipped just
    because the Guard Layer isn't wired up in the container.
    """
    if ai_guard is not None:
        content = ai_guard.sanitize_output(response.content)
    else:
        content = _default_sanitizer().sanitize(response.content)
    return f"🤖 Phoenix AI\n\n{content}\n\nProvider: {response.provider}"


def _default_sanitizer() -> OutputSanitizer:
    """Lazily-created fallback OutputSanitizer, used only when no AIGuard is registered."""
    global _DEFAULT_SANITIZER
    if _DEFAULT_SANITIZER is None:
        _DEFAULT_SANITIZER = OutputSanitizer()
    return _DEFAULT_SANITIZER


_DEFAULT_SANITIZER: Optional[OutputSanitizer] = None
