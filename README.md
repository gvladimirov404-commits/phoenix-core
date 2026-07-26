# phoenix-core
Modular Python AI framework with a Telegram control interface, GitHub integration (repository info + issues), persistent conversation memory (SQLite), and an AI Guard Layer for rate limiting/retry/sanitization. Currently V1/alpha — see [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md) for current scope and known limitations before deploying.

**Version:** 0.1.0-alpha — single source of truth: `phoenix_core/_version.py`.

## AI Layer (V1 — DeepSeek and Groq)

Set the following environment variables (e.g. in a local `.env` file — see `.env.example`):

```bash
# DeepSeek — one of the two supported providers
PHOENIX_AI_DEEPSEEK_API_KEY=your-deepseek-api-key   # required to enable DeepSeek
PHOENIX_AI_DEEPSEEK_MODEL=deepseek-chat              # optional, defaults to deepseek-chat
PHOENIX_AI_DEEPSEEK_BASE_URL=https://api.deepseek.com # optional, defaults shown
PHOENIX_AI_DEEPSEEK_TIMEOUT=30                        # optional, seconds
PHOENIX_AI_DEEPSEEK_MAX_RETRIES=3                     # optional

# Groq — the other supported provider (Task 014). Env var names are unprefixed
# (GROQ_*, not PHOENIX_AI_GROQ_*) to match Groq's own SDK/docs convention.
GROQ_API_KEY=your-groq-api-key                        # required to enable Groq
GROQ_MODEL=llama-3.3-70b-versatile                    # optional, defaults shown (Groq's model roster changes
                                                       # fairly often — check https://console.groq.com/docs/models
                                                       # or GET {base_url}/models if requests start failing)
GROQ_BASE_URL=https://api.groq.com/openai/v1          # optional, defaults shown
GROQ_TIMEOUT=30                                       # optional, seconds
GROQ_MAX_RETRIES=3                                    # optional

# Both providers can be configured at once; this picks which one AIRouter uses by default.
AI_DEFAULT_PROVIDER=deepseek                          # optional, "deepseek" (default) or "groq"

AI_MAX_PROMPT_LENGTH=4000                             # optional, max /ask prompt length in characters
AI_MAX_CONVERSATION_MESSAGES=20                       # optional, max messages kept per user conversation
AI_MAX_CONTEXT_CHARS=8000                             # optional, max combined chars sent as context per request
AI_RATE_LIMIT_REQUESTS=10                             # optional, max /ask requests per user per rate-limit window
AI_RATE_LIMIT_WINDOW=60                               # optional, rate-limit window length in seconds
AI_GUARD_MAX_CONTEXT_CHARS=12000                      # optional, AI Guard's hard ceiling on assembled context
AI_GUARD_MAX_RETRIES=2                                # optional, max retries for transient AI provider errors
MEMORY_BACKEND=sqlite                                 # optional, conversation storage backend (only 'sqlite' implemented)
SQLITE_DATABASE=phoenix.db                            # optional, path to the SQLite database fileConversations now survive an application restart. `ConversationManager`'s
public API is unchanged from Task 010 and stays fully synchronous — this
was a deliberate correction: `aiosqlite` (true async I/O) would have
required every public method to become `async def`, which was ruled
incompatible with keeping the API stable. Storage instead uses the
stdlib `sqlite3` module (synchronous, no ORM, raw SQL), isolated behind a
backend-agnostic interface:

```
ConversationManager (unchanged, synchronous)
        │  no SQL lives here
        ▼
ConversationStore (phoenix_core/memory/storage/base.py — abstract interface)
        │
        ▼
SQLiteConversationStore (phoenix_core/memory/storage/sqlite_store.py — the only implementation today)
        │
        ▼
