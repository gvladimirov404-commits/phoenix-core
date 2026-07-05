# 🚨 Incident Response Plan

> This document defines the incident response procedures for Phoenix Core security incidents. All team members must be familiar with these procedures.

---

## Table of Contents

1. [Incident Response Lifecycle](#incident-response-lifecycle)
2. [Incident Detection](#incident-detection)
3. [Severity Classification](#severity-classification)
4. [Containment](#containment)
5. [Eradication](#eradication)
6. [Recovery](#recovery)
7. [Lessons Learned](#lessons-learned)
8. [Communication Plan](#communication-plan)
9. [Contact List](#contact-list)
10. [Playbooks](#playbooks)

---

## Incident Response Lifecycle

```
    ┌─────────────┐
    │  DETECTION  │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │  ANALYSIS   │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │ CONTAINMENT │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │ ERADICATION │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │  RECOVERY   │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │ POST-INCIDENT│
    └─────────────┘
```

---

## Incident Detection

### Automated Detection

| Source | Alert Type | Threshold |
|--------|-----------|-----------|
| Application logs | Failed auth burst | >10 failures/minute |
| Rate limiter | Threshold exceeded | >100 requests/minute |
| GitHub API | Unauthorized access | Any 401/403 error |
| AI provider | Cost anomaly | >200% of daily average |
| Docker | Container escape attempt | Any seccomp violation |
| Filesystem | Unauthorized file change | Any modification to `/app` |

### Manual Detection

- User reports suspicious bot behavior
- Unexpected GitHub repository changes
- Unusual AI provider billing
- Security scanner findings
- Responsible disclosure from external researcher

### Detection Tools

```bash
# Real-time log monitoring
tail -f logs/phoenix.log | grep -E "ERROR|CRITICAL|security"

# Failed auth analysis
jq 'select(.event == "unauthorized_access_attempt")' logs/phoenix.log

# Rate limit violations
jq 'select(.event == "rate_limit_exceeded")' logs/phoenix.log
```

---

## Severity Classification

| Severity | Criteria | Response Time | Examples |
|----------|----------|---------------|----------|
| **P0 - Critical** | Active exploitation, data breach, system compromise | 15 minutes | Bot token leaked, unauthorized repo access |
| **P1 - High** | Potential breach, significant vulnerability | 1 hour | Dependency with known CVE, misconfiguration |
| **P2 - Medium** | Limited impact, no active exploitation | 4 hours | Rate limit bypass, information disclosure |
| **P3 - Low** | Minimal impact, theoretical risk | 24 hours | Outdated dependency, minor misconfiguration |

### Severity Assessment Matrix

```
                    IMPACT
              Low    Medium   High    Critical
           ┌──────┬────────┬───────┬──────────┐
    High   │  P2  │   P1   │   P0  │    P0    │
LIKELIHOOD ├──────┼────────┼───────┼──────────┤
    Medium │  P3  │   P2   │   P1  │    P1    │
           ├──────┼────────┼───────┼──────────┤
    Low    │  P3  │   P3   │   P2  │    P2    │
           └──────┴────────┴───────┴──────────┘
```

---

## Containment

### Short-Term Containment (0-1 hour)

```bash
# 1. Isolate affected instance
docker stop phoenix-core

# 2. Revoke compromised credentials
# (See secrets-management.md for provider-specific steps)

# 3. Block suspicious IPs
iptables -A INPUT -s SUSPICIOUS_IP -j DROP

# 4. Enable maintenance mode (if applicable)
# Return "Service temporarily unavailable" to Telegram
```

### Long-Term Containment (1-24 hours)

```bash
# 1. Deploy clean instance from known-good image
docker-compose -f docker-compose.prod.yml up -d

# 2. Rotate ALL secrets (assume lateral movement)
./scripts/rotate-secrets.sh

# 3. Enable enhanced logging
export PHOENIX_LOG_LEVEL=DEBUG

# 4. Restrict access
# Update allowed_users in Telegram config
```

### Evidence Preservation

```bash
# Create forensic snapshot
docker commit phoenix-core incident-$(date +%Y%m%d-%H%M%S)

# Export logs
docker logs phoenix-core > incident-logs-$(date +%Y%m%d-%H%M%S).txt

# Save filesystem state
docker export phoenix-core > incident-fs-$(date +%Y%m%d-%H%M%S).tar
```

---

## Eradication

### Root Cause Analysis

1. **Identify attack vector**
   - Review logs for initial access point
   - Check for vulnerable dependencies
   - Verify configuration integrity

2. **Verify scope**
   - Check all connected systems
   - Review GitHub audit logs
   - Check AI provider usage logs

3. **Remove persistence**
   - Check for cron jobs, systemd services
   - Verify plugin integrity
   - Check for backdoors in code

### Clean Rebuild Procedure

```bash
#!/bin/bash
# scripts/incident-rebuild.sh

set -euo pipefail

echo "🔥 Starting incident rebuild..."

# 1. Stop all services
docker-compose down

# 2. Remove all containers and volumes
docker system prune -af --volumes

# 3. Pull fresh images
docker-compose pull

# 4. Rotate all secrets
./scripts/rotate-secrets.sh

# 5. Start with clean state
docker-compose up -d

# 6. Verify health
curl -f http://localhost:8080/health || exit 1

echo "✅ Rebuild complete"
```

---

## Recovery

### Service Restoration

```bash
# 1. Verify clean state
docker exec phoenix-core python -c "import phoenix_core; print('OK')"

# 2. Restore from backup (if needed)
# tar -xzf backup-2026-07-05.tar.gz -C /app/data

# 3. Gradual traffic restoration
# Start with 10% traffic, monitor for anomalies

# 4. Full restoration
# Remove maintenance mode, restore normal operation
```

### Verification Checklist

- [ ] All services healthy (`/health` endpoint returns 200)
- [ ] No unauthorized processes running
- [ ] All secrets rotated and verified
- [ ] GitHub repository integrity confirmed
- [ ] AI provider billing normal
- [ ] Telegram bot responding correctly
- [ ] Audit logs capturing events
- [ ] Rate limiting functional

---

## Lessons Learned

### Post-Incident Review

Within 72 hours of incident resolution:

1. **Timeline reconstruction**
   - When was the incident first detected?
   - When did the attack begin?
   - What was the attack vector?

2. **Impact assessment**
   - Data compromised?
   - Services affected?
   - Financial impact?

3. **Response evaluation**
   - Detection speed?
   - Containment effectiveness?
   - Communication quality?

4. **Improvement actions**
   - What prevented faster detection?
   - What would have prevented the incident?
   - What should be automated?

### Documentation Template

```markdown
# Incident Report: INC-2026-001

## Summary
Brief description of the incident.

## Timeline
- 2026-07-05 10:00 UTC - First detection
- 2026-07-05 10:15 UTC - Containment initiated
- 2026-07-05 11:30 UTC - Eradication complete
- 2026-07-05 12:00 UTC - Service restored

## Root Cause
Detailed explanation of how the incident occurred.

## Impact
- Users affected: X
- Data compromised: Y
- Downtime: Z minutes

## Actions Taken
1. Immediate containment
2. Eradication steps
3. Recovery procedure

## Lessons Learned
- What worked well
- What needs improvement

## Action Items
- [ ] Implement monitoring for X
- [ ] Update procedure for Y
- [ ] Train team on Z
```

---

## Communication Plan

### Internal Communication

| Audience | Channel | Timing | Content |
|----------|---------|--------|---------|
| Security Team | PagerDuty/Slack | Immediate | Alert with severity |
| Engineering | Slack #incidents | Within 15 min | Status update |
| Management | Email | Within 1 hour | Executive summary |
| All staff | Slack #general | After containment | All-clear notice |

### External Communication

| Audience | Channel | Timing | Content |
|----------|---------|--------|---------|
| Users | Status page | After assessment | Service status |
| Regulators | Email | As required | Breach notification |
| Media | Press release | If warranted | Public statement |

### Communication Templates

**Initial Alert:**
```
🚨 SECURITY INCIDENT - SEV [P0/P1/P2/P3]

Detected: [TIME]
Severity: [LEVEL]
Status: [INVESTIGATING/CONTAINED/RESOLVED]

Impact: [BRIEF DESCRIPTION]

Next update: [TIME]
Incident commander: [NAME]
```

**Status Update:**
```
📋 INCIDENT UPDATE - INC-[NUMBER]

Current status: [STATUS]
Actions taken: [LIST]
Estimated resolution: [TIME]

No further details at this time.
```

**All Clear:**
```
✅ INCIDENT RESOLVED - INC-[NUMBER]

Resolution time: [DURATION]
Root cause: [BRIEF]
Impact: [SUMMARY]

Full post-mortem: [LINK]
```

---

## Contact List

| Role | Name | Phone | Email | Slack |
|------|------|-------|-------|-------|
| Incident Commander | TBD | +1-XXX-XXX-XXXX | ic@phoenix.dev | @ic |
| Security Lead | TBD | +1-XXX-XXX-XXXX | security@phoenix.dev | @security |
| DevOps Lead | TBD | +1-XXX-XXX-XXXX | devops@phoenix.dev | @devops |
| Legal | TBD | +1-XXX-XXX-XXXX | legal@phoenix.dev | - |
| PR/Communications | TBD | +1-XXX-XXX-XXXX | pr@phoenix.dev | - |

### External Contacts

| Service | Emergency Contact | URL |
|---------|------------------|-----|
| GitHub | security@github.com | github.com/security |
| Telegram | @BotSupport | telegram.org/support |
| Cloud Provider | See console | - |

---

## Playbooks

### Playbook: Compromised Telegram Bot Token

```bash
# 1. Revoke token immediately
# Contact @BotFather, use /revoke command

# 2. Stop bot instance
docker stop phoenix-core

# 3. Generate new token
# @BotFather -> /newbot or /token

# 4. Update environment
export PHOENIX_TELEGRAM_BOT_TOKEN="NEW_TOKEN"

# 5. Restart
docker-compose up -d

# 6. Verify no unauthorized access
# Check logs for unknown user_ids
```

### Playbook: Compromised GitHub PAT

```bash
# 1. Revoke token
# GitHub Settings -> Developer settings -> Personal access tokens

# 2. Audit repository access
# GitHub -> Repository -> Settings -> Security -> Audit log

# 3. Check for unauthorized commits
git log --since="24 hours ago" --oneline

# 4. Rotate token and update
export PHOENIX_GITHUB_TOKEN="NEW_TOKEN"

# 5. Verify webhook integrity
# Check webhook delivery history
```

### Playbook: AI Provider Key Abuse

```bash
# 1. Revoke key in provider dashboard
# Qwen: DashScope Console
# DeepSeek: API Dashboard
# Kimi: Moonshot Console

# 2. Check usage logs
# Review API call patterns for anomalies

# 3. Generate new key
# Provider dashboard -> Create new key

# 4. Update and restart
export PHOENIX_QWEN_API_KEY="NEW_KEY"
docker-compose up -d

# 5. Implement cost alerts
# Set up billing alerts at 50%, 100%, 200% of normal
```

---

## Related Documents

- [Security Architecture](security-architecture.md)
- [Threat Model](threat-model.md)
- [Secrets Management](secrets-management.md)
- [Secure Development Lifecycle](secure-development-lifecycle.md)
- [SECURITY.md](../SECURITY.md)

---

*Last updated: 2026-07-05*
