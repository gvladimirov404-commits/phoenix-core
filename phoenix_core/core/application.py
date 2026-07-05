"""
Main application class that orchestrates all components.
Implements the Facade pattern for simplified interaction.
"""
import asyncio
import signal
from typing import Any, Dict, Optional

from phoenix_core.ai.router import AIRouter
from phoenix_core.config.settings import Settings
from phoenix_core.core.container import Container
from phoenix_core.github.client import GitHubClient
from phoenix_core.plugins.registry import PluginRegistry
from phoenix_core.telegram.bot import TelegramBot
from phoenix_core.utils.logger import configure_logging, get_logger
from phoenix_core.utils.exceptions import PhoenixError

logger = get_logger(__name__)


class PhoenixApplication:
    """Main application orchestrator"""
    def __init__(self, settings: Settings):
        self.settings = settings
        self.container = Container()
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None
        self._components: list = []

        configure_logging(
            level=settings.logging.level,
            format_type=settings.logging.format,
            file_path=settings.logging.file_path,
            max_bytes=settings.logging.max_bytes,
            backup_count=settings.logging.backup_count,
            enable_console=settings.logging.enable_console,
        )

        logger.info(f"Initializing Phoenix Core v{settings.app_version}")
        self._initialize_container()

    def _initialize_container(self) -> None:
        """Register all services in the DI container"""
        self.container.register("settings", self.settings)

        ai_router = AIRouter(
            self.settings.ai_providers,
            self.settings.ai_default_provider
        )
        self.container.register("ai_router", ai_router)
        self._components.append(ai_router)

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

        for sig in (signal.SIGTERM, signal.SIGINT):
            asyncio.get_event_loop().add_signal_handler(sig, self._signal_handler)

        logger.info("Starting Phoenix Core components...")

        try:
            for component in self._components:
                if hasattr(component, "start"):
                    logger.debug(f"Starting component: {component.__class__.__name__}")
                    await component.start()

            logger.info("Phoenix Core is running. Press Ctrl+C to stop.")

            await self._shutdown_event.wait()

        except Exception as e:
            logger.error(f"Application error: {e}")
            raise PhoenixError(f"Application failed: {e}") from e
        finally:
            await self.stop()

    def _signal_handler(self) -> None:
        """Handle shutdown signals"""
        logger.info("Shutdown signal received")
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
                    logger.debug(f"Stopping component: {component.__class__.__name__}")
                    await component.stop()
                except Exception as e:
                    logger.error(f"Error stopping {component.__class__.__name__}: {e}")

        logger.info("Phoenix Core stopped")

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all components"""
        health = {"status": "healthy", "components": {}}

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
