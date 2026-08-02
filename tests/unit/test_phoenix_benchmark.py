"""Unit tests for PhoenixBenchmark (Benchmark roadmap item)."""
import pytest

from phoenix_core.ai.base import AIResponse, BaseAIProvider
from phoenix_core.ai.benchmark import DEFAULT_PROMPTS, PhoenixBenchmark
from phoenix_core.ai.router import AIRouter

from .conftest import MockAIProvider

pytestmark = pytest.mark.asyncio


class FlakyProvider(BaseAIProvider):
    def __init__(self, fail_on_call=None, **kwargs):
        super().__init__(api_key="k", model="m", **kwargs)
        self.calls = 0
        self._fail_on_call = fail_on_call

    @property
    def name(self) -> str:
        return "flaky"

    @property
    def available_models(self):
        return ["m"]

    async def chat(self, messages, model=None, temperature=0.7, max_tokens=None, **kwargs):
        self.calls += 1
        if self._fail_on_call is not None and self.calls == self._fail_on_call:
            raise RuntimeError("flaky failure")
        return AIResponse(content="ok", provider=self.name, model=self.validate_model(model))

    async def stream_chat(self, messages, model=None, temperature=0.7, max_tokens=None, **kwargs):
        raise NotImplementedError

    async def health_check(self):
        return {"status": "configured"}


def make_router() -> AIRouter:
    return AIRouter(providers=[], default_provider="mock")


class TestPhoenixBenchmarkRun:
    async def test_single_provider_all_prompts_succeed(self) -> None:
        router = make_router()
        router.register_provider("mock", MockAIProvider(response_content="ok"))
        benchmark = PhoenixBenchmark(router, prompts=["p1", "p2"])

        results = await benchmark.run()

        assert set(results.keys()) == {"mock"}
        bench = results["mock"]
        assert bench.attempts == 2
        assert bench.successes == 2
        assert bench.success_rate == 1.0
        assert bench.average_latency_seconds >= 0
        assert bench.errors == []

    async def test_provider_failure_within_run_is_recorded(self) -> None:
        router = make_router()
        router.register_provider("flaky", FlakyProvider(fail_on_call=2))
        benchmark = PhoenixBenchmark(router, prompts=["p1", "p2", "p3"])

        results = await benchmark.run()

        bench = results["flaky"]
        assert bench.attempts == 3
        assert bench.successes == 2
        assert bench.errors == ["RuntimeError"]
        assert 0 < bench.success_rate < 1

    async def test_multiple_providers_benchmarked_independently(self) -> None:
        router = make_router()
        router.register_provider("good", MockAIProvider(response_content="ok"))
        router.register_provider("bad", MockAIProvider(should_fail=RuntimeError("down")))
        benchmark = PhoenixBenchmark(router, prompts=["p1"])

        results = await benchmark.run()

        assert results["good"].successes == 1
        assert results["bad"].successes == 0
        assert results["bad"].errors == ["RuntimeError"]

    async def test_no_providers_returns_empty_dict(self) -> None:
        router = make_router()
        benchmark = PhoenixBenchmark(router, prompts=["p1"])

        results = await benchmark.run()

        assert results == {}

    async def test_default_prompts_used_when_none_provided(self) -> None:
        router = make_router()
        provider = MockAIProvider(response_content="ok")
        router.register_provider("mock", provider)
        benchmark = PhoenixBenchmark(router)

        await benchmark.run()

        assert len(provider.calls) == len(DEFAULT_PROMPTS)
