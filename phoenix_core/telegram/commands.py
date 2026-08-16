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

Task 019 addition: cmd_brief provides a daily crypto morning brief
(BTC/ETH price + top 5 gainers/losers) built entirely on top of the
existing CryptoProvider abstraction (get_market, get_top_coins) — no new
architectural layers, no new HTTP calls, no new cache.
"""
from datetime import datetime, timezone
from typing import List, Optional

from phoenix_core._version import __version__ as _PHOENIX_VERSION
from phoenix_core.ai.base import AIResponse
from phoenix_core.core.container import Container
from phoenix_core.guard.guard import AIGuard
from phoenix_core.guard.sanitizer import OutputSanitizer
from phoenix_core.memory.context_builder import ContextBuilder, DEFAULT_MAX_CONTEXT_CHARS
from phoenix_core.services.crypto.base import CryptoMarket
from phoenix_core.services.crypto.intent import detect_crypto_intent
from phoenix_core.services.intel.feargreed_provider import FearGreedReading, explain_classification
from phoenix_core.services.intel.fees_provider import FeeEstimate
from phoenix_core.services.intel.news_provider import NewsItem
from phoenix_core.telegram.context import CommandContext
from phoenix_core.utils.exceptions import (
    AIProviderConnectionError,
    AIProviderError,
    AIProviderNotFoundError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    ConfigurationError,
    ContextTooLargeError,
    CryptoConnectionError,
    CryptoError,
    CryptoNotFoundError,
    CryptoRateLimitError,
    CryptoTimeoutError,
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

_MSG_CRYPTO_NOT_CONFIGURED = "Крипто модулът не е конфигуриран."
_MSG_CRYPTO_USAGE = "Употреба: /crypto <символ|top>. Пример: /crypto btc"
_MSG_CRYPTO_RATE_LIMIT = "Достигнат е лимитът на заявки към крипто доставчика. Опитай отново след малко."
_MSG_CRYPTO_CONNECTION = "Проблем с връзката към крипто доставчика. Опитай отново."
_MSG_CRYPTO_GENERIC_ERROR = "Възникна грешка при взимане на крипто данни."

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
        "Три неща, с които да започнеш:\n"
        "🔭 /watch <символ> — включва фоново наблюдение; ще ти пиша, ако нещо "
        "значимо се промени, дори да не питаш\n"
        "🔎 /research <символ> — пълен доклад с ясно посочени данни, покритие "
        "и увереност — никога без основание\n"
        "🧠 /copilot <символ> — AI обобщава пазара, сигналите и риска в един "
        "кратък брифинг\n\n"
        "Използвай /help за списък с всички команди."
    )


async def cmd_help(args: List[str], context: CommandContext, container: Container) -> str:
    """Onboarding: what the bot does, every command, example questions, and
    what's coming next (Task 020) — the command list itself stays dynamic
    (from CommandDispatcher.list_commands()) so it never drifts out of sync
    with what's actually registered."""
    try:
        dispatcher = container.resolve("command_dispatcher")
    except KeyError:
        return "⚠️ Списъкът с команди не е наличен."

    lines = [
        "👋 Добре дошъл в Phoenix Core!",
        "",
        "Твоят ежедневен крипто и AI асистент в Telegram — цени, новини,",
        "пазарно настроение, такси по мрежата, плюс AI отговори.",
        "",
        "Три неща изграждат основния workflow:",
        "🔭 /watch — пасивно наблюдение във фонов режим; Phoenix ти пише сам, "
        "ако нещо значимо се промени",
        "🔎 /research — evidence-based доклад с ясно посочени данни и увереност",
        "🧠 /copilot — AI обобщава пазара в кратък брифинг",
        "",
        "📖 Команди:",
    ]
    for name, description in dispatcher.list_commands():
        lines.append(f"/{name} — {description}")

    lines.extend([
        "",
        "💬 Примерни въпроси (пиши директно, без команда):",
        "• Колко струва bitcoin?",
        "• Какво е asyncio?",
    ])
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


def _format_crypto_market(market: CryptoMarket) -> str:
    change = market.change_24h_pct
    change_str = f"{change:+.2f}%" if change is not None else "—"
    market_cap = f"{market.market_cap_usd:,.0f} USD" if market.market_cap_usd is not None else "—"
    volume = f"{market.volume_24h_usd:,.0f} USD" if market.volume_24h_usd is not None else "—"
    price = f"{market.price_usd:,.2f} USD" if market.price_usd is not None else "—"
    lines = [
        f"{market.name} ({market.symbol})", "", "Price:", price, "", "24h:", change_str,
        "", "Market Cap:", market_cap, "", "24h Volume:", volume, "", "Last Updated:",
        market.last_updated or "—",
    ]
    return "\n".join(lines)


def _format_crypto_top_coins(coins: List[CryptoMarket]) -> str:
    lines = ["🏆 Топ крипто по пазарна капитализация:"]
    for index, coin in enumerate(coins, start=1):
        change = coin.change_24h_pct
        change_str = f"{change:+.2f}%" if change is not None else "—"
        price = f"{coin.price_usd:,.2f} USD" if coin.price_usd is not None else "—"
        lines.append(f"{index}. {coin.name} ({coin.symbol}) — {price} ({change_str})")
    return "\n".join(lines)


