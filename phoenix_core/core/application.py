"""
Main application class that orchestrates all components.
Implements the Facade pattern for simplified interaction.
"""
import asyncio
import signal
from typing import Any, Dict, List, Optional

from phoenix_core.ai.router import AIRouter
from phoenix_core.config.settings import Settings
from phoenix_core.core.container import Container
from phoenix_core.github.client import GitHubClient
from phoenix_core.guard.cost_guard import CostGuard
from phoenix_core.guard.guard import AIGuard
from phoenix_core.guard.rate_limiter import RateLimiter
from phoenix_core.guard.retry import RetryPolicy
from phoenix_core.guard.sanitizer import OutputSanitizer
from phoenix_core.services.crypto.coingecko_provider import CoinGeckoProvider
from phoenix_core.services.intel.feargreed_provider import AlternativeMeFearGreedProvider
from phoenix_core.services.intel.fees_provider import MempoolSpaceFeesProvider
from phoenix_core.services.intel.aggregator import MarketIntelligenceAggregator
from phoenix_core.services.intel.news_provider import GoogleNewsRSSProvider
from phoenix_core.services.intel.news_provider import CryptoPanicNewsProvider
from phoenix_core.services.watchlist.manager import WatchlistManager
from phoenix_core.memory.context_builder import ContextBuilder
from phoenix_core.memory.manager import ConversationManager
from phoenix_core.plugins.registry import PluginRegistry
from phoenix_core.telegram.bot import TelegramBot
from phoenix_core.utils.logger import configure_logging, get_logger
from phoenix_core.utils.exceptions import PhoenixError, StorageError
from phoenix_core.services.research.snapshot_store import SQLiteSnapshotStore
from phoenix_core.services.research.alert_cooldown_store import SQLiteAlertCooldownStore
from phoenix_core.services.research.alert_service import AlertService
from phoenix_core.services.research.alert_scheduler import AlertScheduler
from phoenix_core.services.notifications.telegram_notification import TelegramNotificationService

logger = get_logger(__name__)


