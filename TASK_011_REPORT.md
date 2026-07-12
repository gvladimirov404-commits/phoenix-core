# Task 011 — Финален отчет

## 1. Нови файлове

- `phoenix_core/guard/__init__.py` — публичен surface на пакета
- `phoenix_core/guard/rate_limiter.py` — `RateLimiter` (fixed-window per user)
- `phoenix_core/guard/cost_guard.py` — `CostGuard` (размер на prompt/context, не пари)
- `phoenix_core/guard/retry.py` — `RetryPolicy` (bounded retry + exponential backoff)
- `phoenix_core/guard/sanitizer.py` — `OutputSanitizer` (Telegram дължина + Markdown баланс)
- `phoenix_core/guard/guard.py` — `AIGuard` facade, композира горните 4
- `tests/unit/test_rate_limiter.py`, `test_cost_guard.py`, `test_retry_policy.py`, `test_output_sanitizer.py`, `test_ai_guard.py`

## 2. Променени файлове

- `phoenix_core/utils/exceptions.py` — `GuardError` + `RateLimitExceededError`, `PromptTooLargeError`, `ContextTooLargeError`
- `phoenix_core/config/settings.py` — `ai_rate_limit_requests` (`AI_RATE_LIMIT_REQUESTS`, default 10), `ai_rate_limit_window` (`AI_RATE_LIMIT_WINDOW`, default 60), `ai_guard_max_context_chars` (`AI_GUARD_MAX_CONTEXT_CHARS`, default 12000), `ai_guard_max_retries` (`AI_GUARD_MAX_RETRIES`, default 2)
- `phoenix_core/core/application.py` — регистрира `ai_guard` в Container-а, добавен в `_components` за `health_check()`
- `phoenix_core/telegram/commands.py` — `cmd_ask` минава през `AIGuard.guard_request()`/`call_provider()`; `_format_ai_response()` вече санитизира изхода; нов `_MSG_CONTEXT_TOO_LARGE`; `AIGuard` в `_COMPONENT_LABELS`
- `tests/unit/test_telegram_commands.py` — нови тестове за интеграцията с Guard (`TestAskCommandWithGuard`, `TestOutputSanitizationWithoutGuard`), обновен `/status` тест
- `README.md`, `.env.example`

**AIRouter публичният интерфейс, Container, ConversationManager API и общата архитектура не са пипани.** Guard слоят се извиква изцяло от `commands.cmd_ask`, отвън AIRouter.

## 3. Как работи AI Guard Layer

`AIGuard` е facade, който `cmd_ask` извиква на две места:

1. **Преди** извикване на provider: `guard_request(user_id, prompt, messages)` — rate limit → размер на prompt → размер на context, в тази последователност (rate limit е най-евтин и се проверява първи).
2. **Около** извикването: `call_provider(lambda: ai_router.chat(messages=messages))` — минава през `RetryPolicy`.
3. **След** успешен отговор: `sanitize_output(response.content)` — преди форматирането за Telegram.

Ако `ai_guard` липсва от Container-а, `/ask` пада обратно към директно извикване на `ai_router.chat()` (точно поведението от Task 010) — но **sanitization винаги се изпълнява**, дори без Guard, чрез lazily-създаден `OutputSanitizer` по подразбиране, защото това е чисто defensive и без странични ефекти.

## 4. Как работи Rate Limiting

`RateLimiter` — fixed-window (не sliding log): за всеки `user_id` пази `(window_start, count)`. При проверка: ако прозорецът е изтекъл (`now - window_start >= window_seconds`), се рестартира автоматично. Ако `count >= max_requests`, хвърля `RateLimitExceededError` и логва „Rate limit hit" (само `user_id`, лимити — без съдържание). `/ask` връща същото приятелско съобщение, което вече се ползваше за provider-level 429.

## 5. Как работи Retry Policy

`RetryPolicy.run(coro_factory)` — извиква подадения callable (нов coroutine на всеки опит, не се преизползва); при `AIProviderTimeoutError`/`AIProviderConnectionError` изчаква exponential backoff (`min(base_delay * 2^attempt, max_delay)`) и опитва отново, до `max_retries` пъти. Всичко друго (auth, validation, `AIProviderNotFoundError`, `ConfigurationError`) излиза веднага без retry.

