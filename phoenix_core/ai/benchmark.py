"""PhoenixBenchmark — runs a fixed set of sample questions against every
currently configured AI provider and reports latency and success rate per
provider (Benchmark roadmap item). Useful for deciding when a newly
enabled provider (e.g. DeepSeek) is worth using, and for spotting a
provider that has started degrading.
"""
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from phoenix_core.ai.router import AIRouter
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_PROMPTS = [
    "Какво е bitcoin накратко?",
    "Обясни какво е blockchain с едно изречение.",
    "Кажи едно число между 1 и 10.",
]


@dataclass
class ProviderBenchmark:
    """Aggregated results for a single provider across all test prompts."""

    provider: str
    attempts: int = 0
    successes: int = 0
    total_latency_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Fraction of prompts this provider answered successfully."""
        return self.successes / self.attempts if self.attempts else 0.0

    @property
    def average_latency_seconds(self) -> float:
        """Average response time across successful prompts only."""
        return self.total_latency_seconds / self.successes if self.successes else 0.0


class PhoenixBenchmark:
    """Runs a fixed prompt set against every registered AI provider and
    aggregates latency/success-rate per provider. One provider's failures
    are isolated and never block the others from being benchmarked."""

    def __init__(self, ai_router: AIRouter, prompts: Optional[List[str]] = None) -> None:
        self._ai_router = ai_router
        self._prompts = prompts or DEFAULT_PROMPTS

    async def run(self) -> Dict[str, ProviderBenchmark]:
        results: Dict[str, ProviderBenchmark] = {}
        for name in self._ai_router.list_providers():
            bench = ProviderBenchmark(provider=name)
            for prompt in self._prompts:
                bench.attempts += 1
                start = time.monotonic()
                try:
                    await self._ai_router.chat(
                        messages=[{"role": "user", "content": prompt}], provider=name
                    )
                    elapsed = time.monotonic() - start
                    bench.successes += 1
                    bench.total_latency_seconds += elapsed
                except Exception as e:
                    logger.warning(
                        "Benchmark prompt failed",
                        provider=name,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    bench.errors.append(type(e).__name__)
            results[name] = bench
        return results
