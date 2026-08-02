"""Unit tests for phoenix_core.plugins.registry.PluginRegistry and
phoenix_core.plugins.base.PhoenixPlugin (Plugin System roadmap item)."""
import pytest

from phoenix_core.plugins.base import PhoenixPlugin
from phoenix_core.plugins.registry import PluginRegistry


class FakeDispatcher:
    """Minimal test double for CommandDispatcher — just records calls."""

    def __init__(self) -> None:
        self.registered = []

    def register(self, name, handler, description) -> None:
        self.registered.append((name, handler, description))


_VALID_PLUGIN_SOURCE = '''\
from phoenix_core.plugins.base import PhoenixPlugin

class PingPlugin(PhoenixPlugin):
    @property
    def name(self) -> str:
        return "ping"

    @property
    def description(self) -> str:
        return "Replies with pong"

    def register_commands(self, dispatcher) -> None:
        dispatcher.register("ping", lambda *a: "pong", self.description)

PLUGIN = PingPlugin()
'''

_FAILING_REGISTRATION_PLUGIN_SOURCE = '''\
from phoenix_core.plugins.base import PhoenixPlugin

class FailingPlugin(PhoenixPlugin):
    @property
    def name(self) -> str:
        return "failing"

    def register_commands(self, dispatcher) -> None:
        raise RuntimeError("boom")

PLUGIN = FailingPlugin()
'''


class TestPhoenixPluginBase:
    def test_cannot_instantiate_abstract_base_directly(self) -> None:
        with pytest.raises(TypeError):
            PhoenixPlugin()

    def test_description_defaults_to_empty_string(self) -> None:
        class MinimalPlugin(PhoenixPlugin):
            @property
            def name(self) -> str:
                return "minimal"

            def register_commands(self, dispatcher) -> None:
                pass

        assert MinimalPlugin().description == ""

    def test_subclass_can_override_description(self) -> None:
        class DescribedPlugin(PhoenixPlugin):
            @property
            def name(self) -> str:
                return "described"

            @property
            def description(self) -> str:
                return "Has a description"

            def register_commands(self, dispatcher) -> None:
                pass

        assert DescribedPlugin().description == "Has a description"


class TestPluginRegistryConstruction:
    def test_defaults(self) -> None:
        registry = PluginRegistry()
        assert registry.directories == []
        assert registry.auto_load is False

    def test_custom_directories_and_auto_load(self) -> None:
        registry = PluginRegistry(directories=["plugins"], auto_load=True)
        assert registry.directories == ["plugins"]
        assert registry.auto_load is True


class TestDiscover:
    def test_no_directories_configured(self) -> None:
        registry = PluginRegistry()
        registry.discover()
        assert registry.list_plugins() == []

    def test_nonexistent_directory_is_skipped_without_crashing(self, tmp_path) -> None:
        registry = PluginRegistry(directories=[str(tmp_path / "does_not_exist")])
        registry.discover()
        assert registry.list_plugins() == []

    def test_loads_a_valid_plugin_file(self, tmp_path) -> None:
        (tmp_path / "ping_plugin.py").write_text(_VALID_PLUGIN_SOURCE)
        registry = PluginRegistry(directories=[str(tmp_path)])
        registry.discover()
        assert registry.list_plugins() == [{"name": "ping", "description": "Replies with pong"}]

    def test_files_starting_with_underscore_are_skipped(self, tmp_path) -> None:
        (tmp_path / "_helper.py").write_text("PLUGIN = None\n")
        registry = PluginRegistry(directories=[str(tmp_path)])
        registry.discover()
        assert registry.list_plugins() == []

    def test_file_missing_plugin_variable_is_isolated_as_a_load_error(self, tmp_path) -> None:
        (tmp_path / "broken.py").write_text("x = 1\n")
        registry = PluginRegistry(directories=[str(tmp_path)])
        registry.discover()
        assert registry.list_plugins() == []

    def test_file_with_wrong_plugin_type_is_isolated(self, tmp_path) -> None:
        (tmp_path / "wrong_type.py").write_text("PLUGIN = object()\n")
        registry = PluginRegistry(directories=[str(tmp_path)])
        registry.discover()
        assert registry.list_plugins() == []

    def test_syntax_error_in_plugin_file_is_isolated(self, tmp_path) -> None:
        (tmp_path / "syntax_error.py").write_text("def broken(:\n")
        registry = PluginRegistry(directories=[str(tmp_path)])
        registry.discover()  # must not raise
        assert registry.list_plugins() == []

    def test_one_broken_file_does_not_block_a_valid_one(self, tmp_path) -> None:
        (tmp_path / "broken.py").write_text("x = 1\n")
        (tmp_path / "ping_plugin.py").write_text(_VALID_PLUGIN_SOURCE)
        registry = PluginRegistry(directories=[str(tmp_path)])
        registry.discover()
        assert [p["name"] for p in registry.list_plugins()] == ["ping"]


class TestRegisterAllCommands:
    def test_registers_commands_from_loaded_plugins(self, tmp_path) -> None:
        (tmp_path / "ping_plugin.py").write_text(_VALID_PLUGIN_SOURCE)
        registry = PluginRegistry(directories=[str(tmp_path)])
        registry.discover()

        dispatcher = FakeDispatcher()
        registry.register_all_commands(dispatcher)

        assert len(dispatcher.registered) == 1
        name, _handler, description = dispatcher.registered[0]
        assert name == "ping"
        assert description == "Replies with pong"

    def test_one_plugin_registration_failure_does_not_block_others(self, tmp_path) -> None:
        (tmp_path / "failing_plugin.py").write_text(_FAILING_REGISTRATION_PLUGIN_SOURCE)
        (tmp_path / "ping_plugin.py").write_text(_VALID_PLUGIN_SOURCE)
        registry = PluginRegistry(directories=[str(tmp_path)])
        registry.discover()

        dispatcher = FakeDispatcher()
        registry.register_all_commands(dispatcher)  # must not raise

        assert [name for name, _h, _d in dispatcher.registered] == ["ping"]


class TestHealthCheck:
    async def test_status_configured_when_no_plugins_and_no_errors(self) -> None:
        registry = PluginRegistry()
        health = await registry.health_check()
        assert health["status"] == "configured"
        assert health["loaded"] == []
        assert health["errors"] == {}

    async def test_status_healthy_when_plugins_loaded_without_errors(self, tmp_path) -> None:
        (tmp_path / "ping_plugin.py").write_text(_VALID_PLUGIN_SOURCE)
        registry = PluginRegistry(directories=[str(tmp_path)])
        registry.discover()
        health = await registry.health_check()
        assert health["status"] == "healthy"
        assert health["loaded"] == ["ping"]

    async def test_status_misconfigured_when_any_load_error_exists(self, tmp_path) -> None:
        (tmp_path / "broken.py").write_text("x = 1\n")
        registry = PluginRegistry(directories=[str(tmp_path)])
        registry.discover()
        health = await registry.health_check()
        assert health["status"] == "misconfigured"
        assert "broken.py" in health["errors"]

    async def test_lifecycle_hooks_do_not_raise(self) -> None:
        registry = PluginRegistry()
        await registry.start()
        await registry.stop()


class TestInstall:
    def test_install_raises_not_implemented(self) -> None:
        registry = PluginRegistry()
        with pytest.raises(NotImplementedError):
            registry.install("some-plugin")
