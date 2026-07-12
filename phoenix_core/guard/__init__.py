"""
AI Guard Layer (Task 011).

Runtime-safety layer that sits between phoenix_core.telegram.commands.cmd_ask
and AIRouter — never inside AIRouter itself (Task 011, Задача 1: "Не
смесвай тази логика с AIRouter"). Four independent, individually testable
components, composed behind one facade:

    RateLimiter      — per-user request rate limiting (rate_limiter.py)
    CostGuard        — size-based prompt/context ceilings, no monetary cost (cost_guard.py)
    RetryPolicy      — bounded retry + backoff for transient provider errors (retry.py)
    OutputSanitizer  — length/Markdown-token cleanup before sending to Telegram (sanitizer.py)
    AIGuard          — facade composing all four (guard.py)

Public surface:
    AIGuard, RateLimiter, CostGuard, RetryPolicy, OutputSanitizer
"""
from phoenix_core.guard.cost_guard import CostGuard
from phoenix_core.guard.guard import AIGuard
from phoenix_core.guard.rate_limiter import RateLimiter
from phoenix_core.guard.retry import RetryPolicy
from phoenix_core.guard.sanitizer import OutputSanitizer

__all__ = ["AIGuard", "RateLimiter", "CostGuard", "RetryPolicy", "OutputSanitizer"]