async def cmd_crypto(args: List[str], context: CommandContext, container: Container) -> str:
    try:
        crypto_provider = container.resolve("crypto_provider")
    except KeyError:
        return _MSG_CRYPTO_NOT_CONFIGURED

    if not args:
        return _MSG_CRYPTO_USAGE

    target = args[0].strip().lower()

    if target == "top":
        limit = 10
        if len(args) > 1 and args[1].isdigit():
            limit = max(1, min(int(args[1]), 25))
        try:
            coins = await crypto_provider.get_top_coins(limit=limit)
        except CryptoRateLimitError:
            return _MSG_CRYPTO_RATE_LIMIT
        except (CryptoTimeoutError, CryptoConnectionError):
            return _MSG_CRYPTO_CONNECTION
        except CryptoError:
            return _MSG_CRYPTO_GENERIC_ERROR
        return _format_crypto_top_coins(coins)

    try:
        market = await crypto_provider.get_market(target)
    except CryptoNotFoundError:
        return f"⚠️ Непознат крипто символ: {args[0]}"
    except CryptoRateLimitError:
        return _MSG_CRYPTO_RATE_LIMIT
    except (CryptoTimeoutError, CryptoConnectionError):
        return _MSG_CRYPTO_CONNECTION
    except CryptoError:
        return _MSG_CRYPTO_GENERIC_ERROR

    return _format_crypto_market(market)


_BRIEF_GAINERS_LOSERS_UNIVERSE = 100


def _format_brief_price_block(label: str, market: CryptoMarket) -> str:
    change = market.change_24h_pct
    change_str = f"{change:+.1f}%" if change is not None else "—"
    price = market.price_usd
    if price is None:
        price_str = "—"
    elif price >= 1000:
        price_str = f"${price:,.0f}"
    else:
        price_str = f"${price:,.2f}"
    return f"{label}\n{price_str}\n{change_str}"


def _format_brief_mover_line(index: int, coin: CryptoMarket) -> str:
    change = coin.change_24h_pct
    change_str = f"{change:+.1f}%" if change is not None else "—"
    price = f"${coin.price_usd:,.2f}" if coin.price_usd is not None else "—"
    return f"{index}. {coin.symbol} {price} ({change_str})"


def _format_brief(btc: CryptoMarket, eth: CryptoMarket, universe: List[CryptoMarket]) -> str:
    """Render the /brief text (Task 019). Gainers/losers are the top-N-by-market-cap
    coins (get_top_coins), re-sorted here by 24h % change — the free CoinGecko
    tier has no dedicated "biggest movers" endpoint, so this reuses the
    existing get_top_coins call rather than adding a new provider method."""
    ranked = [c for c in universe if c.change_24h_pct is not None]
    gainers = sorted(ranked, key=lambda c: c.change_24h_pct, reverse=True)[:5]
    losers = sorted(ranked, key=lambda c: c.change_24h_pct)[:5]

    lines = ["📊 Phoenix Morning Brief", ""]
    lines.append(_format_brief_price_block("BTC", btc))
    lines.append("")
    lines.append(_format_brief_price_block("ETH", eth))
    lines.append("")
    lines.append("🚀 Top Gainers")
    for index, coin in enumerate(gainers, start=1):
        lines.append(_format_brief_mover_line(index, coin))
    lines.append("")
    lines.append("📉 Top Losers")
    for index, coin in enumerate(losers, start=1):
        lines.append(_format_brief_mover_line(index, coin))
    lines.append("")
    lines.append("Последна актуализация:")
    lines.append(datetime.now(timezone.utc).strftime("%H:%M UTC"))
    return "\n".join(lines)


async def cmd_brief(args: List[str], context: CommandContext, container: Container) -> str:
    """Daily crypto morning brief: BTC/ETH price + top 5 gainers/losers (Task 019).

    Reuses the existing CryptoProvider abstraction only (get_market,
    get_top_coins) — no new HTTP calls and no new cache layer, since
    CoinGeckoProvider's own TTLCache already covers both calls at the
    configured TTL (default 60s, PHOENIX_CRYPTO_CACHE_TTL_SECONDS).
    """
    try:
        crypto_provider = container.resolve("crypto_provider")
    except KeyError:
        return _MSG_CRYPTO_NOT_CONFIGURED

    try:
        btc = await crypto_provider.get_market("btc")
        eth = await crypto_provider.get_market("eth")
        universe = await crypto_provider.get_top_coins(limit=_BRIEF_GAINERS_LOSERS_UNIVERSE)
    except CryptoRateLimitError:
        return _MSG_CRYPTO_RATE_LIMIT
    except (CryptoTimeoutError, CryptoConnectionError):
        return _MSG_CRYPTO_CONNECTION
    except CryptoError:
        return _MSG_CRYPTO_GENERIC_ERROR

    return _format_brief(btc, eth, universe)


_MSG_NEWS_NOT_CONFIGURED = "Модулът за новини не е конфигуриран (липсва CryptoPanic API token)."
_MSG_NEWS_USAGE = "Употреба: /news <символ>. Пример: /news btc"


def _format_news(symbol: str, items: List[NewsItem]) -> str:
    lines = [f"📰 Последни новини: {symbol.upper()}", ""]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item.title}")
        if item.source:
            lines.append(f"   Източник: {item.source}")
        lines.append(f"   {item.url}")
        lines.append("")
    return "\n".join(lines).rstrip()


async def cmd_news(args: List[str], context: CommandContext, container: Container) -> str:
    """Last 5 news items for a coin symbol (Task 020), via NewsProvider."""
    try:
        news_provider = container.resolve("news_provider")
    except KeyError:
        return _MSG_NEWS_NOT_CONFIGURED

    if not args:
        return _MSG_NEWS_USAGE

    symbol = args[0].strip().lower()
    try:
        items = await news_provider.get_news(symbol, limit=5)
    except CryptoRateLimitError:
        return _MSG_CRYPTO_RATE_LIMIT
    except (CryptoTimeoutError, CryptoConnectionError):
        return _MSG_CRYPTO_CONNECTION
    except CryptoError:
        return _MSG_CRYPTO_GENERIC_ERROR

    if not items:
        return f"Няма намерени новини за {symbol.upper()}."

    return _format_news(symbol, items)


