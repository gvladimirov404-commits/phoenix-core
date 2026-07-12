"""
V1 bootstrap stub for the plugin system.

This module contains no business logic. It exists so that
phoenix_core.core.application and phoenix_core.cli can import and
instantiate PluginRegistry without raising ModuleNotFoundError. No plugin
discovery, loading, or installation is performed by this module. That
functionality is out of scope for the V1 bootstrap task and is
intentionally not implemented here.
"""
from typing import Any, Dict, List, Optional

from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)


class PluginRegistry:
    """Registry for discovering and managing plugins.

    V1 stub: stores configuration only. No plugin discovery or loading is
    performed yet.
    """

    def __init__(
        self,
        directories: Optional[List[str]] = None,
        auto_load: bool = False,
    ):
        """Store plugin configuration only (V1 stub — no discovery/loading happens here).

        Args:
            directories: Directories that would be scanned for plugins once implemented.
            auto_load: Whether plugins would be auto-loaded on startup once implemented.
        """
        self.directories = directories or []
        self.auto_load = auto_load
        self._plugins: Dict[str, Any] = {}

    async def start(self) -> None:
        """Lifecycle no-op."""
        logger.debug("PluginRegistry.start() called (stub)", auto_load=self.auto_load)

    async def stop(self) -> None:
        """Lifecycle no-op."""
        logger.debug("PluginRegistry.stop() called (stub)")

    async def health_check(self) -> Dict[str, Any]:
        """Report the stub status (plugin system is not implemented yet)."""
        return {
            "status": "unknown",
            "detail": "PluginRegistry is a V1 stub; plugin system is not implemented yet",
        }

    def list_plugins(self) -> List[Dict[str, str]]:
        """Not implemented yet (V1 stub) — always raises NotImplementedError."""
        raise NotImplementedError(
            "Plugin discovery is not implemented yet (V1 stub)"
        )

    def install(self, plugin_name: str) -> None:
        """Not implemented yet (V1 stub) — always raises NotImplementedError."""
        raise NotImplementedError(
            "Plugin installation is not implemented yet (V1 stub)"
        )
