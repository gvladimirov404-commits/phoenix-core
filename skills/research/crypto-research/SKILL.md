---
name: crypto-research
description: Multi-source research pass on a crypto asset producing a structured intelligence report
version: 1
category: research
tags: [crypto, research, intelligence]
risk_level: low
---

## When to use
The user asks for a deeper look at a specific coin than `/intel` or `/explain`
alone provide — e.g. "what's really going on with BTC," "give me a full
research report on ETH." Triggered by the `/research <symbol>` command.

## Required inputs
- A coin symbol (e.g. `btc`, `eth`).

## Procedure
1. Fetch a `MarketSnapshot` via the existing `MarketIntelligenceAggregator`
   (`market_intel_aggregator` in the container) — do not build a second
   market-data client.
2. If the snapshot is empty (every sub-source failed), stop and tell the
   user plainly — never fabricate data to fill the report.
3. Run `StrategyRegistry.evaluate_all(snapshot)` for the existing built-in
   signals (fear/greed contrarian, momentum) — do not invent new scoring.
4. Derive an `EvidenceReport` via `phoenix_core.services.research.evidence
   .derive_evidence(snapshot)` — coverage is computed from which
   `MarketSnapshot` fields are actually populated, never guessed.
5. Send one prompt to the configured AI provider (`ai_router`), asking
   only for the interpretive narrative (what's happening + a one-line,
   non-prescriptive conclusion) — the AI never generates the factual
   fields (price, sentiment value, source names); those are assembled in
   code from the snapshot directly.
6. Assemble the final report: MARKET / WHAT'S HAPPENING / SIGNALS / RISKS
   / EVIDENCE / SOURCES / AI ANALYSIS / CONCLUSION / CONFIDENCE.

## Evidence rules
- A fact is only stated if the corresponding `MarketSnapshot` field is not
  `None`.
- Missing fields are listed explicitly under EVIDENCE, never silently
  dropped or guessed at.
- BTC network fees are only ever counted as "expected evidence" when the
  symbol is BTC — a non-BTC symbol is never penalized for a data point it
  was never going to have.

## Confidence rules
- Confidence (LOW/MEDIUM/HIGH) is derived purely from the fraction of
  expected sources that returned data — never asked of the AI, never a
  free-form percentage.
- Confidence reflects evidence coverage, not correctness. The report must
  say so explicitly every time it's shown.

## Output format
See `_format_research_report` in `phoenix_core/telegram/commands.py` for
the exact section order and emoji headers. Do not reorder sections without
updating this file to match.

## Pitfalls
- Do not let the AI's free-text response overwrite or contradict a factual
  field that was already assembled from real data.
- Do not turn a missing data point into an inferred number.
- Do not let the CONCLUSION section read as investment advice — it must
  stay a plain description of which signals dominate, nothing more.

## Verification
- `tests/unit/test_research_capability.py` — the extracted business
  logic (`phoenix_core.services.research.research_capability.run_research`),
  including missing-data and AI-failure paths, tested directly without
  any Telegram objects.
