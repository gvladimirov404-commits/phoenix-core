"""Skill Manager — declarative SKILL.md discovery and loading (TASK-024).

Skills are Markdown instruction files with YAML frontmatter, describing
a capability an AI provider can be prompted to follow (e.g.
skills/research/crypto-research/SKILL.md). This package only discovers
and parses skill files — it never executes anything from them, and has
no relationship to phoenix_core.plugins (which loads and runs Python
code); the two systems are intentionally separate.
"""
from phoenix_core.skills.manager import SkillManager
from phoenix_core.skills.models import SkillDefinition

__all__ = ["SkillManager", "SkillDefinition"]