_MSG_FEAR_NOT_CONFIGURED = "Fear & Greed модулът не е конфигуриран."

_FEAR_EMOJI = {"Extreme Fear": "😱", "Fear": "😨", "Neutral": "😐", "Greed": "🤑", "Extreme Greed": "🚀"}


def _format_fear(reading: FearGreedReading) -> str:
    emoji = _FEAR_EMOJI.get(reading.classification, "📊")
    explanation = explain_classification(reading.classification)
    lines = [f"{emoji} Fear & Greed Index", "", f"Стойност: {reading.value}/100", f"Категория: {reading.classification}"]
    if explanation:
        lines.append("")
        lines.append(explanation)
    return "\n".join(lines)


async def cmd_fear(args: List[str], context: CommandContext, container: Container) -> str:
    """Current Crypto Fear & Greed Index reading (Task 020), via FearGreedProvider."""
    try:
        feargreed_provider = container.resolve("feargreed_provider")
    except KeyError:
        return _MSG_FEAR_NOT_CONFIGURED

    try:
        reading = await feargreed_provider.get_current()
    except CryptoRateLimitError:
        return _MSG_CRYPTO_RATE_LIMIT
    except (CryptoTimeoutError, CryptoConnectionError):
        return _MSG_CRYPTO_CONNECTION
    except CryptoError:
        return _MSG_CRYPTO_GENERIC_ERROR

    return _format_fear(reading)


_MSG_GAS_NOT_CONFIGURED = "Модулът за такси не е конфигуриран."


def _format_gas(estimate: FeeEstimate) -> str:
    return "\n".join([
        "⛽ Bitcoin Network Fees", "",
        f"🚀 Най-бързо (следващ блок): {estimate.fastest_sat_vb:.0f} sat/vB",
        f"⏱️ ~30 мин: {estimate.half_hour_sat_vb:.0f} sat/vB",
        f"🕐 ~1 час: {estimate.hour_sat_vb:.0f} sat/vB",
        f"💤 Икономично: {estimate.economy_sat_vb:.0f} sat/vB",
    ])


async def cmd_gas(args: List[str], context: CommandContext, container: Container) -> str:
    """Recommended Bitcoin network fees (Task 020), via FeesProvider."""
    try:
        fees_provider = container.resolve("fees_provider")
    except KeyError:
        return _MSG_GAS_NOT_CONFIGURED

    try:
        estimate = await fees_provider.get_recommended_fees()
    except CryptoRateLimitError:
        return _MSG_CRYPTO_RATE_LIMIT
    except (CryptoTimeoutError, CryptoConnectionError):
        return _MSG_CRYPTO_CONNECTION
    except CryptoError:
        return _MSG_CRYPTO_GENERIC_ERROR

    return _format_gas(estimate)


_MSG_WATCH_UNAVAILABLE = "Watchlist модулът не е наличен в момента."
_MSG_WATCH_EMPTY = "📋 Твоят watchlist е празен. Добави монети с /watch btc eth sol"


async def cmd_watch(args: List[str], context: CommandContext, container: Container) -> str:
    """Save coin symbols to the caller's watchlist, or show it with no args (Task 020).

    Persistence only — no notifications/alerts yet, via WatchlistManager.
    """
    try:
        watchlist_manager = container.resolve("watchlist_manager")
    except KeyError:
        return _MSG_WATCH_UNAVAILABLE

    if args:
        symbols = watchlist_manager.add_symbols(context.user_id, args)
    else:
        symbols = watchlist_manager.get_watchlist(context.user_id)

    if not symbols:
        return _MSG_WATCH_EMPTY

    lines = ["📋 Твоят watchlist:"]
    for symbol in symbols:
        lines.append(f"• {symbol}")
    return "\n".join(lines)


def _format_market_intel(snapshot) -> str:
    lines = [f"\U0001F50E \u041f\u0430\u0437\u0430\u0440\u0435\u043d \u043f\u0440\u0435\u0433\u043b\u0435\u0434: {snapshot.symbol}", ""]

    if snapshot.market is not None:
        m = snapshot.market
        change = m.change_24h_pct
        change_str = f"{change:+.2f}%" if change is not None else "\u2014"
        price = f"{m.price_usd:,.2f} USD" if m.price_usd is not None else "\u2014"
        lines.append(f"\u0426\u0435\u043d\u0430: {price} ({change_str} 24\u0447)")
    else:
        lines.append("\u0426\u0435\u043d\u0430: \u043d\u0435 \u0435 \u0434\u043e\u0441\u0442\u044a\u043f\u043d\u0430 \u0432 \u043c\u043e\u043c\u0435\u043d\u0442\u0430")

    if snapshot.fear_greed is not None:
        fg = snapshot.fear_greed
        lines.append(f"\u041d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u0438\u0435: {fg.value}/100 ({fg.classification})")
    else:
        lines.append("\u041d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u0438\u0435: \u043d\u0435 \u0435 \u0434\u043e\u0441\u0442\u044a\u043f\u043d\u043e \u0432 \u043c\u043e\u043c\u0435\u043d\u0442\u0430")

    if snapshot.fees is not None:
        f = snapshot.fees
        lines.append(f"BTC \u0442\u0430\u043a\u0441\u0438: {f.fastest_sat_vb:g} sat/vB (\u043d\u0430\u0439-\u0431\u044a\u0440\u0437\u0430)")

    if snapshot.top_news is not None:
        n = snapshot.top_news
        lines.append("")
        lines.append(f"\U0001F4F0 {n.title}")
        if n.source:
            lines.append(f"\u0418\u0437\u0442\u043e\u0447\u043d\u0438\u043a: {n.source}")

    return "\n".join(lines)


