# 📋 Software Bill of Materials (SBOM)

> This document describes the SBOM generation and management strategy for Phoenix Core, ensuring transparency and supply chain security.

---

## Overview

A Software Bill of Materials (SBOM) is a comprehensive inventory of all components, libraries, and dependencies used in Phoenix Core. SBOMs are essential for:

- **Vulnerability Management** — Quickly identify affected components when CVEs are disclosed
- **License Compliance** — Track open-source licenses
- **Supply Chain Security** — Verify integrity of all dependencies
- **Audit & Compliance** — Meet regulatory requirements (e.g., EO 14028)

## Supported Formats

| Format | Standard | File Extension | Use Case |
|--------|----------|---------------|----------|
| **CycloneDX** | OWASP | `.json`, `.xml` | Primary format, rich metadata |
| **SPDX** | Linux Foundation | `.json`, `.rdf` | Standardized, widely adopted |

## Generation

### Manual Generation

```bash
# Install CycloneDX
pip install cyclonedx-bom

# Generate CycloneDX SBOM from requirements.txt
cyclonedx-py -r -o sbom.cyclonedx.json

# Generate with hashes for integrity verification
cyclonedx-py -r --output-format json -o sbom.cyclonedx.json
```

### Automated Generation

SBOMs are automatically generated:
- On every push to `main`
- On every release
- On demand via `workflow_dispatch`

See `.github/workflows/sbom.yml`.

## SBOM Contents

A typical Phoenix Core SBOM includes:

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "components": [
    {
      "type": "library",
      "name": "httpx",
      "version": "0.25.0",
      "purl": "pkg:pypi/httpx@0.25.0",
      "licenses": [{"license": {"id": "BSD-3-Clause"}}],
      "hashes": [{"alg": "SHA-256", "content": "..."}]
    }
  ]
}
```

## Verification

```bash
# Verify SBOM integrity
# (Using CycloneDX CLI or similar tools)

# Compare SBOM against installed packages
pip install sbomdiff
sbomdiff sbom.cyclonedx.json --environment
```

## Distribution

SBOMs are attached to:
- GitHub Releases (automatically)
- Container image labels
- Artifact storage

```dockerfile
# Add SBOM to container image
LABEL org.opencontainers.image.sbom="https://github.com/phoenix-team/phoenix-core/releases/download/v1.0.0/sbom.cyclonedx.json"
```

## Related Documents

- [SLSA Supply Chain Security](slsa.md)
- [Secure Development Lifecycle](secure-development-lifecycle.md)
- [Security Architecture](security-architecture.md)

---

*Last updated: 2026-07-05*
