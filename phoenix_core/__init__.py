"""
Phoenix Core - Modular Python AI Framework (v0.1.0-alpha)

A clean-architecture framework featuring:
- AI router with pluggable providers (DeepSeek and Groq implemented; the
  router/config layer is designed for more, not yet built)
- Telegram control interface (command dispatcher, conversation memory, AI Guard Layer)
- Persistent conversation storage (SQLite backend, swappable via ConversationStore)
- GitHub integration (repository info, issues)
- Plugin system (registry scaffolding; discovery/loading not yet implemented)
- Termux/Android-friendly (no heavy system dependencies)
"""

from phoenix_core._version import __version__

__author__ = "Phoenix Team"
__license__ = "MIT"

from phoenix_core.core.application import PhoenixApplication
from phoenix_core.core.container import Container

__all__ = ["PhoenixApplication", "Container", "__version__"]
