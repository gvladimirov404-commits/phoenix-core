"""ConsensusEngine — sends the same question to every currently configured
AI provider and returns each one's answer side by side (Roadmap item 5 /
TASK-021 Part 9). Works with a single provider today (only Groq is active)
and needs no changes when a second provider (e.g. DeepSeek) is enabled -
every provider AIRouter knows about is queried automatically.
"""
from dataclasses import dataclass, field
from typing import Dict, List

from phoenix_core.ai.base import AIResponse
from phoenix_core.ai.router import AIRouter
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ConsensusResult:
    """One answer per currently configured AI provider.

    `responses` holds a successful AIResponse per provider that answered;
    `errors` holds a short reason per provider that failed. A provider
    appears in exactly one of the two.
    """

    question: str
    responses: Dict[str, AIResponse] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def provider_count(self) -> int:
        """How many providers were queried in total (answered + failed)."""
        return len(self.responses) + len(self.errors)


class ConsensusEngine:
    """Queries every registered AI provider with the same question, isolating
    each provider's failure so one broken provider never blocks the rest."""

    def __init__(self, ai_router: AIRouter) -> None:
        self._ai_router = ai_router

    async def get_consensus(self, messages: List[Dict[str, str]]) -> ConsensusResult:
        question = messages[-1]["content"] if messages else ""
        result = ConsensusResult(question=question)

        for name in self._ai_router.list_providers():
            try:
                response = await self._ai_router.chat(messages=messages, provider=name)
                result.responses[name] = response
            except Exception as e:
                logger.warning(
                    "Consensus sub-provider failed",
                    provider=name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                result.errors[name] = type(e).__name__

        return result
