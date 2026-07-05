# 🧪 Fuzz Testing

> This document describes the fuzz testing strategy for Phoenix Core using Atheris, a coverage-guided Python fuzzing engine.

---

## Overview

Fuzz testing is an automated technique for finding bugs by providing invalid, unexpected, or random data as inputs. Phoenix Core uses [Atheris](https://github.com/google/atheris), Google's coverage-guided Python fuzzer based on libFuzzer.

## Why Fuzz?

| Benefit | Description |
|---------|-------------|
| **Bug Discovery** | Finds edge cases missed by unit tests |
| **Security** | Uncovers crashes that could be exploited |
| **Robustness** | Validates input handling under extreme conditions |
| **Coverage** | Maximizes code path exploration |

## Fuzz Targets

| Target | File | Focus |
|--------|------|-------|
| Configuration Parser | `tests/fuzz/config_fuzzer.py` | Pydantic settings validation |
| Secret Manager | `tests/fuzz/secrets_fuzzer.py` | Encryption/decryption roundtrips |
| Input Sanitization | `tests/fuzz/input_fuzzer.py` | HTML escaping, regex, truncation |

## Running Fuzz Tests

### Local Execution

```bash
# Install Atheris
pip install atheris

# Run configuration fuzzer
python tests/fuzz/config_fuzzer.py -atheris_runs=10000

# Run with coverage report
python -m coverage run tests/fuzz/config_fuzzer.py -atheris_runs=10000
python -m coverage html

# Run with maximum time limit
python tests/fuzz/secrets_fuzzer.py -max_total_time=300
```

### CI/CD Execution

Fuzz tests run automatically:
- **Weekly** (Sundays at 2 AM UTC)
- **On demand** via `workflow_dispatch`
- **On push** to `main` when fuzz-related files change

See `.github/workflows/fuzz.yml`.

## Fuzzing Best Practices

### Writing Fuzz Targets

```python
import atheris
import sys

with atheris.instrument_imports():
    import my_module

def TestOneInput(data):
    """Your fuzz target function."""
    fdp = atheris.FuzzedDataProvider(data)

    # Consume structured data
    string_input = fdp.ConsumeUnicodeNoSurrogates(256)
    int_input = fdp.ConsumeIntInRange(0, 100)

    # Call the function under test
    try:
        my_module.process(string_input, int_input)
    except ExpectedException:
        pass  # Expected, ignore

if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput, enable_python_coverage=True)
    atheris.Fuzz()
```

### Corpus Management

```bash
# Create seed corpus directory
mkdir -p tests/fuzz/corpus/config

# Add seed inputs
echo '{"app_name": "test"}' > tests/fuzz/corpus/config/seed1.json

# Run with corpus
python tests/fuzz/config_fuzzer.py tests/fuzz/corpus/config/
```

## Interpreting Results

### Coverage Report

```bash
# Generate HTML coverage report
python -m coverage html

# View report
python -m http.server 8000 --directory htmlcov
```

### Crash Analysis

When Atheris finds a crash:

1. **Save the crashing input** — Atheris saves it as `crash-<hash>`
2. **Reproduce locally** — Run the fuzzer with the crash file
3. **Minimize** — Use `atheris` minimization features
4. **Fix and verify** — Add regression test, run fuzzer again

```bash
# Reproduce crash
python tests/fuzz/config_fuzzer.py crash-abc123

# Minimize crash
python tests/fuzz/config_fuzzer.py crash-abc123 -minimize_crash=1
```

## OSS-Fuzz Integration

For long-term continuous fuzzing, consider integrating with [OSS-Fuzz](https://github.com/google/oss-fuzz):

1. Fork `google/oss-fuzz`
2. Add Phoenix Core project configuration
3. Submit PR to OSS-Fuzz repository
4. Google runs fuzzers continuously on their infrastructure

## Related Documents

- [Secure Development Lifecycle](secure-development-lifecycle.md)
- [Security Architecture](security-architecture.md)

---

*Last updated: 2026-07-05*
