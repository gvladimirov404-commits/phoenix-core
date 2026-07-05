# 🏗️ Security Architecture

> This document describes the complete security architecture of Phoenix Core. It is intended for security auditors, DevOps engineers, and developers integrating Phoenix Core into production environments.

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Authorization (RBAC)](#authorization-rbac)
4. [Least Privilege Principle](#least-privilege-principle)
5. [Defense in Depth](#defense-in-depth)
6. [Secure API Design](#secure-api-design)
7. [Input Validation](#input-validation)
8. [Output Encoding](#output-encoding)
9. [Encryption](#encryption)
10. [Secret Management](#secret-management)
11. [Logging & Monitoring](#logging--monitoring)
12. [Audit Trail](#audit-trail)
13. [Rate Limiting](#rate-limiting)
14. [Container Security](#container-security)
15. [CI/CD Security](#cicd-security)
16. [Supply Chain Security](#supply-chain-security)

---

## Overview

Phoenix Core implements a **defense-in-depth** security model with multiple independent layers of protection. The architecture follows the principle that no single security control should be the sole line of defense.

```
┌─────────────────────────────────────────────────────────────┐
│                    PERIMETER LAYER                          │
│  (Rate Limiting, WAF, DDoS Protection, TLS 1.3)             │
├─────────────────────────────────────────────────────────────┤
│                    APPLICATION LAYER                          │
│  (Authentication, Authorization, Input Validation)          │
├─────────────────────────────────────────────────────────────┤
│                    DATA LAYER                                 │
│  (Encryption at Rest, Encryption in Transit, Secret Mgmt)     │
├─────────────────────────────────────────────────────────────┤
│                    INFRASTRUCTURE LAYER                     │
│  (Container Security, Network Policies, Host Hardening)      │
├─────────────────────────────────────────────────────────────┤
│                    MONITORING LAYER                           │
│  (Audit Logging, Anomaly Detection, Incident Response)      │
└─────────────────────────────────────────────────────────────┘
```

---

## Authentication

### Telegram Bot Authentication

- **Token-based**: Each bot instance uses a unique Telegram Bot API token.
- **User Verification**: Only whitelisted `user_id`s can execute commands.
- **Command Prefixing**: All commands require the `/` prefix to prevent accidental execution.

```python
# phoenix_core/telegram/bot.py
def _is_authorized(self, user_id: int) -> bool:
    if not self.settings.allowed_users:
        return True  # Open mode (not recommended for production)
    return user_id in self.settings.allowed_users
```

### GitHub API Authentication

- **PAT (Personal Access Token)**: Scoped to minimum required permissions.
- **Webhook Verification**: HMAC-SHA256 signature validation for incoming webhooks.

```python
# GitHub webhook verification
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

### AI Provider Authentication

- **API Keys**: Stored as `SecretStr` (never logged or serialized).
- **Key Rotation**: Support for multiple keys with automatic failover.

---

## Authorization (RBAC)

Phoenix Core implements a **minimal RBAC model** suitable for its scope:

| Role | Telegram Commands | GitHub Operations | AI Access |
|------|-------------------|-------------------|-----------|
| **Admin** | All commands | Full access | All providers |
| **Operator** | `/status`, `/ai`, `/providers` | Read-only | All providers |
| **Viewer** | `/status` | None | None |

### Implementation

```python
# Authorization decorator
from functools import wraps

def require_role(min_role: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id
            role = get_user_role(user_id)  # From database/config
            if ROLE_HIERARCHY[role] < ROLE_HIERARCHY[min_role]:
                await update.message.reply_text("Insufficient permissions.")
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator
```

---

## Least Privilege Principle

Every component operates with the **minimum permissions necessary**:

### Docker Container
- Runs as non-root user (`phoenix`)
- Read-only root filesystem (`--read-only`)
- Dropped Linux capabilities (`--cap-drop=ALL`)
- No new privileges (`--security-opt=no-new-privileges:true`)

### GitHub Token Scopes
| Scope | Required | Reason |
|-------|----------|--------|
| `repo` | Yes | Repository read/write |
| `workflow` | Optional | Trigger Actions |
| `admin:repo_hook` | No | Webhooks managed externally |

### AI Provider Keys
- Each provider key is isolated; compromise of one does not affect others.
- Keys are never exposed in logs, stack traces, or health check endpoints.

---

## Defense in Depth

```
Layer 1: Network
  ├── TLS 1.3 for all external connections
  ├── Certificate pinning for AI providers (optional)
  └── Network segmentation (Docker networks)

Layer 2: Application
  ├── Input validation (Pydantic schemas)
  ├── Output encoding (Markdown/HTML escaping)
  └── Rate limiting per user/IP

Layer 3: Data
  ├── AES-256 encryption for logs (optional)
  ├── Secret encryption at rest
  └── No plaintext secrets in memory longer than necessary

Layer 4: Infrastructure
  ├── Non-root containers
  ├── Read-only filesystems
  └── Capability dropping

Layer 5: Monitoring
  ├── Structured audit logging
  ├── Failed authentication alerts
  └── Anomaly detection on API usage
```

---

## Secure API Design

### AI Provider API

```python
# All AI requests validated before sending
async def chat(self, messages: List[Dict[str, str]], **kwargs):
    # Validate message structure
    for msg in messages:
        if not isinstance(msg.get("content"), str):
            raise ValidationError("Invalid message content")
        if len(msg["content"]) > 100_000:
            raise ValidationError("Message too long")

    # Sanitize kwargs
    allowed_params = {"temperature", "max_tokens", "top_p"}
    kwargs = {k: v for k, v in kwargs.items() if k in allowed_params}

    # Execute with timeout
    return await self._execute_with_timeout(messages, **kwargs)
```

### Telegram Webhook API

- Validates `X-Telegram-Bot-Api-Secret-Token` header.
- Rejects requests with invalid or missing tokens.
- Parses updates via Pydantic models for type safety.

---

## Input Validation

### Pydantic Models

All configuration and external input is validated via Pydantic:

```python
class AIProviderConfig(BaseSettings):
    timeout: int = Field(default=30, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
    priority: int = Field(default=1, ge=1, le=10)
```

### Telegram Message Validation

```python
# Prevent command injection in Telegram
import re

def sanitize_input(text: str) -> str:
    # Remove control characters
    text = re.sub(r'[ -]', '', text)
    # Limit length
    return text[:4000]
```

### GitHub Payload Validation

- Webhook signatures verified with HMAC-SHA256.
- Payload size limited to 1MB.
- JSON schema validation for all event types.

---

## Output Encoding

### Telegram Messages

```python
from html import escape

def safe_reply(text: str) -> str:
    # Escape HTML to prevent injection
    return escape(text[:4000])
```

### AI Response Handling

```python
def sanitize_ai_response(response: str) -> str:
    # Strip potential markdown injection
    response = response.replace("```", "")
    # Truncate if excessively long
    return response[:8000]
```

---

## Encryption

### At Rest

| Data | Method | Key Management |
|------|--------|----------------|
| Log files | AES-256-GCM (optional) | `PHOENIX_SECRET_KEY` |
| Secrets in `.env` | None (user responsibility) | Environment variable |
| Plugin data | Plugin-defined | Plugin-defined |

### In Transit

- All AI provider APIs use **TLS 1.2+** (enforced by `httpx`).
- Telegram Bot API uses HTTPS.
- GitHub API uses HTTPS with certificate verification.

### Secret Encryption

```python
from phoenix_core.utils.secrets import SecretManager

manager = SecretManager(master_key=os.environ["PHOENIX_SECRET_KEY"])
encrypted = manager.encrypt("sensitive_value")
decrypted = manager.decrypt(encrypted)
```

---

## Secret Management

See [Secrets Management Guide](secrets-management.md) for detailed procedures.

### Quick Reference

| Secret Type | Storage | Rotation Frequency |
|-------------|---------|-------------------|
| Telegram Bot Token | Environment variable | On compromise |
| GitHub PAT | Environment variable | 90 days |
| AI API Keys | Environment variable | 90 days |
| Application Secret Key | Environment variable | 180 days |

---

## Logging & Monitoring

### Structured Logging

```json
{
  "timestamp": "2026-07-05T11:30:00Z",
  "level": "warning",
  "event": "unauthorized_access_attempt",
  "user_id": 123456789,
  "command": "/ai",
  "source_ip": "192.168.1.1",
  "user_agent": "TelegramBot/1.0"
}
```

### Security Events Logged

- Authentication failures
- Authorization failures
- Rate limit violations
- Secret access attempts
- Configuration changes
- Plugin load/unload events

---

## Audit Trail

All security-relevant actions are recorded:

```python
async def log_audit_event(
    action: str,
    user_id: Optional[int],
    details: Dict[str, Any],
    success: bool
) -> None:
    logger.info(
        "audit_event",
        action=action,
        user_id=user_id,
        details=details,
        success=success,
        timestamp=datetime.utcnow().isoformat(),
    )
```

### Retention Policy

| Log Type | Retention | Encryption |
|----------|-----------|------------|
| Security audit | 1 year | AES-256-GCM |
| Application | 90 days | Optional |
| Debug | 7 days | No |

---

## Rate Limiting

### Global Rate Limits

```python
from collections import defaultdict
import time

class RateLimiter:
    def __init__(self, max_requests: int = 100, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self.requests = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        self.requests[key] = [
            req for req in self.requests[key]
            if now - req < self.window
        ]
        if len(self.requests[key]) >= self.max_requests:
            return False
        self.requests[key].append(now)
        return True
```

### Per-Command Limits

| Command | Limit | Window |
|---------|-------|--------|
| `/ai` | 10 | 60s |
| `/github` | 20 | 60s |
| `/status` | 30 | 60s |

---

## Container Security

### Dockerfile Security Features

```dockerfile
# Non-root user
RUN groupadd -r phoenix && useradd -r -g phoenix phoenix
USER phoenix

# Read-only filesystem (runtime)
# docker run --read-only --tmpfs /tmp phoenix-core

# Dropped capabilities
# docker run --cap-drop=ALL --cap-add=NET_BIND_SERVICE phoenix-core

# Health check
HEALTHCHECK --interval=30s --timeout=10s   CMD python -c "import phoenix_core; print('OK')" || exit 1
```

### Security Scanning

```bash
# Trivy vulnerability scan
trivy image phoenix-core:latest

# Docker Bench for Security
docker run -it --net host --pid host   docker/docker-bench-security
```

---

## CI/CD Security

### Pipeline Stages

```
1. Code Checkout
   └── Signed commit verification

2. Static Analysis
   ├── Bandit (Python security linter)
   ├── Semgrep (pattern matching)
   └── CodeQL (deep analysis)

3. Dependency Scanning
   ├── Safety (known vulnerabilities)
   ├── pip-audit (PyPI advisories)
   └── Dependabot (automated PRs)

4. Secret Scanning
   ├── GitHub secret scanning
   ├── TruffleHog (deep scan)
   └── Custom regex patterns

5. Container Scanning
   ├── Trivy (OS + app vulnerabilities)
   └── Dockle (CIS benchmark)

6. Build & Test
   └── Isolated build environment
```

See [Secure Development Lifecycle](secure-development-lifecycle.md) for details.

---

## Supply Chain Security

### Dependency Management

- **Lock files**: `requirements.txt` pinned to exact versions.
- **Hash verification**: `pip install --require-hashes` (recommended).
- **Vulnerability scanning**: Automated via Dependabot + Safety.

### Base Image

- `python:3.11-slim` — minimal attack surface.
- Regularly rebuilt to incorporate OS security updates.
- Scanned with Trivy before deployment.

### SBOM Generation

```bash
# Generate Software Bill of Materials
pip install cyclonedx-bom
cyclonedx-py -r -o sbom.json
```

---

## Related Documents

- [Threat Model](threat-model.md)
- [Secrets Management](secrets-management.md)
- [Incident Response](incident-response.md)
- [Secure Development Lifecycle](secure-development-lifecycle.md)
- [SECURITY.md](../SECURITY.md)

---

*Last updated: 2026-07-05*
