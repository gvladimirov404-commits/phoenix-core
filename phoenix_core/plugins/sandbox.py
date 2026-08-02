"""Static and runtime guardrails applied to plugin code when
settings.plugins.sandboxed is enabled (Sandbox Mode roadmap item).

This is source-level and runtime-level protection, not OS-level process
isolation — it blocks the most common ways a plugin file could do
something dangerous (importing os/subprocess/socket, calling
open/eval/exec/__import__) and caps how long a plugin's command handler
is allowed to run. It does not protect against every possible attack;
it raises the bar for accidental or careless plugin code, which is the
realistic threat model for a solo-maintained plugin directory, not a
guarantee against a deliberately malicious one.
"""
import asyncio
import ast
from typing import Callable

ALLOWED_MODULES = {
    "typing",
    "dataclasses",
    "math",
    "json",
    "re",
    "datetime",
    "decimal",
    "collections",
}

FORBIDDEN_CALLS = {"eval", "exec", "compile", "open", "__import__"}


class PluginSecurityError(Exception):
    """Raised when a plugin's source code violates the sandbox policy."""


def validate_plugin_source(source: str, filename: str) -> None:
    """Parse a plugin file's source and reject it if it imports a
    non-whitelisted module or calls a forbidden builtin. Raises
    PluginSecurityError on any violation; does nothing on a clean file.
    phoenix_core.* imports are always allowed (trusted internal code)."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        raise PluginSecurityError(f"Syntax error: {e}") from e

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(alias.name, filename)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                _check_module(node.module, filename)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                raise PluginSecurityError(
                    f"{filename} calls forbidden builtin '{func.id}'"
                )


def _check_module(module_name: str, filename: str) -> None:
    top_level = module_name.split(".")[0]
    if top_level == "phoenix_core" or top_level in ALLOWED_MODULES:
        return
    raise PluginSecurityError(f"{filename} imports disallowed module '{module_name}'")


def wrap_handler_with_timeout(handler: Callable, timeout_seconds: float = 10.0) -> Callable:
    """Return an async wrapper that cancels `handler` if it runs longer
    than timeout_seconds, returning a friendly message instead of hanging
    the bot forever on a runaway plugin command."""

    async def wrapped(args, context, container):
        try:
            return await asyncio.wait_for(handler(args, context, container), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return "⚠️ Плъгин командата отне твърде дълго време и беше прекратена."

    return wrapped


class SandboxedDispatcherProxy:
    """Wraps a CommandDispatcher so every command a plugin registers
    through it automatically gets a timeout guard, without the plugin
    itself needing to know or cooperate."""

    def __init__(self, dispatcher, timeout_seconds: float = 10.0) -> None:
        self._dispatcher = dispatcher
        self._timeout_seconds = timeout_seconds

    def register(self, name: str, handler: Callable, description: str = "") -> None:
        self._dispatcher.register(
            name, wrap_handler_with_timeout(handler, self._timeout_seconds), description
        )