async def cmd_intel(args: List[str], context: CommandContext, container: Container) -> str:
    """Consolidated market snapshot: price, sentiment, BTC fees, top news (Roadmap item 2)."""
    if not args:
        return "\u0423\u043f\u043e\u0442\u0440\u0435\u0431\u0430: /intel <\u0441\u0438\u043c\u0432\u043e\u043b>. \u041f\u0440\u0438\u043c\u0435\u0440: /intel btc"

    try:
        aggregator = container.resolve("market_intel_aggregator")
    except KeyError:
        return "\u041c\u043e\u0434\u0443\u043b\u044a\u0442 \u0437\u0430 \u043f\u0430\u0437\u0430\u0440\u0435\u043d \u043f\u0440\u0435\u0433\u043b\u0435\u0434 \u043d\u0435 \u0435 \u043d\u0430\u043b\u0438\u0447\u0435\u043d."

    symbol = args[0].strip().lower()
    snapshot = await aggregator.get_snapshot(symbol)

    if snapshot.is_empty:
        return f"\u26a0\ufe0f \u041d\u0435 \u0443\u0441\u043f\u044f\u0445 \u0434\u0430 \u0432\u0437\u0435\u043c\u0430 \u043d\u0438\u043a\u0430\u043a\u0432\u0438 \u0434\u0430\u043d\u043d\u0438 \u0437\u0430 {symbol.upper()} \u0432 \u043c\u043e\u043c\u0435\u043d\u0442\u0430. \u041e\u043f\u0438\u0442\u0430\u0439 \u043e\u0442\u043d\u043e\u0432\u043e \u043f\u043e-\u043a\u044a\u0441\u043d\u043e."

    return _format_market_intel(snapshot)


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

    crypto_intent = detect_crypto_intent(question)
    if crypto_intent is not None:
        try:
            crypto_provider = container.resolve("crypto_provider")
        except KeyError:
            crypto_provider = None
        if crypto_provider is not None:
            intent_kind, intent_symbol = crypto_intent
            try:
                if intent_kind == "top":
                    coins = await crypto_provider.get_top_coins(limit=10)
                    return _format_crypto_top_coins(coins)
                else:
                    market = await crypto_provider.get_market(intent_symbol)
                    return _format_crypto_market(market)
            except CryptoNotFoundError:
                pass
            except CryptoError:
                return _MSG_CRYPTO_GENERIC_ERROR

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


_MSG_EXPLAIN_USAGE = "Употреба: /explain <символ>. Пример: /explain btc"
_MSG_EXPLAIN_INTEL_UNAVAILABLE = "Модулът за пазарен преглед не е наличен."
_MSG_EXPLAIN_NO_DATA = "⚠️ Не успях да взема достатъчно данни, за да обясня движението. Опитай отново по-късно."


def _build_explain_prompt(snapshot) -> str:
    """Build a Bulgarian-language prompt describing a MarketSnapshot, asking
    the AI to explain the price movement in plain language (Roadmap item 1)."""
    parts = [
        f"Ти си крипто анализатор. Обясни накратко (3-4 изречения, на български) "
        f"защо цената на {snapshot.symbol} може да се движи по този начин, само "
        f"въз основа на следните данни:"
    ]

    if snapshot.market is not None:
        m = snapshot.market
        change = m.change_24h_pct
        change_str = f"{change:+.2f}%" if change is not None else "неизвестна"
        parts.append(f"- Цена: {m.price_usd} USD, промяна за 24ч: {change_str}")
    else:
        parts.append("- Няма налична информация за цената.")

    if snapshot.fear_greed is not None:
        fg = snapshot.fear_greed
        parts.append(f"- Пазарно настроение (Fear & Greed индекс): {fg.value}/100 ({fg.classification})")

    if snapshot.fees is not None:
        f = snapshot.fees
        parts.append(f"- BTC такси по мрежата в момента: {f.fastest_sat_vb:g} sat/vB (най-бърза опция)")

    if snapshot.top_news is not None:
        n = snapshot.top_news
        parts.append(f"- Водеща новина: \"{n.title}\" (Източник: {n.source or 'неизвестен'})")

    parts.append(
        "Не давай инвестиционен съвет и не гарантирай бъдещо движение — "
        "само обясни възможните причини на база наличните данни."
    )
    return "\n".join(parts)


