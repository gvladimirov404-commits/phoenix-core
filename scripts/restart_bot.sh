#!/usr/bin/env bash
set -uo pipefail

SESSION="phoenix"
APP_DIR="$HOME/phoenix-core"
LOG_FILE="$APP_DIR/live_app.log"
START_CMD="cd $APP_DIR && python -m phoenix_core.cli start"
PROC_PATTERN="phoenix_core.cli start"

echo "== Phoenix Core: restart_bot.sh =="

OLD_PID=$(pgrep -f "$PROC_PATTERN" | head -n1 || true)

if [ -n "${OLD_PID:-}" ]; then
    echo "Stopping existing process (PID $OLD_PID)..."
    kill "$OLD_PID" 2>/dev/null || true
    for i in 1 2 3 4 5 6 7 8 9 10; do
        if ! kill -0 "$OLD_PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "WARNING: PID $OLD_PID did not stop gracefully within 10s, forcing kill -9"
        kill -9 "$OLD_PID" 2>/dev/null || true
        sleep 1
    else
        echo "Previous process stopped cleanly."
    fi
else
    echo "No previous Phoenix Core process found - starting fresh (this is fine)."
fi

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "tmux session '$SESSION' does not exist - creating it."
    tmux new-session -d -s "$SESSION"
fi

echo "Starting new instance inside tmux session '$SESSION'..."
tmux send-keys -t "$SESSION" "$START_CMD" C-m

echo "Waiting for startup..."
sleep 5

NEW_PID=$(pgrep -f "$PROC_PATTERN" | head -n1 || true)

if [ -z "${NEW_PID:-}" ]; then
    echo "ERROR: Phoenix Core did not start - no matching process found."
    echo "Check the tmux session manually: tmux attach -t $SESSION"
    exit 1
fi

if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "Phoenix Core is running. New PID: $NEW_PID"
else
    echo "ERROR: found PID $NEW_PID but it is not alive."
    exit 1
fi

echo ""
echo "== Last 20 log lines ($LOG_FILE) =="
if [ -f "$LOG_FILE" ]; then
    tail -n 20 "$LOG_FILE"
else
    echo "(log file not found yet: $LOG_FILE)"
fi

exit 0
