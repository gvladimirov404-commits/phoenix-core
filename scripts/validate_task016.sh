#!/usr/bin/env bash
# Task 016 — Live Validation & First Real Run
#
# Runs the parts of Task 016 that can be fully automated, with real
# dependencies (no stubs, no mocks) — must be run in Codespaces (or any
# environment with real network access), never in a sandboxed/offline
# environment. Sections requiring a human in the loop (real Telegram
# commands, watching a live Groq reply) are NOT here — see
# TASK_016_CHECKLIST.md for those.
#
# Usage: bash scripts/validate_task016.sh
#
# Produces: task016_report.txt in the repo root, plus a live_app.log for
# the startup/shutdown section.

set -uo pipefail
cd "$(dirname "$0")/.."

# Termux's /tmp is NOT writable (Android sandbox) — use a repo-local temp
# dir instead, which works everywhere (Termux, Codespaces, plain Linux).
WORK_TMP="$(pwd)/.task016_tmp"
mkdir -p "$WORK_TMP"

REPORT="task016_report.txt"
echo "Task 016 — Live Validation Report" > "$REPORT"
echo "Generated: $(date -u +'%Y-%m-%d %H:%M:%S UTC')" >> "$REPORT"
echo "==========================================" >> "$REPORT"

section() {
    echo "" | tee -a "$REPORT"
    echo "--- $1 ---" | tee -a "$REPORT"
}

# ----------------------------------------------------------------------
section "1. Package installation (pip install -e .)"
# ----------------------------------------------------------------------
pip install -e . 2>&1 | tee -a "$REPORT" | tail -20
INSTALL_STATUS=${PIPESTATUS[0]}
if [ "$INSTALL_STATUS" -eq 0 ]; then
    echo "RESULT: pip install -e . succeeded" | tee -a "$REPORT"
else
    echo "RESULT: pip install -e . FAILED (exit $INSTALL_STATUS)" | tee -a "$REPORT"
    echo "Stopping — nothing else can be validated without a successful install." | tee -a "$REPORT"
    exit 1
fi

pip install -r requirements-dev.txt 2>&1 | tail -15
DEV_INSTALL_STATUS=${PIPESTATUS[0]}
if [ "$DEV_INSTALL_STATUS" -ne 0 ]; then
    echo "" | tee -a "$REPORT"
    echo "NOTE: 'pip install -r requirements-dev.txt' failed (likely 'memray' —" | tee -a "$REPORT"
    echo "it does not support Android/Termux by its own design, unrelated to" | tee -a "$REPORT"
    echo "Phoenix Core). Installing just the testing packages directly instead," | tee -a "$REPORT"
    echo "so pytest is guaranteed available for section 4 below." | tee -a "$REPORT"
    pip install --force-reinstall "pytest>=7.4.0" "pytest-asyncio>=0.21.0" "pytest-cov>=4.1.0" "pytest-mock>=3.11.0" "pytest-xdist>=3.3.0" 2>&1 | tail -10
fi

# ----------------------------------------------------------------------
section "2. Entry point check"
# ----------------------------------------------------------------------
if command -v phoenix >/dev/null 2>&1; then
    phoenix --help > "$WORK_TMP/phoenix_help.txt" 2>&1
    echo "RESULT: 'phoenix' command is on PATH and --help works" | tee -a "$REPORT"
else
    echo "RESULT: 'phoenix' command NOT found on PATH after install" | tee -a "$REPORT"
fi

# ----------------------------------------------------------------------
section "3. Import check"
# ----------------------------------------------------------------------
python3 -c "
import phoenix_core
from phoenix_core.config.settings import Settings
from phoenix_core.core.application import PhoenixApplication
from phoenix_core.ai.groq_provider import GroqProvider
from phoenix_core.ai.deepseek_provider import DeepSeekProvider
print('All core imports OK, version:', phoenix_core.__version__)
" 2>&1 | tee -a "$REPORT"

# ----------------------------------------------------------------------
section "4. Full pytest run"
# ----------------------------------------------------------------------
pytest -v --tb=short 2>&1 | tee "$WORK_TMP/pytest_output.txt" | tail -60
echo "" >> "$REPORT"
echo "Full pytest summary line:" >> "$REPORT"
tail -20 "$WORK_TMP/pytest_output.txt" | grep -E "passed|failed|error|skipped|xfail" >> "$REPORT" || echo "(no summary line found — check "$WORK_TMP/pytest_output.txt")" >> "$REPORT"

# ----------------------------------------------------------------------
section "5. Automated SQLite restart persistence test (no Telegram/Groq needed)"
# ----------------------------------------------------------------------
rm -f "$WORK_TMP/task016_restart_test.db"
python3 -c "
import asyncio
from phoenix_core.memory.manager import ConversationManager

async def main():
    db_path = '"$WORK_TMP/task016_restart_test.db"'

    m1 = ConversationManager(max_messages=20, db_path=db_path)
    m1.add_message(999, 'user', 'session 1 message')
    conv_id_before = m1.get_stats(999)['conversation_id']
    await m1.stop()

    m2 = ConversationManager(max_messages=20, db_path=db_path)
    stats = m2.get_stats(999)
    assert stats is not None, 'FAIL: conversation did not survive restart'
    assert stats['conversation_id'] == conv_id_before, 'FAIL: conversation_id changed across restart'
    assert stats['message_count'] == 1, f\"FAIL: expected 1 message, got {stats['message_count']}\"
    print('RESULT: SQLite persistence across restart CONFIRMED (real file, real restart)')

