"""ResearchCapability — Telegram-independent business logic for the
crypto-research Skill (skills/research/crypto-research/SKILL.md).

Extracted from phoenix_core.telegram.commands.cmd_research (TASK-023 P1 #1)
so the same orchestration — fetch snapshot, evaluate strategy signals,
derive evidence, ask the AI provider for the interpretive narrative — is
callable directly from tests, a future Web UI, or an agent layer, without
any Telegram Update/Context objects in scope.

This module owns orchestration only. It does not format a Telegram
response string — that stays in commands.py, unchanged, so /research's
existing output format and error messages are fully preserved.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional

from phoenix_core.core.container import Container
from phoenix_core.guard.sanitizer import OutputSanitizer
from phoenix_core.services.research.evidence import EvidenceReport, derive_evidence
from phoenix_core.services.strategy.registry import StrategyRegistry
from phoenix_core.utils.exceptions import (
    AIProviderConnectionError,
    AIProviderError,
    AIProviderNotFoundError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    ConfigurationError,
    ContextTooLargeError,
    PromptTooLargeError,
    RateLimitExceededError,
    ValidationError,
)
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

_FALLBACK_SANITIZER: Optional[OutputSanitizer] = None


def _fallback_sanitizer() -> OutputSanitizer:
    """Lazily-created fallback OutputSanitizer, used only when no AIGuard
    is registered in the container. Mirrors commands._default_sanitizer()
    but is defined locally here to avoid importing from commands.py
    (this module must have no Telegram dependency)."""
    global _FALLBACK_SANITIZER
    if _FALLBACK_SANITIZER is None:
        _FALLBACK_SANITIZER = OutputSanitizer()
    return _FALLBACK_SANITIZER


class ResearchUnavailableError(Exception):
    """Raised when a required service (market intelligence or AI) isn't
    configured in the container. Callers map this to their own
    user-facing message — this module carries no Telegram-specific text."""


class ResearchNoDataError(Exception):
    """Raised when the market snapshot came back completely empty (every
    sub-source failed) — nothing to research, never fabricated."""


class ResearchAIError(Exception):
    """Raised when the AI provider call failed. Wraps the original
    exception's type name so callers can map it to their own
    user-facing message without this module needing to know Telegram
    error strings."""

    def __init__(self, reason: str, original: Exception) -> None:
        super().__init__(reason)
        self.reason = reason
        self.original = original


@dataclass
class ResearchResult:
    """The structured result of a research pass — everything the existing
    Telegram formatter (_format_research_report) needs, and nothing more."""

    snapshot: Any
    signals: Dict[str, Any]
    evidence: EvidenceReport
    ai_text: str
    provider: str


async def run_research(
    symbol: str,
    container: Container,
    build_prompt,
    user_id: Optional[int] = None,
) -> ResearchResult:
    """Run the crypto-research Skill's orchestration for `symbol`.

    Args:
        symbol: Coin symbol (e.g. "btc"). Case/whitespace are normalized
            downstream by MarketIntelligenceAggregator, same as before.
        container: DI container to resolve market_intel_aggregator,
            ai_router, and (optionally) ai_guard from.
        build_prompt: Callable(snapshot, signals, evidence) -> str that
            builds the AI prompt text. Passed in rather than imported,
            so the exact prompt wording stays defined once, in
            commands.py's _build_research_prompt — this function does
            not duplicate or reinterpret that text.
        user_id: Optional caller id, used only for AI Guard rate limiting
            and structured logging — never for business logic branching.

    Returns:
        A ResearchResult with the snapshot, signals, evidence, AI text,
        and provider name — ready for a caller to format however it needs.

    Raises:
        ResearchUnavailableError: market_intel_aggregator or ai_router
            isn't registered in the container.
        ResearchNoDataError: the market snapshot was completely empty.
        ResearchAIError: the AI provider call failed for any reason.
    """
    try:
        aggregator = container.resolve("market_intel_aggregator")
    except KeyError:
        raise ResearchUnavailableError("market_intel_aggregator not configured")

    normalized_symbol = symbol.strip().lower()
    snapshot = await aggregator.get_snapshot(normalized_symbol)

    if snapshot.is_empty:
        raise ResearchNoDataError(f"no data available for {normalized_symbol}")

    signals = StrategyRegistry().evaluate_all(snapshot)
    evidence = derive_evidence(snapshot)

    try:
        ai_router = container.resolve("ai_router")
    except KeyError:
        raise ResearchUnavailableError("ai_router not configured")

    try:
        ai_guard = container.resolve("ai_guard")
    except KeyError:
        ai_guard = None

    prompt = build_prompt(snapshot, signals, evidence)
    messages = [{"role": "user", "content": prompt}]

    logger.info(
        "AI request started", command="research", user_id=user_id, symbol=snapshot.symbol
    )

    if ai_guard is not None:
        try:
            ai_guard.guard_request(user_id, prompt, messages)
        except RateLimitExceededError as e:
            raise ResearchAIError("rate_limit", e)
        except PromptTooLargeError as e:
            raise ResearchAIError("invalid_input", e)
        except ContextTooLargeError as e:
            raise ResearchAIError("context_too_large", e)

    try:
        if ai_guard is not None:
            response = await ai_guard.call_provider(lambda: ai_router.chat(messages=messages))
        else:
            response = await ai_router.chat(messages=messages)
    except ConfigurationError as e:
        logger.warning("AI request failed: not configured", command="research")
        raise ResearchAIError("not_configured", e)
    except AIProviderNotFoundError as e:
        logger.warning("AI request failed: provider not found", command="research")
        raise ResearchAIError("provider_not_found", e)
    except AIProviderTimeoutError as e:
        logger.warning("AI request failed: timeout", command="research")
        raise ResearchAIError("timeout", e)
    except AIProviderConnectionError as e:
        logger.warning("AI request failed: connection error", command="research")
        raise ResearchAIError("connection", e)
    except AIProviderRateLimitError as e:
        logger.warning("AI request failed: rate limited", command="research")
        raise ResearchAIError("rate_limit", e)
    except AIProviderError as e:
        logger.error("AI request failed: provider error", command="research")
        raise ResearchAIError("generic_error", e)
    except ValidationError as e:
        logger.warning("AI request failed: invalid input", command="research")
        raise ResearchAIError("invalid_input", e)

    logger.info("AI request completed", command="research", provider=response.provider)

    if ai_guard is not None:
        ai_text = ai_guard.sanitize_output(response.content)
    else:
        ai_text = _fallback_sanitizer().sanitize(response.content)

    return ResearchResult(
        snapshot=snapshot,
        signals=signals,
        evidence=evidence,
        ai_text=ai_text,
        provider=response.provider,
    )