SQLite file at SQLITE_DATABASE (default: phoenix.db), created automatically on first run
```

- **Schema** (created automatically, no external migration tool): a
  `conversations` table (`id`, `user_id` unique, `created_at`, `updated_at`)
  and a `messages` table (`id`, `conversation_id`, `role`, `content`,
  `timestamp`), each with an index on its foreign key column.
- **`ConversationManager(db_path=...)`** defaults to `":memory:"` — an
  ephemeral, isolated database scoped to that instance's lifetime. This
  is what keeps every unit test side-effect-free by default while still
  exercising the real SQL code path. `PhoenixApplication` passes
  `Settings.sqlite_database` (a real file path) so conversations actually
  persist across restarts.
- **Swappable by construction**: `ConversationManager(store=...)` accepts
  any `ConversationStore` implementation — a future Redis- or
  aiosqlite-backed store is a new class implementing the same interface,
  with zero changes to `ConversationManager`, `ContextBuilder`,
  `commands.py`, or `AIRouter`. `MEMORY_BACKEND` is reserved for
  selecting between backends later; only `"sqlite"` is implemented today
  (an unsupported value logs a warning and falls back to SQLite).
- Every persistence event (database opened/initialized, conversation
  created/saved/deleted, memory trimmed) is logged — content is never
  logged, only ids and counts.
- `/health` and `/status` report the SQLite backend's `database_available`,
  `database_path`, `active_conversations`, and `total_stored_messages`.
- If the configured database file exists but is corrupted/unreadable,
  `PhoenixApplication` catches the failure and falls back to an isolated
  in-memory conversation store rather than crashing at startup (Task 013)
  — the bot still starts and `/ask` still works, just without persistence
  until the file is fixed. This is logged clearly as an error.

### AI Guard Layer (Task 011)

`/ask` now runs through a runtime-safety layer *between* `commands.py` and
`AIRouter` — never inside `AIRouter` itself (`phoenix_core/guard/`):

```
CommandContext → AIGuard.guard_request() (rate limit → prompt size → context size)
              → AIGuard.call_provider() (AIRouter.chat(), retried on transient errors)
              → AIGuard.sanitize_output() (before the text is sent to Telegram)
