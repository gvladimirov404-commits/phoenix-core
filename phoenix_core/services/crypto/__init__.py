"""Crypto market data module (Task CRYPTO-001)."""
from phoenix_core.services.crypto.base import CryptoMarket, CryptoPrice, CryptoProvider
from phoenix_core.services.crypto.coingecko_provider import CoinGeckoProvider
from phoenix_core.services.crypto.intent import detect_crypto_intent

__all__ = ["CryptoMarket", "CryptoPrice", "CryptoProvider", "CoinGeckoProvider", "detect_crypto_intent"]
