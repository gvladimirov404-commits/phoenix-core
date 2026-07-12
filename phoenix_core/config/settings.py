"""
Application configuration using Pydantic Settings.
Supports environment variables, .env files, and YAML config.
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from phoenix_core._version import __version__ as _PHOENIX_VERSION


class AIProviderConfig(BaseSettings):
    """Configuration for an AI provider"""
    model_config = SettingsConfigDict(env_prefix="PHOENIX_AI_")

    name: str = Field(..., description="Provider name")
    api_key: SecretStr = Field(..., description="API key for the provider")
    base_url: Optional[str] = Field(None, description="Custom base URL")
    model: str = Field(default="default", description="Default model to use")
    timeout: int = Field(default=30, ge=1, le=300, description="Request timeout in seconds")
    max_retries: int = Field(default=3, ge=0, le=10, description="Max retry attempts")
    priority: int = Field(default=1, ge=1, le=10, description="Provider priority (1=highest)")
    enabled: bool = Field(default=True, description="Whether provider is enabled")


class TelegramConfig(BaseSettings):
    """Telegram bot configuration"""
    model_config = SettingsConfigDict(env_prefix="PHOENIX_TELEGRAM_")

    bot_token: SecretStr = Field(default=SecretStr(""), description="Telegram Bot API token")
    allowed_users: List[int] = Field(default=[], description="List of allowed user IDs")
    webhook_url: Optional[str] = Field(None, description="Webhook URL (if using webhooks)")
    webhook_port: int = Field(default=8443, ge=1, le=65535, description="Webhook port")
    polling_interval: float = Field(default=1.0, ge=0.1, le=60.0, description="Polling interval")
    command_prefix: str = Field(default="/", description="Command prefix")


class GitHubConfig(BaseSettings):
    """GitHub integration configuration"""
    model_config = SettingsConfigDict(env_prefix="PHOENIX_GITHUB_")

    token: SecretStr = Field(default=SecretStr(""), description="GitHub personal access token")
    owner: str = Field(default="", description="Repository owner/username")
    repo: str = Field(default="", description="Repository name")
    default_branch: str = Field(default="main", description="Default branch")
    actions_enabled: bool = Field(default=True, description="Enable GitHub Actions integration")
    webhook_secret: Optional[SecretStr] = Field(None, description="Webhook secret for verification")


class LoggingConfig(BaseSettings):
    """Logging configuration"""
    model_config = SettingsConfigDict(env_prefix="PHOENIX_LOG_")

    level: str = Field(default="INFO", description="Logging level")
    format: str = Field(
        default="json",
        description="Log format (json, console, or simple)",
    )
    file_path: Optional[str] = Field(None, description="Log file path")
    max_bytes: int = Field(default=10_485_760, description="Max log file size in bytes")
    backup_count: int = Field(default=5, description="Number of backup files")
    enable_console: bool = Field(default=True, description="Enable console output")

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        """Normalize and validate the log level against the standard logging levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()


class PluginConfig(BaseSettings):
    """Plugin system configuration"""
    model_config = SettingsConfigDict(env_prefix="PHOENIX_PLUGIN_")

    enabled: bool = Field(default=True, description="Enable plugin system")
    directories: List[str] = Field(
        default=["plugins"],
        description="Directories to scan for plugins",
    )
    auto_load: bool = Field(default=True, description="Auto-load plugins on startup")
    sandboxed: bool = Field(default=False, description="Run plugins in sandbox mode")


class SecurityConfig(BaseSettings):
    """Security configuration"""
    model_config = SettingsConfigDict(env_prefix="PHOENIX_SECURITY_")

    secret_key: SecretStr = Field(default=SecretStr(""), description="Application secret key")
    encrypt_logs: bool = Field(default=False, description="Encrypt log files")
    allowed_hosts: List[str] = Field(default=["*"], description="Allowed hosts")
    rate_limit: int = Field(default=100, description="Requests per minute limit")


