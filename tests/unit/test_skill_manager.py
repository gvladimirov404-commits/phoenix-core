"""Unit tests for phoenix_core.skills.manager.SkillManager (Task 024)."""
import pytest

from phoenix_core.skills.manager import SkillManager


def _write_skill(tmp_path, subdir, filename, content):
    skill_dir = tmp_path / subdir
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / filename).write_text(content, encoding="utf-8")
    return skill_dir / filename


_VALID_SKILL = """---
name: test-skill
description: A test skill for unit testing
version: 1
category: research
tags: [test, unit]
risk_level: low
---

## When to use
For testing purposes only.

## Procedure
1. Do the thing.
2. Return the result.
"""


class TestValidSkillLoading:
    def test_valid_skill_loads_correctly(self, tmp_path) -> None:
        _write_skill(tmp_path, "test-skill", "SKILL.md", _VALID_SKILL)
        manager = SkillManager(directories=[str(tmp_path)])

        manager.discover()

        assert manager.has("test-skill")

    def test_frontmatter_fields_are_parsed(self, tmp_path) -> None:
        _write_skill(tmp_path, "test-skill", "SKILL.md", _VALID_SKILL)
        manager = SkillManager(directories=[str(tmp_path)])
        manager.discover()

        skill = manager.get("test-skill")

        assert skill.name == "test-skill"
        assert skill.description == "A test skill for unit testing"
        assert skill.version == "1"
        assert skill.category == "research"
        assert skill.tags == ["test", "unit"]
        assert skill.risk_level == "low"

    def test_markdown_body_becomes_instructions(self, tmp_path) -> None:
        _write_skill(tmp_path, "test-skill", "SKILL.md", _VALID_SKILL)
        manager = SkillManager(directories=[str(tmp_path)])
        manager.discover()

        skill = manager.get("test-skill")

        assert "## When to use" in skill.instructions
        assert "## Procedure" in skill.instructions
        assert "name: test-skill" not in skill.instructions

    def test_extra_frontmatter_fields_are_preserved(self, tmp_path) -> None:
        content = _VALID_SKILL.replace("risk_level: low", "risk_level: low\ncustom_field: custom_value")
        _write_skill(tmp_path, "test-skill", "SKILL.md", content)
        manager = SkillManager(directories=[str(tmp_path)])
        manager.discover()

        skill = manager.get("test-skill")

        assert skill.extra.get("custom_field") == "custom_value"


class TestValidationRejection:
    def test_missing_name_is_rejected(self, tmp_path) -> None:
        content = """---
description: Missing a name field
---

Body text.
"""
        _write_skill(tmp_path, "bad-skill", "SKILL.md", content)
        manager = SkillManager(directories=[str(tmp_path)])

        manager.discover()

        assert manager.list_skills() == []

    def test_missing_description_is_rejected(self, tmp_path) -> None:
        content = """---
name: bad-skill
---

Body text.
"""
        _write_skill(tmp_path, "bad-skill", "SKILL.md", content)
        manager = SkillManager(directories=[str(tmp_path)])

        manager.discover()

        assert manager.list_skills() == []

    def test_malformed_yaml_is_rejected(self, tmp_path) -> None:
        content = """---
name: bad-skill
description: [unterminated list
---

Body text.
"""
        _write_skill(tmp_path, "bad-skill", "SKILL.md", content)
        manager = SkillManager(directories=[str(tmp_path)])

        manager.discover()

        assert manager.list_skills() == []


class TestMissingDirectory:
    def test_missing_directory_does_not_crash(self, tmp_path) -> None:
        nonexistent = tmp_path / "does-not-exist"
        manager = SkillManager(directories=[str(nonexistent)])

        manager.discover()  # must not raise

        assert manager.list_skills() == []


class TestDuplicateNames:
    def test_duplicate_skill_names_keep_first_discovered(self, tmp_path) -> None:
        first = _VALID_SKILL
        second = _VALID_SKILL.replace(
            "description: A test skill for unit testing",
            "description: A DIFFERENT description",
        )
        _write_skill(tmp_path, "skill-a", "SKILL.md", first)
        _write_skill(tmp_path, "skill-b", "SKILL.md", second)
        manager = SkillManager(directories=[str(tmp_path)])

        manager.discover()

        assert len(manager.list_skills()) == 1
        assert manager.get("test-skill").description == "A test skill for unit testing"


class TestLookup:
    def test_get_returns_the_skill(self, tmp_path) -> None:
        _write_skill(tmp_path, "test-skill", "SKILL.md", _VALID_SKILL)
        manager = SkillManager(directories=[str(tmp_path)])
        manager.discover()

        skill = manager.get("test-skill")

        assert skill.name == "test-skill"

    def test_get_missing_skill_raises_key_error(self, tmp_path) -> None:
        manager = SkillManager(directories=[str(tmp_path)])
        manager.discover()

        with pytest.raises(KeyError):
            manager.get("nonexistent-skill")

    def test_has_returns_true_for_loaded_skill(self, tmp_path) -> None:
        _write_skill(tmp_path, "test-skill", "SKILL.md", _VALID_SKILL)
        manager = SkillManager(directories=[str(tmp_path)])
        manager.discover()

        assert manager.has("test-skill") is True

    def test_has_returns_false_for_unknown_skill(self, tmp_path) -> None:
        manager = SkillManager(directories=[str(tmp_path)])
        manager.discover()

        assert manager.has("unknown") is False


class TestNoCodeExecution:
    def test_discovery_does_not_execute_python_from_skill_directory(self, tmp_path) -> None:
        skill_dir = tmp_path / "malicious-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(_VALID_SKILL, encoding="utf-8")

        # A .py file sitting alongside SKILL.md — if SkillManager ever
        # imported or executed it, this file's side effect (writing a
        # marker file) would prove it. It must never run.
        marker_path = tmp_path / "executed.marker"
        (skill_dir / "malicious.py").write_text(
            f"open({marker_path!r}, 'w').close()\n", encoding="utf-8"
        )

        manager = SkillManager(directories=[str(tmp_path)])
        manager.discover()

        assert not marker_path.exists()
        assert manager.has("test-skill")


class TestApplicationWiring:
    """Task 026: verify SkillsConfig.enabled/auto_load actually gate
    discovery through the real PhoenixApplication wiring, not just in
    SkillManager isolation. The real skills/research/crypto-research/
    SKILL.md file on disk is what proves discovery would have found
    something if it had run."""

    def test_skills_disabled_prevents_discovery(self) -> None:
        from phoenix_core.config.settings import Settings, SkillsConfig
        from phoenix_core.core.application import PhoenixApplication

        settings = Settings(skills=SkillsConfig(enabled=False, directories=["skills"]))
        app = PhoenixApplication(settings)

        skill_manager = app.container.resolve("skill_manager")

        assert skill_manager.list_skills() == []

    def test_auto_load_false_prevents_discovery(self) -> None:
        from phoenix_core.config.settings import Settings, SkillsConfig
        from phoenix_core.core.application import PhoenixApplication

        settings = Settings(
            skills=SkillsConfig(enabled=True, auto_load=False, directories=["skills"])
        )
        app = PhoenixApplication(settings)

        skill_manager = app.container.resolve("skill_manager")

        assert skill_manager.list_skills() == []
