"""Evidence and confidence derivation for crypto research reports
(crypto-research Skill, TASK-023). Confidence is derived purely from how
many of the expected data sources in a MarketSnapshot actually returned
data — it reflects EVIDENCE COVERAGE, not correctness. A high-confidence
report can still be wrong; this only tells the reader how much of the
expected data Phoenix actually had when it wrote the report.
"""
from dataclasses import dataclass
from typing import List


@dataclass
class EvidenceReport:
    """What data sources were available for a given MarketSnapshot, and
    what that implies about confidence. Never claims truth — only coverage."""

    available_sources: List[str]
    missing_sources: List[str]
    confidence: str  # "LOW", "MEDIUM", "HIGH"

    @property
    def coverage_fraction(self) -> str:
        total = len(self.available_sources) + len(self.missing_sources)
        return f"{len(self.available_sources)}/{total}" if total else "0/0"


def derive_evidence(snapshot) -> EvidenceReport:
    """Derive an EvidenceReport from a MarketSnapshot's actual field
    availability. Only counts sources genuinely expected for this symbol —
    BTC network fees are only ever expected for BTC, so a non-BTC symbol
    is never penalized for a fee reading it was never going to get."""
    expected = {
        "market": snapshot.market,
        "sentiment": snapshot.fear_greed,
        "news": snapshot.top_news,
    }
    if snapshot.symbol == "BTC":
        expected["network_fees"] = snapshot.fees

    available = [name for name, value in expected.items() if value is not None]
    missing = [name for name, value in expected.items() if value is None]

    total = len(expected)
    if total == 0:
        confidence = "LOW"
    else:
        ratio = len(available) / total
        if ratio >= 0.75:
            confidence = "HIGH"
        elif ratio >= 0.5:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

    return EvidenceReport(available_sources=available, missing_sources=missing, confidence=confidence)
