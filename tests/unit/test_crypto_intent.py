"""Unit tests for phoenix_core.services.crypto.intent.detect_crypto_intent."""
from phoenix_core.services.crypto.intent import detect_crypto_intent


class TestPriceIntent:
    def test_bulgarian_price_question_with_symbol(self) -> None:
        assert detect_crypto_intent("Колко струва BTC?") == ("price", "btc")

    def test_english_price_question_with_symbol(self) -> None:
        assert detect_crypto_intent("What is the BTC price?") == ("price", "btc")

    def test_short_symbol_price_question(self) -> None:
        assert detect_crypto_intent("ETH price?") == ("price", "eth")

    def test_bulgarian_coin_name_alias(self) -> None:
        assert detect_crypto_intent("Колко струва биткойн?") == ("price", "btc")

    def test_english_coin_name_alias(self) -> None:
        assert detect_crypto_intent("How much is bitcoin?") == ("price", "btc")

    def test_solana_alias(self) -> None:
        assert detect_crypto_intent("колко струва solana") == ("price", "sol")


class TestTopCoinsIntent:
    def test_bulgarian_top_coins(self) -> None:
        assert detect_crypto_intent("Топ криптовалути") == ("top", None)

    def test_english_top_coins(self) -> None:
        assert detect_crypto_intent("Top cryptocurrencies") == ("top", None)


class TestNoIntent:
    def test_unrelated_question_returns_none(self) -> None:
        assert detect_crypto_intent("Какво е времето днес?") is None

    def test_symbol_mentioned_without_price_keyword_returns_none(self) -> None:
        assert detect_crypto_intent("Обичам BTC отдавна") is None

    def test_empty_string_returns_none(self) -> None:
        assert detect_crypto_intent("") is None
