"""Base class every Phoenix plugin must implement (Plugin System roadmap item).

A plugin is a Python file placed in a directory listed under
settings.plugins.directories (default: "plugins" relative to the working
directory). The file must define a module-level `PLUGIN` variable holding
an instance of a PhoenixPlugin subclass — PluginRegistry discovers these
files, imports them, and calls register_commands() on each one to wire its
commands into the running bot's CommandDispatcher.
"""
from abc import ABC, abstractmethod


class PhoenixPlugin(ABC):
    """Minimal contract a plugin must satisfy to be loaded by PluginRegistry."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin name (used as its key in the registry and /plugins list)."""
        ...

    @property
    def description(self) -> str:
        """One-line description shown in /plugins. Optional to override."""
        return ""

    @abstractmethod
    def register_commands(self, dispatcher) -> None:
        """Register this plugin's Telegram commands into the given CommandDispatcher.

        Call dispatcher.register(name, handler, description) for each command
        the plugin provides, exactly like TelegramBot._register_commands does
        for the built-in commands.
        """
        ...