**Важна бележка:** `DeepSeekProvider` вече прави собствен retry за 5xx отговори *вътре* в HTTP слоя, преди изобщо да хвърли изключение. Guard-ният `RetryPolicy` работи на едно ниво по-нагоре (около `AIRouter.chat()`) и хваща само `AIProviderTimeoutError`/`AIProviderConnectionError` — умишлено НЕ хваща генеричния `AIProviderError`, защото DeepSeek използва точно този клас както за 401/403 автентикация, така и за други неразпознати HTTP грешки; нямаше как безопасно да различа „временна грешка" от „auth се провали" на това ниво. Детайли в `phoenix_core/guard/retry.py` docstring.

## 6. Как работи Output Sanitization

`OutputSanitizer.sanitize(text)`:
- балансира `*`, `_`, `` ` ``, ``` ``` ``` — ако броят е нечетен, добавя затварящ символ в края;
- след това съкращава до 4096 символа (истинският лимит на Telegram `sendMessage`) с ясен маркер „…[съкратено, отговорът беше твърде дълъг]".

Работи независимо дали `AIGuard` е регистриран — виж т. 3.

## 7. Тестово покритие

- `test_rate_limiter.py` — лимит, различни потребители, изтичане на прозорец (с monkeypatch на `time.monotonic`), `active_entries`, health_check
- `test_cost_guard.py` — prompt/context в/над лимита, гранични случаи, health_check
- `test_retry_policy.py` — успех без retry, успех след N неуспешни опита, изчерпване на retry-и, non-retryable изключения не се повтарят (вкл. изричен тест, че генеричният `AIProviderError` не се retry-ва)
- `test_output_sanitizer.py` — passthrough, баланс на всеки тип token, truncation, гранични случаи
- `test_ai_guard.py` — facade композицията, ред на проверките, health_check агрегация
- `test_telegram_commands.py::TestAskCommandWithGuard` — rate limit блокира заявка без да вика provider-а, rate limit е per-user, oversized context блокиран, успешен отговор минава през sanitizer, retry при временна грешка, изчерпване на retry-и
- `test_telegram_commands.py::TestOutputSanitizationWithoutGuard` — sanitization работи и без Guard в контейнера

Само `MockAIProvider` и monkeypatch на `asyncio.sleep`/`time.monotonic` — без реални HTTP заявки и без реално чакане.

**Ограничение на средата:** отново нямам мрежа/runtime зависимости тук, затова `pytest` не се изпълни физически. Направих `py_compile` (чисто) на всички нови/променени файлове плюс ръчно изпълнение на цялата бизнес логика (RateLimiter, CostGuard, RetryPolicy, OutputSanitizer, AIGuard facade) директно в Python с фалшив logger — всички проверени случаи минаха успешно. Истинско `pytest` изпълнение — в Codespaces.

## 8. Известни ограничения

- `RateLimiter` е fixed-window, не sliding log — възможен е кратък burst около границата на прозореца (приемлив компромис за anti-abuse механизъм, не прецизна квота)
- Retry-ят покрива само `AIProviderTimeoutError`/`AIProviderConnectionError`; генеричният `AIProviderError` (auth + прочие HTTP грешки в DeepSeek) не се retry-ва — виж т. 5
- `OutputSanitizer`-ът балансира Markdown token-и чрез просто броене на четност — не е пълен Markdown parser (умишлено, по т. 5 от спецификацията)
- Всичко е in-memory и process-local, като `ConversationManager` от Task 010 — рестарт нулира rate-limit прозорците

## 9. Препоръка за Task 012

Разделяне на DeepSeek-ния генеричен `AIProviderError` на по-конкретни класове
(напр. `AIProviderAuthenticationError` vs `AIProviderServerError`), за да може
retry policy-то по-нататък да различава auth провал от изчерпан 5xx retry
без риск да повтаря auth грешки. Извън това — интеграционен тест в
Codespaces с реален DeepSeek sandbox key, за да се потвърди, че двете
retry нива (provider-level 5xx + guard-level timeout/connection) не влизат
в конфликт на практика.
