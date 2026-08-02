"""Unit tests for Strategy Lab strategies and StrategyRegistry (Strategy Lab roadmap item)."""
from phoenix_core.services.crypto.base import CryptoMarket
from phoenix_core.services.intel.aggregator import MarketSnapshot
from phoenix_core.services.intel.feargreed_provider import FearGreedReading
from phoenix_core.services.strategy.builtin import FearGreedContrarianStrategy, MomentumStrategy
from phoenix_core.services.strategy.registry import StrategyRegistry


def make_snapshot(change_24h_pct=None, fear_greed_value=None):
    market = None
    if change_24h_pct is not None:
        market = CryptoMarket(
            symbol="BTC",
            name="BTC",
            price_usd=50000.0,
            change_24h_pct=change_24h_pct,
            market_cap_usd=1.0,
            volume_24h_usd=1.0,
            last_updated="2026-08-02",
        )
    fear_greed = None
    if fear_greed_value is not None:
        fear_greed = FearGreedReading(value=fear_greed_value, classification="x", timestamp="0")
    return MarketSnapshot(symbol="BTC", market=market, fear_greed=fear_greed, fees=None, top_news=None)


class TestFearGreedContrarianStrategy:
    def test_extreme_fear_is_bullish(self) -> None:
        strategy = FearGreedContrarianStrategy()
        signal = strategy.evaluate(make_snapshot(fear_greed_value=15))
        assert signal.signal == "bullish"
        assert "15" in signal.reasoning

    def test_extreme_greed_is_bearish(self) -> None:
        strategy = FearGreedContrarianStrategy()
        signal = strategy.evaluate(make_snapshot(fear_greed_value=85))
        assert signal.signal == "bearish"
        assert "85" in signal.reasoning

    def test_moderate_sentiment_is_neutral(self) -> None:
        strategy = FearGreedContrarianStrategy()
        signal = strategy.evaluate(make_snapshot(fear_greed_value=50))
        assert signal.signal == "neutral"

    def test_missing_fear_greed_is_unknown(self) -> None:
        strategy = FearGreedContrarianStrategy()
        signal = strategy.evaluate(make_snapshot())
        assert signal.signal == "unknown"


class TestMomentumStrategy:
    def test_strong_rise_is_bullish(self) -> None:
        strategy = MomentumStrategy()
        signal = strategy.evaluate(make_snapshot(change_24h_pct=6.0))
        assert signal.signal == "bullish"

    def test_strong_drop_is_bearish(self) -> None:
        strategy = MomentumStrategy()
        signal = strategy.evaluate(make_snapshot(change_24h_pct=-5.0))
        assert signal.signal == "bearish"

    def test_small_change_is_neutral(self) -> None:
        strategy = MomentumStrategy()
        signal = strategy.evaluate(make_snapshot(change_24h_pct=0.5))
        assert signal.signal == "neutral"

    def test_missing_market_data_is_unknown(self) -> None:
        strategy = MomentumStrategy()
        signal = strategy.evaluate(make_snapshot())
        assert signal.signal == "unknown"


class TestStrategyRegistry:
    def test_list_strategies_returns_both_builtin_strategies(self) -> None:
        registry = StrategyRegistry()
        names = {s["name"] for s in registry.list_strategies()}
        assert names == {"fear_greed_contrarian", "momentum"}

    def test_get_returns_strategy_by_name(self) -> None:
        registry = StrategyRegistry()
        assert registry.get("momentum") is not None
        assert registry.get("unknown_strategy") is None

    def test_evaluate_all_runs_every_strategy(self) -> None:
        registry = StrategyRegistry()
        snapshot = make_snapshot(change_24h_pct=1.0, fear_greed_value=50)
        results = registry.evaluate_all(snapshot)
        assert set(results.keys()) == {"fear_greed_contrarian", "momentum"}