```

Four independent, individually testable components behind one `AIGuard` facade:

- **`RateLimiter`** — fixed-window request limiting per user (`AI_RATE_LIMIT_REQUESTS`
  requests per `AI_RATE_LIMIT_WINDOW` seconds); the window resets automatically once
  it expires. Over the limit → friendly message, provider never called.
- **`CostGuard`** — size-based (never monetary) protection: rejects an
  oversized prompt (reuses `AI_MAX_PROMPT_LENGTH`) or an oversized
  assembled context (`AI_GUARD_MAX_CONTEXT_CHARS` — a hard ceiling above
  `ContextBuilder`'s own `AI_MAX_CONTEXT_CHARS`, which already trims
  context on every `/ask`; this is a defensive backstop, not a
  replacement for that trimming).
- **`RetryPolicy`** — bounded retries with exponential backoff, but only
  for unambiguously transient errors (`AIProviderTimeoutError`,
  `AIProviderConnectionError`); authentication, invalid-request, and
  validation errors are never retried. `AI_GUARD_MAX_RETRIES` controls
  how many *additional* attempts are made after the first.
- **`OutputSanitizer`** — truncates responses over Telegram's 4096-char
  message limit (with a clear marker) and closes any unbalanced
  Markdown-ish token (`*`, `_`, `` ` ``, ` ``` `) before the text is sent.
  This always runs on `/ask` responses, even if `AIGuard` itself isn't
  registered in the container.

If `AIGuard` isn't available for any reason, `/ask` still works — it
skips rate limiting/cost guarding/retry and calls `AIRouter.chat()`
directly, exactly like before Task 011 (output sanitization still runs,
via a default `OutputSanitizer`).

No rate-limit, retry, or oversized-request log ever includes prompt or
conversation content — only counts and limits.

`/health` and `/status` include an "AI Guard Layer" entry reporting each
sub-component's configured limits and (for `RateLimiter`) how many users
currently have an active window.

## Telegram Bot (V1 MVP)

Set the following environment variable (e.g. in a local `.env` file — see `.env.example`):

```bash
PHOENIX_TELEGRAM_BOT_TOKEN=your-telegram-bot-token   # required to enable the bot
```

All commands are routed through a central `CommandDispatcher` (see
`phoenix_core/telegram/dispatcher.py`); the handler for each command lives
in `phoenix_core/telegram/commands.py` and only calls into the already
existing `AIRouter` / `ConversationManager` / `GitHubClient` /
`PluginRegistry` / `PhoenixApplication` services via the DI Container — no
duplicated business logic. Since Task 010, every handler also receives a
`CommandContext` (see `phoenix_core/telegram/context.py`) describing who
issued the command (`user_id`, `chat_id`, `username`, `language_code`) —
built once by `TelegramBot._handle` from the Telegram `Update` and passed
through unchanged by the dispatcher. Handlers that don't need caller
identity simply ignore it.

Supported commands:

- `/start` — greeting, Phoenix Core version, pointer to `/help`
- `/help` — lists every available command with a short description
- `/version` — version, read only from `phoenix_core._version.__version__`
- `/status` — per-component status overview (Telegram, GitHub, AI, Conversation Memory, Plugin Registry) + overall, via `PhoenixApplication.health_check()`
- `/health` — concise overall health summary, via the same `PhoenixApplication.health_check()`
- `/repo` — configured GitHub repository info (name, owner, default branch, visibility, stars, forks, open issues), via `GitHubClient.get_repository()`
- `/issues` — the 5 most recent open issues (number, title, status, author), via `GitHubClient.list_issues()`
- `/plugins` — Plugin Registry status (V1 stub — plugin discovery isn't implemented yet)
- `/ai` — configured AI providers, which one is default, and their status (`configured` / `unavailable`) — does **not** call any AI model
- `/ask <question>` — sends the question, plus the caller's conversation history, to the configured AI provider via `AIRouter.chat()` and returns a formatted, sanitized answer (rejects empty prompts, prompts over `AI_MAX_PROMPT_LENGTH`, and — via the AI Guard Layer — rate-limited or oversized-context requests) — see Conversation Memory Engine and AI Guard Layer above
- `/reset` — deletes the caller's current conversation
- `/memory` — shows conversation stats for the caller (id, message count, context size, last activity)
- `/brief` — daily crypto morning brief: BTC/ETH price + top 5 gainers/losers over the last 24h, via `CryptoProvider`
- `/news <symbol>` — last 5 news items for a coin (title, source, link), via `NewsProvider`- `/news <symbol>` — last 5 news items for a coin (title, source, link), via `NewsProvider`
- `/fear` — current Crypto Fear & Greed Index reading, via `FearGreedProvider`
- `/gas` — recommended Bitcoin network fees (sat/vB), via `FeesProvider`
- `/watch [symbols...]` — add coins to your watchlist, or show it with no arguments — persistence only, no alerts yet

Example `/status` response:

```
📊 Статус на Phoenix Core:
✅ AI слой: healthy
✅ Telegram: healthy
✅ GitHub: configured
❓ Plugin Registry: unknown