class Settings(BaseSettings):
    """Main application settings"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # Application
    app_name: str = Field(default="Phoenix Core", description="Application name")
    app_version: str = Field(default=_PHOENIX_VERSION, description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="production", description="Environment (development, staging, production)")

    # AI Providers
    ai_providers: List[AIProviderConfig] = Field(default=[], description="AI provider configurations")
    ai_default_provider: str = Field(default="deepseek", description="Default AI provider")
    ai_fallback_enabled: bool = Field(default=True, description="Enable fallback between providers")
    ai_request_timeout: int = Field(default=60, ge=1, le=300, description="Global AI request timeout")
    ai_max_prompt_length: int = Field(
        default=4000, ge=1, description="Maximum allowed /ask prompt length, in characters"
    )
    ai_max_conversation_messages: int = Field(
        default=20, ge=1, description="Max messages kept per user conversation (Conversation Memory Engine)"
    )
    ai_max_context_chars: int = Field(
        default=8000, ge=1, description="Max combined character length of context sent to the AI provider"
    )
    ai_rate_limit_requests: int = Field(
        default=10, ge=1, description="Max AI requests allowed per user within one rate-limit window"
    )
    ai_rate_limit_window: int = Field(
        default=60, ge=1, description="Rate-limit window length, in seconds"
    )
    ai_guard_max_context_chars: int = Field(
        default=12000, ge=1,
        description="Hard ceiling (chars) on the assembled context the AI Guard Layer will allow through",
    )
    ai_guard_max_retries: int = Field(
        default=2, ge=0, description="Max retry attempts the AI Guard Layer makes for transient provider errors"
    )
    memory_backend: str = Field(
        default="sqlite",
        description="Conversation Memory storage backend. Only 'sqlite' is implemented today.",
    )
    sqlite_database: str = Field(
        default="phoenix.db",
        description="Path to the SQLite database file used for persistent conversation storage",
    )

    # Telegram
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)

    # GitHub
    github: GitHubConfig = Field(default_factory=GitHubConfig)

    # Logging
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Plugins
    plugins: PluginConfig = Field(default_factory=PluginConfig)

    # Security
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    # Paths
    data_dir: str = Field(default="./data", description="Data directory")
    temp_dir: str = Field(default="./temp", description="Temporary directory")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Normalize and validate the environment name against the supported set."""
        valid_envs = ["development", "staging", "production", "testing"]
        if v.lower() not in valid_envs:
            raise ValueError(f"Invalid environment: {v}. Must be one of {valid_envs}")
        return v.lower()

    @model_validator(mode="after")
    def _populate_ai_providers_from_env(self) -> "Settings":
        """Build ai_providers from flat PHOENIX_AI_DEEPSEEK_* env vars if not set explicitly.

        This keeps AIProviderConfig (the already-planned per-provider schema) as the
        single source of truth, while letting the single-provider V1 setup be
        configured with plain env vars instead of a JSON blob.
        """
        if self.ai_providers:
            return self

        deepseek_api_key = os.environ.get("PHOENIX_AI_DEEPSEEK_API_KEY")
        if deepseek_api_key:
            self.ai_providers = [
                AIProviderConfig(
                    name="deepseek",
                    api_key=deepseek_api_key,
                    base_url=os.environ.get("PHOENIX_AI_DEEPSEEK_BASE_URL") or None,
                    model=os.environ.get("PHOENIX_AI_DEEPSEEK_MODEL", "deepseek-chat"),
                    timeout=int(os.environ.get("PHOENIX_AI_DEEPSEEK_TIMEOUT", "30")),
                    max_retries=int(os.environ.get("PHOENIX_AI_DEEPSEEK_MAX_RETRIES", "3")),
                    priority=1,
                    enabled=True,
                )
            ]
        return self

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Settings":
        """Load settings from file or environment"""
        if config_path and os.path.exists(config_path):
            # Load from YAML/JSON config file
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
            return cls(**config_data)
        return cls()

    def to_dict(self, hide_secrets: bool = True) -> Dict[str, Any]:
        """Convert settings to dictionary"""
        data = self.model_dump()
        if hide_secrets:
            # Mask secret values
            self._mask_secrets(data)
        return data

    def _mask_secrets(self, data: Dict[str, Any]) -> None:
        """Recursively mask secret values"""
        for key, value in data.items():
            if isinstance(value, dict):
                self._mask_secrets(value)
            elif any(secret_key in key.lower() for secret_key in ["token", "key", "secret", "password"]):
                data[key] = "***REDACTED***"

    def ensure_directories(self) -> None:
        """Create necessary directories"""
        for dir_path in [self.data_dir, self.temp_dir]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
        if self.logging.file_path:
            Path(self.logging.file_path).parent.mkdir(parents=True, exist_ok=True)
