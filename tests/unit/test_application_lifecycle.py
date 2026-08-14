from unittest.mock import AsyncMock, patch

import pytest

from phoenix_core.config.settings import Settings
from phoenix_core.core.application import PhoenixApplication


@pytest.mark.asyncio
async def test_application_stop_closes_chanify_client() -> None:
    fake_client = AsyncMock()

    with patch(
        "phoenix_core.integrations.chanify.ChanifyClient",
        return_value=fake_client,
    ):
        settings = Settings(
            chanify={
                "enabled": True,
                "api_key": "test-api-key",
            }
        )

        application = PhoenixApplication(settings)

        # The application lifecycle only stops components when it is running.
        application._running = True

        chanify = application.container.resolve("chanify")

        assert chanify.enabled is True
        assert chanify._client is fake_client

        await application.stop()

        fake_client.close.assert_awaited_once()
        assert chanify._client is None
        assert chanify.enabled is False

@pytest.mark.asyncio
async def test_application_stop_stops_components_in_reverse_order() -> None:
    settings = Settings(
        chanify={
            "enabled": False,
            "api_key": "",
        }
    )

    application = PhoenixApplication(settings)

    first = AsyncMock()
    second = AsyncMock()
    third = AsyncMock()

    first.__class__.__name__ = "FirstComponent"
    second.__class__.__name__ = "SecondComponent"
    third.__class__.__name__ = "ThirdComponent"

    application._components = [first, second, third]
    application._running = True

    await application.stop()

    first.stop.assert_awaited_once()
    second.stop.assert_awaited_once()
    third.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_application_stop_continues_after_component_failure() -> None:
    settings = Settings(
        chanify={
            "enabled": False,
            "api_key": "",
        }
    )

    application = PhoenixApplication(settings)

    failing = AsyncMock()
    failing.stop.side_effect = RuntimeError("test failure")

    healthy = AsyncMock()

    application._components = [failing, healthy]
    application._running = True

    await application.stop()

    failing.stop.assert_awaited_once()
    healthy.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_application_stop_is_idempotent_when_not_running() -> None:
    settings = Settings(
        chanify={
            "enabled": False,
            "api_key": "",
        }
    )

    application = PhoenixApplication(settings)

    component = AsyncMock()
    application._components = [component]
    application._running = False

    await application.stop()

    component.stop.assert_not_awaited()

@pytest.mark.asyncio
async def test_application_stop_calls_components_in_reverse_order() -> None:
    settings = Settings(
        chanify={
            "enabled": False,
            "api_key": "",
        }
    )

    application = PhoenixApplication(settings)

    call_order = []

    class Component:
        def __init__(self, name: str) -> None:
            self.name = name

        async def stop(self) -> None:
            call_order.append(self.name)

    first = Component("first")
    second = Component("second")
    third = Component("third")

    application._components = [first, second, third]
    application._running = True

    await application.stop()

    assert call_order == ["third", "second", "first"]