async def cmd_explain(args: List[str], context: CommandContext, container: Container) -> str:
    """AI-generated plain-language explanation of a coin's current price
    movement, built from the same MarketIntelligenceAggregator snapshot
    /intel uses (Roadmap item 1 / TASK-021 Part 9)."""
    if not args:
        return _MSG_EXPLAIN_USAGE

    try:
        aggregator = container.resolve("market_intel_aggregator")
    except KeyError:
        return _MSG_EXPLAIN_INTEL_UNAVAILABLE

    symbol = args[0].strip().lower()
    snapshot = await aggregator.get_snapshot(symbol)

    if snapshot.is_empty:
        return _MSG_EXPLAIN_NO_DATA

    try:
        ai_router = container.resolve("ai_router")
    except KeyError:
        return _MSG_AI_UNAVAILABLE

    try:
        ai_guard = container.resolve("ai_guard")
    except KeyError:
        ai_guard = None

    prompt = _build_explain_prompt(snapshot)
    messages = [{"role": "user", "content": prompt}]

    logger.info(
        "AI request started", command="explain", user_id=context.user_id, symbol=snapshot.symbol
    )

    if ai_guard is not None:
        try:
            ai_guard.guard_request(context.user_id, prompt, messages)
        except RateLimitExceededError:
            return _MSG_AI_RATE_LIMIT
        except PromptTooLargeError:
            return _MSG_INVALID_INPUT
        except ContextTooLargeError:
            return _MSG_CONTEXT_TOO_LARGE

    try:
        if ai_guard is not None:
            response = await ai_guard.call_provider(lambda: ai_router.chat(messages=messages))
        else:
            response = await ai_router.chat(messages=messages)
    except ConfigurationError:
        logger.warning("AI request failed: not configured", command="explain")
        return _MSG_AI_NOT_CONFIGURED
    except AIProviderNotFoundError:
        logger.warning("AI request failed: provider not found", command="explain")
        return _MSG_AI_PROVIDER_NOT_FOUND
    except AIProviderTimeoutError:
        logger.warning("AI request failed: timeout", command="explain")
        return _MSG_AI_TIMEOUT
    except AIProviderConnectionError:
        logger.warning("AI request failed: connection error", command="explain")
        return _MSG_AI_CONNECTION
    except AIProviderRateLimitError:
        logger.warning("AI request failed: rate limited", command="explain")
        return _MSG_AI_RATE_LIMIT
    except AIProviderError:
        logger.error("AI request failed: provider error", command="explain")
        return _MSG_AI_GENERIC_ERROR
    except ValidationError:
        logger.warning("AI request failed: invalid input", command="explain")
        return _MSG_INVALID_INPUT

    logger.info("AI request completed", command="explain", provider=response.provider)

    if ai_guard is not None:
        content = ai_guard.sanitize_output(response.content)
    else:
        content = _default_sanitizer().sanitize(response.content)

    return f"🧠 Обяснение за {snapshot.symbol}\n\n{content}\n\nProvider: {response.provider}"


from phoenix_core.ai.consensus import ConsensusEngine

_MSG_CONSENSUS_USAGE = "Употреба: /consensus <въпрос>. Пример: /consensus Ще расте ли bitcoin?"
_MSG_CONSENSUS_UNAVAILABLE = "AI слоят не е наличен в момента."


def _format_consensus(result, ai_guard=None) -> str:
    lines = [f"⚖️ Консенсус ({result.provider_count} provider-а):", ""]

    for name, response in result.responses.items():
        if ai_guard is not None:
            content = ai_guard.sanitize_output(response.content)
        else:
            content = _default_sanitizer().sanitize(response.content)
        lines.append(f"🤖 {name}:")
        lines.append(content)
        lines.append("")

    if result.errors:
        failed = ", ".join(result.errors.keys())
        lines.append(f"⚠️ Неуспешни: {failed}")
        lines.append("")

    if len(result.responses) == 1 and not result.errors:
        lines.append(
            "ℹ️ В момента е активен само един AI provider — сравнение ще е "
            "възможно, когато се активира втори (напр. DeepSeek)."
        )

    return "\n".join(lines).strip()


async def cmd_consensus(args: List[str], context: CommandContext, container: Container) -> str:
    """Ask every currently configured AI provider the same question and show
    each answer side by side (Roadmap item 5 / TASK-021 Part 9). Degrades
    gracefully to a single-provider answer when only one is configured, and
    needs no changes to start comparing once a second provider is enabled."""
    if not args:
        return _MSG_CONSENSUS_USAGE

    question = " ".join(args)

    try:
        settings = container.resolve("settings")
        max_length = settings.ai_max_prompt_length
    except KeyError:
        max_length = _DEFAULT_MAX_PROMPT_LENGTH

    if len(question) > max_length:
        return f"⚠️ Заявката е твърде дълга (максимум {max_length} символа)."

    try:
        ai_router = container.resolve("ai_router")
    except KeyError:
        return _MSG_CONSENSUS_UNAVAILABLE

    if not ai_router.list_providers():
        return _MSG_CONSENSUS_UNAVAILABLE

    try:
        ai_guard = container.resolve("ai_guard")
    except KeyError:
        ai_guard = None

    engine = ConsensusEngine(ai_router)
    messages = [{"role": "user", "content": question}]

    # AI Guard (Task 030): /consensus fans out to every configured provider,
    # making it the most expensive command in the bot, but the guard check
    # itself is a single per-user check against the one question text the
    # user actually sent — the same rate-limit/prompt-size/context-size
    # semantics as /ask, /explain, /research. It must run before any
    # provider is contacted, so a rejected request never reaches
    # ConsensusEngine.get_consensus() at all.
    if ai_guard is not None:
        try:
            ai_guard.guard_request(context.user_id, question, messages)
        except RateLimitExceededError:
            return _MSG_AI_RATE_LIMIT
        except PromptTooLargeError:
            return f"⚠️ Заявката е твърде дълга (максимум {max_length} символа)."
        except ContextTooLargeError:
            return _MSG_CONTEXT_TOO_LARGE

    logger.info(
        "Consensus request started",
        command="consensus",
        user_id=context.user_id,
        question_length=len(question),
    )

    result = await engine.get_consensus(messages)

    if not result.responses:
        return "⚠️ Нито един AI provider не успя да отговори в момента. Опитай отново по-късно."

    return _format_consensus(result, ai_guard)


from phoenix_core.ai.benchmark import PhoenixBenchmark

_MSG_BENCHMARK_UNAVAILABLE = "AI слоят не е наличен в момента."


def _format_benchmark(results) -> str:
    if not results:
        return "⚠️ Няма конфигуриран AI provider в момента."

    lines = ["📊 Benchmark на AI provider-ите:", ""]
    for name, bench in results.items():
        lines.append(f"🤖 {name}:")
        lines.append(
            f"• Успеваемост: {bench.successes}/{bench.attempts} ({bench.success_rate * 100:.0f}%)"
        )
        if bench.successes:
            lines.append(f"• Средно време за отговор: {bench.average_latency_seconds:.2f}s")
        if bench.errors:
            lines.append(f"• Грешки: {', '.join(bench.errors)}")
        lines.append("")

    return "\n".join(lines).strip()


