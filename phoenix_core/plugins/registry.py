"""Plugin system — discovers, loads, and registers Python plugins found in
configured directories (Plugin System roadmap item).

A plugin is any .py file in a scanned directory that exposes a module-level
`PLUGIN` variable holding a PhoenixPlugin instance. Loading is best-effort
per file: one broken plugin file is skipped with a logged warning and never
prevents the others from loading or the bot from starting — the same
degrade-rather-than-crash contract used throughout Phoenix Core.
"""
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional

from phoenix_core.plugins.base import PhoenixPlugin
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)


class PluginRegistry:
    """Discovers and loads PhoenixPlugin instances from configured directories,
    and registers each loaded plugin's commands into a CommandDispatcher."""

    def __init__(
        self,
        directories: Optional[List[str]] = None,
        auto_load: bool = False,
    ):
        """Store plugin configuration.

        Args:
            directories: Directories to scan for plugin .py files.
            auto_load: Whether the application should discover and register
                plugins automatically on startup (checked by the caller).
        """
        self.directories = directories or []
        self.auto_load = auto_load
        self._plugins: Dict[str, PhoenixPlugin] = {}
        self._load_errors: Dict[str, str] = {}

    async def start(self) -> None:
        """Lifecycle hook — discovery itself is triggered by the caller
        (see PhoenixApplication) so it can also wire commands into the
        dispatcher; this just logs the current state."""
        logger.debug(
            "PluginRegistry.start() called",
            auto_load=self.auto_load,
            loaded=len(self._plugins),
        )

    async def stop(self) -> None:
        """Lifecycle no-op — plugins hold no resources of their own to release."""
        logger.debug("PluginRegistry.stop() called")

    async def health_check(self) -> Dict[str, Any]:
        """Report how many plugins loaded successfully vs failed."""
        if self._load_errors:
            status = "misconfigured"
        elif self._plugins:
            status = "healthy"
        else:
            status = "configured"
        return {
            "status": status,
            "detail": f"{len(self._plugins)} plugin(s) loaded, {len(self._load_errors)} failed",
            "loaded": list(self._plugins.keys()),
            "errors": dict(self._load_errors),
        }

    def discover(self) -> None:
        """Scan every configured directory for .py files exposing a PLUGIN
        instance, and load each one. Failures are isolated per file — a
        directory that doesn't exist is simply skipped."""
        for directory in self.directories:
            dir_path = Path(directory)
            if not dir_path.is_dir():
                continue
            for py_file in sorted(dir_path.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                self._load_file(py_file)

    def _load_file(self, py_file: Path) -> None:
        """Import a single plugin file and register its PLUGIN instance.
        Any failure (bad syntax, missing PLUGIN, wrong type) is caught and
        recorded rather than propagated, so one bad file never blocks startup."""
        module_name = f"phoenix_plugin_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load spec for {py_file}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            plugin = getattr(module, "PLUGIN", None)
            if plugin is None or not isinstance(plugin, PhoenixPlugin):
                raise ValueError(
                    f"{py_file.name} does not define a PLUGIN instance of PhoenixPlugin"
                )
            self._plugins[plugin.name] = plugin
            logger.info("Plugin loaded", plugin=plugin.name, file=py_file.name)
        except Exception as e:
            logger.warning(
                "Plugin failed to load",
                file=py_file.name,
                error=str(e),
                error_type=type(e).__name__,
            )
            self._load_errors[py_file.name] = str(e)

    def register_all_commands(self, dispatcher) -> None:
        """Register every loaded plugin's commands into the given
        CommandDispatcher. One plugin's registration failure is isolated
        and never blocks the rest from registering."""
        for name, plugin in self._plugins.items():
            try:
                plugin.register_commands(dispatcher)
            except Exception as e:
                logger.warning(
                    "Plugin command registration failed",
                    plugin=name,
                    error=str(e),
                    error_type=type(e).__name__,
                )

    def list_plugins(self) -> List[Dict[str, str]]:
        """Return name/description for every successfully loaded plugin."""
        return [{"name": p.name, "description": p.description} for p in self._plugins.values()]

    def install(self, plugin_name: str) -> None:
        """Not implemented yet — remote/marketplace plugin installation is
        out of scope for this roadmap item; only local directory discovery
        is supported so far."""
        raise NotImplementedError(
            "Remote plugin installation is not implemented yet"
        )
