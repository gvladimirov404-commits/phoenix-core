# 🔒 Security Policy

> **Phoenix Core** takes security seriously. This document outlines our security practices, vulnerability reporting process, and responsible disclosure policy.

---

## Supported Versions

| Version | Status | Support End Date |
|---------|--------|------------------|
| 1.0.x   | ✅ Active | 2027-07-05 |
| < 1.0   | ❌ End-of-Life | 2026-07-05 |

We provide security patches for the latest minor version of each major release. Users are strongly encouraged to upgrade to the latest version promptly.

---

## Reporting a Vulnerability

### Private Disclosure (Preferred)

If you discover a security vulnerability, **please do not open a public issue**.

Instead, report it privately via one of the following channels:

| Channel | Details |
|---------|---------|
| 🔐 GitHub Security Advisories | [Report privately](https://github.com/phoenix-team/phoenix-core/security/advisories/new) |
| 📧 Email | `security@phoenix.dev` (GPG key below) |
| 🔑 GPG Key | `0xABCD1234EFGH5678` — [download public key](https://phoenix.dev/security.gpg) |

### What to Include

- Description of the vulnerability
- Steps to reproduce (proof-of-concept if possible)
- Affected versions
- Potential impact assessment
- Suggested mitigation (if any)

### Response Timeline

| Phase | Timeline | Action |
|-------|----------|--------|
| Acknowledgment | Within 48 hours | We confirm receipt of your report |
| Initial Assessment | Within 5 business days | We validate and classify severity |
| Patch Development | 7–30 days | Depends on severity (see below) |
| Coordinated Disclosure | After patch release | Public disclosure with credit |

---

## Responsible Disclosure Policy

We follow the **Coordinated Vulnerability Disclosure (CVD)** model:

1. **Reporter** submits vulnerability privately.
2. **Maintainers** acknowledge, assess, and develop a fix.
3. **Patch** is released and deployed.
4. **Public Disclosure** occurs after users have had reasonable time to patch (minimum 7 days).
5. **Credit** is given to the reporter (unless anonymity is requested).

### Disclosure Timeline

| Severity | Patch Target | Public Disclosure After |
|----------|--------------|------------------------|
| 🔴 Critical | 7 days | 7 days post-patch |
| 🟠 High | 14 days | 14 days post-patch |
| 🟡 Medium | 30 days | 30 days post-patch |
| 🟢 Low | Next scheduled release | Next scheduled release |

> **Exception:** If a vulnerability is actively exploited in the wild, disclosure may be accelerated to protect users.

---

## Security Contact

- **Primary:** `security@phoenix.dev`
- **Response Team:** Phoenix Core Security Team
- **Keybase:** [@phoenixsecurity](https://keybase.io/phoenixsecurity)
- **Status Page:** [status.phoenix.dev](https://status.phoenix.dev)

---

## Patch Policy

- All security patches are released as **patch versions** (e.g., `1.0.1`).
- Patches are backported to the latest supported minor version.
- Security fixes are **never** bundled with unrelated feature releases.
- Each security release includes:
  - CVE identifier (if applicable)
  - Detailed changelog entry
  - Upgrade instructions

---

## Security Best Practices for Users

### 1. Keep Dependencies Updated
```bash
pip install --upgrade -r requirements.txt
```

### 2. Use Strong Secrets
```bash
# Generate a secure secret key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Run with Minimal Privileges
```bash
# Never run as root
useradd -r phoenix
su - phoenix
python -m phoenix_core start
```

### 4. Enable All Security Features
```bash
export PHOENIX_SECURITY_ENCRYPT_LOGS=true
export PHOENIX_SECURITY_RATE_LIMIT=100
```

### 5. Monitor for Anomalies
```bash
tail -f logs/phoenix.log | grep -i "security\|unauthorized\|error"
```

### 6. Use Docker Security Options
```bash
docker run --read-only --cap-drop=ALL --user=phoenix phoenix-core
```

---

## Security Hall of Fame

We thank the following security researchers for their responsible disclosures:

| Researcher | Vulnerability | Date |
|------------|--------------|------|
| *Your name here* | — | — |

---

## Related Documentation

- [Security Architecture](docs/security-architecture.md)
- [Threat Model](docs/threat-model.md)
- [Secrets Management](docs/secrets-management.md)
- [Incident Response](docs/incident-response.md)
- [Secure Development Lifecycle](docs/secure-development-lifecycle.md)

---

*Last updated: 2026-07-05*
