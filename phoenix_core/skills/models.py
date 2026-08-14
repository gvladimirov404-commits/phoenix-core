"""SkillDefinition — the parsed representation of one SKILL.md file
(TASK-024). Purely declarative data: a Skill is Markdown instructions
plus metadata, never executable code. SkillManager parses SKILL.md files
into this shape; nothing in this module executes anything.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SkillDefinition:
    """One discovered skill, parsed from a SKILL.md file's YAML
    frontmatter (metadata) and Markdown body (instructions)."""

    name: str
    description: str
    version: str
    category: str
    tags: List[str]
    risk_level: str
    instructions: str
    path: str
    extra: Dict[str, Any] = field(default_factory=dict)
