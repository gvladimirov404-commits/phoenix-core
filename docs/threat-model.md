# 🎯 Threat Model

> This document presents a comprehensive threat model for Phoenix Core using the STRIDE methodology. It identifies assets, trust boundaries, entry points, threat actors, and mitigation strategies.

---

## Table of Contents

1. [Scope & Objectives](#scope--objectives)
2. [Assets](#assets)
3. [Trust Boundaries](#trust-boundaries)
4. [Entry Points](#entry-points)
5. [Threat Actors](#threat-actors)
6. [STRIDE Analysis](#stride-analysis)
7. [Risk Matrix](#risk-matrix)
8. [Mitigations](#mitigations)
9. [Residual Risks](#residual-risks)
10. [Review Schedule](#review-schedule)

---

## Scope & Objectives

### In Scope

- Phoenix Core application code
- Telegram Bot integration
- GitHub API integration
- AI provider integrations (Qwen, DeepSeek, Kimi)
- Plugin system
- Docker deployment
- CI/CD pipeline

### Out of Scope

- Telegram platform security
- GitHub platform security
- AI provider infrastructure security
- Host OS hardening (covered separately)

### Objectives

1. Identify threats to confidentiality, integrity, and availability.
2. Assess risk levels for each threat.
3. Define mitigations for high and critical risks.
4. Document residual risks after mitigation.

---

## Assets

| ID | Asset | Value | Owner | Location |
|----|-------|-------|-------|----------|
| A1 | Telegram Bot Token | Critical | Operator | Environment variable |
| A2 | GitHub PAT | Critical | Operator | Environment variable |
| A3 | AI API Keys (Qwen, DeepSeek, Kimi) | Critical | Operator | Environment variable |
| A4 | Application Secret Key | Critical | Operator | Environment variable |
| A5 | User Data (Telegram IDs) | High | Users | Memory/Logs |
| A6 | AI Conversation History | Medium | Users | Memory/Temp files |
| A7 | GitHub Repository Data | High | Users | GitHub API |
| A8 | Plugin Code | High | Developers | Filesystem |
| A9 | Audit Logs | High | System | Filesystem |
| A10 | Configuration Files | High | System | Filesystem |

---

## Trust Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                        UNTRUSTED ZONE                            │
│  (Internet, Telegram Servers, GitHub, AI Providers)              │
├─────────────────────────────────────────────────────────────────┤
│                        TRUST BOUNDARY 1                          │
│                        (Network Perimeter)                         │
├─────────────────────────────────────────────────────────────────┤
│                        SEMI-TRUSTED ZONE                         │
│  (Docker Network, Reverse Proxy, Load Balancer)                  │
├─────────────────────────────────────────────────────────────────┤
│                        TRUST BOUNDARY 2                          │
│                        (Container Boundary)                      │
├─────────────────────────────────────────────────────────────────┤
│                        TRUSTED ZONE                              │
│  (Phoenix Core Application, Secrets, Logs)                       │
├─────────────────────────────────────────────────────────────────┤
│                        TRUST BOUNDARY 3                          │
│                        (Process Boundary)                        │
├─────────────────────────────────────────────────────────────────┤
│                        HIGHLY TRUSTED ZONE                       │
│  (Secret Manager, Encryption Keys)                               │
└─────────────────────────────────────────────────────────────────┘
```

### Boundary Descriptions

| Boundary | Controls |
|----------|----------|
| Network Perimeter | TLS 1.3, Certificate validation, Rate limiting |
| Container Boundary | Docker isolation, Non-root user, Read-only FS |
| Process Boundary | Memory isolation, Capability dropping, Seccomp |

---

## Entry Points

| ID | Entry Point | Protocol | Authentication | Authorization |
|----|-------------|----------|----------------|---------------|
| EP1 | Telegram Bot API | HTTPS | Token (Telegram) | User ID whitelist |
| EP2 | GitHub API | HTTPS | PAT | Repository scopes |
| EP3 | AI Provider APIs | HTTPS | API Key | Provider account |
| EP4 | Health Check Endpoint | HTTP | None | Public |
| EP5 | Plugin Loader | Filesystem | None | File permissions |
| EP6 | Configuration Files | Filesystem | OS-level | File permissions |
| EP7 | Environment Variables | OS | OS-level | Process isolation |

---

## Threat Actors

| Actor | Motivation | Capability | Risk Level |
|-------|-----------|------------|------------|
| **Script Kiddie** | Reputation, curiosity | Low (automated tools) | Medium |
| **Cybercriminal** | Financial gain, data theft | Medium (custom malware) | High |
| **APT / Nation State** | Espionage, sabotage | High (zero-days, insiders) | Critical |
| **Malicious Insider** | Revenge, financial gain | High (legitimate access) | Critical |
| **Compromised Dependency** | Supply chain attack | Medium (trusted code) | High |
| **AI Provider Attacker** | Data poisoning, model theft | Medium (API access) | Medium |

---

## STRIDE Analysis

### Spoofing

| ID | Threat | Asset | Risk | Mitigation |
|----|--------|-------|------|------------|
| S1 | Attacker spoofs Telegram webhook sender | A1 | High | HMAC signature validation |
| S2 | Attacker uses stolen bot token | A1 | Critical | Token rotation, IP whitelisting |
| S3 | Attacker impersonates GitHub webhook | A2 | High | Webhook secret verification |
| S4 | Man-in-the-middle on AI provider connection | A3 | Medium | TLS 1.3, certificate pinning |

### Tampering

| ID | Threat | Asset | Risk | Mitigation |
|----|--------|-------|------|------------|
| T1 | Attacker modifies plugin code | A8 | High | File integrity monitoring, code signing |
| T2 | Attacker tampers with configuration | A10 | High | Read-only filesystem, checksums |
| T3 | Attacker modifies audit logs | A9 | High | Append-only logs, log forwarding |
| T4 | Attacker tampers with AI responses | A6 | Medium | Response signature verification |

### Repudiation

| ID | Threat | Asset | Risk | Mitigation |
|----|--------|-------|------|------------|
| R1 | User denies executing command | A5 | Medium | Comprehensive audit logging |
| R2 | Admin denies configuration change | A10 | Medium | Immutable audit trail |
| R3 | Attacker denies breach | A9 | High | External log aggregation |

### Information Disclosure

| ID | Threat | Asset | Risk | Mitigation |
|----|--------|-------|------|------------|
| I1 | Secrets leaked in logs | A1-A4 | Critical | Secret masking, structured logging |
| I2 | AI conversation data exposed | A6 | High | Data minimization, encryption |
| I3 | GitHub repository data leaked | A7 | High | Minimal scopes, access logging |
| I4 | Stack traces expose internals | A10 | Medium | Sanitized error messages |
| I5 | Container image contains secrets | A1-A4 | Critical | Multi-stage builds, .dockerignore |

### Denial of Service

| ID | Threat | Asset | Risk | Mitigation |
|----|--------|-------|------|------------|
| D1 | Telegram message flood | A1 | High | Rate limiting per user |
| D2 | AI API abuse (cost bombing) | A3 | Critical | Rate limiting, cost alerts |
| D3 | GitHub API rate limit exhaustion | A2 | Medium | Caching, request batching |
| D4 | Plugin infinite loop | A8 | Medium | Execution timeouts, resource limits |
| D5 | Memory exhaustion | System | High | Container memory limits |

### Elevation of Privilege

| ID | Threat | Asset | Risk | Mitigation |
|----|--------|-------|------|------------|
| E1 | Plugin escapes sandbox | A8 | Critical | Sandboxing, capability dropping |
| E2 | Container breakout | System | Critical | Non-root user, seccomp profiles |
| E3 | Privilege escalation via config | A10 | High | Input validation, schema enforcement |
| E4 | GitHub token scope escalation | A2 | Medium | Minimal scopes, regular review |

---

## Risk Matrix

### Likelihood Scale

| Score | Description |
|-------|-------------|
| 1 | Rare (once per year or less) |
| 2 | Unlikely (once per quarter) |
| 3 | Possible (once per month) |
| 4 | Likely (once per week) |
| 5 | Almost certain (daily) |

### Impact Scale

| Score | Description |
|-------|-------------|
| 1 | Negligible (no significant effect) |
| 2 | Low (minor inconvenience) |
| 3 | Medium (operational impact) |
| 4 | High (data breach, financial loss) |
| 5 | Critical (system compromise, legal liability) |

### Risk Score = Likelihood × Impact

| Score | Risk Level | Action |
|-------|-----------|--------|
| 1–4 | Low | Monitor |
| 5–9 | Medium | Plan mitigation |
| 10–16 | High | Implement mitigation |
| 17–25 | Critical | Immediate action required |

### Prioritized Threats

| Threat | Likelihood | Impact | Score | Priority |
|--------|-----------|--------|-------|----------|
| I1 - Secrets in logs | 3 | 5 | 15 | 🔴 Critical |
| I5 - Secrets in container | 3 | 5 | 15 | 🔴 Critical |
| D2 - AI API abuse | 4 | 5 | 20 | 🔴 Critical |
| E1 - Plugin sandbox escape | 2 | 5 | 10 | 🟠 High |
| E2 - Container breakout | 2 | 5 | 10 | 🟠 High |
| S2 - Stolen bot token | 3 | 4 | 12 | 🟠 High |
| T1 - Plugin tampering | 2 | 4 | 8 | 🟡 Medium |
| T3 - Log tampering | 2 | 4 | 8 | 🟡 Medium |
| I3 - GitHub data leak | 2 | 4 | 8 | 🟡 Medium |
| D1 - Message flood | 4 | 3 | 12 | 🟠 High |

---

## Mitigations

### Implemented

| Threat | Mitigation | Status |
|--------|-----------|--------|
| I1 | Secret masking in logs | ✅ Implemented |
| I5 | Multi-stage Docker build, .dockerignore | ✅ Implemented |
| D1 | Per-user rate limiting | ✅ Implemented |
| D2 | Global rate limiting, cost monitoring | ✅ Implemented |
| E2 | Non-root user, capability dropping | ✅ Implemented |
| S1 | Telegram webhook verification | ✅ Implemented |
| S3 | GitHub webhook HMAC verification | ✅ Implemented |
| T2 | Read-only filesystem option | ✅ Implemented |
| T3 | Structured audit logging | ✅ Implemented |

### Planned

| Threat | Mitigation | Target Date |
|--------|-----------|-------------|
| E1 | Plugin sandboxing (seccomp, gVisor) | Q3 2026 |
| I2 | Conversation encryption at rest | Q3 2026 |
| S4 | Certificate pinning for AI providers | Q4 2026 |
| T1 | Plugin code signing | Q4 2026 |

---

## Residual Risks

After implementing all mitigations, the following risks remain:

| Risk | Reason | Acceptance Criteria |
|------|--------|---------------------|
| AI provider compromise | Out of our control | Monitor provider security advisories |
| Telegram platform breach | Out of our control | Enable 2FA on bot account |
| Zero-day in Python/runtime | Unknown vulnerability | Subscribe to CVE feeds, rapid patching |
| Physical device theft | Mobile/Termux deployments | Device encryption, remote wipe |
| Insider threat (admin) | Legitimate access | Segregation of duties, audit logs |

---

## Review Schedule

| Activity | Frequency | Owner |
|----------|-----------|-------|
| Threat model review | Quarterly | Security Team |
| Penetration testing | Annually | External vendor |
| Dependency vulnerability scan | Weekly | Automated (Dependabot) |
| Code security review | Per PR | Automated + Manual |
| Incident response drill | Semi-annually | Security Team |

---

## Related Documents

- [Security Architecture](security-architecture.md)
- [Secrets Management](secrets-management.md)
- [Incident Response](incident-response.md)
- [Secure Development Lifecycle](secure-development-lifecycle.md)
- [SECURITY.md](../SECURITY.md)

---

*Last updated: 2026-07-05*
