"""Unit tests for phoenix_core.services.research.research_capability.
Tests the capability directly — no Telegram objects, no real network
calls, no real API keys."""
from types import SimpleNamespace

import pytest

from phoenix_core.core.container import Container
from phoenix_core.services.research.research_capability import (
    ResearchAIError,
    ResearchNoDataError,
    ResearchResult,
    ResearchUnavailableError,
    run_research,
)
from phoenix_core.utils.exceptions import (
    AIProviderTimeoutError,
    ConfigurationError,
)


def _snapshot(symbol="BTC", price=100.0, empty=False):
    if empty:
        return SimpleNamespace(symbol=symbol, market=None, fear_greed=None, top_news=None, fees=None, is_empty=True)
    return SimpleNamespace(
        symbol=symbol,
        market=SimpleNamespace(price_usd=price, change_24h_pct=1.0),
        fear_greed=SimpleNamespace(value=50, classification="Neutral"),
        top_news=SimpleNamespace(title="Some headline", source="Test"),
        fees=None,
        is_empty=False,
    )


class FakeAggregator:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    async def get_snapshot(self, symbol):
        return self._snapshot


class FakeAIResponse:
    def __init__(self, content="AI narrative text", provider="fake-provider"):
        self.content = content
        self.provider = provider


class FakeAIRouter:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    async def chat(self, messages):
        if self._error is not None:
            raise self._error
        return self._response


def _dummy_build_prompt(snapshot, signals, evidence, skill_instructions=None):
    return f"prompt for {snapshot.symbol}"


class TestSuccessfulResearchFlow:
    @pytest.mark.asyncio
    async def test_returns_research_result_with_expected_fields(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))

        result = await run_research("btc", container, _dummy_build_prompt, user_id=1)

        assert isinstance(result, ResearchResult)
        assert result.snapshot.symbol == "BTC"
        assert result.ai_text == "AI narrative text"
        assert result.provider == "fake-provider"
        assert result.evidence is not None
        assert isinstance(result.signals, dict)


class TestEmptySnapshot:
    @pytest.mark.asyncio
    async def test_empty_snapshot_raises_no_data_error(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot(empty=True)))
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))

        with pytest.raises(ResearchNoDataError):
            await run_research("btc", container, _dummy_build_prompt, user_id=1)


class TestMissingServices:
    @pytest.mark.asyncio
    async def test_missing_aggregator_raises_unavailable_error(self) -> None:
        container = Container()
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))

        with pytest.raises(ResearchUnavailableError):
            await run_research("btc", container, _dummy_build_prompt, user_id=1)

    @pytest.mark.asyncio
    async def test_missing_ai_router_raises_unavailable_error(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))

        with pytest.raises(ResearchUnavailableError):
            await run_research("btc", container, _dummy_build_prompt, user_id=1)


class TestStrategyAndEvidenceIntegration:
    @pytest.mark.asyncio
    async def test_signals_and_evidence_are_derived_from_snapshot(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))

        result = await run_research("btc", container, _dummy_build_prompt, user_id=1)

        assert result.evidence.confidence in {"LOW", "MEDIUM", "HIGH"}
        assert "market" in result.evidence.available_sources


class TestAIFailureHandling:
    @pytest.mark.asyncio
    async def test_ai_timeout_raises_research_ai_error(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(error=AIProviderTimeoutError("timeout")))

        with pytest.raises(ResearchAIError) as exc_info:
            await run_research("btc", container, _dummy_build_prompt, user_id=1)
        assert exc_info.value.reason == "timeout"

    @pytest.mark.asyncio
    async def test_ai_not_configured_raises_research_ai_error(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(error=ConfigurationError("no key")))

        with pytest.raises(ResearchAIError) as exc_info:
            await run_research("btc", container, _dummy_build_prompt, user_id=1)
        assert exc_info.value.reason == "not_configured"