Общо: ✅ healthy
```

Example `/repo` response:

```
📦 Repository:
• Име: phoenix-core
• Owner: gvladimirov404-commits
• Default branch: main
• Видимост: public
• ⭐ Stars: 3
• 🍴 Forks: 0
• 🐛 Open issues: 2
```

Unknown commands and any unexpected internal error return a short, friendly
message (never a stack trace, never a token/secret) — see Task 008 Задача 3/5.

Without `PHOENIX_TELEGRAM_BOT_TOKEN` set, the bot is simply not started — the rest of the app runs normally.

## GitHub Client (V1 MVP)

Set the following environment variables (e.g. in a local `.env` file — see `.env.example`):

```bash
PHOENIX_GITHUB_TOKEN=your-github-personal-access-token   # required to enable the GitHub client
PHOENIX_GITHUB_OWNER=your-org-or-username                 # required
PHOENIX_GITHUB_REPO=your-repo-name                        # required
```

Supported operations:

- Check access to the configured repository
- Get repository info
- Get the current authenticated user's info
- Create an issue
- List issues

Not supported (out of scope for V1): Pull Requests, branch management, releases, commits, Actions/workflows.

Without `PHOENIX_GITHUB_TOKEN` set, the GitHub client is simply not started — the rest of the app runs normally.




## Crypto Module (Task CRYPTO-001)

Real-time crypto market data via the free CoinGecko API (no API key needed).

### Commands
- `/crypto btc`, `/crypto eth`, `/crypto sol` — price, 24h change, market cap, volume
- `/crypto top [N]` — top N coins by market cap (default 10)
- `/brief` — daily morning brief: BTC/ETH price, plus the top 5 gainers and top 5 losers (by 24h % change) among the top 100 coins by market cap (Task 019)

### Natural language
Questions like "Колко струва bitcoin?" or "What is the BTC price?" are answered
directly from CryptoProvider, without needing to know /crypto exists.

### Config (env vars, all optional)
- PHOENIX_CRYPTO_ENABLED (default: true)
- PHOENIX_CRYPTO_CACHE_TTL_SECONDS (default: 60)
- PHOENIX_CRYPTO_TIMEOUT / PHOENIX_CRYPTO_MAX_RETRIES / PHOENIX_CRYPTO_BASE_URL

No trading, wallet management, or investment advice — market data only.

## Market Intelligence (Task 020)

Three new read-only data sources, each following the same `Provider` +
`TTLCache` + retry shape as `CoinGeckoProvider`, and reusing the existing
`Crypto*` exception hierarchy rather than introducing a parallel one —
these are conceptually still "crypto data provider" failures.

### News — `/news <symbol>`
Backed by [CryptoPanic](https://cryptopanic.com/developers/api/) (`phoenix_core/services/intel/news_provider.py`).
Requires a free API token — sign up at
[cryptopanic.com/developers/api/keys](https://cryptopanic.com/developers/api/keys):

```bash
PHOENIX_NEWS_ENABLED=true                    # optional, default true
PHOENIX_NEWS_API_TOKEN=your-cryptopanic-token # required to enable /news
PHOENIX_NEWS_BASE_URL=https://cryptopanic.com/api/v2 # optional, default shown
PHOENIX_NEWS_TIMEOUT=15                       # optional, seconds
PHOENIX_NEWS_MAX_RETRIES=2                    # optional
PHOENIX_NEWS_CACHE_TTL_SECONDS=60             # optional
```

Without `PHOENIX_NEWS_API_TOKEN` set, `/news` returns a short friendly
"not configured" message rather than failing.

### Fear & Greed Index — `/fear`
Backed by the free, no-API-key [alternative.me](https://alternative.me/crypto/fear-and-greed-index/) endpoint
(`phoenix_core/services/intel/feargreed_provider.py`). Enabled automatically
whenever `PHOENIX_CRYPTO_ENABLED` is true (same flag as `/crypto`/`/brief`) —
no separate config needed.

### Bitcoin Network Fees — `/gas`
Backed by the free, no-API-key [mempool.space](https://mempool.space/docs/api/rest) endpoint
(`phoenix_core/services/intel/fees_provider.py`). Reports Bitcoin fee tiers
(sat/vB) rather than Ethereum gas — CoinGecko's free tier has no gas
endpoint, and Etherscan's gas oracle requires its own API key. Also rides
on `PHOENIX_CRYPTO_ENABLED`.

### Watchlist — `/watch [symbols...]`
Lets a user save coin symbols and retrieve them later — persistence only,
no notifications yet. Mirrors the Conversation Memory Engine's storage
split exactly (`phoenix_core/services/watchlist/store.py` +
`manager.py`, vs. `phoenix_core/memory/storage/` +
`manager.py`): a synchronous `SQLiteWatchlistStore` (its own
`watchlist_items` table in the same `SQLITE_DATABASE` file) behind a
`WatchlistManager` facade. `/watch btc eth sol` adds symbols (deduplicated,
case-normalized, capped at 50 per user) and returns the full list; `/watch`
with no arguments just shows it. Survives an app restart, same as
Conversation Memory.