async def cmd_benchmark(args: List[str], context: CommandContext, container: Container) -> str:
    """Run a fixed prompt set against every configured AI provider and
    report latency/success rate per provider (Benchmark roadmap item).
    Useful for deciding when a newly enabled provider is worth using,
    or for spotting a provider that has started degrading."""
    try:
        ai_router = container.resolve("ai_router")
    except KeyError:
        return _MSG_BENCHMARK_UNAVAILABLE

    if not ai_router.list_providers():
        return _MSG_BENCHMARK_UNAVAILABLE

    try:
        ai_guard = container.resolve("ai_guard")
    except KeyError:
        ai_guard = None

    # AI Guard (Task 032): /benchmark fans out to every configured
    # provider using a fixed internal prompt set — the user supplies no
    # text of their own. guard_request() still represents the single
    # logical /benchmark action (one rate-limit check per invocation,
    # same as every other AI command), using a fixed representative
    # string rather than inventing a new guard API or multiplying the
    # check by provider/prompt count. Must run before any provider work
    # begins, so a rejected request never reaches PhoenixBenchmark.run().
    if ai_guard is not None:
        benchmark_action = "/benchmark"
        benchmark_messages = [{"role": "user", "content": benchmark_action}]
        try:
            ai_guard.guard_request(context.user_id, benchmark_action, benchmark_messages)
        except RateLimitExceededError:
            return _MSG_AI_RATE_LIMIT
        except PromptTooLargeError:
            return _MSG_INVALID_INPUT
        except ContextTooLargeError:
            return _MSG_CONTEXT_TOO_LARGE

    logger.info("Benchmark started", command="benchmark", user_id=context.user_id)

    benchmark = PhoenixBenchmark(ai_router)
    results = await benchmark.run()

    return _format_benchmark(results)


from phoenix_core.services.strategy.registry import StrategyRegistry

_MSG_STRATEGY_USAGE = "Употреба: /strategy <символ> [стратегия]. Пример: /strategy btc или /strategy btc momentum"
_MSG_STRATEGY_INTEL_UNAVAILABLE = "Модулът за пазарен преглед не е наличен."
_MSG_STRATEGY_NO_DATA = "⚠️ Не успях да взема достатъчно данни, за да оценя стратегиите. Опитай отново по-късно."
_MSG_STRATEGY_UNKNOWN = "Няма стратегия с това име. Използвай /strategy <символ> без второ име, за да видиш всички."

_STRATEGY_SIGNAL_ICONS = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡", "unknown": "⚪"}


def _format_strategy_signal(signal) -> str:
    icon = _STRATEGY_SIGNAL_ICONS.get(signal.signal, "⚪")
    return f"{icon} {signal.strategy_name}: {signal.reasoning}"


async def cmd_strategy(args: List[str], context: CommandContext, container: Container) -> str:
    """Evaluate one or all built-in Strategy Lab strategies against a coin's
    current market snapshot (Strategy Lab roadmap item). Purely informational
    — every result carries a disclaimer and this never recommends an action."""
    if not args:
        return _MSG_STRATEGY_USAGE

    try:
        aggregator = container.resolve("market_intel_aggregator")
    except KeyError:
        return _MSG_STRATEGY_INTEL_UNAVAILABLE

    symbol = args[0].strip().lower()
    strategy_name = args[1].strip().lower() if len(args) > 1 else None

    snapshot = await aggregator.get_snapshot(symbol)
    if snapshot.is_empty:
        return _MSG_STRATEGY_NO_DATA

    registry = StrategyRegistry()

    if strategy_name is not None:
        strategy = registry.get(strategy_name)
        if strategy is None:
            return _MSG_STRATEGY_UNKNOWN
        signals = {strategy_name: strategy.evaluate(snapshot)}
    else:
        signals = registry.evaluate_all(snapshot)

    lines = [f"🧪 Strategy Lab — {snapshot.symbol}", ""]
    for signal in signals.values():
        lines.append(_format_strategy_signal(signal))
    lines.append("")
    lines.append("ℹ️ Информативно, не е финансов съвет.")

    return "\n".join(lines)


_MSG_COPILOT_USAGE = "Употреба: /copilot <символ>. Пример: /copilot btc"
_MSG_COPILOT_INTEL_UNAVAILABLE = "Модулът за пазарен преглед не е наличен."
_MSG_COPILOT_NO_DATA = "⚠️ Не успях да взема достатъчно данни за брифинга. Опитай отново по-късно."


def _build_copilot_prompt(snapshot, signals) -> str:
    """Build a Bulgarian-language prompt asking the AI to synthesize the
    market snapshot and Strategy Lab signals into a short briefing — never
    a buy/sell recommendation, only a balanced read of what the data and
    signals currently show, with risks explicitly named."""
    parts = [
        f"Ти си крипто анализатор, който пише кратък информативен брифинг за {snapshot.symbol}. "
        "Синтезирай наличните данни и сигнали в 4-5 изречения на български. "
        "СТРОГО ВАЖНО: не давай пряка препоръка да се купува или продава, не гарантирай бъдещо "
        "движение — само опиши какво показват данните и къде си противоречат сигналите, "
        "и спомени поне един конкретен риск."
    ]

    if snapshot.market is not None:
        m = snapshot.market
        change = m.change_24h_pct
        change_str = f"{change:+.2f}%" if change is not None else "неизвестна"
        parts.append(f"- Цена: {m.price_usd} USD, промяна за 24ч: {change_str}")
    else:
        parts.append("- Няма налична информация за цената.")

    if snapshot.fear_greed is not None:
        fg = snapshot.fear_greed
        parts.append(f"- Пазарно настроение (Fear & Greed индекс): {fg.value}/100 ({fg.classification})")

    if snapshot.top_news is not None:
        n = snapshot.top_news
        parts.append(f"- Водеща новина: \"{n.title}\" (Източник: {n.source or 'неизвестен'})")

    if signals:
        parts.append("- Сигнали от Strategy Lab:")
        for signal in signals.values():
            parts.append(f"  • {signal.strategy_name}: {signal.signal} — {signal.reasoning}")

    return "\n".join(parts)


