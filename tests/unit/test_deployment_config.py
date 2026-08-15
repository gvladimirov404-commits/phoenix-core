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
