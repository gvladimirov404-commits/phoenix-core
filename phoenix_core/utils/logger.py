"""
Structured logging with multiple output formats.
Supports JSON, console (rich), and simple text formats.
"""
import logging
import logging.handlers
import sys
from types import TracebackType
from typing import Any, Dict, Optional, Type

import structlog
from rich.console import Console
from rich.logging import RichHandler


def configure_logging(
    level: str = "INFO",
    format_type: str = "console",
    file_path: Optional[str] = None,
    max_bytes: int = 10_485_760,
    backup_count: int = 5,
    enable_console: bool = True,
) -> None:
    """Configure structured logging"""
    # Configure standard library logging
    logging_level = getattr(logging, level.upper(), logging.INFO)
    handlers: list[logging.Handler] = []

    if enable_console:
        if format_type == "console":
            console = Console(stderr=True)
            rich_handler = RichHandler(
                console=console,
                rich_tracebacks=True,
                tracebacks_show_locals=True,
            )
            rich_handler.setLevel(logging_level)
            handlers.append(rich_handler)
        else:
            stream_handler = logging.StreamHandler(sys.stderr)
            stream_handler.setLevel(logging_level)
            handlers.append(stream_handler)

    if file_path:
        file_handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging_level)
        handlers.append(file_handler)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging_level)
    root_logger.handlers = []
    for handler in handlers:
        root_logger.addHandler(handler)

    # httpx/httpcore log the full request URL at INFO level by default.
    # The Telegram Bot API embeds the bot token directly in the URL path
    # (https://api.telegram.org/bot<TOKEN>/method — not an Authorization
    # header), so leaving these at INFO leaks the real token into logs on
    # every Telegram API call (Task 016, live validation finding). Capping
    # them at WARNING keeps real httpx/httpcore problems visible while
    # suppressing their routine per-request logging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Configure structlog
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]

    if format_type == "json":
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    elif format_type == "simple":
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=False),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance"""
    return structlog.get_logger(name)


class LogContext:
    """Context manager for adding context to logs"""
    def __init__(self, **context: Any):
        """Store key/value pairs to bind onto all logs emitted inside this context."""
        self.context = context
        self.token: Optional[Dict[str, Any]] = None

    def __enter__(self) -> "LogContext":
        """Bind the stored context vars for the duration of the `with` block."""
        self.token = structlog.contextvars.bind_contextvars(**self.context)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Unbind the context vars bound by __enter__."""
        structlog.contextvars.unbind_contextvars(*self.context.keys())
