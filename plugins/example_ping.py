"""Example plugin — proves the Plugin System works end-to-end.

Drop any .py file like this one into a directory listed under
settings.plugins.directories (default: "plugins") and it will be
discovered, loaded, and its commands registered automatically on startup.
"""
from phoenix_core.plugins.base import PhoenixPlugin


class PingPlugin(PhoenixPlugin):
    @property
    def name(self) -> str:
        return "ping"

    @property
    def description(self) -> str:
        return "Example plugin — replies with pong to prove the plugin system works"

    def register_commands(self, dispatcher) -> None:
        dispatcher.register("ping", self.cmd_ping, "Example plugin command")

    async def cmd_ping(self, args, context, container) -> str:
        return "🏓 pong! Plugin system works."


PLUGIN = PingPlugin()
