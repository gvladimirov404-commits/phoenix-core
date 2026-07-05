"""
Secure secret management with encryption support.
"""
import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class SecretManager:
    """Manages secrets with optional encryption"""
    def __init__(self, master_key: Optional[str] = None):
        self._master_key = master_key or os.environ.get("PHOENIX_SECRET_KEY", "")
        self._cipher = None
        if self._master_key:
            self._cipher = self._create_cipher()

    def _create_cipher(self) -> Fernet:
        """Create Fernet cipher from master key"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"phoenix_core_salt_v1",
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self._master_key.encode()))
        return Fernet(key)

    def encrypt(self, value: str) -> str:
        """Encrypt a string value"""
        if not self._cipher:
            raise RuntimeError("Secret manager not initialized with master key")
        encrypted = self._cipher.encrypt(value.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt(self, encrypted_value: str) -> str:
        """Decrypt an encrypted string"""
        if not self._cipher:
            raise RuntimeError("Secret manager not initialized with master key")
        encrypted = base64.urlsafe_b64decode(encrypted_value.encode())
        return self._cipher.decrypt(encrypted).decode()

    def hash_value(self, value: str) -> str:
        """Create a secure hash of a value"""
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def generate_key() -> str:
        """Generate a new encryption key"""
        return Fernet.generate_key().decode()

    @staticmethod
    def mask_secret(value: str, visible_chars: int = 4) -> str:
        """Mask a secret value, showing only last N characters"""
        if len(value) <= visible_chars:
            return "*" * len(value)
        return "*" * (len(value) - visible_chars) + value[-visible_chars:]


class EnvironmentSecretLoader:
    """Load secrets from environment variables with validation"""
    @staticmethod
    def load_required(name: str) -> str:
        """Load a required environment variable"""
        value = os.environ.get(name)
        if not value:
            raise ValueError(f"Required environment variable {name} is not set")
        return value

    @staticmethod
    def load_optional(name: str, default: Optional[str] = None) -> Optional[str]:
        """Load an optional environment variable"""
        return os.environ.get(name, default)

    @staticmethod
    def load_bool(name: str, default: bool = False) -> bool:
        """Load a boolean environment variable"""
        value = os.environ.get(name, str(default)).lower()
        return value in ("true", "1", "yes", "on")

    @staticmethod
    def load_int(name: str, default: int = 0) -> int:
        """Load an integer environment variable"""
        try:
            return int(os.environ.get(name, str(default)))
        except ValueError:
            return default