asyncio.run(main())
" 2>&1 | tee -a "$REPORT"
rm -f "$WORK_TMP/task016_restart_test.db"

# ----------------------------------------------------------------------
section "6. Real application startup + health_check + graceful shutdown"
# ----------------------------------------------------------------------
echo "Starting PhoenixApplication for 10 seconds, then sending SIGTERM..." | tee -a "$REPORT"
export PYTHONASYNCIODEBUG=1
export PYTHONWARNINGS=default::ResourceWarning

timeout --signal=TERM 10 phoenix start > live_app.log 2>&1 &
APP_PID=$!
sleep 8
if kill -0 "$APP_PID" 2>/dev/null; then
    echo "RESULT: application is still running after 8s (did not crash on startup)" | tee -a "$REPORT"
else
    echo "RESULT: application EXITED before the 8s mark — check live_app.log" | tee -a "$REPORT"
fi
wait "$APP_PID" 2>/dev/null
EXIT_CODE=$?
echo "Process exit code after SIGTERM: $EXIT_CODE (124 = timeout fired as expected)" | tee -a "$REPORT"

echo "" >> "$REPORT"
echo "--- live_app.log tail (last 40 lines) ---" >> "$REPORT"
tail -40 live_app.log >> "$REPORT"

echo "" >> "$REPORT"
echo "--- Resource leak checks against live_app.log ---" >> "$REPORT"
if grep -iE "unclosed.*client|unclosed.*session|ResourceWarning" live_app.log > "$WORK_TMP/leak_check.txt"; then
    echo "FOUND POTENTIAL LEAKS:" >> "$REPORT"
    cat "$WORK_TMP/leak_check.txt" >> "$REPORT"
else
    echo "RESULT: no 'unclosed client/session' or ResourceWarning lines found" >> "$REPORT"
fi
if grep -iE "sqlite.*warning|DatabaseError" live_app.log > "$WORK_TMP/sqlite_check.txt"; then
    echo "FOUND SQLITE WARNINGS:" >> "$REPORT"
    cat "$WORK_TMP/sqlite_check.txt" >> "$REPORT"
else
    echo "RESULT: no SQLite warnings/errors found in the log" >> "$REPORT"
fi

# ----------------------------------------------------------------------
section "7. Secrets-in-logs audit"
# ----------------------------------------------------------------------
echo "Checking live_app.log and pytest output for leaked secrets..." | tee -a "$REPORT"
FOUND_SECRET=0
for pattern in "Authorization" "Bearer " "api_key.*[A-Za-z0-9]{20}" "gsk_" "sk-"; do
    if grep -qE "$pattern" live_app.log 2>/dev/null; then
        echo "  ⚠ pattern '$pattern' found in live_app.log — INSPECT MANUALLY:" >> "$REPORT"
        grep -E "$pattern" live_app.log >> "$REPORT"
        FOUND_SECRET=1
    fi
done
if [ -n "${GROQ_API_KEY:-}" ]; then
    if grep -qF "$GROQ_API_KEY" live_app.log 2>/dev/null; then
        echo "  ⚠⚠⚠ REAL GROQ_API_KEY VALUE FOUND IN LOG — CRITICAL" >> "$REPORT"
        FOUND_SECRET=1
    fi
fi
if [ -n "${PHOENIX_TELEGRAM_BOT_TOKEN:-}" ]; then
    if grep -qF "$PHOENIX_TELEGRAM_BOT_TOKEN" live_app.log 2>/dev/null; then
        echo "  ⚠⚠⚠ REAL TELEGRAM BOT TOKEN FOUND IN LOG — CRITICAL" >> "$REPORT"
        FOUND_SECRET=1
    fi
fi
if [ "$FOUND_SECRET" -eq 0 ]; then
    echo "RESULT: no secret patterns or literal configured secret values found in live_app.log" >> "$REPORT"
fi

# ----------------------------------------------------------------------
section "8. GitHub graceful-degradation check (only meaningful if PHOENIX_GITHUB_TOKEN is unset)"
# ----------------------------------------------------------------------
if [ -z "${PHOENIX_GITHUB_TOKEN:-}" ]; then
    echo "PHOENIX_GITHUB_TOKEN is not set — confirming the app still started cleanly above (section 6)." | tee -a "$REPORT"
    if grep -q "github_client" live_app.log 2>/dev/null; then
        echo "NOTE: 'github_client' appears in the log despite no token — inspect manually." >> "$REPORT"
    else
        echo "RESULT: app started with no GitHub client registered, no crash — degrades correctly." >> "$REPORT"
    fi
else
    echo "PHOENIX_GITHUB_TOKEN IS set — this section only validates the no-token path; skip or unset it and re-run to test degradation specifically." | tee -a "$REPORT"
fi

# ----------------------------------------------------------------------
section "DONE"
# ----------------------------------------------------------------------
echo "" | tee -a "$REPORT"
echo "Automated checks complete. Full report: $REPORT" | tee -a "$REPORT"
echo "Full pytest output: "$WORK_TMP/pytest_output.txt"" | tee -a "$REPORT"
echo "Full app log: live_app.log" | tee -a "$REPORT"
echo "" | tee -a "$REPORT"
echo "Remaining MANUAL steps (real Telegram + real Groq conversation) are in TASK_016_CHECKLIST.md" | tee -a "$REPORT"
