"""StrategyRegistry — holds every built-in Strategy Lab strategy and runs
them against a MarketSnapshot (Strategy Lab roadmap item)."""
from typing import Dict, List, Optional

from phoenix_core.services.strategy.base import Strategy, StrategySignal
from phoenix_core.services.strategy.builtin import FearGreedContrarianStrategy, MomentumStrategy


class StrategyRegistry:
    """Registers and runs every built-in strategy. Stateless per instance —
    safe to construct fresh on every command call."""

    def __init__(self) -> None:
        self._strategies: Dict[str, Strategy] = {
            s.name: s for s in (FearGreedContrarianStrategy(), MomentumStrategy())
        }

    def get(self, name: str) -> Optional[Strategy]:
        return self._strategies.get(name)

    def list_strategies(self) -> List[Dict[str, str]]:
        return [{"name": s.name, "description": s.description} for s in self._strategies.values()]

    def evaluate_all(self, snapshot) -> Dict[str, StrategySignal]:
        return {name: strategy.evaluate(snapshot) for name, strategy in self._strategies.items()}
