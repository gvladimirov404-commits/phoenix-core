# Developer Workflow (Task DEV-001)

Recommended local development loop for Phoenix Core on Termux.

## The 5 steps

1. Code - make the change (in your own sandbox/session, then rsync or edit directly in ~/phoenix-core).
2. Tests - run: python -m pytest tests/ -q
   Fix any failure before moving on.
3. Restart - run: ./scripts/restart_bot.sh
   Stops the running bot (if any) and starts a fresh instance inside the phoenix tmux session, loading whatever is currently on disk. Mandatory after any code change - Python does not hot-reload; a running process keeps executing the code it started with, however old.
4. Health Check - run: ./scripts/health_check.sh
   Confirms the process is up, SQLite is reachable, configuration loads without errors, Telegram token and AI provider are configured.
5. Telegram Live Test - send a real command (/ask ..., /crypto btc) to the bot in Telegram and confirm the actual behavior matches expectations. Automated tests and a passing health check are necessary but not sufficient - only a live message proves the deployed process behaves correctly end to end.

## One-command version

Run: ./scripts/dev_test.sh

Runs steps 2-4 (tests, restart, health check) in order and stops at the first failure with a clear error message. Step 5 stays manual on purpose - it needs a human reading the actual reply.

## Script reference

- scripts/restart_bot.sh - stops the existing bot process (graceful kill, falls back to kill -9 after 10s), starts a new one inside the phoenix tmux session (created if missing), prints the new PID, tails the last 20 lines of live_app.log. Safe to run when no bot is currently running.
- scripts/health_check.sh - checks process, SQLite, configuration loading, Telegram token, and AI provider configuration; prints PASS/FAIL per check plus a summary line; exits non-zero if anything failed.
- scripts/dev_test.sh - orchestrates the above two plus the test suite, stopping immediately on the first failing step.

## Why this exists

Task 017 traced a real production bug back to an operational mistake, not a code defect: a live bot process kept running old code for hours after the fix had already been committed, because nobody restarted it. These scripts make "restart after every change" a single command instead of a sequence of manual steps that's easy to skip under time pressure.
