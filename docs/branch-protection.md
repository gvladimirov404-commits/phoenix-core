# 🌿 Branch Protection

> This document describes the required branch protection rules for Phoenix Core to ensure code quality, security, and auditability.

---

## Required Branch Protection Rules

### `main` Branch

| Rule | Setting | Rationale |
|------|---------|-----------|
| **Require pull request reviews** | 2 reviewers | Prevents unilateral changes |
| **Dismiss stale reviews** | ✅ Enabled | Ensures latest code reviewed |
| **Require review from CODEOWNERS** | ✅ Enabled | Security-critical files require expert review |
| **Require status checks** | ✅ Enabled | CI must pass before merge |
| **Require signed commits** | ✅ Enabled | Non-repudiation of authorship |
| **Require linear history** | ✅ Enabled | Clean, auditable history |
| **Include administrators** | ✅ Enabled | No exceptions, even for admins |
| **Restrict pushes** | ✅ Enabled | Only via pull requests |
| **Require conversation resolution** | ✅ Enabled | All review comments addressed |

### `develop` Branch

| Rule | Setting | Rationale |
|------|---------|-----------|
| **Require pull request reviews** | 1 reviewer | Faster iteration, still reviewed |
| **Require status checks** | ✅ Enabled | CI must pass |
| **Require signed commits** | ✅ Enabled | Consistent with main |
| **Require linear history** | ✅ Enabled | Clean history |

### Required Status Checks

```yaml
# These must pass before merge:
checks:
  - "Security Scanning"           # Bandit, Semgrep, GitLeaks
  - "CodeQL Analysis"             # Deep semantic analysis
  - "Dependency Review"           # No vulnerable dependencies
  - "Dependency Audit"            # Safety + pip-audit
  - "Container Security Scan"     # Trivy + Dockle
  - "Tests (3.10)"               # Unit tests Python 3.10
  - "Tests (3.11)"               # Unit tests Python 3.11
  - "Tests (3.12)"               # Unit tests Python 3.12
  - "Lint with flake8"           # Code style
  - "Type check with mypy"        # Type safety
  - "Format check with black"     # Code formatting
```

## Signed Commits

### Why Signed Commits?

- **Authentication**: Proves the commit author is who they claim
- **Integrity**: Ensures commit content hasn't been tampered with
- **Non-repudiation**: Author cannot deny creating the commit
- **Audit trail**: Cryptographically verifiable history

### Setting Up GPG Signing

```bash
# Generate GPG key
gpg --full-generate-key
# Select: RSA and RSA, 4096 bits, no expiration

# List keys
gpg --list-secret-keys --keyid-format=long

# Configure Git
git config --global user.signingkey YOUR_KEY_ID
git config --global commit.gpgsign true
git config --global tag.gpgsign true

# Sign a commit
git commit -S -m "Signed commit"

# Verify signature
git log --show-signature -1
```

### Adding GPG Key to GitHub

```bash
# Export public key
gpg --armor --export YOUR_KEY_ID

# Copy output and paste at:
# GitHub Settings -> SSH and GPG keys -> New GPG key
```

### Enforcing Signed Commits

```
Repository Settings -> Branches -> Branch protection rules -> main
-> Require signed commits -> Enable
```

## Linear History

### Why Linear History?

- **Simpler bisecting**: `git bisect` works without merge commits
- **Cleaner history**: Easier to understand change timeline
- **Better cherry-picking**: Individual commits can be cherry-picked
- **Consistent with signed commits**: Each commit has its own signature

### Enabling Linear History

```
Repository Settings -> Branches -> Branch protection rules -> main
-> Require linear history -> Enable
```

### Workflow with Linear History

```bash
# Instead of: git merge feature-branch
# Use: git rebase main

git checkout feature-branch
git rebase main
# Resolve conflicts if any
git checkout main
git merge feature-branch  # Fast-forward only
```

## Force Push Protection

### Why Disable Force Push?

- **History integrity**: Prevents rewriting published history
- **Collaboration safety**: Protects other developers' work
- **Audit trail**: Maintains complete change history

### Configuration

```
Repository Settings -> Branches -> Branch protection rules -> main
-> Allow force pushes -> Disable (unchecked)
```

## Admin Enforcement

### Why Include Administrators?

Even repository administrators must follow the same rules:

- **No bypass**: Admins cannot merge failing PRs
- **Audit compliance**: All changes go through the same process
- **Team trust**: Demonstrates commitment to process

### Configuration

```
Repository Settings -> Branches -> Branch protection rules -> main
-> Do not allow bypassing the above settings -> Enable
```

## CODEOWNERS Integration

### How It Works

The `CODEOWNERS` file automatically assigns reviewers based on file paths:

```
# Security-critical files
SECURITY.md @phoenix-team/security
docs/security*.md @phoenix-team/security
phoenix_core/utils/secrets.py @phoenix-team/security

# CI/CD
.github/workflows/ @phoenix-team/devops

# Core application
phoenix_core/core/ @phoenix-team/maintainers
```

### Require CODEOWNERS Review

```
Repository Settings -> Branches -> Branch protection rules -> main
-> Require review from CODEOWNERS -> Enable
```

## GitHub Configuration Steps

### Step-by-Step Setup

1. **Navigate to Settings**
   ```
   Repository -> Settings -> Branches
   ```

2. **Add Rule for `main`**
   ```
   Branch name pattern: main
   ```

3. **Configure Protection**
   ```
   ☑️ Restrict pushes that create files larger than 100MB
   ☑️ Require a pull request before merging
      ☑️ Require approvals: 2
      ☑️ Dismiss stale PR approvals when new commits are pushed
      ☑️ Require review from CODEOWNERS
      ☑️ Require approval of the most recent reviewable push
   ☑️ Require status checks to pass before merging
      ☑️ Require branches to be up to date before merging
      [Add all required checks]
   ☑️ Require conversation resolution before merging
   ☑️ Require signed commits
   ☑️ Require linear history
   ☑️ Include administrators
   ☐ Allow force pushes
   ☐ Allow deletions
   ```

4. **Save Changes**

## Verification

### Test Branch Protection

```bash
# Try direct push to main (should fail)
git checkout main
git push origin main
# Expected: remote rejected (protected branch)

# Create PR from feature branch
git checkout -b test-branch
git commit -S -m "Test signed commit"
git push origin test-branch
# Create PR on GitHub
# Verify: requires 2 reviews, all checks must pass
```

## Related Documents

- [Security Architecture](security-architecture.md)
- [Secure Development Lifecycle](secure-development-lifecycle.md)
- [Incident Response](incident-response.md)

---

*Last updated: 2026-07-05*
