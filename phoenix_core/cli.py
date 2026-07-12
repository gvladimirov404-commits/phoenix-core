"""
Command-line interface for Phoenix Core.
"""
import asyncio
import sys
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from phoenix_core._version import __version__
from phoenix_core.config.settings import Settings
from phoenix_core.core.application import PhoenixApplication
from phoenix_core.utils.logger import get_logger

console = Console()
logger = get_logger(__name__)


@click.group()
@click.version_option(version=__version__, prog_name="phoenix")
@click.option("--config", "-c", type=click.Path(), help="Path to configuration file")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx: click.Context, config: Optional[str], verbose: bool) -> None:
    """Phoenix Core - Production-Ready Modular Framework"""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    ctx.obj["verbose"] = verbose

    if verbose:
        console.print("[dim]Verbose mode enabled[/dim]")


@cli.command()
@click.pass_context
def start(ctx: click.Context) -> None:
    """Start the Phoenix Core application"""
    config_path = ctx.obj.get("config_path")
    verbose = ctx.obj.get("verbose", False)

    # Display banner
    banner = Text()
    banner.append("🔥 ", style="bold red")
    banner.append("Phoenix Core", style="bold yellow")
    banner.append(f" v{__version__}", style="dim")
    console.print(Panel(banner, border_style="red"))

    async def _run() -> None:
        settings = Settings.load(config_path)
        app = PhoenixApplication(settings)
        await app.start()

    try:
        asyncio.run(_run())
    except Exception as e:
        logger.error("Failed to start application", error=str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--host", default="0.0.0.0", help="Health check host")
@click.option("--port", default=8080, type=int, help="Health check port")
def health(host: str, port: int) -> None:
    """Run health check server"""
    from phoenix_core.utils.health import HealthServer

    server = HealthServer(host=host, port=port)
    asyncio.run(server.start())


@cli.command()
def plugins() -> None:
    """List available plugins"""
    from phoenix_core.plugins.registry import PluginRegistry

    registry = PluginRegistry()
    available = registry.list_plugins()

    console.print("[bold]Available Plugins:[/bold]")
    for plugin in available:
        console.print(f"  • {plugin['name']} - {plugin['description']}")


@cli.command()
@click.argument("plugin_name")
def install_plugin(plugin_name: str) -> None:
    """Install a plugin"""
    from phoenix_core.plugins.registry import PluginRegistry

    registry = PluginRegistry()
    try:
        registry.install(plugin_name)
        console.print(f"[green]Plugin '{plugin_name}' installed successfully[/green]")
    except Exception as e:
        console.print(f"[red]Failed to install plugin: {e}[/red]")


def main() -> None:
    """Main entry point (sync so console_scripts / `python -m` can call it directly)"""
    cli()


if __name__ == "__main__":
    cli()
