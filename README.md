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
SQLITE_DATABASE=phoenix.db                            # optional, path to the SQLite database file
```

Both DeepSeek and Groq are implemented against the same `BaseAIProvider`
interface and the same OpenAI-compatible chat completions request shape —
`AIRouter`, AI Guard, Conversation Memory, and the Telegram layer work
identically regardless of which is selected. Switching providers is a
config-only change: set `AI_DEFAULT_PROVIDER=groq` and `GROQ_API_KEY`,
nothing else needs to change. If `AI_DEFAULT_PROVIDER` doesn't match any
configured provider (e.g. `GROQ_API_KEY` is set but `AI_DEFAULT_PROVIDER`
is left at its default `deepseek`), `/ask` degrades to a friendly
"provider not configured" message rather than crashing.

Run locally:

```bash
pip install -r requirements.txt
python -m phoenix_core start
```

Without `PHOENIX_AI_DEEPSEEK_API_KEY` set, the app still starts, but any AI request will fail with a clear configuration error rather than a crash.

### AI Runtime flow (Task 009)

```
Telegram → CommandDispatcher → /ask → AIRouter → AI Provider → Response → Telegram
```

`AIRouter.chat()` validates the input, resolves the configured provider (via
`get_provider()`), calls it, and returns a standardized `AIResponse`. Every
call is logged with a short request id correlating "provider selected" →
request started → completed/failed — never the prompt content itself.
`AIRouter.list_providers()` / `is_provider_available()` expose provider
configuration/availability for introspection (used by `/ai`).

Use `/ask` from Telegram:

```
/ask Какво е asyncio?
```

Example response:

```
🤖 Phoenix AI

asyncio е вградена Python библиотека за асинхронно програмиране...

Provider: deepseek
```

If the prompt is empty, exceeds `AI_MAX_PROMPT_LENGTH`, or no provider is
configured, `/ask` returns a short friendly message instead of calling the
provider — see the Telegram section below for the full command list.

### Conversation Memory Engine (Task 010)

`/ask` now remembers the current conversation per Telegram user — this is
short-term conversation memory, not long-term/persistent memory (see
`phoenix_core/memory/`):

```
Telegram → CommandDispatcher → ConversationManager → ContextBuilder → AIRouter → Provider → Conversation updated → Telegram
```

- **`ConversationManager`** (`phoenix_core/memory/manager.py`) owns
  conversation lifecycle: create/load, append messages, trim, reset, and
  report stats. It never calls an AI model.
- **`ContextBuilder`** (`phoenix_core/memory/context_builder.py`) turns a
  stored `Conversation` into the `List[Dict[str, str]]` shape `AIRouter.chat()`
  expects. `AIRouter` itself is unchanged and has no knowledge of how (or
  whether) history is stored.
- Storage is in-memory and process-local (V1 MVP) — conversations are lost
  on restart. Every access goes through `ConversationManager`'s public
  methods, so a Redis/SQLite-backed implementation can replace the storage
  later without touching `AIRouter`, `commands.py`, or `ContextBuilder`.
- History is capped at `AI_MAX_CONVERSATION_MESSAGES` messages per user
  (oldest dropped first); the context sent to the provider is additionally
  capped at `AI_MAX_CONTEXT_CHARS` combined characters (oldest dropped
  first, but the newest message is always kept).
- No message content is ever logged — only counts, ids, and timestamps.

New commands:

- `/reset` — deletes the caller's current conversation; the next `/ask` starts a new one
- `/memory` — shows conversation id, message count, context size (characters), and last activity — never the conversation content itself

If `ConversationManager` isn't available for any reason, `/ask` still
works — it falls back to a single-turn request, exactly like before Task 010.

### Persistent storage — SQLite backend (Task 012)

Conversations now survive an application restart. `ConversationManager`'s
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


