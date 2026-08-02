"""Base types for Strategy Lab (Strategy Lab roadmap item).

A Strategy is a small, self-contained rule evaluated against a
MarketSnapshot (the same snapshot /intel and /explain use). It never
recommends an action or predicts the future with certainty — it only
surfaces one interpretation of the current data, always paired with a
disclaimer, so it is informational rather than financial advice.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StrategySignal:
    """Result of evaluating one Strategy against one MarketSnapshot."""

    strategy_name: str
    signal: str  # one of: "bullish", "bearish", "neutral", "unknown"
    reasoning: str


class Strategy(ABC):
    """Minimal contract every Strategy Lab strategy must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name (used as its key in the registry)."""
        ...

    @property
    def description(self) -> str:
        """One-line description of what this strategy looks at."""
        return ""

    @abstractmethod
    def evaluate(self, snapshot) -> StrategySignal:
        """Return this strategy's signal for the given market snapshot."""
        ...
