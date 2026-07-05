# 🔗 SLSA Supply Chain Security

> This document describes the SLSA (Supply-chain Levels for Software Artifacts) implementation for Phoenix Core, ensuring artifact integrity and provenance.

---

## Overview

[SLSA](https://slsa.dev/) is a security framework that provides standards and controls to prevent tampering, improve integrity, and secure packages and infrastructure. Phoenix Core targets **SLSA Level 3**.

## SLSA Levels

| Level | Description | Phoenix Core Status |
|-------|-------------|---------------------|
| **1** | Provenance — build process documented | ✅ Implemented |
| **2** | Signed provenance — trustworthy build service | ✅ Implemented |
| **3** | Hardened builds — hermetic, reproducible | 🔄 In Progress |
| **4** | Two-person review, reproducible builds | 📋 Planned |

## Implementation

### Provenance Generation

SLSA provenance is generated automatically on every release using the [SLSA GitHub Generator](https://github.com/slsa-framework/slsa-github-generator).

```yaml
# .github/workflows/slsa.yml
# See workflow file for full configuration
```

### Provenance Contents

```json
{
  "_type": "https://in-toto.io/Statement/v0.1",
  "subject": [
    {
      "name": "phoenix-core-1.0.0.tar.gz",
      "digest": {
        "sha256": "abc123..."
      }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v0.2",
  "predicate": {
    "builder": {
      "id": "https://github.com/slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@refs/tags/v1.9.0"
    },
    "buildType": "https://github.com/slsa-framework/slsa-github-generator/generic@v1",
    "invocation": {
      "configSource": {
        "uri": "git+https://github.com/phoenix-team/phoenix-core@refs/tags/v1.0.0",
        "digest": {
          "sha1": "def456..."
        }
      }
    }
  }
}
```

### Verification

```bash
# Install SLSA verifier
wget https://github.com/slsa-framework/slsa-verifier/releases/download/v2.4.0/slsa-verifier-linux-amd64
chmod +x slsa-verifier-linux-amd64

# Verify provenance
./slsa-verifier-linux-amd64 verify-artifact   --provenance-path phoenix-core.intoto.jsonl   --source-uri github.com/phoenix-team/phoenix-core   --source-tag v1.0.0   phoenix-core-1.0.0.tar.gz
```

## Supply Chain Controls

| Control | Implementation |
|---------|---------------|
| **Source Integrity** | Signed commits, branch protection |
| **Build Integrity** | GitHub Actions, SLSA provenance |
| **Dependency Integrity** | SBOM, dependency scanning |
| **Distribution Integrity** | Signed releases, checksums |

## Related Documents

- [SBOM](sbom.md)
- [Release Signing](release-signing.md)
- [Secure Development Lifecycle](secure-development-lifecycle.md)

---

*Last updated: 2026-07-05*
