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
from phoenix_core.memory.context_builder import ContextBuilder
from phoenix_core.memory.manager import ConversationManager
from phoenix_core.plugins.registry import PluginRegistry
from phoenix_core.telegram.bot import TelegramBot
from phoenix_core.utils.logger import configure_logging, get_logger
from phoenix_core.utils.exceptions import PhoenixError, StorageError

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
        )
        self.container.register("plugin_registry", plugin_registry)
        self._components.append(plugin_registry)

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
