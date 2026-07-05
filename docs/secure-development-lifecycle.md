# 🛡️ Secure Development Lifecycle (SDLC)

> This document defines the Secure Development Lifecycle for Phoenix Core. Every phase of development incorporates security activities to ensure production-ready code.

---

## Table of Contents

1. [Overview](#overview)
2. [Design Review](#design-review)
3. [Security Requirements](#security-requirements)
4. [Code Review](#code-review)
5. [Static Analysis](#static-analysis)
6. [Dependency Scanning](#dependency-scanning)
7. [Container Scanning](#container-scanning)
8. [Penetration Testing](#penetration-testing)
9. [Release Approval](#release-approval)
10. [Continuous Monitoring](#continuous-monitoring)

---

## Overview

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  DESIGN  │──▶│   CODE   │──▶│  BUILD   │──▶│  TEST    │──▶│ DEPLOY   │
│          │   │          │   │          │   │          │   │          │
│ Threat   │   │ Secure   │   │ SAST     │   │ DAST     │   │ Runtime  │
│ Model    │   │ Coding   │   │ SCA      │   │ Pen Test │   │ Monitor  │
│ Review   │   │ Review   │   │ Container│   │ Fuzzing  │   │ Alert    │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

---

## Design Review

### Security Architecture Review

Before any significant feature is developed, the following must be reviewed:

| Check | Question | Owner |
|-------|----------|-------|
| Trust Boundaries | What new trust boundaries are introduced? | Security Team |
| Data Flow | What sensitive data flows through the system? | Architect |
| Authentication | How are users/services authenticated? | Security Team |
| Authorization | What permissions are required? | Product Owner |
| Secrets | What new secrets are needed? | DevOps |
| Logging | What security events must be logged? | Security Team |
| Compliance | Are there regulatory requirements? | Legal |

### Threat Modeling

Every new feature requires a mini threat model:

```markdown
## Feature: [Name]

### Assets
- [List new assets]

### Entry Points
- [List new entry points]

### Threats
| Threat | Risk | Mitigation |
|--------|------|------------|
| [STRIDE category] | [High/Med/Low] | [How addressed] |

### Acceptance Criteria
- [ ] All High risks mitigated
- [ ] Security tests written
- [ ] Documentation updated
```

---

## Security Requirements

### Functional Requirements

| ID | Requirement | Priority | Test Method |
|----|-------------|----------|-------------|
| SEC-001 | All secrets stored in environment variables | Must | SAST scan |
| SEC-002 | Input validated via Pydantic schemas | Must | Unit tests |
| SEC-003 | Rate limiting on all external endpoints | Must | Integration tests |
| SEC-004 | Audit logging for all auth events | Must | Log review |
| SEC-005 | TLS 1.2+ for all external connections | Must | SSL scan |
| SEC-006 | Non-root container execution | Must | Container scan |
| SEC-007 | Secrets masked in logs | Must | Log review |
| SEC-008 | Dependency vulnerability scanning | Must | CI/CD pipeline |
| SEC-009 | Signed commits for all releases | Must | Git verification |
| SEC-010 | Health endpoint exposed (no auth) | Should | Integration tests |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| SEC-NF-001 | Mean time to detect (MTTD) | < 15 minutes |
| SEC-NF-002 | Mean time to respond (MTTR) | < 1 hour (P0) |
| SEC-NF-003 | Vulnerability patch SLA | 7 days (Critical) |
| SEC-NF-004 | Security test coverage | > 80% |
| SEC-NF-005 | Dependency update frequency | Weekly |

---

## Code Review

### Security-Focused Review Checklist

```markdown
## PR Security Review

### Input Handling
- [ ] All user input validated
- [ ] No SQL/command injection vectors
- [ ] File uploads restricted (if applicable)
- [ ] Path traversal prevented

### Authentication & Authorization
- [ ] Auth checks present on all endpoints
- [ ] Principle of least privilege followed
- [ ] No hardcoded credentials
- [ ] Session management secure

### Data Protection
- [ ] Sensitive data encrypted at rest
- [ ] TLS enforced for data in transit
- [ ] Secrets not logged
- [ ] PII handled per policy

### Error Handling
- [ ] No sensitive data in error messages
- [ ] Stack traces not exposed to users
- [ ] All errors logged securely

### Dependencies
- [ ] No new vulnerable dependencies
- [ ] Licenses compatible
- [ ] Minimal dependency footprint

### Configuration
- [ ] Security settings have safe defaults
- [ ] No debug mode in production
- [ ] Feature flags for risky features
```

### Review Process

1. **Author** submits PR with security checklist completed
2. **Automated checks** run (SAST, dependency scan, secret scan)
3. **Peer reviewer** performs code review with security focus
4. **Security champion** reviews for high-risk changes
5. **Approval** requires all checks passing + 2 reviewers

---

## Static Analysis

### Tools & Configuration

#### Bandit (Python Security Linter)

```yaml
# .bandit.yaml
skips: [B101, B601]  # Skip assert and shell injection (handled separately)
severity: MEDIUM
confidence: MEDIUM
```

```bash
# Run locally
bandit -r phoenix_core -f json -o bandit-report.json

# In CI
bandit -r phoenix_core -ll -ii
```

#### Semgrep (Pattern-Based Analysis)

```yaml
# .semgrep.yaml
rules:
  - id: no-hardcoded-secrets
    pattern-regex: (?i)(api[_-]?key|token|secret|password)\s*=\s*["'][^"']{10,}["']
    languages: [python]
    message: "Potential hardcoded secret detected"
    severity: ERROR

  - id: no-eval
    pattern: eval(...)
    languages: [python]
    message: "Avoid using eval()"
    severity: ERROR

  - id: safe-deserialization
    pattern: pickle.loads(...)
    languages: [python]
    message: "Unsafe deserialization detected"
    severity: WARNING
```

```bash
# Run locally
semgrep --config .semgrep.yaml phoenix_core/

# In CI
semgrep --config=auto --error phoenix_core/
```

#### CodeQL (Deep Semantic Analysis)

```yaml
# .github/workflows/codeql.yml
name: CodeQL
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 9 * * 1'  # Weekly Monday 9 AM

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      actions: read
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: python
          queries: security-extended,security-and-quality
      - uses: github/codeql-action/analyze@v3
```

---

## Dependency Scanning

### Dependabot

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "09:00"
    open-pull-requests-limit: 10
    labels:
      - dependencies
      - security
    commit-message:
      prefix: "deps"
      include: scope

  - package-ecosystem: docker
    directory: /
    schedule:
      interval: weekly
```

### Safety

```bash
# Install
pip install safety

# Check current environment
safety check

# Check requirements file
safety check -r requirements.txt

# In CI
safety check -r requirements.txt --json --output safety-report.json
```

### pip-audit

```bash
# Install
pip install pip-audit

# Audit dependencies
pip-audit --desc --format=json --output=pip-audit-report.json

# In CI
pip-audit --desc --requirement=requirements.txt
```

### Dependency Review (GitHub)

```yaml
# .github/workflows/dependency-review.yml
name: Dependency Review
on: [pull_request]

permissions:
  contents: read

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/dependency-review-action@v3
        with:
          fail-on-severity: moderate
          deny-licenses: GPL-2.0, GPL-3.0
```

---

## Container Scanning

### Trivy

```bash
# Scan image
trivy image phoenix-core:latest

# Scan filesystem
trivy filesystem .

# Generate SARIF for GitHub
trivy image --format sarif --output trivy-report.sarif phoenix-core:latest
```

```yaml
# .github/workflows/container-scan.yml
name: Container Security Scan
on:
  push:
    branches: [main]
  pull_request:
    paths:
      - Dockerfile
      - docker-compose.yml

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build image
        run: docker build -t phoenix-core:test .

      - name: Run Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: phoenix-core:test
          format: sarif
          output: trivy-results.sarif

      - name: Upload to GitHub Security
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: trivy-results.sarif
```

### Dockle (CIS Benchmark)

```bash
# Install
docker run --rm goodwithtech/dockle:latest phoenix-core:latest

# In CI
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock   goodwithtech/dockle:latest phoenix-core:test
```

---

## Penetration Testing

### Scope

| Area | Frequency | Method |
|------|-----------|--------|
| External APIs | Annually | External vendor |
| Telegram Bot | Annually | External vendor |
| GitHub Integration | Annually | External vendor |
| Container/Infra | Semi-annually | Internal + tool-assisted |
| Plugin System | Per major release | Internal |

### Internal Testing Tools

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run security-focused tests
pytest tests/security/ -v

# Fuzzing (optional)
pip install hypothesis
pytest --hypothesis-profile=security tests/
```

### Penetration Test Report Template

```markdown
# Penetration Test Report

## Executive Summary
- Scope: [What was tested]
- Duration: [Dates]
- Tester: [Name/Firm]
- Overall Risk: [Critical/High/Medium/Low]

## Findings
| ID | Finding | Severity | Status |
|----|---------|----------|--------|
| PT-001 | [Description] | High | Open |

## Recommendations
[Prioritized list of fixes]

## Retest
[Results after fixes applied]
```

---

## Release Approval

### Release Checklist

```markdown
## Release [VERSION] Security Checklist

### Pre-Release
- [ ] All SAST checks passing
- [ ] All dependency scans clean
- [ ] Container scan clean (no HIGH/CRITICAL)
- [ ] Code review completed (2+ approvals)
- [ ] Security tests passing (>80% coverage)
- [ ] Documentation updated
- [ ] CHANGELOG includes security fixes

### Release
- [ ] Version bumped
- [ ] Git tag signed
- [ ] Docker image scanned
- [ ] SBOM generated
- [ ] Release notes published

### Post-Release
- [ ] Monitoring alerts verified
- [ ] Health checks passing
- [ ] No error spikes
- [ ] Security metrics baseline recorded
```

### Signed Releases

```bash
# Sign git tag
git tag -s v1.0.0 -m "Release v1.0.0"

# Verify signature
git tag -v v1.0.0

# Sign Docker image
docker trust sign phoenix-team/phoenix-core:v1.0.0
```

---

## Continuous Monitoring

### Runtime Security

| Metric | Tool | Alert Threshold |
|--------|------|-----------------|
| Failed auth attempts | Application logs | >10/minute |
| Rate limit violations | Application logs | >5/minute |
| Error rate | Application logs | >1% |
| Container CPU/Memory | Docker stats | >80% |
| Vulnerability count | Trivy (scheduled) | Any CRITICAL |
| Dependency age | Dependabot | >30 days |

### Security Metrics Dashboard

```python
# Example: Prometheus metrics
from prometheus_client import Counter, Histogram

auth_failures = Counter('phoenix_auth_failures_total', 'Auth failures')
request_duration = Histogram('phoenix_request_duration_seconds', 'Request duration')
rate_limit_hits = Counter('phoenix_rate_limit_hits_total', 'Rate limit hits')
```

### Alerting Rules

```yaml
# config/prometheus-alerts.yml
groups:
  - name: phoenix-security
    rules:
      - alert: PhoenixHighAuthFailures
        expr: rate(phoenix_auth_failures_total[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High authentication failure rate"

      - alert: PhoenixRateLimitExceeded
        expr: rate(phoenix_rate_limit_hits_total[5m]) > 0.05
        for: 1m
        labels:
          severity: critical
```

---

## Security Training

### Onboarding

All new developers must complete:

1. **OWASP Top 10** awareness training
2. **Secure coding in Python** course
3. **Phoenix Core security guidelines** review
4. **Incident response** walkthrough

### Ongoing

- Monthly security newsletter
- Quarterly lunch-and-learn sessions
- Annual penetration test participation

---

## Related Documents

- [Security Architecture](security-architecture.md)
- [Threat Model](threat-model.md)
- [Secrets Management](secrets-management.md)
- [Incident Response](incident-response.md)
- [SECURITY.md](../SECURITY.md)

---

*Last updated: 2026-07-05*
