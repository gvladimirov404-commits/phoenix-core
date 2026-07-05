"""
Phoenix Core - Production-Ready Modular Python Framework

A clean-architecture framework featuring:
- Multi-model AI router (Qwen, DeepSeek, Kimi, extensible)
- Telegram control interface
- GitHub integration with Actions support
- Plugin system
- Docker & Termux compatibility
"""

__version__ = "1.0.0"
__author__ = "Phoenix Team"
__license__ = "MIT"

from phoenix_core.core.application import PhoenixApplication
from phoenix_core.core.container import Container

__all__ = ["PhoenixApplication", "Container", "__version__"]