class PhoenixApplication:
    """Main application orchestrator"""
    def __init__(self, settings: Settings) -> None:
        """Configure logging and build the DI container from settings.

        Args:
            settings: Fully loaded application Settings.
        """
        self.settings = settings
        self.container = Container()
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None
        self._components: List[Any] = []

        configure_logging(
            level=settings.logging.level,
            format_type=settings.logging.format,
            file_path=settings.logging.file_path,
            max_bytes=settings.logging.max_bytes,
            backup_count=settings.logging.backup_count,
            enable_console=settings.logging.enable_console,
        )

        logger.info("Initializing Phoenix Core", app_version=settings.app_version)
        self._initialize_container()

    def _initialize_container(self) -> None:
        """Register all services in the DI container"""
        self.container.register("settings", self.settings)
        # Registered so components (e.g. Telegram command handlers) can reuse
        # this application's health_check() instead of re-aggregating it themselves.
        self.container.register("application", self)

        ai_router = AIRouter(
            self.settings.ai_providers,
            self.settings.ai_default_provider
        )
        self.container.register("ai_router", ai_router)
        self._components.append(ai_router)

        if self.settings.memory_backend != "sqlite":
            logger.warning(
                "Unsupported MEMORY_BACKEND configured — falling back to sqlite",
                requested_backend=self.settings.memory_backend,
            )

        try:
            conversation_manager = ConversationManager(
                max_messages=self.settings.ai_max_conversation_messages,
                db_path=self.settings.sqlite_database,
            )
        except StorageError as e:
            # A corrupted/unreadable database file must not take down the
            # whole app (Task 013, Задача 5 — "повредена SQLite база").
            # Degrade to an isolated in-memory conversation store so every
            # other component (Telegram, AI, GitHub) still starts normally;
            # conversation history just won't persist across restarts until
            # this is fixed on disk.
            logger.error(
                "Conversation storage unavailable, falling back to in-memory (no persistence)",
                database_path=self.settings.sqlite_database,
                error=str(e),
            )
            conversation_manager = ConversationManager(
                max_messages=self.settings.ai_max_conversation_messages,
            )
        self.container.register("conversation_manager", conversation_manager)
        self._components.append(conversation_manager)

        context_builder = ContextBuilder(max_context_chars=self.settings.ai_max_context_chars)
        self.container.register("context_builder", context_builder)

        ai_guard = AIGuard(
            rate_limiter=RateLimiter(
                max_requests=self.settings.ai_rate_limit_requests,
                window_seconds=self.settings.ai_rate_limit_window,
            ),
            cost_guard=CostGuard(
                max_prompt_chars=self.settings.ai_max_prompt_length,
                max_context_chars=self.settings.ai_guard_max_context_chars,
            ),
            retry_policy=RetryPolicy(max_retries=self.settings.ai_guard_max_retries),
            sanitizer=OutputSanitizer(),
        )
        self.container.register("ai_guard", ai_guard)
        self._components.append(ai_guard)

        if self.settings.crypto.enabled:
            crypto_provider = CoinGeckoProvider(
                base_url=self.settings.crypto.base_url,
                timeout=self.settings.crypto.timeout,
                max_retries=self.settings.crypto.max_retries,
                cache_ttl_seconds=self.settings.crypto.cache_ttl_seconds,
            )
            self.container.register("crypto_provider", crypto_provider)
            self._components.append(crypto_provider)

            # Fear & Greed and Bitcoin fees need no API key, so they ride on
            # the same enable flag as the rest of the crypto market-data
            # surface (Task 020) rather than needing their own config toggle.
            feargreed_provider = AlternativeMeFearGreedProvider(
                timeout=self.settings.crypto.timeout,
                max_retries=self.settings.crypto.max_retries,
            )
            self.container.register("feargreed_provider", feargreed_provider)
            self._components.append(feargreed_provider)

            fees_provider = MempoolSpaceFeesProvider(timeout=self.settings.crypto.timeout,
                max_retries=self.settings.crypto.max_retries,
            )
            self.container.register("fees_provider", fees_provider)
            self._components.append(fees_provider)

        if self.settings.news.enabled:
            # CryptoPanic's API is blocked by Cloudflare bot protection from
            # this environment (see project notes) — GoogleNewsRSSProvider
            # is a free, keyless, reliably-accessible replacement with the
            # same NewsProvider interface. No token required anymore.
            news_provider = GoogleNewsRSSProvider(
                timeout=self.settings.news.timeout,
                max_retries=self.settings.news.max_retries,
                cache_ttl_seconds=self.settings.news.cache_ttl_seconds,
            )
            self.container.register("news_provider", news_provider)
            self._components.append(news_provider)

        try:
            _crypto_provider_for_intel = self.container.resolve("crypto_provider")
        except KeyError:
            _crypto_provider_for_intel = None
        if _crypto_provider_for_intel is not None:
            try:
                _feargreed_for_intel = self.container.resolve("feargreed_provider")
            except KeyError:
                _feargreed_for_intel = None
            try:
                _fees_for_intel = self.container.resolve("fees_provider")
            except KeyError:
                _fees_for_intel = None
            try:
                _news_for_intel = self.container.resolve("news_provider")
            except KeyError:
                _news_for_intel = None

            market_intel_aggregator = MarketIntelligenceAggregator(
                crypto_provider=_crypto_provider_for_intel,
                feargreed_provider=_feargreed_for_intel,
                fees_provider=_fees_for_intel,
                news_provider=_news_for_intel,
            )
            self.container.register("market_intel_aggregator", market_intel_aggregator)

        try:
            watchlist_manager = WatchlistManager(db_path=self.settings.sqlite_database)
        except StorageError as e:
            # Same degrade-rather-than-crash contract as conversation_manager
            # above (Task 013 precedent) — /watch still works, just without
            # persistence across restarts until the file is fixed.
            logger.error(
                "Watchlist storage unavailable, falling back to in-memory (no persistence)",
                database_path=self.settings.sqlite_database,
                error=str(e),
            )
            watchlist_manager = WatchlistManager()
        self.container.register("watchlist_manager", watchlist_manager)
        self._components.append(watchlist_manager)

        if self.settings.telegram.bot_token.get_secret_value():
            telegram_bot = TelegramBot(
                token=self.settings.telegram.bot_token.get_secret_value(),
                settings=self.settings.telegram,
                container=self.container,
            )
            self.container.register("telegram_bot", telegram_bot)
            self._components.append(telegram_bot)

        if self.settings.github.token.get_secret_value():
            github_client = GitHubClient(
                token=self.settings.github.token.get_secret_value(),
                settings=self.settings.github,
            )
            self.container.register("github_client", github_client)
            self._components.append(github_client)

        plugin_registry = PluginRegistry(
            directories=self.settings.plugins.directories,
            auto_load=self.settings.plugins.auto_load,
            sandboxed=self.settings.plugins.sandboxed,
        )
        self.container.register("plugin_registry", plugin_registry)
        if plugin_registry.auto_load:
            plugin_registry.discover()
            try:
                _plugin_dispatcher = self.container.resolve("command_dispatcher")
            except KeyError:
                _plugin_dispatcher = None
            if _plugin_dispatcher is not None:
                plugin_registry.register_all_commands(_plugin_dispatcher)
        self._components.append(plugin_registry)

        # Alert pipeline (Task 023 Phase G) — conditional on crypto being
        # enabled (needs market_intel_aggregator), the alert feature flag,
        # and telegram_bot being configured (needs a notification channel).
        # Any missing piece degrades to "alerts disabled", never a crash.
        if self.settings.alerts.enabled and self.settings.crypto.enabled:
            try:
                snapshot_store = SQLiteSnapshotStore(db_path=self.settings.sqlite_database)
                snapshot_store.initialize()
                alert_cooldown_store = SQLiteAlertCooldownStore(db_path=self.settings.sqlite_database)
                alert_cooldown_store.initialize()
            except StorageError as e:
                logger.error(
                    "Alert storage unavailable, alert pipeline disabled",
                    database_path=self.settings.sqlite_database,
                    error=str(e),
                )
                snapshot_store = None
                alert_cooldown_store = None

            if snapshot_store is not None and alert_cooldown_store is not None:
                self.container.register("snapshot_store", snapshot_store)

                try:
                    _aggregator_for_alerts = self.container.resolve("market_intel_aggregator")
                except KeyError:
                    _aggregator_for_alerts = None

                try:
                    _telegram_bot_for_alerts = self.container.resolve("telegram_bot")
                except KeyError:
                    _telegram_bot_for_alerts = None

                if _aggregator_for_alerts is not None and _telegram_bot_for_alerts is not None:
                    notification_service = TelegramNotificationService(_telegram_bot_for_alerts)
                    self.container.register("notification_service", notification_service)

                    alert_service = AlertService(
                        aggregator=_aggregator_for_alerts,
                        snapshot_store=snapshot_store,
                        cooldown_store=alert_cooldown_store,
                        watchlist_manager=watchlist_manager,
                        notification_service=notification_service,
                        cooldown_seconds=self.settings.alerts.cooldown_seconds,
                    )
                    self.container.register("alert_service", alert_service)

                    alert_scheduler = AlertScheduler(
                        alert_service=alert_service,
                        interval_seconds=self.settings.alerts.poll_interval_seconds,
                    )
                    self.container.register("alert_scheduler", alert_scheduler)
                    self._components.append(alert_scheduler)
                else:
                    logger.warning(
                        "Alert pipeline disabled: market intelligence or Telegram bot not available"
                    )

        logger.info("Container initialized with all services")

    async def start(self) -> None:
        """Start the application and all components"""
        self._running = True
        self._shutdown_event = asyncio.Event()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._signal_handler, sig)

        logger.info("Starting Phoenix Core components...")

        try:
            for component in self._components:
                if hasattr(component, "start"):
                    logger.debug("Starting component", component=component.__class__.__name__)
                    await component.start()

            logger.info("Phoenix Core is running. Press Ctrl+C to stop.")

            await self._shutdown_event.wait()

        except Exception as e:
            logger.error("Application error", error=str(e))
            raise PhoenixError(f"Application failed: {e}") from e
        finally:
            await self.stop()

    def _signal_handler(self, sig: signal.Signals) -> None:
        """Handle shutdown signals.

        Logs which specific signal triggered the shutdown (Task 017) — this
        distinguishes a deliberate Ctrl+C (SIGINT) from the process being
        terminated externally (SIGTERM, e.g. Android/Termux killing the
        session or app in the background), which was previously
        indistinguishable in the logs.
        """
        logger.info("Shutdown signal received", signal=sig.name)
        if self._shutdown_event:
            self._shutdown_event.set()

    async def stop(self) -> None:
        """Stop the application and all components"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping Phoenix Core...")

        for component in reversed(self._components):
            if hasattr(component, "stop"):
                try:
                    logger.debug("Stopping component", component=component.__class__.__name__)
                    await component.stop()
                except Exception as e:
                    logger.error(
                        "Error stopping component",
                        component=component.__class__.__name__,
                        error=str(e),
                    )

        logger.info("Phoenix Core stopped")

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all components"""
        health: Dict[str, Any] = {"status": "healthy", "components": {}}

        for component in self._components:
            name = component.__class__.__name__
            try:
                if hasattr(component, "health_check"):
                    component_health = await component.health_check()
                    health["components"][name] = component_health
                else:
                    health["components"][name] = {"status": "unknown"}
            except Exception as e:
                health["components"][name] = {"status": "unhealthy", "error": str(e)}
                health["status"] = "unhealthy"

        return health
