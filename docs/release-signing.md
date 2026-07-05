# ✍️ Release Signing

> This document describes the cryptographic signing strategy for Phoenix Core releases using Sigstore Cosign with GitHub OIDC keyless signing.

---

## Overview

All Phoenix Core releases are cryptographically signed to ensure:
- **Authenticity** — Proof that artifacts were built by the official CI pipeline
- **Integrity** — Assurance that artifacts have not been tampered with
- **Non-repudiation** — Binding of artifacts to the specific GitHub workflow run

## Technology Stack

| Component | Purpose |
|-----------|---------|
| **Sigstore Cosign** | Signing and verification tool |
| **Fulcio** | Free certificate authority (OIDC-based) |
| **Rekor** | Transparency log for signatures |
| **GitHub OIDC** | Identity provider for keyless signing |

## How It Works

### Keyless Signing Flow

```
1. GitHub Actions workflow runs
   └── Generates OIDC token (identity proof)

2. Cosign requests certificate from Fulcio
   └── Fulcio issues short-lived certificate (valid ~10 minutes)

3. Cosign signs artifact with ephemeral key
   └── Private key exists only in memory, discarded after signing

4. Signature + certificate recorded in Rekor
   └── Public transparency log for audit

5. Signature uploaded to release / registry
   └── Users can verify without trusting any single party
```

## What Gets Signed

| Artifact | Signing Method | Verification |
|----------|---------------|--------------|
| Python wheels/sdists | `cosign sign-blob` | `cosign verify-blob` |
| Docker images | `cosign sign` | `cosign verify` |
| Checksum files | `cosign sign-blob` | `cosign verify-blob` |
| SBOM files | `cosign sign-blob` | `cosign verify-blob` |

## Verification

### Verify Release Artifacts

```bash
# Download release artifacts and signature files
wget https://github.com/phoenix-team/phoenix-core/releases/download/v1.0.0/checksums.txt
wget https://github.com/phoenix-team/phoenix-core/releases/download/v1.0.0/checksums.txt.sig
wget https://github.com/phoenix-team/phoenix-core/releases/download/v1.0.0/checksums.txt.pem

# Verify signature
cosign verify-blob   --signature checksums.txt.sig   --certificate checksums.txt.pem   --certificate-identity "https://github.com/phoenix-team/phoenix-core/.github/workflows/release-signing.yml@refs/tags/v1.0.0"   --certificate-oidc-issuer "https://token.actions.githubusercontent.com"   checksums.txt

# Verify checksums
sha256sum --ignore-missing -c checksums.txt
```

### Verify Docker Image

```bash
# Verify container image signature
cosign verify   --certificate-identity "https://github.com/phoenix-team/phoenix-core/.github/workflows/release-signing.yml@refs/tags/v1.0.0"   --certificate-oidc-issuer "https://token.actions.githubusercontent.com"   ghcr.io/phoenix-team/phoenix-core:v1.0.0
```

### Verify in Air-Gapped Environment

```bash
# Save image locally (with network)
cosign save ghcr.io/phoenix-team/phoenix-core:v1.0.0 --dir ./phoenix-image

# Transfer to air-gapped environment
# ...

# Verify offline
cosign verify   --offline   --local-image ./phoenix-image   --certificate-identity "https://github.com/phoenix-team/phoenix-core/.github/workflows/release-signing.yml@refs/tags/v1.0.0"   --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```

## Trust Model

### Why Keyless?

| Aspect | Traditional Key-Based | Keyless (OIDC) |
|--------|----------------------|----------------|
| Key management | Complex (HSM, rotation, storage) | None required |
| Key compromise risk | High (long-lived keys) | Zero (ephemeral keys) |
| Identity binding | Weak (anyone with key) | Strong (OIDC identity) |
| Transparency | Optional | Mandatory (Rekor) |
| Revocation | Complex | Automatic (certificate expiry) |

### Trust Anchors

1. **Fulcio** — Trust that GitHub's OIDC provider is authentic
2. **Rekor** — Trust that the transparency log is append-only
3. **GitHub** — Trust that the workflow identity is correct

## Policy Enforcement

### Kubernetes Admission Controller

```yaml
# Example: Kyverno policy to require signed images
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-phoenix-signature
spec:
  validationFailureAction: Enforce
  rules:
    - name: check-cosign-signature
      match:
        resources:
          kinds:
            - Pod
      validate:
        message: "Phoenix Core images must be signed by Cosign"
        foreach:
          - list: "request.object.spec.containers"
            deny:
              conditions:
                - key: "{{ element.image }}"
                  operator: NotEquals
                  value: "ghcr.io/phoenix-team/phoenix-core:*"
```

## Related Documents

- [SLSA Supply Chain Security](slsa.md)
- [SBOM](sbom.md)
- [Secure Development Lifecycle](secure-development-lifecycle.md)

---

*Last updated: 2026-07-05*
