"""Unit tests for the optional Chanify advertising integration."""

from unittest.mock import AsyncMock, patch

import pytest

from phoenix_core.config.settings import ChanifyConfig
from phoenix_core.integrations.chanify import ChanifyIntegration


def make_config(
    *,
    enabled: bool = False,
    api_key: str = "",
) -> ChanifyConfig:
    return ChanifyConfig(
        enabled=enabled,
        api_key=api_key,
    )


class TestChanifyIntegration:

    def test_disabled_chanify_has_no_client(self) -> None:
        integration = ChanifyIntegration(make_config(enabled=False))

        assert integration.enabled is False
        assert integration._client is None

    def test_enabled_without_api_key_has_no_client(self) -> None:
        integration = ChanifyIntegration(make_config(enabled=True, api_key=""))

        assert integration.enabled is False
        assert integration._client is None

    @pytest.mark.asyncio
    async def test_show_ad_when_disabled_returns_false(self) -> None:
        integration = ChanifyIntegration(make_config(enabled=False))

        result = await integration.show_ad(chat_id=123)

        assert result is False

    @pytest.mark.asyncio
    async def test_show_ad_calls_chanify_sdk_with_chat_id(self) -> None:
        fake_client = AsyncMock()
        fake_client.show_ad.return_value = True

        with patch(
            "phoenix_core.integrations.chanify.ChanifyClient",
            return_value=fake_client,
        ) as client_class:
            integration = ChanifyIntegration(
                make_config(enabled=True, api_key="test-api-key")
            )

        client_class.assert_called_once_with("test-api-key")
        assert integration.enabled is True

        result = await integration.show_ad(chat_id=987)

        assert result is True
        fake_client.show_ad.assert_awaited_once_with(
            chat_id=987,
            user=None,
            after_delay=0,
        )

    @pytest.mark.asyncio
    async def test_show_ad_failure_is_swallowed(self) -> None:
        fake_client = AsyncMock()
        fake_client.show_ad.side_effect = RuntimeError("simulated Chanify failure")

        with patch(
            "phoenix_core.integrations.chanify.ChanifyClient",
            return_value=fake_client,
        ):
            integration = ChanifyIntegration(
                make_config(enabled=True, api_key="test-api-key")
            )

        result = await integration.show_ad(chat_id=123)

        assert result is False

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        fake_client = AsyncMock()

        with patch(
            "phoenix_core.integrations.chanify.ChanifyClient",
            return_value=fake_client,
        ):
            integration = ChanifyIntegration(
                make_config(enabled=True, api_key="test-api-key")
            )

        assert integration.enabled is True

        await integration.close()

        fake_client.close.assert_awaited_once()
        assert integration.enabled is False
        assert integration._client is None

    @pytest.mark.asyncio
    async def test_close_failure_is_swallowed(self) -> None:
        fake_client = AsyncMock()
        fake_client.close.side_effect = RuntimeError("simulated close failure")

        with patch(
            "phoenix_core.integrations.chanify.ChanifyClient",
            return_value=fake_client,
        ):
            integration = ChanifyIntegration(
                make_config(enabled=True, api_key="test-api-key")
            )

        await integration.close()

        assert integration.enabled is False
        assert integration._client is None

    @pytest.mark.asyncio
    async def test_stop_delegates_to_close(self) -> None:
        fake_client = AsyncMock()

        with patch(
            "phoenix_core.integrations.chanify.ChanifyClient",
            return_value=fake_client,
        ):
            integration = ChanifyIntegration(
                make_config(enabled=True, api_key="test-api-key")
            )

            await integration.stop()

        fake_client.close.assert_awaited_once()
        assert integration.enabled is False
        assert integration._client is None
