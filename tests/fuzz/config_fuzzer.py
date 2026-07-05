#!/usr/bin/env python3
"""
Fuzz test for configuration parsing.
Targets: phoenix_core.config.settings
"""
import sys
import atheris
import json

with atheris.instrument_imports():
    from phoenix_core.config.settings import Settings, AIProviderConfig


def TestOneInput(data):
    """Fuzz configuration parsing."""
    fdp = atheris.FuzzedDataProvider(data)

    # Fuzz with random JSON-like input
    try:
        json_str = fdp.ConsumeUnicodeNoSurrogates(4096)
        config = json.loads(json_str)

        # Try to create settings from fuzzed data
        if isinstance(config, dict):
            Settings(**config)
    except (json.JSONDecodeError, Exception):
        pass

    # Fuzz AIProviderConfig
    try:
        name = fdp.ConsumeUnicodeNoSurrogates(50)
        api_key = fdp.ConsumeUnicodeNoSurrogates(100)
        if name and api_key:
            AIProviderConfig(name=name, api_key=api_key)
    except Exception:
        pass


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput, enable_python_coverage=True)
    atheris.Fuzz()
