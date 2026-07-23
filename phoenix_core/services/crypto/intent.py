"""Lightweight crypto-question intent detection (Task CRYPTO-001)."""
import re
from typing import Optional, Tuple

_TOP_COINS_PATTERNS = (
    re.compile(r"топ\s*(крипто|монети|коини|coins)", re.IGNORECASE),
    re.compile(r"top\s*(crypto|coins)", re.IGNORECASE),
)
_PRICE_KEYWORDS = re.compile(r"(цена|price|струва|курс|колко\s+е|how\s+much)", re.IGNORECASE)
_NAME_ALIASES = {
    "btc": ("bitcoin", "биткойн", "биткоин"),
    "eth": ("ethereum", "етериум", "етеряум"),
    "sol": ("solana", "солана"),
    "bnb": ("binance coin", "бинанс койн"),
    "xrp": ("ripple",),
    "ada": ("cardano", "кардано"),
    "doge": ("dogecoin", "доджкойн"),
    "ton": ("toncoin",),
    "dot": ("polkadot",),
    "avax": ("avalanche",),
    "link": ("chainlink",),
    "ltc": ("litecoin",),
}
_KNOWN_SYMBOLS = tuple(_NAME_ALIASES.keys()) + ("usdt", "usdc", "trx", "matic")


def detect_crypto_intent(question: str) -> Optional[Tuple[str, Optional[str]]]:
    lowered = question.lower()
    for pattern in _TOP_COINS_PATTERNS:
        if pattern.search(lowered):
            return ("top", None)
    for symbol, aliases in _NAME_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                return ("price", symbol)
    if _PRICE_KEYWORDS.search(lowered):
        for symbol in _KNOWN_SYMBOLS:
            if re.search(rf"\b{re.escape(symbol)}\b", lowered):
                return ("price", symbol)
    return None
