#!/usr/bin/env bash
# health_check.sh — verify Phoenix Core's runtime prerequisites and print a
# concise PASS/FAIL summary (Task DEV-001).
set -uo pipefail

APP_DIR="$HOME/phoenix-core"
PROC_PATTERN="phoenix_core.cli start"

cd "$APP_DIR" || { echo "ERROR: cannot cd to $APP_DIR"; exit 1; }

PASS_COUNT=0
FAIL_COUNT=0

run_check() {
    local name="$1"
    local code="$2"
    local output
    output=$(python3 -c "$code" 2>&1)
    local status=$?
    if [ "$status" -eq 0 ]; then
        echo "PASS - $name"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "FAIL - $name"
        if [ -n "$output" ]; then
            echo "$output" | sed 's/^/    /'
        fi
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

echo "== Phoenix Core: health_check.sh =="
echo ""

if pgrep -f "$PROC_PATTERN" > /dev/null 2>&1; then
    echo "PASS - Bot process running"
    PASS_COUNT=$((PASS_COUNT + 1))
else
    echo "FAIL - Bot process running"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

run_check "SQLite database accessible" '
import sqlite3, sys
try:
    conn = sqlite3.connect("phoenix.db")
    conn.execute("SELECT 1")
    conn.close()
except Exception as e:
    print(f"detail: {e}")
    sys.exit(1)
'

run_check "Configuration loads correctly" '
import sys
try:
    from phoenix_core.config.settings import Settings
    Settings.load()
except Exception as e:
    print(f"detail: {e}")
    sys.exit(1)
'

run_check "Telegram token configured" '
import sys
from phoenix_core.config.settings import Settings
s = Settings.load()
token = s.telegram.bot_token.get_secret_value()
if not token:
    print("detail: PHOENIX_TELEGRAM_BOT_TOKEN is empty")
    sys.exit(1)
'

run_check "AI provider configured" '
import sys
from phoenix_core.config.settings import Settings
s = Settings.load()
if not s.ai_providers:
    print("detail: no AI providers configured (ai_providers is empty)")
    sys.exit(1)
'

echo ""
echo "== Summary: $PASS_COUNT passed, $FAIL_COUNT failed =="

if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0
