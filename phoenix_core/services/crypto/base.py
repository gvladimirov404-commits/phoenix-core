"""Abstract base class for crypto market data providers (Task CRYPTO-001)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CryptoPrice:
    symbol: str
    name: str
    price_usd: float
    change_24h_pct: Optional[float]
    last_updated: Optional[str]


@dataclass
class CryptoMarket:
    symbol: str
    name: str
    price_usd: float
    change_24h_pct: Optional[float]
    market_cap_usd: Optional[float]
    volume_24h_usd: Optional[float]
    last_updated: Optional[str]
    market_cap_rank: Optional[int] = None


class CryptoProvider(ABC):
    """Abstract base class for crypto market data providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def get_price(self, symbol: str) -> CryptoPrice: ...

    @abstractmethod
    async def get_market(self, symbol: str) -> CryptoMarket: ...

    @abstractmethod
    async def get_top_coins(self, limit: int = 10) -> List[CryptoMarket]: ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]: ...
