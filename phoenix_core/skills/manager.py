"""SkillManager — discovers, parses, and exposes SKILL.md files
(TASK-024). Purely declarative: parses YAML frontmatter + Markdown body
into a SkillDefinition. Never imports or executes anything from a skill
directory — no Python code is ever loaded from a SKILL.md file or its
surrounding directory, unlike phoenix_core.plugins.registry.PluginRegistry
(which does load .py files) — these are deliberately separate systems.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from phoenix_core.skills.models import SkillDefinition
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

_REQUIRED_FIELDS = ("name", "description")
_KNOWN_FIELDS = {"name", "description", "version", "category", "tags", "risk_level"}


class SkillLoadError(Exception):
    """Raised internally when a single SKILL.md file fails to parse.
    Always caught within SkillManager — never propagates out of
    discover(), so one bad file never blocks the others."""


def _split_frontmatter(text: str) -> Optional[tuple]:
    """Split a SKILL.md file's text into (frontmatter_yaml, body).
    Returns None if the file doesn't start with a '---' delimited block."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    _, frontmatter_raw, body = parts
    return frontmatter_raw, body.lstrip("\n")


def _parse_skill_file(path: Path) -> SkillDefinition:
    """Parse one SKILL.md file into a SkillDefinition. Raises
    SkillLoadError for any problem — missing frontmatter, malformed
    YAML, or missing required fields."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise SkillLoadError(f"Could not read {path}: {e}") from e

    split = _split_frontmatter(text)
    if split is None:
        raise SkillLoadError(f"{path} has no YAML frontmatter block")
    frontmatter_raw, body = split

    try:
        frontmatter = yaml.safe_load(frontmatter_raw)
    except yaml.YAMLError as e:
        raise SkillLoadError(f"Malformed YAML frontmatter in {path}: {e}") from e

    if not isinstance(frontmatter, dict):
        raise SkillLoadError(f"Frontmatter in {path} is not a mapping")

    missing = [f for f in _REQUIRED_FIELDS if not frontmatter.get(f)]
    if missing:
        raise SkillLoadError(f"{path} is missing required field(s): {', '.join(missing)}")

    extra = {k: v for k, v in frontmatter.items() if k not in _KNOWN_FIELDS}

    return SkillDefinition(
        name=str(frontmatter["name"]),
        description=str(frontmatter["description"]),
        version=str(frontmatter.get("version", "")),
        category=str(frontmatter.get("category", "")),
        tags=list(frontmatter.get("tags", []) or []),
        risk_level=str(frontmatter.get("risk_level", "")),
        instructions=body.strip(),
        path=str(path),
        extra=extra,
    )


class SkillManager:
    """Discovers SKILL.md files under configured directories and exposes
    them by name. Declarative only — never executes skill content."""

    def __init__(self, directories: Optional[List[str]] = None) -> None:
        """Create a manager for the given directories (not yet scanned —
        call discover())."""
        self.directories = directories or []
        self._skills: Dict[str, SkillDefinition] = {}
        self._load_errors: Dict[str, str] = {}

    def discover(self) -> None:
        """Scan every configured directory recursively for SKILL.md
        files and load each one. A missing directory is skipped (logged,
        not an error). An invalid SKILL.md is skipped (logged) without
        blocking the rest. A duplicate skill name keeps the first
        discovered definition and logs a warning."""
        for directory in self.directories:
            dir_path = Path(directory)
            if not dir_path.is_dir():
                logger.info("Skill directory not found, skipping", directory=directory)
                continue

            for skill_file in sorted(dir_path.rglob("SKILL.md")):
                self._load_file(skill_file)

    def _load_file(self, skill_file: Path) -> None:
        try:
            skill = _parse_skill_file(skill_file)
        except SkillLoadError as e:
            logger.warning(
                "Skill failed to load", file=str(skill_file), error=str(e)
            )
            self._load_errors[str(skill_file)] = str(e)
            return

        if skill.name in self._skills:
            logger.warning(
                "Duplicate skill name, keeping first discovered",
                name=skill.name,
                kept_path=self._skills[skill.name].path,
                ignored_path=skill.path,
            )
            return

        self._skills[skill.name] = skill
        logger.info("Skill loaded", name=skill.name, file=str(skill_file))

    def list_skills(self) -> List[SkillDefinition]:
        """Return every successfully loaded skill."""
        return list(self._skills.values())

    def get(self, name: str) -> SkillDefinition:
        """Return the skill with exactly this name.

        Raises:
            KeyError: if no skill with this exact name was loaded.
        """
        skill = self._skills.get(name)
        if skill is None:
            raise KeyError(f"Skill '{name}' not found")
        return skill

    def has(self, name: str) -> bool:
        """Return True if a skill with exactly this name was loaded."""
        return name in self._skills

    async def health_check(self) -> Dict[str, Any]:
        """Report how many skills loaded successfully vs failed, for
        /health and /status (same shape as PluginRegistry.health_check)."""
        if self._load_errors:
            status = "misconfigured"
        elif self._skills:
            status = "healthy"
        else:
            status = "configured"
        return {
            "status": status,
            "detail": f"{len(self._skills)} skill(s) loaded, {len(self._load_errors)} failed",
            "loaded": list(self._skills.keys()),
            "errors": dict(self._load_errors),
        }
