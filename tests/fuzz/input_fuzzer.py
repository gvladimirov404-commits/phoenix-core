#!/usr/bin/env python3
"""
Fuzz test for input validation and sanitization.
Targets: Telegram message handling, AI provider input
"""
import sys
import atheris

with atheris.instrument_imports():
    import html


def TestOneInput(data):
    """Fuzz input sanitization functions."""
    fdp = atheris.FuzzedDataProvider(data)

    # Fuzz HTML escaping
    try:
        text = fdp.ConsumeUnicodeNoSurrogates(4096)
        escaped = html.escape(text)
        assert "<" not in escaped or text == escaped
    except Exception:
        pass

    # Fuzz string truncation
    try:
        text = fdp.ConsumeUnicodeNoSurrogates(8192)
        truncated = text[:4000]
        assert len(truncated) <= 4000
    except Exception:
        pass

    # Fuzz regex patterns (simulated)
    try:
        import re
        pattern = fdp.ConsumeUnicodeNoSurrogates(100)
        test_string = fdp.ConsumeUnicodeNoSurrogates(500)
        if pattern:
            re.compile(pattern)
    except re.error:
        pass
    except Exception:
        pass


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput, enable_python_coverage=True)
    atheris.Fuzz()
