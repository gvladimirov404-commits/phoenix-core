"""Unit tests for AI provider configuration loading from environment variables."""
from phoenix_core.config.settings import Settings


class TestAIProviderEnvLoading:
    def test_no_provider_configured_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv("PHOENIX_AI_DEEPSEEK_API_KEY", raising=False)
        settings = Settings()
        assert settings.ai_providers == []

    def test_builds_deepseek_provider_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("PHOENIX_AI_DEEPSEEK_API_KEY", "sk-test-123")
        monkeypatch.setenv("PHOENIX_AI_DEEPSEEK_MODEL", "deepseek-chat")
        settings = Settings()

        assert len(settings.ai_providers) == 1
        provider_config = settings.ai_providers[0]
        assert provider_config.name == "deepseek"
        assert provider_config.api_key.get_secret_value() == "sk-test-123"
        assert provider_config.model == "deepseek-chat"
        assert provider_config.enabled is True

    def test_default_provider_is_deepseek(self) -> None:
        settings = Settings()
        assert settings.ai_default_provider == "deepseek"

    def test_default_max_prompt_length(self) -> None:
        settings = Settings()
        assert settings.ai_max_prompt_length == 4000

    def test_max_prompt_length_configurable_via_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AI_MAX_PROMPT_LENGTH", "500")
        settings = Settings()
        assert settings.ai_max_prompt_length == 500

    def test_settings_boots_without_any_secrets_configured(self, monkeypatch) -> None:
        """The core Task 002 regression: Settings() must not require every
        integration's secret to be set just to construct the object."""
        for var in (
            "PHOENIX_AI_DEEPSEEK_API_KEY",
            "PHOENIX_TELEGRAM_BOT_TOKEN",
            "PHOENIX_GITHUB_TOKEN",
            "PHOENIX_SECURITY_SECRET_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        settings = Settings()
        assert settings.ai_providers == []
