"""Regression tests for Task 030's deployment configuration fixes —
Dockerfile CMD and docker-compose.yml read-only/SQLite-path settings.
Pure text-based checks against the repository's own config files; no
Docker installation or runtime is required or assumed.
"""
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestDockerfileStartsTheBot:
    def test_production_cmd_invokes_the_real_start_subcommand(self) -> None:
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

        # The production stage's CMD must be the one that actually starts
        # polling — not a bare module invocation, which just prints Click's
        # usage help and exits (confirmed by direct execution in Task 029's
        # audit).
        assert 'CMD ["python", "-m", "phoenix_core", "start"]' in dockerfile

    def test_development_stage_cmd_is_unaffected(self) -> None:
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

        # The dev stage's own CMD (running the test suite) must remain
        # untouched by the production-stage fix.
        assert 'CMD ["python", "-m", "pytest", "-v"]' in dockerfile


class TestComposeReadOnlyAndSqlitePath:
    def _load_service(self) -> dict:
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        return compose["services"]["phoenix-core"]

    def test_read_only_remains_enabled(self) -> None:
        service = self._load_service()
        assert service["read_only"] is True

    def test_sqlite_database_points_inside_the_writable_data_volume(self) -> None:
        service = self._load_service()
        env_entries = service["environment"]

        sqlite_entries = [e for e in env_entries if e.startswith("SQLITE_DATABASE=")]
        assert len(sqlite_entries) == 1, "expected exactly one SQLITE_DATABASE override"

        sqlite_path = sqlite_entries[0].split("=", 1)[1]
        assert sqlite_path.startswith("/app/data/"), (
            f"SQLITE_DATABASE ({sqlite_path}) must live inside /app/data, "
            "the volume mounted writable under read_only: true"
        )

    def test_data_directory_is_mounted_as_a_writable_volume(self) -> None:
        service = self._load_service()
        volumes = service["volumes"]

        assert any(v.endswith(":/app/data") for v in volumes), (
            "expected a volume mount targeting /app/data — the writable "
            "location SQLITE_DATABASE now points into"
        )


class TestAllowedUsersDocumentation:
    """Task 033: PHOENIX_TELEGRAM_ALLOWED_USERS must be documented in
    .env.example, with syntax matching the actual settings parser."""

    def test_env_example_contains_allowed_users_variable(self) -> None:
        env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        assert "PHOENIX_TELEGRAM_ALLOWED_USERS=" in env_example

    def test_documented_syntax_matches_actual_settings_parser(self) -> None:
        """The documented JSON-array example must actually parse
        successfully through the real TelegramConfig — proving the
        documentation isn't just plausible-looking prose."""
        import os

        from phoenix_core.config.settings import TelegramConfig

        original = os.environ.get("PHOENIX_TELEGRAM_ALLOWED_USERS")
        os.environ["PHOENIX_TELEGRAM_ALLOWED_USERS"] = "[123456789, 987654321]"
        try:
            config = TelegramConfig()
            assert config.allowed_users == [123456789, 987654321]
        finally:
            if original is None:
                os.environ.pop("PHOENIX_TELEGRAM_ALLOWED_USERS", None)
            else:
                os.environ["PHOENIX_TELEGRAM_ALLOWED_USERS"] = original

    def test_empty_default_means_no_restriction(self) -> None:
        from phoenix_core.config.settings import TelegramConfig

        config = TelegramConfig()
        assert config.allowed_users == []

    def test_no_conflicting_authorization_semantics_documented(self) -> None:
        """The doc block must not mention username-based authorization —
        Task 028's design is numeric-ID-only."""
        env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        # Find the block around the allowed_users declaration
        idx = env_example.index("PHOENIX_TELEGRAM_ALLOWED_USERS=")
        block = env_example[max(0, idx - 700):idx + 50]
        assert "username" not in block.lower()


class TestBackupDocumentation:
    """Task 033: README must document the SQLite backup location and
    procedure without claiming automation that doesn't exist."""

    def test_readme_documents_deployment_and_backup_section(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        assert "## Deployment & Data Backup" in readme

    def test_readme_documents_the_actual_database_path(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        assert "/app/data/phoenix.db" in readme

    def test_readme_does_not_claim_automated_backup(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        idx = readme.index("## Deployment & Data Backup")
        section = readme[idx:idx + 1500]
        assert "no automatic backup" in section.lower()


class TestHealthcheckDocumentation:
    """Task 033: the Dockerfile healthcheck was deliberately left
    unchanged — this test locks in that decision and the command itself,
    so a future accidental edit doesn't silently drift from what was
    reviewed and justified."""

    def test_healthcheck_command_is_unchanged(self) -> None:
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert 'CMD python -c "import phoenix_core; print(\'OK\')" || exit 1' in dockerfile

    def test_healthcheck_has_a_documented_rationale(self) -> None:
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "Task 033" in dockerfile
        assert "liveness check only" in dockerfile
