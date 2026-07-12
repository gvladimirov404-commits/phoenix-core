# Phoenix Core — Release Checklist (v0.1.0-alpha)

This checklist is the minimum set of things to verify before deploying
Phoenix Core anywhere. It reflects the state of the project after
Task 013 (Production Validation & End-to-End Readiness).

## Environment variables

Required for the bot to actually do anything useful — see `.env.example`
for the full list with defaults. At minimum for a working deployment:

- [ ] `PHOENIX_TELEGRAM_BOT_TOKEN` set (bot won't start without it — `TelegramBot.start()` raises `ConfigurationError` if empty)
- [ ] `PHOENIX_AI_DEEPSEEK_API_KEY` set, if `/ask` is expected to work (without it, `/ask` degrades to a friendly "AI слоят не е конфигуриран" message rather than failing)
- [ ] `PHOENIX_GITHUB_TOKEN` / `PHOENIX_GITHUB_OWNER` / `PHOENIX_GITHUB_REPO` set, if `/repo` and `/issues` are expected to work (otherwise they degrade to a friendly "не е конфигуриран" message)
- [ ] `SQLITE_DATABASE` points to a writable path (default `phoenix.db`, relative to the working directory — confirm this is what's intended before deploying, especially under Termux/Codespaces where the working directory can vary between runs)
- [ ] Rate limit / cost guard / retry defaults (`AI_RATE_LIMIT_REQUESTS`, `AI_RATE_LIMIT_WINDOW`, `AI_MAX_PROMPT_LENGTH`, `AI_MAX_CONVERSATION_MESSAGES`, `AI_MAX_CONTEXT_CHARS`, `AI_GUARD_MAX_CONTEXT_CHARS`, `AI_GUARD_MAX_RETRIES`) reviewed — the shipped defaults are reasonable for a single-user/small-group bot, revisit if usage patterns differ

## Startup

- [ ] Clean start (no existing `phoenix.db`) creates the SQLite file and schema automatically — verified in `test_sqlite_conversation_store.py::TestInitialize`
- [ ] `PhoenixApplication` registers every component (`ai_router`, `conversation_manager`, `context_builder`, `ai_guard`, `github_client` if configured, `telegram_bot`, `plugin_registry`) without raising, even when optional services (AI, GitHub) are unconfigured
- [ ] A corrupted `phoenix.db` file does **not** crash startup — `PhoenixApplication` catches `StorageError` and falls back to an in-memory conversation store, logging the failure clearly (Task 013 fix — see final report §5)
- [ ] `phoenix start` (CLI entry point) boots successfully with a valid `.env`

## Shutdown

- [ ] `PhoenixApplication.stop()` calls `stop()` on every component that defines one (`TelegramBot`, `AIRouter`, `ConversationManager`) — confirmed by code review; `ConversationManager.stop()` closes the SQLite connection cleanly
- [ ] Stopping mid-request is not specifically handled/tested — a request in flight when shutdown is triggered may not complete gracefully (known limitation, see final report)

## Database (SQLite)

- [ ] Schema (`conversations`, `messages` tables + indexes) created automatically, idempotently — safe to restart repeatedly
- [ ] Conversations persist across restarts — verified with a real file-based test in `test_conversation_manager.py::TestPersistenceAcrossRestart` and `test_task013_e2e.py::TestRestartValidation`
- [ ] `/health` and `/status` report `database_available`, `database_path`, `active_conversations`, `total_stored_messages`
- [ ] Corrupted database file degrades to in-memory rather than crashing (see Startup above)
- [ ] No message content ever appears in logs — only counts, ids, timestamps (verified by grep audit, see final report §3)

## Telegram

- [ ] All 12 commands respond through the same `CommandDispatcher` path: `/start /help /version /status /health /repo /issues /plugins /ai /ask /reset /memory`
- [ ] Unknown commands return a friendly message, never a stack trace
- [ ] Every command handler catches its own expected failure modes; `CommandDispatcher`'s blanket `except Exception` is the only safety net for genuinely unexpected errors

## AI (AIRouter + AI Guard Layer)

- [ ] Missing AI provider configuration degrades `/ask` to a friendly message, not a crash
- [ ] Rate limiting blocks excess requests per user without calling the provider
- [ ] Oversized prompt/context rejected before the provider is called
- [ ] Transient errors (`AIProviderTimeoutError`, `AIProviderConnectionError`) retry with bounded backoff; auth/validation errors do not retry
- [ ] Retry exhaustion still returns a friendly message, not a raised exception
- [ ] AI response text is sanitized (length + Markdown-token balancing) before being sent to Telegram, even if `AIGuard` itself isn't registered

## GitHub

- [ ] Missing token: `/repo` and `/issues` degrade to a friendly message
- [ ] Auth failure, not-found, forbidden, and rate-limit errors from the GitHub API each map to a distinct friendly message, with no token or internal detail leaked

## Tests

- [ ] `py_compile` passes on the full `phoenix_core/` and `tests/` tree (verified in this environment; see final report for why full `pytest` couldn't run here)
- [ ] Unit tests cover: Container, CommandDispatcher, CommandContext, TelegramBot, all command handlers, AIRouter, DeepSeekProvider, GitHubClient, PluginRegistry stub, ConversationManager, ContextBuilder, SQLiteConversationStore, RateLimiter, CostGuard, RetryPolicy, OutputSanitizer, AIGuard
- [ ] Integration tests (`tests/unit/test_task012_integration.py`, `tests/unit/test_task013_e2e.py`) cover the full Telegram → Dispatcher → ConversationManager → SQLite → AI Guard → AIRouter → response chain, restart persistence, and every error scenario from Task 013 §5
- [ ] **Action required before tagging a release:** run the full suite for real in Codespaces/Termux (`pytest`) — this environment has no network access and is missing `httpx`, `pydantic`, `pydantic-settings`, `structlog`, `python-telegram-bot`, so tests here were validated via `py_compile`, manual logic execution (for stdlib-only modules like the SQLite store), and code review rather than a live `pytest` run

## Known limitations (carried into v0.1.0-alpha)

- Conversation storage is single-connection SQLite (no WAL, no pooling) — fine for a single-user/small-group bot, not load-tested beyond that
- `RateLimiter` is fixed-window, not sliding-log — a short burst at a window boundary is possible
- Retry only covers unambiguous transient errors (`AIProviderTimeoutError`/`AIProviderConnectionError`); DeepSeek's generic `AIProviderError` (shared between auth failures and other HTTP errors) is not retried — see Task 011 report
- `MEMORY_BACKEND` only supports `"sqlite"` today; other values log a warning and fall back to SQLite
- Plugin discovery/loading is a stub (`PluginRegistry.list_plugins()` raises `NotImplementedError`) — `/plugins` reports this honestly rather than pretending plugins exist
- No graceful handling of shutdown mid-request (see Shutdown above)
- Full `pytest` run has not happened in a real environment as part of this task — required before tagging

## Sign-off

- [ ] Full `pytest` run completed in Codespaces/Termux with no failures
- [ ] `.env` reviewed against `.env.example` for the target deployment
- [ ] This checklist reviewed and any unchecked item explicitly accepted as a known limitation for v0.1.0-alpha
