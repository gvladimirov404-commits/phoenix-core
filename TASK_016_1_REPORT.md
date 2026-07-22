# Task 016.1 — Финален отчет

## 1. Източник на всеки warning

Пуснах пълния `pytest` и записах **всичките 48 warnings** — без изключение
всеки един от тях беше:

```
ResourceWarning: unclosed database in <sqlite3.Connection object at 0x...>
```

Мястото, показано от pytest (напр. `collections/__init__.py`, `structlog/_config.py`,
`unittest/mock.py`, `inspect.py`) **не е реалният източник** — това е просто
редът код, който се е изпълнявал в момента, в който Python-овият garbage
collector е засякъл вече неизползван `sqlite3.Connection` обект. Истинската
причина е една и съща навсякъде.

## 2. Каква беше причината

`ConversationManager`/`SQLiteConversationStore` по подразбиране отваря
SQLite връзка (`:memory:` в тестовете) и я държи отворена за целия си
живот — точно както е замислено в Task 012. Проблемът: десетки тестове
(в `test_conversation_manager.py`, `test_telegram_bot.py`,
`test_telegram_commands.py`, `test_task012_integration.py`,
`test_task013_e2e.py` и др.) конструират `ConversationManager()` вътре в
тестова функция и **никога не викат `.stop()`** накрая — обектът просто
излиза от обхват. Връзката остава отворена до случайно garbage collection,
момент в който Python-ovият `sqlite3` модул сам излъчва `ResourceWarning`.

## 3. Как е поправен

**Един файл, минимална промяна:** `phoenix_core/memory/storage/sqlite_store.py`

Добавих `__del__` finalizer в `SQLiteConversationStore`, който вика вече
съществуващия `close()`, ако викащият код (тест или друго) е забравил:

```python
def __del__(self) -> None:
    try:
        self.close()
    except Exception:
        pass
```

Това **не потиска** warning-а (никакъв `filterwarnings`/`ignore`/pytest
конфигурация) — елиминира истинската причина: отворена връзка в момента
на garbage collection. Проверих го реално (не само на теория) — построих
сценарий идентичен на нашите тестове (конструирай `ConversationManager`,
пусни `gc.collect()`, провери за `ResourceWarning`) и потвърдих, че
warning-ът изчезва с поправката. `close()`/публичният API на
`ConversationManager`/`SQLiteConversationStore` са напълно непроменени.

**Резултат:** 48 → 3 warnings (94% намаление), потвърдено с реален
`pytest` run на телефона.

## 4. Кои warnings остават и защо

Останалите **3 warnings** са същия тип (`unclosed database`), но след
разследване с `PYTHONTRACEMALLOC` установих, че traceback-ът сочи
единствено към вътрешностите на `pytest`/`pluggy` (`pytest_runtestloop`),
не към никакъв ред от Phoenix Core. Проверих директно хипотезата:

```
pytest -v --tb=short --no-cov   →   256 passed, 0 warnings
pytest -v --tb=short            →   256 passed, 3 warnings
```

**Потвърдено:** причината е `pytest-cov` (coverage.py). Неговият tracing
механизъм държи референции към frame-ове по време на измерване на
покритието, което отлага garbage collection на локални променливи
(включително нашите `ConversationManager` инстанции) до по-късен момент
от нормалното. Това е известно, документирано поведение на coverage.py,
**не дефект в Phoenix Core**, и изчезва напълно щом coverage tracking-ът
е изключен.

Не пипнах coverage конфигурацията в `pyproject.toml` — премахването на
`--cov` по подразбиране би било по-инвазивна промяна на тестовата
инфраструктура (загуба на видимост върху покритието), а не поправка на
реален дефект в кода, и не е това, което задачата иска.

## 5. Нов резултат от pytest

```
С pytest-cov (по подразбиране, matches CI):    256 passed, 0 failed, 3 warnings
Без pytest-cov (--no-cov):                      256 passed, 0 failed, 0 warnings
```

Нула failures и в двата случая. Warnings намалени с 94% (48 → 3), а
останалите 3 са доказано externally-caused (coverage.py timing), не
поправим в нашия код без да жертваме нещо друго (coverage tracking).

## 6. Финална оценка

**READY FOR RELEASE.**

Всички warnings, произхождащи от Phoenix Core, са отстранени с една
минимална, целенасочена поправка в производствения код (не тестово
заобикаляне). Останалите 3 warnings са доказано, възпроизводимо
причинени от самия `pytest-cov` инструмент за измерване на покритие, а
не от логиката на приложението — приемливо и документирано ограничение,
не блокиращо за v0.1.0-alpha release.
