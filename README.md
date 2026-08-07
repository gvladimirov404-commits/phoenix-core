# Phoenix Core 🔥

**An AI-powered crypto intelligence assistant, built as a modular framework — controlled entirely through Telegram.**

## The problem it solves

Anyone tracking crypto markets juggles too many tabs: a price tracker, a news feed, a sentiment index, a fee estimator, and separate AI chat for "why is it moving?" Phoenix Core consolidates all of that into one Telegram bot, and adds a layer none of those tools have on their own: **AI that synthesizes the raw data into a plain-language briefing**, with built-in guardrails so it never pretends to be a financial advisor.

## Try it in one command

```
/copilot BTC
```

This single command triggers the whole pipeline: live market data → sentiment analysis → rule-based strategy signals → an AI-written briefing that explains what the data shows — always closing with a clear disclaimer. See [Example flow](#example-flow-copilot-btc) below.

## Architecture

```
Telegram (CommandDispatcher)
        │
        ├── /intel ──────► MarketIntelligenceAggregator ──► CryptoProvider (CoinGecko)
        │                          │                    ├─► FearGreedProvider (alternative.me)
        │                          │                    ├─► FeesProvider (mempool.space)
        │                          │                    └─► NewsProvider (Google News RSS)
        │                          │        (all four fetched concurrently via asyncio.gather)
        │                          ▼
        │                    MarketSnapshot
        │                          │
        ├── /strategy ──► StrategyRegistry (FearGreedContrarian, Momentum) ─┐
        │                                                                   │
        ├── /explain ───► AIRouter (Groq / DeepSeek) ◄─────────────────────┤
        ├── /consensus ─►      │                                           │
        └── /copilot ───►      └── synthesizes MarketSnapshot + signals ───┘
                                    into an AI briefing (never financial advice)

Plugin System: PluginRegistry discovers .py files in plugins/, each exposing
a PhoenixPlugin instance — commands register into the same CommandDispatcher.
Sandbox Mode (opt-in): AST-validates plugin source + wraps every plugin
command with a runtime timeout, before it's ever loaded.
```

Everything is wired through a small dependency-injection `Container` (`phoenix_core/core/`), so every service — AI router, crypto providers, plugin registry — is swappable without touching the command handlers.

## Core features

| Command | What it does |
|---|---|
| `/intel <symbol>` | Consolidated market snapshot: price, 24h change, sentiment, BTC fees, top news — all fetched in parallel |
| `/explain <symbol>` | AI explains, in plain language, why the price is moving |
| `/consensus <question>` | Asks every configured AI provider the same question side by side (ready for a second provider like DeepSeek with zero code changes) |
| `/strategy <symbol>` | Evaluates simple, transparent rules (contrarian sentiment, momentum) against live data — always labeled "informational, not financial advice" |
| `/copilot <symbol>` | The flagship command — synthesizes everything above into one AI-written briefing |
| `/benchmark` | Measures latency and success rate of every configured AI provider |
| `/plugins` | Lists every loaded plugin; drop a `.py` file in `plugins/` to add a command without touching core code |
| `/watch`, `/brief`, `/news`, `/fear`, `/gas`, `/crypto` | Underlying data primitives `/intel` composes — also usable standalone |
| `/ask`, `/reset`, `/memory` | General-purpose AI chat with persistent, per-user conversation memory |

Full list with examples: send `/help` to the running bot.

## Example flow: `/copilot BTC`

1. **Market data** — current price and 24h % change, fetched from CoinGecko.
2. **Crypto intelligence** — Fear & Greed index reading, aggregated alongside the price.
3. **Explainable AI** — the briefing text itself, written by the configured AI provider (Groq by default).
4. **Strategy analysis** — the Strategy Lab's contrarian-sentiment and momentum signals are fed into the same briefing.
5. **Risk warning** — the AI is explicitly instructed to name a concrete risk, and every reply ends with a disclaimer regardless of what the model produces.
6. **AI provider status** — the reply is signed with which provider answered (`Provider: groq`), matching what `/consensus` and `/benchmark` report.

One command, one bot, no context-switching.

## Installation

```bash
git clone https://github.com/gvladimirov404-commits/phoenix-core.git
cd phoenix-core
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: at minimum set GROQ_API_KEY and PHOENIX_TELEGRAM_BOT_TOKEN

python -m phoenix_core.cli start
```

All dependency versions in `requirements.txt` are pinned (`==`), verified against a clean virtual environment — no surprise breakage from an unrelated upstream release.

Every integration degrades gracefully: leave a variable unset (GitHub token, a specific AI provider, plugin sandboxing) and that feature is simply skipped — the rest of the bot runs normally.

### Running tests

```bash
python -m pytest tests/ -q
```

## Plugin System & Sandbox Mode

Drop a Python file into `plugins/` exposing a module-level `PLUGIN` instance of `PhoenixPlugin`, and it's discovered and registered automatically on startup — no core code changes needed. See `plugins/example_ping.py` for a minimal working example.

Set `PHOENIX_PLUGINS_SANDBOXED=true` to enable Sandbox Mode: plugin source is statically checked against an import/builtin whitelist before it's ever executed, and every plugin command gets a runtime timeout — so one careless or malicious plugin file can't take down the bot.

## Status

v0.1.0-alpha. Core framework, AI layer (Groq + DeepSeek), Telegram bot, GitHub integration, crypto/market intelligence, Strategy Lab, Trading Copilot, and Plugin System (with Sandbox Mode) are implemented and tested. See `docs/` for deeper design notes on individual subsystems.
