# 🔐 Secrets Management Guide

> This document defines the complete secrets management strategy for Phoenix Core, covering generation, storage, rotation, and revocation of all sensitive credentials.

---

## Table of Contents

1. [Principles](#principles)
2. [Secret Types](#secret-types)
3. [GitHub Secrets](#github-secrets)
4. [Environment Variables](#environment-variables)
5. [Secret Rotation](#secret-rotation)
6. [Key Lifecycle](#key-lifecycle)
7. [Never Store Secrets in Source Code](#never-store-secrets-in-source-code)
8. [Secret Scanning](#secret-scanning)
9. [Credential Revocation](#credential-revocation)
10. [Recovery Procedures](#recovery-procedures)

---

## Principles

1. **Never commit secrets to version control.**
2. **Encrypt secrets at rest** (when not in environment variables).
3. **Rotate secrets regularly** (maximum 90 days).
4. **Use least-privilege scopes** for all tokens.
5. **Audit all secret access** through structured logging.
6. **Separate production and development secrets** completely.

---

## Secret Types

| Secret | Type | Rotation | Storage |
|--------|------|----------|---------|
| Telegram Bot Token | Bearer token | On compromise | Environment variable |
| GitHub PAT | OAuth token | 90 days | GitHub Secrets / Environment variable |
| AI API Keys (Qwen, DeepSeek, Kimi) | API key | 90 days | Environment variable |
| Application Secret Key | Symmetric key | 180 days | Environment variable |
| Docker Registry Password | Password | 90 days | CI/CD secrets |
| SSH Deploy Key | Asymmetric key | 180 days | GitHub Deploy Keys |

---

## GitHub Secrets

### Repository Secrets

Store production secrets in GitHub repository settings:

```bash
# Navigate to: Settings > Secrets and variables > Actions
# Add the following secrets:

PHOENIX_TELEGRAM_BOT_TOKEN
PHOENIX_GITHUB_TOKEN
PHOENIX_QWEN_API_KEY
PHOENIX_DEEPSEEK_API_KEY
PHOENIX_KIMI_API_KEY
PHOENIX_SECRET_KEY
```

### Organization Secrets

For multi-repository deployments, use GitHub Organization secrets:

```
Organization Settings > Secrets and variables > Actions
```

### Environment Secrets

For different deployment environments:

```
Settings > Environments > production > Environment secrets
```

### Accessing Secrets in GitHub Actions

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    steps:
      - name: Deploy
        env:
          TELEGRAM_TOKEN: ${{ secrets.PHOENIX_TELEGRAM_BOT_TOKEN }}
          GITHUB_TOKEN: ${{ secrets.PHOENIX_GITHUB_TOKEN }}
        run: |
          echo "TELEGRAM_TOKEN=$TELEGRAM_TOKEN" >> .env
          docker-compose up -d
```

---

## Environment Variables

### Local Development

```bash
# .env (NEVER commit this file)
PHOENIX_TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
PHOENIX_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PHOENIX_QWEN_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PHOENIX_DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PHOENIX_KIMI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PHOENIX_SECURITY_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

### Production (Systemd)

```ini
# /etc/systemd/system/phoenix-core.service
[Service]
Environment="PHOENIX_TELEGRAM_BOT_TOKEN=..."
Environment="PHOENIX_GITHUB_TOKEN=..."
Environment="PHOENIX_QWEN_API_KEY=..."
EnvironmentFile=/etc/phoenix-core/secrets.env
```

### Docker

```yaml
# docker-compose.yml
services:
  phoenix-core:
    env_file:
      - .env
    environment:
      - PHOENIX_SECURITY_SECRET_KEY=${PHOENIX_SECURITY_SECRET_KEY}
```

### Termux

```bash
# ~/.bashrc or ~/.zshrc
export PHOENIX_TELEGRAM_BOT_TOKEN="..."
export PHOENIX_GITHUB_TOKEN="..."
```

---

## Secret Rotation

### Automated Rotation Schedule

| Secret | Frequency | Method | Owner |
|--------|-----------|--------|-------|
| GitHub PAT | 90 days | GitHub UI / API | Security Team |
| AI API Keys | 90 days | Provider dashboard | DevOps |
| Telegram Bot Token | On demand | @BotFather | Admin |
| Application Secret Key | 180 days | Script | Security Team |

### Rotation Procedure

```bash
#!/bin/bash
# scripts/rotate-secrets.sh

set -euo pipefail

echo "🔐 Starting secret rotation..."

# 1. Generate new secrets
NEW_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Update environment
export PHOENIX_SECURITY_SECRET_KEY="$NEW_SECRET_KEY"

# 3. Restart application (zero-downtime)
docker-compose up -d --no-deps --build phoenix-core

# 4. Verify health
curl -f http://localhost:8080/health || exit 1

# 5. Revoke old secrets (manual step)
echo "⚠️  Remember to revoke old secrets in provider dashboards!"

echo "✅ Secret rotation complete"
```

### Key Rotation Without Downtime

```python
# Support multiple secret keys during transition
class SecretManager:
    def __init__(self, primary_key: str, fallback_keys: List[str] = None):
        self._primary = primary_key
        self._fallbacks = fallback_keys or []

    def decrypt(self, encrypted: str) -> str:
        # Try primary first
        try:
            return self._decrypt_with_key(encrypted, self._primary)
        except Exception:
            # Try fallbacks
            for key in self._fallbacks:
                try:
                    return self._decrypt_with_key(encrypted, key)
                except Exception:
                    continue
        raise ValueError("Failed to decrypt with any key")
```

---

## Key Lifecycle

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Create  │───▶│  Active  │───▶│  Rotate  │───▶│  Revoke  │───▶│ Destroy  │
│          │    │          │    │          │    │          │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
  Generate      Distribute      Overlap period   Remove access   Secure
  with CSRNG    to systems      (both keys       from all        deletion
                                valid)           systems
```

### States

| State | Description | Actions Allowed |
|-------|-------------|-----------------|
| **Create** | Key generated, not yet distributed | None |
| **Active** | Key in use | Encrypt, Decrypt |
| **Rotate** | New key active, old key still valid | Decrypt (old), Encrypt (new) |
| **Revoke** | Key disabled, no new operations | Decrypt (emergency) |
| **Destroy** | Key permanently deleted | None |

---

## Never Store Secrets in Source Code

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: detect-private-key
```

### Git Hooks (Manual)

```bash
# .git/hooks/pre-commit
#!/bin/bash
if grep -rE '(api[_-]?key|token|secret|password)\s*[=:]\s*["'][^"']{10,}["']'    --include='*.py' --include='*.yaml' --include='*.yml' --include='*.json' .; then
    echo "❌ Potential secret detected in commit!"
    exit 1
fi
```

### Safe Code Patterns

```python
# ❌ BAD - Hardcoded secret
API_KEY = "sk-1234567890abcdef"

# ✅ GOOD - Environment variable
import os
API_KEY = os.environ["PHOENIX_QWEN_API_KEY"]

# ✅ GOOD - Pydantic Settings
from phoenix_core.config.settings import Settings
settings = Settings()
api_key = settings.ai_providers[0].api_key.get_secret_value()
```

---

## Secret Scanning

### GitHub Secret Scanning

Enable in repository settings:

```
Settings > Security > Secret scanning > Enable
```

### TruffleHog (Local Scan)

```bash
# Install
pip install truffleHog

# Scan entire history
truffleHog --regex --entropy=False .

# Scan latest commit only
truffleHog --regex --entropy=False --max_depth=1 .
```

### GitLeaks (Alternative)

```bash
# Docker-based scan
docker run -v $(pwd):/code zricethezav/gitleaks detect --source /code -v
```

### Custom Patterns

```bash
# .gitleaks.toml
[[rules]]
id = "phoenix-api-key"
description = "Phoenix API Key"
regex = '''(?i)(phoenix|qwen|deepseek|kimi)[-_]?api[-_]?key\s*[=:]\s*["']?[a-zA-Z0-9]{20,}["']?'''
tags = ["apikey", "phoenix"]
```

---

## Credential Revocation

### Immediate Revocation Checklist

```
□ Revoke compromised token in provider dashboard
□ Rotate all related secrets (assume lateral movement)
□ Review access logs for unauthorized usage
□ Check for unauthorized commits/code changes
□ Notify team members
□ Document incident (see incident-response.md)
```

### Provider-Specific Revocation

| Provider | Revocation URL | Time to Effect |
|----------|---------------|----------------|
| Telegram | @BotFather → /revoke | Immediate |
| GitHub | Settings > Developer settings > Tokens | Immediate |
| Qwen | DashScope Console | Immediate |
| DeepSeek | API Dashboard | Immediate |
| Kimi | Moonshot Console | Immediate |

### Automated Revocation Detection

```python
# Monitor for revoked tokens
async def check_token_health():
    try:
        await github_client.get_rate_limit()
    except GithubException as e:
        if e.status == 401:
            logger.critical("GitHub token appears revoked!")
            # Alert on-call engineer
            await alert_security_team("GitHub token revoked")
```

---

## Recovery Procedures

### Lost Secret Key

```bash
# 1. Generate new key
NEW_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Update all instances
# (Kubernetes secrets, Docker env, systemd, etc.)

# 3. Restart services
systemctl restart phoenix-core

# 4. Re-encrypt existing data (if applicable)
# (Requires old key - maintain backup during rotation)
```

### Backup Policy

| Data | Backup Frequency | Encryption | Retention |
|------|-----------------|------------|-----------|
| Encrypted secrets | After rotation | AES-256-GCM | 1 year |
| Audit logs | Daily | AES-256-GCM | 1 year |
| Configuration | On change | No | 30 days |

---

## Related Documents

- [Security Architecture](security-architecture.md)
- [Threat Model](threat-model.md)
- [Incident Response](incident-response.md)
- [Secure Development Lifecycle](secure-development-lifecycle.md)
- [SECURITY.md](../SECURITY.md)

---

*Last updated: 2026-07-05*