class TestNoTelegramDependency:
    def test_module_has_no_telegram_import_statements(self) -> None:
        import phoenix_core.services.research.research_capability as module
        source = module.__file__
        with open(source, "r", encoding="utf-8") as f:
            lines = f.readlines()
        import_lines = [
            line for line in lines
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        telegram_imports = [line for line in import_lines if "telegram" in line.lower()]
        assert telegram_imports == [], f"Found Telegram import(s): {telegram_imports}"


class FakeSkillManager:
    """Minimal in-memory stand-in matching SkillManager's public get()/has()
    contract, used only to test the run_research <-> SkillManager wiring
    without needing real SKILL.md files on disk here (TASK-025)."""

    def __init__(self, skills=None):
        self._skills = skills or {}

    def get(self, name):
        if name not in self._skills:
            raise KeyError(f"Skill '{name}' not found")
        return self._skills[name]

    def has(self, name):
        return name in self._skills


class TestSkillIntegration:
    @pytest.mark.asyncio
    async def test_skill_is_used_when_available(self, tmp_path) -> None:
        """Test 1 (TASK-025): a real SkillManager, backed by a real
        temporary SKILL.md file, is registered in the container and its
        crypto-research skill reaches the research workflow."""
        from phoenix_core.skills.manager import SkillManager

        skill_dir = tmp_path / "crypto-research"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: crypto-research\n"
            "description: Test skill for integration testing\n"
            "---\n\n"
            "## Procedure\nDo the research thing.\n",
            encoding="utf-8",
        )
        skill_manager = SkillManager(directories=[str(tmp_path)])
        skill_manager.discover()
        assert skill_manager.has("crypto-research")

        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))
        container.register("skill_manager", skill_manager)

        received = {}

        def capturing_build_prompt(snapshot, signals, evidence, skill_instructions=None):
            received["skill_instructions"] = skill_instructions
            return "prompt"

        await run_research("btc", container, capturing_build_prompt, user_id=1)

        assert received["skill_instructions"] is not None
        assert "Do the research thing." in received["skill_instructions"]

    @pytest.mark.asyncio
    async def test_skill_instructions_are_not_lost(self, tmp_path) -> None:
        """Test 2 (TASK-025): a unique marker string in the SKILL.md body
        reaches the build_prompt callable unmodified."""
        from phoenix_core.skills.manager import SkillManager

        skill_dir = tmp_path / "crypto-research"
        skill_dir.mkdir(parents=True)
        marker = "TEST_SKILL_INSTRUCTION_MARKER"
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: crypto-research\n"
            "description: Marker test skill\n"
            "---\n\n"
            f"{marker}\n",
            encoding="utf-8",
        )
        skill_manager = SkillManager(directories=[str(tmp_path)])
        skill_manager.discover()

        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))
        container.register("skill_manager", skill_manager)

        received = {}

        def capturing_build_prompt(snapshot, signals, evidence, skill_instructions=None):
            received["skill_instructions"] = skill_instructions
            return "prompt"

        await run_research("btc", container, capturing_build_prompt, user_id=1)

        assert marker in received["skill_instructions"]

    @pytest.mark.asyncio
    async def test_missing_skill_manager_does_not_crash(self) -> None:
        """Test 3 (TASK-025): no skill_manager registered at all — research
        proceeds normally with skill_instructions=None, no traceback."""
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))
        # No skill_manager registered.

        received = {}

        def capturing_build_prompt(snapshot, signals, evidence, skill_instructions=None):
            received["skill_instructions"] = skill_instructions
            return "prompt"

        result = await run_research("btc", container, capturing_build_prompt, user_id=1)

        assert received["skill_instructions"] is None
        assert isinstance(result, ResearchResult)

    @pytest.mark.asyncio
    async def test_missing_crypto_research_skill_falls_back_cleanly(self) -> None:
        """Test 4 (TASK-025): a SkillManager is registered and has other
        skills, but not crypto-research — falls back to
        skill_instructions=None, no fabricated SkillDefinition, no crash."""
        other_skill = SimpleNamespace(name="other-skill", instructions="unrelated")
        skill_manager = FakeSkillManager(skills={"other-skill": other_skill})

        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))
        container.register("skill_manager", skill_manager)

        received = {}

        def capturing_build_prompt(snapshot, signals, evidence, skill_instructions=None):
            received["skill_instructions"] = skill_instructions
            return "prompt"

        result = await run_research("btc", container, capturing_build_prompt, user_id=1)

        assert received["skill_instructions"] is None
        assert isinstance(result, ResearchResult)
