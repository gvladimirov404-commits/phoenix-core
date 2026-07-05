# 🔍 Secrets Scanning

> This document describes the secrets scanning strategy for Phoenix Core, including automated detection of leaked credentials, API keys, and sensitive data.

---

## Overview

Secrets scanning is a critical security control that prevents accidental exposure of sensitive credentials in source code, commit history, and CI/CD artifacts.

## Tools

### GitLeaks

[GitLeaks](https://github.com/gitleaks/gitleaks) is the primary secrets scanning tool used in Phoenix Core.

#### Configuration

The `.gitleaks.toml` file defines custom rules for detecting Phoenix-specific secrets:

| Rule | Pattern | Example |
|------|---------|---------|
| `phoenix-api-key` | AI provider API keys | `sk-abc123...` |
| `telegram-bot-token` | Telegram bot tokens | `123456:ABC-DEF...` |
| `github-pat-classic` | GitHub classic PATs | `ghp_xxxxxxxx...` |
| `github-pat-fine-grained` | GitHub fine-grained PATs | `github_pat_...` |
| `phoenix-secret-key` | Application secret keys | `phoenix-secret-key=...` |

#### Running Locally

```bash
# Install GitLeaks
brew install gitleaks

# Scan current directory
gitleaks detect --source . --config .gitleaks.toml

# Scan with verbose output
gitleaks detect --source . --config .gitleaks.toml --verbose

# Scan git history
gitleaks detect --source . --config .gitleaks.toml --log-opts="--all"
```

#### CI/CD Integration

GitLeaks runs automatically on every push and pull request via `.github/workflows/gitleaks.yml`.

### Pre-commit Hook

```bash
# Install pre-commit
pip install pre-commit
pre-commit install

# Now GitLeaks runs before every commit
```

### Allowlist

The `.gitleaks.toml` allowlist excludes:
- Test files (`tests/`)
- Documentation (`docs/`)
- Example placeholders (`your-api-key-here`)
- Demo/test tokens (`sk-test-...`, `ghp_test_...`)

---

## Response to Detected Secrets

If GitLeaks detects a secret:

1. **Do not commit.** The commit will be blocked.
2. **Revoke the exposed secret** immediately in the provider dashboard.
3. **Generate a new secret** and update your local `.env` file.
4. **Clean git history** if the secret was already committed:
   ```bash
   git filter-branch --force --index-filter      'git rm --cached --ignore-unmatch path/to/file'      HEAD
   ```
5. **Force push** the cleaned history (coordinate with team).

---

## Related Documents

- [Secrets Management](secrets-management.md)
- [Security Architecture](security-architecture.md)
- [Secure Development Lifecycle](secure-development-lifecycle.md)

---

*Last updated: 2026-07-05*
