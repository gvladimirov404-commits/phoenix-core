"""Unit tests for phoenix_core.telegram.dispatcher.CommandDispatcher."""
from phoenix_core.core.container import Container
from phoenix_core.telegram.context import CommandContext
from phoenix_core.telegram.dispatcher import CommandDispatcher


def make_context(user_id: int = 1, chat_id: int = 1) -> CommandContext:
    return CommandContext(user_id=user_id, chat_id=chat_id)


async def ok_handler(args, context, container):
    return f"ok:{','.join(args)}"


async def boom_handler(args, context, container):
    raise RuntimeError("some internal detail that must not leak")


class TestRegistrationAndListing:
    def test_register_and_list_commands(self) -> None:
        dispatcher = CommandDispatcher()
        dispatcher.register("start", ok_handler, "Greeting")
        dispatcher.register("help", ok_handler, "List commands")

        commands = dispatcher.list_commands()

        assert commands == [("help", "List commands"), ("start", "Greeting")]

    def test_list_commands_empty_when_none_registered(self) -> None:
        dispatcher = CommandDispatcher()
        assert dispatcher.list_commands() == []


class TestDispatch:
    async def test_dispatch_calls_registered_handler_with_args(self) -> None:
        dispatcher = CommandDispatcher()
        dispatcher.register("greet", ok_handler, "Greeting")
        container = Container()

        result = await dispatcher.dispatch("greet", ["a", "b"], make_context(), container)

        assert result == "ok:a,b"

    async def test_dispatch_unknown_command_returns_friendly_message(self) -> None:
        dispatcher = CommandDispatcher()
        container = Container()

        result = await dispatcher.dispatch("does-not-exist", [], make_context(), container)

        assert "Непозната команда" in result

    async def test_dispatch_handler_exception_returns_generic_friendly_message(self) -> None:
        dispatcher = CommandDispatcher()
        dispatcher.register("boom", boom_handler, "Explodes")
        container = Container()

        result = await dispatcher.dispatch("boom", [], make_context(), container)

        assert "some internal detail" not in result
        assert "Traceback" not in result
        assert "грешка" in result

    async def test_dispatch_passes_the_same_container_through(self) -> None:
        dispatcher = CommandDispatcher()
        container = Container()
        container.register("marker", "expected-value")

        async def handler(args, context, container):
            return container.resolve("marker")

        dispatcher.register("check", handler, "Container passthrough check")

        result = await dispatcher.dispatch("check", [], make_context(), container)

        assert result == "expected-value"

    async def test_dispatch_passes_the_context_through(self) -> None:
        dispatcher = CommandDispatcher()
        container = Container()

        async def handler(args, context, container):
            return f"user:{context.user_id}"

        dispatcher.register("whoami", handler, "Echo caller id")

        result = await dispatcher.dispatch("whoami", [], make_context(user_id=42), container)

        assert result == "user:42"
