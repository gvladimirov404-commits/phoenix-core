"""Deterministic change detection between two market snapshots (TASK-023
Phase F). Purely rule-based — no AI, no network calls, no side effects.
Compares a previously stored SnapshotRecord against a freshly fetched
MarketSnapshot and returns short, concrete Bulgarian-language change
descriptions, ready to be reused as-is by the Alert layer (Phase G).

If there is no previous snapshot, the first-ever capture is never treated
as a change — detect_changes returns an empty list.
"""
from typing import Any, List, Optional

PRICE_CHANGE_THRESHOLD_PCT = 3.0
FEE_SPIKE_THRESHOLD_SAT_VB = 20.0


def detect_changes(previous_row: Optional[Any], current: Any) -> List[str]:
    """Compare `previous_row` (a SnapshotRecord, or None) against `current`
    (a MarketSnapshot) and return a list of short Bulgarian change
    descriptions. Returns [] when there is nothing to compare against yet."""
    if previous_row is None:
        return []

    changes: List[str] = []

    price_change = _detect_price_change(previous_row, current)
    if price_change is not None:
        changes.append(price_change)

    sentiment_change = _detect_sentiment_change(previous_row, current)
    if sentiment_change is not None:
        changes.append(sentiment_change)

    news_change = _detect_news_change(previous_row, current)
    if news_change is not None:
        changes.append(news_change)

    fee_change = _detect_fee_spike(previous_row, current)
    if fee_change is not None:
        changes.append(fee_change)

    return changes


def _detect_price_change(previous_row: Any, current: Any) -> Optional[str]:
    market = current.market
    if market is None or market.price_usd is None:
        return None
    if previous_row.price_usd is None or previous_row.price_usd == 0:
        return None

    old_price = previous_row.price_usd
    new_price = market.price_usd
    pct_change = ((new_price - old_price) / old_price) * 100

    if abs(pct_change) < PRICE_CHANGE_THRESHOLD_PCT:
        return None

    direction = "нагоре" if pct_change > 0 else "надолу"
    return (
        f"\U0001F4B0 Цената се движи {direction}: {old_price:,.2f} \u2192 {new_price:,.2f} USD "
        f"({pct_change:+.2f}%)"
    )


def _detect_sentiment_change(previous_row: Any, current: Any) -> Optional[str]:
    fear_greed = current.fear_greed
    if fear_greed is None or fear_greed.classification is None:
        return None
    if previous_row.fear_greed_classification is None:
        return None
    if fear_greed.classification == previous_row.fear_greed_classification:
        return None

    return (
        f"\U0001F628 Пазарното настроение се промени: "
        f"{previous_row.fear_greed_classification} \u2192 {fear_greed.classification}"
    )


def _detect_news_change(previous_row: Any, current: Any) -> Optional[str]:
    top_news = current.top_news
    if top_news is None or not top_news.title:
        return None
    if previous_row.top_news_title is None:
        return None
    if top_news.title == previous_row.top_news_title:
        return None

    return f"\U0001F4F0 Нова водеща новина: \"{top_news.title}\""


def _detect_fee_spike(previous_row: Any, current: Any) -> Optional[str]:
    fees = current.fees
    if fees is None or fees.fastest_sat_vb is None:
        return None
    if previous_row.fees_fastest_sat_vb is None:
        return None

    old_fee = previous_row.fees_fastest_sat_vb
    new_fee = fees.fastest_sat_vb
    diff = new_fee - old_fee

    if abs(diff) < FEE_SPIKE_THRESHOLD_SAT_VB:
        return None

    direction = "скочиха" if diff > 0 else "спаднаха"
    return f"\u26FD Таксите по мрежата {direction} значително: {old_fee:g} \u2192 {new_fee:g} sat/vB"
