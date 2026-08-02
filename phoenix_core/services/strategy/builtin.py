"""Built-in Strategy Lab strategies (Strategy Lab roadmap item).

Each strategy is deliberately simple and transparent — a single rule over
one field of the MarketSnapshot — so its reasoning is easy to follow. None
of them predict the future or recommend buying/selling; they only label
the current data one way, for the person to interpret themselves.
"""
from phoenix_core.services.strategy.base import Strategy, StrategySignal


class FearGreedContrarianStrategy(Strategy):
    """Contrarian reading of the Fear & Greed index — extreme fear is
    labeled as a zone some contrarian investors watch for value, extreme
    greed as a zone associated with higher pullback risk."""

    @property
    def name(self) -> str:
        return "fear_greed_contrarian"

    @property
    def description(self) -> str:
        return "Contrarian четене на Fear & Greed индекса"

    def evaluate(self, snapshot) -> StrategySignal:
        if snapshot.fear_greed is None:
            return StrategySignal(
                strategy_name=self.name,
                signal="unknown",
                reasoning="Няма данни за пазарното настроение в момента.",
            )
        value = snapshot.fear_greed.value
        if value <= 25:
            return StrategySignal(
                strategy_name=self.name,
                signal="bullish",
                reasoning=(
                    f"Extreme Fear ({value}/100) — зона, която contrarian "
                    "инвеститори наблюдават за възможна стойност."
                ),
            )
        if value >= 75:
            return StrategySignal(
                strategy_name=self.name,
                signal="bearish",
                reasoning=(
                    f"Extreme Greed ({value}/100) — зона, свързвана с "
                    "по-висок риск от корекция."
                ),
            )
        return StrategySignal(
            strategy_name=self.name,
            signal="neutral",
            reasoning=f"Настроението е умерено ({value}/100) — без изявен сигнал.",
        )


class MomentumStrategy(Strategy):
    """Reads the raw 24h price change direction and magnitude."""

    @property
    def name(self) -> str:
        return "momentum"

    @property
    def description(self) -> str:
        return "Посока и сила на движението за последните 24 часа"

    def evaluate(self, snapshot) -> StrategySignal:
        if snapshot.market is None or snapshot.market.change_24h_pct is None:
            return StrategySignal(
                strategy_name=self.name,
                signal="unknown",
                reasoning="Няма данни за ценовата промяна в момента.",
            )
        change = snapshot.market.change_24h_pct
        if change >= 3:
            return StrategySignal(
                strategy_name=self.name,
                signal="bullish",
                reasoning=f"Силен възходящ момент: {change:+.2f}% за 24ч.",
            )
        if change <= -3:
            return StrategySignal(
                strategy_name=self.name,
                signal="bearish",
                reasoning=f"Силен низходящ момент: {change:+.2f}% за 24ч.",
            )
        return StrategySignal(
            strategy_name=self.name,
            signal="neutral",
            reasoning=f"Слабо изразено движение: {change:+.2f}% за 24ч.",
        )