async def cmd_copilot(args: List[str], context: CommandContext, container: Container) -> str:
    """Trading Copilot: synthesizes /intel market data and Strategy Lab
    signals into a short AI briefing (Trading Copilot roadmap item, final
    TASK-021 item). Purely informational — never recommends buying or
    selling, and always ends with a disclaimer regardless of what the AI
    produced."""
    if not args:
        return _MSG_COPILOT_USAGE

    try:
        aggregator = container.resolve("market_intel_aggregator")
    except KeyError:
        return _MSG_COPILOT_INTEL_UNAVAILABLE

    symbol = args[0].strip().lower()
    snapshot = await aggregator.get_snapshot(symbol)

    if snapshot.is_empty:
        return _MSG_COPILOT_NO_DATA

    signals = StrategyRegistry().evaluate_all(snapshot)

    try:
        ai_router = container.resolve("ai_router")
    except KeyError:
        return _MSG_AI_UNAVAILABLE

    try:
        ai_guard = container.resolve("ai_guard")
    except KeyError:
        ai_guard = None

    prompt = _build_copilot_prompt(snapshot, signals)
    messages = [{"role": "user", "content": prompt}]

    logger.info(
        "AI request started", command="copilot", user_id=context.user_id, symbol=snapshot.symbol
    )

    if ai_guard is not None:
        try:
            ai_guard.guard_request(context.user_id, prompt, messages)
        except RateLimitExceededError:
            return _MSG_AI_RATE_LIMIT
        except PromptTooLargeError:
            return _MSG_INVALID_INPUT
        except ContextTooLargeError:
            return _MSG_CONTEXT_TOO_LARGE

    try:
        if ai_guard is not None:
            response = await ai_guard.call_provider(lambda: ai_router.chat(messages=messages))
        else:
            response = await ai_router.chat(messages=messages)
    except ConfigurationError:
        logger.warning("AI request failed: not configured", command="copilot")
        return _MSG_AI_NOT_CONFIGURED
    except AIProviderNotFoundError:
        logger.warning("AI request failed: provider not found", command="copilot")
        return _MSG_AI_PROVIDER_NOT_FOUND
    except AIProviderTimeoutError:
        logger.warning("AI request failed: timeout", command="copilot")
        return _MSG_AI_TIMEOUT
    except AIProviderConnectionError:
        logger.warning("AI request failed: connection error", command="copilot")
        return _MSG_AI_CONNECTION
    except AIProviderRateLimitError:
        logger.warning("AI request failed: rate limited", command="copilot")
        return _MSG_AI_RATE_LIMIT
    except AIProviderError:
        logger.error("AI request failed: provider error", command="copilot")
        return _MSG_AI_GENERIC_ERROR
    except ValidationError:
        logger.warning("AI request failed: invalid input", command="copilot")
        return _MSG_INVALID_INPUT

    logger.info("AI request completed", command="copilot", provider=response.provider)

    if ai_guard is not None:
        content = ai_guard.sanitize_output(response.content)
    else:
        content = _default_sanitizer().sanitize(response.content)

    return (
        f"✈️ Trading Copilot — {snapshot.symbol}\n\n"
        f"{content}\n\n"
        "⚠️ Само информативно — не е финансов съвет и не е препоръка за покупка/продажба.\n\n"
        f"Provider: {response.provider}"
    )


from phoenix_core.services.research.research_capability import (
    ResearchAIError,
    ResearchNoDataError,
    ResearchUnavailableError,
    run_research,
)

_MSG_RESEARCH_USAGE = "Употреба: /research <символ>. Пример: /research btc"
_MSG_RESEARCH_INTEL_UNAVAILABLE = "Модулът за пазарен преглед не е наличен."
_MSG_RESEARCH_NO_DATA = "⚠️ Не успях да взема достатъчно данни за проучването. Опитай отново по-късно."


def _build_research_prompt(snapshot, signals, evidence, skill_instructions=None) -> str:
    """Ask the AI only for the interpretive narrative — every factual figure
    in the final report is assembled separately in code, from real data,
    never from the model (crypto-research Skill, Evidence rules).

    skill_instructions (Task 025) is the crypto-research SKILL.md's
    Markdown body, resolved by research_capability.run_research via
    SkillManager, or None if unavailable — when present, it's included
    as brief guidance for how to interpret the data below; the AI is
    never asked to invent or restate the factual fields themselves,
    the instruction to describe only what the data below shows still
    applies regardless of skill_instructions."""
    parts = [
        f"Ти си крипто анализатор. Напиши кратко проучване за {snapshot.symbol} на български, "
        "в два ясно означени раздела:\n"
        "СЪБИТИЯ И АНАЛИЗ: (3-4 изречения какво се случва и защо, базирано САМО на данните по-долу)\n"
        "ИЗВОД: (1 изречение, БЕЗ пряка препоръка за покупка/продажба)\n"
        "Не измисляй факти извън дадените данни. Ако липсва информация, кажи го изрично."
    ]
    if skill_instructions:
        parts.append(f"Контекст за процедурата на анализа (следвай духа, не цитирай дословно):\n{skill_instructions}")
    if snapshot.market is not None:
        m = snapshot.market
        change_str = f"{m.change_24h_pct:+.2f}%" if m.change_24h_pct is not None else "неизвестна"
        parts.append(f"- Цена: {m.price_usd} USD, промяна 24ч: {change_str}")
    if snapshot.fear_greed is not None:
        fg = snapshot.fear_greed
        parts.append(f"- Настроение: {fg.value}/100 ({fg.classification})")
    if snapshot.top_news is not None:
        n = snapshot.top_news
        parts.append(f"- Новина: \"{n.title}\" ({n.source or 'неизвестен източник'})")
    if signals:
        parts.append("- Strategy сигнали:")
        for s in signals.values():
            parts.append(f"  • {s.strategy_name}: {s.signal} — {s.reasoning}")
    parts.append(f"- Покритие на данните: {evidence.coverage_fraction} ({evidence.confidence})")
    return "\n".join(parts)


