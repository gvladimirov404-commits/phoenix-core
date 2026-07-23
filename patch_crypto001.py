#!/usr/bin/env python3
import sys

def patch_file(path, old, new, marker):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if marker in content:
        print(f"SKIP (already patched): {path}")
        return
    if old not in content:
        print(f"ERROR: anchor not found in {path}")
        print(f"  looking for: {old[:80]!r}")
        sys.exit(1)
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"OK: patched {path}")

patch_file(
    "phoenix_core/utils/exceptions.py",
    old='''class ContextTooLargeError(GuardError):
    """Raised when the assembled conversation context exceeds the configured size limit"""
    pass''',
    new='''class ContextTooLargeError(GuardError):
    """Raised when the assembled conversation context exceeds the configured size limit"""
    pass


class CryptoError(PhoenixError):
    """Raised when a crypto market data operation fails (Task CRYPTO-001)"""
    pass


class CryptoConfigurationError(CryptoError):
    pass


class CryptoNotFoundError(CryptoError):
    pass


class CryptoRateLimitError(CryptoError):
    pass


class CryptoTimeoutError(CryptoError):
    pass


class CryptoConnectionError(CryptoError):
    pass


class CryptoInvalidResponseError(CryptoError):
    pass''',
    marker="class CryptoError(PhoenixError):",
)

patch_file(
    "phoenix_core/config/settings.py",
    old='''class Settings(BaseSettings):
    """Main application settings"""''',
    new='''class CryptoConfig(BaseSettings):
    """Crypto market data provider configuration (Task CRYPTO-001)"""
    model_config = SettingsConfigDict(env_prefix="PHOENIX_CRYPTO_")

    enabled: bool = Field(default=True, description="Enable the crypto market data module")
    base_url: Optional[str] = Field(None, description="Override for the CoinGecko API base URL")
    timeout: int = Field(default=15, ge=1, le=120, description="Request timeout in seconds")
    max_retries: int = Field(default=2, ge=0, le=10, description="Max retry attempts for transient failures")
    cache_ttl_seconds: float = Field(default=60.0, ge=1.0, description="How long cached responses stay valid")


class Settings(BaseSettings):
    """Main application settings"""''',
    marker="class CryptoConfig(BaseSettings):",
)

patch_file(
    "phoenix_core/config/settings.py",
    old='''    # Security
    security: SecurityConfig = Field(default_factory=SecurityConfig)''',
    new='''    # Security
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    # Crypto
    crypto: CryptoConfig = Field(default_factory=CryptoConfig)''',
    marker="    crypto: CryptoConfig = Field(default_factory=CryptoConfig)",
)

patch_file(
    "phoenix_core/core/application.py",
    old="from phoenix_core.guard.sanitizer import OutputSanitizer",
    new="from phoenix_core.guard.sanitizer import OutputSanitizer\nfrom phoenix_core.services.crypto.coingecko_provider import CoinGeckoProvider",
    marker="from phoenix_core.services.crypto.coingecko_provider import CoinGeckoProvider",
)

patch_file(
    "phoenix_core/core/application.py",
    old='''        self.container.register("ai_guard", ai_guard)
        self._components.append(ai_guard)''',
    new='''        self.container.register("ai_guard", ai_guard)
        self._components.append(ai_guard)

        if self.settings.crypto.enabled:
            crypto_provider = CoinGeckoProvider(
                base_url=self.settings.crypto.base_url,
                timeout=self.settings.crypto.timeout,
                max_retries=self.settings.crypto.max_retries,
                cache_ttl_seconds=self.settings.crypto.cache_ttl_seconds,
            )
            self.container.register("crypto_provider", crypto_provider)
            self._components.append(crypto_provider)''',
    marker="if self.settings.crypto.enabled:",
)

patch_file(
    "phoenix_core/telegram/bot.py",
    old='        self._dispatcher.register("memory", telegram_commands.cmd_memory, "Статистика за текущия разговор")',
    new='        self._dispatcher.register("memory", telegram_commands.cmd_memory, "Статистика за текущия разговор")\n        self._dispatcher.register("crypto", telegram_commands.cmd_crypto, "Крипто пазарни данни (напр. /crypto btc, /crypto top)")',
    marker='self._dispatcher.register("crypto"',
)

patch_file(
    "phoenix_core/telegram/commands.py",
    old='''from phoenix_core.guard.sanitizer import OutputSanitizer
from phoenix_core.memory.context_builder import ContextBuilder, DEFAULT_MAX_CONTEXT_CHARS''',
    new='''from phoenix_core.guard.sanitizer import OutputSanitizer
from phoenix_core.memory.context_builder import ContextBuilder, DEFAULT_MAX_CONTEXT_CHARS
from phoenix_core.services.crypto.base import CryptoMarket
from phoenix_core.services.crypto.intent import detect_crypto_intent''',
    marker="from phoenix_core.services.crypto.intent import detect_crypto_intent",
)

patch_file(
    "phoenix_core/telegram/commands.py",
    old='''    ContextTooLargeError,
    GitHubAuthenticationError,''',
    new='''    ContextTooLargeError,
    CryptoConnectionError,
    CryptoError,
    CryptoNotFoundError,
    CryptoRateLimitError,
    CryptoTimeoutError,
    GitHubAuthenticationError,''',
    marker="    CryptoNotFoundError,",
)

patch_file(
    "phoenix_core/telegram/commands.py",
    old="logger = get_logger(__name__)",
    new='''logger = get_logger(__name__)

_MSG_CRYPTO_NOT_CONFIGURED = "Крипто модулът не е конфигуриран."
_MSG_CRYPTO_USAGE = "Употреба: /crypto <символ|top>. Пример: /crypto btc"
_MSG_CRYPTO_RATE_LIMIT = "Достигнат е лимитът на заявки към крипто доставчика. Опитай отново след малко."
_MSG_CRYPTO_CONNECTION = "Проблем с връзката към крипто доставчика. Опитай отново."
_MSG_CRYPTO_GENERIC_ERROR = "Възникна грешка при взимане на крипто данни."''',
    marker='_MSG_CRYPTO_NOT_CONFIGURED = "Крипто модулът не е конфигуриран."',
)

patch_file(
    "phoenix_core/telegram/commands.py",
    old="def _resolve_context_builder(container: Container) -> ContextBuilder:",
    new='''def _format_crypto_market(market: CryptoMarket) -> str:
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
    return "\\n".join(lines)


def _format_crypto_top_coins(coins: List[CryptoMarket]) -> str:
    lines = ["🏆 Топ крипто по пазарна капитализация:"]
    for index, coin in enumerate(coins, start=1):
        change = coin.change_24h_pct
        change_str = f"{change:+.2f}%" if change is not None else "—"
        price = f"{coin.price_usd:,.2f} USD" if coin.price_usd is not None else "—"
        lines.append(f"{index}. {coin.name} ({coin.symbol}) — {price} ({change_str})")
    return "\\n".join(lines)


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


def _resolve_context_builder(container: Container) -> ContextBuilder:''',
    marker="async def cmd_crypto(args: List[str], context: CommandContext, container: Container) -> str:",
)

patch_file(
    "phoenix_core/telegram/commands.py",
    old='''    question = " ".join(args)

    try:
        settings = container.resolve("settings")''',
    new='''    question = " ".join(args)

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
        settings = container.resolve("settings")''',
    marker="crypto_intent = detect_crypto_intent(question)",
)

print("\\nAll CRYPTO-001 patches applied successfully.")
