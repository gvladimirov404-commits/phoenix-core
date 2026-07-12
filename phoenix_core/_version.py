"""
Single source of truth for the Phoenix Core version number.

Every component that needs the version (the `phoenix_core` package,
the CLI, the Telegram bot, README, and packaging metadata in
pyproject.toml / setup.py) reads it from here — directly or indirectly —
instead of hardcoding it.
"""

__version__ = "0.1.0-alpha"
