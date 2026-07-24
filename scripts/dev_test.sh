#!/usr/bin/env bash
# dev_test.sh — full local development workflow: tests -> restart -> health
# check, stopping immediately on the first failure (Task DEV-001).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$APP_DIR" || { echo "ERROR: cannot cd to $APP_DIR"; exit 1; }

echo "=================================================="
echo "Phoenix Core — Full Development Workflow (dev_test.sh)"
echo "=================================================="

echo ""
echo "--- Step 1/3: Running test suite ---"
if ! python -m pytest tests/ -q; then
    echo ""
    echo "ERROR: Test suite failed. Stopping — fix failing tests before restarting the bot."
    exit 1
fi
echo "Test suite passed."

echo ""
echo "--- Step 2/3: Restarting bot ---"
if ! "$SCRIPT_DIR/restart_bot.sh"; then
    echo ""
    echo "ERROR: restart_bot.sh failed. Stopping."
    exit 1
fi

echo ""
echo "--- Step 3/3: Health check ---"
if ! "$SCRIPT_DIR/health_check.sh"; then
    echo ""
    echo "ERROR: health_check.sh reported failures. Investigate before doing a live Telegram test."
    exit 1
fi

echo ""
echo "=================================================="
echo "All steps passed. Ready for a live Telegram test."
echo "=================================================="
exit 0
