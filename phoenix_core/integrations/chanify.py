"""
Chanify advertising integration for Phoenix Core.

This module is intentionally failure-safe:
- Chanify is optional.
- Advertising failures must never break Telegram command responses.
- The API key is supplied through Phoenix Core configuration.
"""

from typing import Any, Optional

from chanify import Chanify as ChanifyClient

from phoenix_core.config.settings import ChanifyConfig
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)


class ChanifyIntegration:
    """Safe Phoenix Core wrapper around the Chanify SDK."""

    def __init__(self, config: ChanifyConfig) -> None:
        self.config = config
        self._client: Optional[ChanifyClient] = None

        api_key = config.api_key.get_secret_value()

        if config.enabled and api_key:
            self._client = ChanifyClient(api_key)

    @property
    def enabled(self) -> bool:
        """Return whether Chanify advertising is actually usable."""
        return self._client is not None

    async def show_ad(
        self,
        chat_id: int,
        user: Any = None,
    ) -> bool:
        """
        Request an advertisement.

        Advertising failures are deliberately swallowed so that
        Phoenix Core's primary Telegram functionality is unaffected.
        """
        if self._client is None:
            return False

        try:
            return await self._client.show_ad(
                chat_id=chat_id,
                user=user,
                after_delay=0,
            )
        except Exception as exc:
            logger.warning(
                "Chanify advertising request failed",
                error_type=type(exc).__name__,
            )
            return False

    async def stop(self) -> None:
        """Stop the integration during PhoenixApplication shutdown."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying Chanify HTTP client."""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as exc:
                logger.warning(
                    "Failed to close Chanify client",
                    error_type=type(exc).__name__,
                )
            finally:
                self._client = None
