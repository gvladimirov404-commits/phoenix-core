# Termux / Android Stability Notes (Task 017)

Android may kill the Phoenix Core process when Termux is backgrounded (RAM pressure or battery optimization). A clean "Shutdown signal received" ~7s after start is consistent with the OS sending SIGTERM, not a code crash.

## Steps for a longer-lived session

1. termux-wake-lock (before starting the bot; requires Termux:API)
2. Settings -> Apps -> Termux -> Battery -> No restrictions
3. Use tmux so the process survives the Termux UI closing:
   pkg install tmux
   tmux new -s phoenix
   cd ~/phoenix-core && python -m phoenix_core.cli start
   (detach: Ctrl+B then D, reattach: tmux attach -t phoenix)
4. Check which signal caused a stop:
   grep "Shutdown signal received" ~/phoenix-core/live_app.log
   SIGINT = Ctrl+C, SIGTERM = killed externally (likely Android/Termux)

These are operational steps, not code changes.
