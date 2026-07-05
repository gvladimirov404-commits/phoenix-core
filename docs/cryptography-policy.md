# 🔐 Cryptography Policy

> This document defines the official cryptography policy for Phoenix Core, specifying approved algorithms, key management practices, and security requirements.

---

## Table of Contents

1. [Purpose](#purpose)
2. [Allowed Algorithms](#allowed-algorithms)
3. [Prohibited Algorithms](#prohibited-algorithms)
4. [Key Management](#key-management)
5. [Key Rotation](#key-rotation)
6. [TLS Requirements](#tls-requirements)
7. [Hashing Policy](#hashing-policy)
8. [Password Policy](#password-policy)
9. [Random Number Generation](#random-number-generation)
10. [Compliance](#compliance)

---

## Purpose

This policy establishes minimum cryptographic standards for all Phoenix Core components to ensure data confidentiality, integrity, and authenticity.

## Allowed Algorithms

### Symmetric Encryption

| Algorithm | Mode | Key Size | Use Case | Status |
|-----------|------|----------|----------|--------|
| **AES** | GCM | 256-bit | Log encryption, data at rest | ✅ Required |
| **AES** | CBC | 256-bit | Legacy compatibility only | ⚠️ Deprecated |
| **ChaCha20-Poly1305** | AEAD | 256-bit | Alternative to AES-GCM | ✅ Approved |

### Asymmetric Encryption

| Algorithm | Key Size | Use Case | Status |
|-----------|----------|----------|--------|
| **RSA** | >= 3072-bit | Key exchange (legacy) | ⚠️ Deprecated |
| **ECDH** | P-256, P-384 | Key exchange | ✅ Required |
| **X25519** | 256-bit | Key exchange | ✅ Preferred |

### Digital Signatures

| Algorithm | Key Size | Use Case | Status |
|-----------|----------|----------|--------|
| **ECDSA** | P-256, P-384 | Code signing, certificates | ✅ Required |
| **Ed25519** | 256-bit | Code signing, Git commits | ✅ Preferred |
| **RSA-PSS** | >= 3072-bit | Legacy compatibility | ⚠️ Deprecated |

### Hash Functions

| Algorithm | Output Size | Use Case | Status |
|-----------|-------------|----------|--------|
| **SHA-256** | 256-bit | General hashing | ✅ Required |
| **SHA-384** | 384-bit | High-security hashing | ✅ Approved |
| **SHA-3-256** | 256-bit | Post-quantum preparation | ✅ Approved |
| **BLAKE2b** | 256-bit | Performance-critical | ✅ Approved |

## Prohibited Algorithms

| Algorithm | Reason | Replacement |
|-----------|--------|-------------|
| **MD5** | Broken collision resistance | SHA-256 |
| **SHA-1** | Deprecated, collision attacks | SHA-256 |
| **DES** | 56-bit key, brute-forceable | AES-256-GCM |
| **3DES** | Sweet32 vulnerability | AES-256-GCM |
| **RC4** | Multiple vulnerabilities | AES-256-GCM |
| **RSA < 2048-bit** | Insufficient security | RSA >= 3072-bit or ECDH |
| **ECDSA with SHA-1** | Weak signature | ECDSA with SHA-256 |

## Key Management

### Key Generation

```python
# Secure key generation examples
import secrets
from cryptography.fernet import Fernet

# Symmetric key (32 bytes = 256 bits)
symmetric_key = secrets.token_bytes(32)

# Fernet key (URL-safe base64-encoded 32 bytes)
fernet_key = Fernet.generate_key()

# Application secret key
app_secret = secrets.token_urlsafe(32)
```

### Key Storage

| Key Type | Storage Method | Access Control |
|----------|---------------|----------------|
| Application secrets | Environment variables | Process-only, no logging |
| Database encryption keys | Hardware Security Module (HSM) | Role-based access |
| TLS private keys | Key Management Service (KMS) | Certificate-based |
| Signing keys | Secure enclave / TPM | Multi-factor authentication |

### Key Lifecycle

```
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│ Generate│──▶│  Store  │──▶│  Use    │──▶│ Rotate  │──▶│ Destroy │
│         │   │         │   │         │   │         │   │         │
│ CSRNG   │   │ HSM/KMS │   │ Minimize│   │ Schedule│   │ Secure  │
│         │   │         │   │ exposure│   │ overlap │   │ deletion│
└─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘
```

## Key Rotation

### Rotation Schedule

| Key Type | Rotation Period | Trigger |
|----------|-----------------|---------|
| Application secret key | 180 days | Scheduled |
| API keys (AI providers) | 90 days | Scheduled |
| TLS certificates | 90 days | Automated (Let's Encrypt) |
| Database encryption keys | 365 days | Scheduled or on suspicion |
| Signing keys | 180 days | Scheduled |

### Rotation Procedure

```python
# Example: Graceful key rotation with overlap period
class RotatingKeyManager:
    def __init__(self, primary_key, secondary_key=None):
        self.primary = primary_key
        self.secondary = secondary_key  # Previous key for decryption

    def encrypt(self, data):
        # Always encrypt with primary key
        return self._encrypt_with_key(data, self.primary)

    def decrypt(self, encrypted_data):
        # Try primary first, then secondary
        try:
            return self._decrypt_with_key(encrypted_data, self.primary)
        except Exception:
            if self.secondary:
                return self._decrypt_with_key(encrypted_data, self.secondary)
            raise
```

## TLS Requirements

### Minimum TLS Version

| Environment | Minimum Version | Recommended |
|-------------|------------------|-------------|
| Production | TLS 1.2 | TLS 1.3 |
| Development | TLS 1.2 | TLS 1.3 |
| Legacy support | TLS 1.2 | N/A |

### Cipher Suites (TLS 1.3)

```
TLS_AES_256_GCM_SHA384
TLS_CHACHA20_POLY1305_SHA256
TLS_AES_128_GCM_SHA256
```

### Certificate Requirements

- **Key type**: ECDSA P-256 or RSA 3072+
- **Signature algorithm**: SHA-256 or better
- **Validity period**: Maximum 90 days (automated renewal)
- **SAN**: Must include all hostnames
- **CT logging**: Required for production

### Certificate Pinning (Optional)

```python
import ssl
import hashlib

# Pin expected certificate hash
EXPECTED_PIN = "sha256/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

def verify_pin(cert_der):
    cert_hash = hashlib.sha256(cert_der).digest()
    cert_pin = "sha256/" + base64.b64encode(cert_hash).decode()
    if cert_pin != EXPECTED_PIN:
        raise ssl.SSLError("Certificate pin mismatch")
```

## Hashing Policy

### Password Hashing

```python
# NEVER use for passwords
# hashlib.sha256(password)  # ❌ WRONG

# Use Argon2 (recommended)
from argon2 import PasswordHasher
ph = PasswordHasher(
    time_cost=3,      # iterations
    memory_cost=65536, # 64 MB
    parallelism=4,
    hash_len=32,
    salt_len=16
)
hash = ph.hash(password)
ph.verify(hash, password)
```

### Data Integrity

```python
import hashlib

# For file integrity
sha256 = hashlib.sha256()
with open('file.bin', 'rb') as f:
    for chunk in iter(lambda: f.read(8192), b''):
        sha256.update(chunk)
digest = sha256.hexdigest()
```

### HMAC for Authentication

```python
import hmac
import hashlib

# For API request signing
def sign_request(payload, secret):
    return hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
```

## Password Policy

### User Passwords

| Requirement | Minimum |
|-------------|---------|
| Length | 12 characters |
| Complexity | Upper, lower, digit, special |
| Dictionary check | No common passwords |
| History | Last 5 passwords |
| Maximum age | 90 days |
| Lockout after | 5 failed attempts |

### Service Account Passwords

| Requirement | Minimum |
|-------------|---------|
| Length | 32 characters |
| Generation | Cryptographically random |
| Storage | Vault / KMS |
| Rotation | 90 days |

## Random Number Generation

### Approved Sources

```python
import secrets
import os

# For cryptographic purposes
random_token = secrets.token_urlsafe(32)
random_bytes = secrets.token_bytes(32)
random_int = secrets.randbelow(1000)

# For nonces
nonce = secrets.token_hex(16)

# NEVER use for cryptographic purposes
# import random
# random.random()  # ❌ PREDICTABLE
```

### Entropy Requirements

| Use Case | Minimum Entropy |
|----------|----------------|
| Session tokens | 128 bits |
| API keys | 256 bits |
| Passwords | 80 bits |
| Nonces | 96 bits |

## Compliance

### Standards Alignment

| Standard | Requirement | Status |
|----------|-------------|--------|
| **NIST SP 800-57** | Key management guidelines | ✅ Compliant |
| **NIST SP 800-131A** | Cryptographic algorithm transitions | ✅ Compliant |
| **PCI-DSS 4.0** | Encryption requirements | ✅ Compliant |
| **FIPS 140-3** | Cryptographic module validation | 📋 Planned |

### Audit Requirements

- Annual cryptographic inventory review
- Quarterly key rotation verification
- Continuous TLS configuration monitoring
- Post-quantum readiness assessment (annual)

## Related Documents

- [Secrets Management](secrets-management.md)
- [Security Architecture](security-architecture.md)
- [Secure Development Lifecycle](secure-development-lifecycle.md)

---

*Last updated: 2026-07-05*