def _derive_research_conclusion(signals) -> str:
    """Purely rule-derived — never asks the AI — so the CONCLUSION line can
    never drift from what the signals actually say (crypto-research Skill,
    Pitfalls: never let free text read as investment advice)."""
    if not signals:
        return "Недостатъчно сигнали за извод."
    values = [s.signal for s in signals.values()]
    if all(v == "unknown" for v in values):
        return "Недостатъчно данни за извод."
    bullish = values.count("bullish")
    bearish = values.count("bearish")
    if bullish > bearish:
        return "Преобладават бичи сигнали от Strategy Lab — информативно, не препоръка."
    if bearish > bullish:
        return "Преобладават мечи сигнали от Strategy Lab — информативно, не препоръка."
    return "Смесени или неутрални сигнали — няма ясна преобладаваща насока."


def _format_research_report(snapshot, signals, evidence, ai_text, provider) -> str:
    lines = [f"🔎 PHOENIX RESEARCH — {snapshot.symbol}", ""]

    lines.append("📊 MARKET")
    if snapshot.market is not None:
        m = snapshot.market
        change_str = f"{m.change_24h_pct:+.2f}%" if m.change_24h_pct is not None else "неизвестна"
        lines.append(f"Цена: {m.price_usd} USD | 24ч: {change_str}")
    else:
        lines.append("Не е налично.")
    lines.append("")

    lines.append("📰 WHAT'S HAPPENING")
    if snapshot.top_news is not None:
        lines.append(f"\"{snapshot.top_news.title}\"")
    else:
        lines.append("Няма налична новина в момента.")
    lines.append("")

    lines.append("📈 SIGNALS")
    if signals:
        for s in signals.values():
            icon = _STRATEGY_SIGNAL_ICONS.get(s.signal, "⚪")
            lines.append(f"{icon} {s.strategy_name}: {s.reasoning}")
    else:
        lines.append("Не е налично.")
    lines.append("")

    lines.append("⚠️ RISKS")
    lines.append("Пазарът на криптовалути е силно волатилен — цената може рязко да се промени без предупреждение.")
    lines.append("")

    lines.append("🔎 EVIDENCE")
    lines.append(f"Налични: {', '.join(evidence.available_sources) or 'няма'}")
    if evidence.missing_sources:
        lines.append(f"Липсващи: {', '.join(evidence.missing_sources)}")
    lines.append("")

    source_names = []
    if snapshot.top_news is not None and snapshot.top_news.source:
        source_names.append(snapshot.top_news.source)
    source_names.append("CoinGecko")
    source_names.append("alternative.me (Fear & Greed)")
    lines.append("📚 SOURCES")
    lines.append(", ".join(source_names))
    lines.append("")

    lines.append("🧠 AI ANALYSIS")
    lines.append(ai_text)
    lines.append("")

    lines.append("🎯 CONCLUSION")
    lines.append(_derive_research_conclusion(signals))
    lines.append("")

    lines.append(
        f"CONFIDENCE: {evidence.confidence} ({evidence.coverage_fraction} източника — "
        "отразява покритие на данните, не истинност)"
    )
    lines.append(f"Provider: {provider}")

    return "\n".join(lines)


async def cmd_research(args: List[str], context: CommandContext, container: Container) -> str:
    """Phoenix's first Skill-driven command (crypto-research Skill,
    skills/research/crypto-research/SKILL.md). Thin Telegram adapter —
    all orchestration lives in phoenix_core.services.research.
    research_capability.run_research (TASK-023 P1 #1), so the same
    business logic is callable independently of Telegram. This function
    only maps ResearchResult / errors to the existing response strings,
    preserving the exact prior /research output and error messages."""
    if not args:
        return _MSG_RESEARCH_USAGE

    symbol = args[0].strip().lower()

    try:
        result = await run_research(
            symbol=symbol,
            container=container,
            build_prompt=_build_research_prompt,
            user_id=context.user_id,
        )
    except ResearchUnavailableError as e:
        if "market_intel_aggregator" in str(e):
            return _MSG_RESEARCH_INTEL_UNAVAILABLE
        return _MSG_AI_UNAVAILABLE
    except ResearchNoDataError:
        return _MSG_RESEARCH_NO_DATA
    except ResearchAIError as e:
        return {
            "rate_limit": _MSG_AI_RATE_LIMIT,
            "invalid_input": _MSG_INVALID_INPUT,
            "context_too_large": _MSG_CONTEXT_TOO_LARGE,
            "not_configured": _MSG_AI_NOT_CONFIGURED,
            "provider_not_found": _MSG_AI_PROVIDER_NOT_FOUND,
            "timeout": _MSG_AI_TIMEOUT,
            "connection": _MSG_AI_CONNECTION,
            "generic_error": _MSG_AI_GENERIC_ERROR,
        }.get(e.reason, _MSG_AI_GENERIC_ERROR)

    return _format_research_report(
        result.snapshot, result.signals, result.evidence, result.ai_text, result.provider
    )
