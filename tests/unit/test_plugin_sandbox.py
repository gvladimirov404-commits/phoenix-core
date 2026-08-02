"""Unit tests for phoenix_core.plugins.sandbox (Sandbox Mode roadmap item)."""
import asyncio

import pytest

from phoenix_core.plugins.sandbox import (
    PluginSecurityError,
    SandboxedDispatcherProxy,
    validate_plugin_source,
    wrap_handler_with_timeout,
)


class TestValidatePluginSource:
    def test_allows_whitelisted_stdlib_and_phoenix_core_imports(self) -> None:
        source = (
            "import typing\n"
            "import json\n"
            "from phoenix_core.plugins.base import PhoenixPlugin\n"
            "from phoenix_core.utils.logger import get_logger\n"
        )
        validate_plugin_source(source, "safe.py")  # should not raise

    def test_rejects_disallowed_import(self) -> None:
        source = "import os\n"
        with pytest.raises(PluginSecurityError):
            validate_plugin_source(source, "evil.py")

    def test_rejects_disallowed_import_from(self) -> None:
        source = "from subprocess import run\n"
        with pytest.raises(PluginSecurityError):
            validate_plugin_source(source, "evil.py")

    def test_rejects_forbidden_builtin_call(self) -> None:
        source = "eval('1+1')\n"
        with pytest.raises(PluginSecurityError):
            validate_plugin_source(source, "evil.py")

    def test_rejects_open_call(self) -> None:
        source = "open('/etc/passwd')\n"
        with pytest.raises(PluginSecurityError):
            validate_plugin_source(source, "evil.py")

    def test_rejects_syntax_error(self) -> None:
        source = "def broken(:\n"
        with pytest.raises(PluginSecurityError):
            validate_plugin_source(source, "broken.py")


class TestWrapHandlerWithTimeout:
    @pytest.mark.asyncio
    async def test_fast_handler_returns_normally(self) -> None:
        async def fast(args, context, container):
            return "ok"

        wrapped = wrap_handler_with_timeout(fast, timeout_seconds=5)
        result = await wrapped([], None, None)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_slow_handler_times_out_with_friendly_message(self) -> None:
        async def slow(args, context, container):
            await asyncio.sleep(1)
            return "too late"

        wrapped = wrap_handler_with_timeout(slow, timeout_seconds=0.05)
        result = await wrapped([], None, None)
        assert "твърде дълго" in result


class FakeDispatcher:
    def __init__(self) -> None:
        self.registered = []

    def register(self, name, handler, description=""):
        self.registered.append((name, handler, description))


class TestSandboxedDispatcherProxy:
    def test_register_forwards_name_and_description(self) -> None:
        fake = FakeDispatcher()
        proxy = SandboxedDispatcherProxy(fake)

        async def handler(args, context, container):
            return "hi"

        proxy.register("greet", handler, "Greets the caller")

        assert len(fake.registered) == 1
        name, wrapped_handler, description = fake.registered[0]
        assert name == "greet"
        assert description == "Greets the caller"
        assert wrapped_handler is not handler

    @pytest.mark.asyncio
    async def test_registered_handler_is_timeout_guarded(self) -> None:
        fake = FakeDispatcher()
        proxy = SandboxedDispatcherProxy(fake, timeout_seconds=0.05)

        async def slow(args, context, container):
            await asyncio.sleep(1)
            return "too late"

        proxy.register("slow", slow)
        _, wrapped_handler, _ = fake.registered[0]

        result = await wrapped_handler([], None, None)
        assert "твърде дълго" in result
