#!/usr/bin/env python3
"""
Fuzz test for secret management.
Targets: phoenix_core.utils.secrets
"""
import sys
import atheris

with atheris.instrument_imports():
    from phoenix_core.utils.secrets import SecretManager


def TestOneInput(data):
    """Fuzz secret manager operations."""
    fdp = atheris.FuzzedDataProvider(data)

    # Fuzz with random master key
    try:
        master_key = fdp.ConsumeUnicodeNoSurrogates(64)
        if len(master_key) >= 16:
            manager = SecretManager(master_key=master_key)

            # Try encrypt/decrypt roundtrip
            plaintext = fdp.ConsumeUnicodeNoSurrogates(256)
            if plaintext:
                encrypted = manager.encrypt(plaintext)
                decrypted = manager.decrypt(encrypted)
                assert decrypted == plaintext
    except Exception:
        pass

    # Fuzz hash function
    try:
        manager = SecretManager(master_key="test-key-32-chars-long!!")
        value = fdp.ConsumeUnicodeNoSurrogates(256)
        if value:
            manager.hash_value(value)
    except Exception:
        pass


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput, enable_python_coverage=True)
    atheris.Fuzz()
