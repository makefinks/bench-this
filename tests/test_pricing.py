import io
import json
from pathlib import Path

import pytest

from agent_bench.models import (
    Defaults,
    TreatmentConfig,
    ImageConfig,
    ModelPrice,
    ProjectConfig,
    Usage,
)
from agent_bench.pricing import ModelsDevPricing
from agent_bench.runner import BenchmarkRunner


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def project(tmp_path: Path, prices=None) -> ProjectConfig:
    benchmark = tmp_path / "benchmarks"
    return ProjectConfig(
        root=tmp_path,
        benchmark_dir=benchmark,
        image=ImageConfig("fixture", benchmark / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
        prices=prices or {},
    )


def config(tmp_path: Path) -> TreatmentConfig:
    return TreatmentConfig(
        root=tmp_path,
        id="openai-model",
        harness="opencode",
        model="model",
        harness_config=tmp_path / "harness",
        workspace_config=tmp_path / "workspace",
        auth_profile="openai",
        arguments=[],
        provider="openai",
    )


def test_models_dev_price_maps_provider_rates_and_caches(monkeypatch):
    calls = []
    payload = {
        "openai": {
            "models": {
                "model": {
                    "cost": {"input": 1, "output": 4, "cache_read": 0.2}
                }
            }
        }
    }

    def urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return Response(json.dumps(payload).encode())

    monkeypatch.setattr("agent_bench.pricing.urllib.request.urlopen", urlopen)
    pricing = ModelsDevPricing(timeout_seconds=1.5)

    price = pricing.price("openai", "model")
    assert price == ModelPrice(1, 4, reasoning_per_million_usd=4, cache_read_per_million_usd=0.2)
    assert pricing.price("openai", "missing") is None
    assert calls == [("https://models.dev/api.json", 1.5)]


def test_models_dev_price_does_not_apply_provider_aliases(monkeypatch):
    payload = {
        "openai": {
            "models": {
                "model": {"cost": {"input": 1, "output": 4, "cache_read": 0.2}}
            }
        }
    }
    monkeypatch.setattr(
        "agent_bench.pricing.urllib.request.urlopen",
        lambda request, timeout: Response(json.dumps(payload).encode()),
    )

    assert ModelsDevPricing().price("openai-codex", "model") is None


@pytest.mark.parametrize(
    "payload",
    [b"not-json", b"[]", b'{"openai":{"models":{"model":{"cost":{"input":1}}}}}'],
)
def test_models_dev_price_tolerates_unusable_data(monkeypatch, payload):
    monkeypatch.setattr(
        "agent_bench.pricing.urllib.request.urlopen",
        lambda request, timeout: Response(payload),
    )

    assert ModelsDevPricing().price("openai", "model") is None


def test_models_dev_price_tolerates_network_failure(monkeypatch):
    def fail(request, timeout):
        raise OSError("offline")

    monkeypatch.setattr("agent_bench.pricing.urllib.request.urlopen", fail)

    assert ModelsDevPricing().price("openai", "model") is None


def test_estimate_prefers_benchmark_price(tmp_path):
    local = ModelPrice(2, 3, reasoning_per_million_usd=3)

    class UnexpectedPricing:
        def price(self, provider, model):
            raise AssertionError("benchmark price should bypass Models.dev")

    runner = BenchmarkRunner(project(tmp_path, {"model": local}), pricing=UnexpectedPricing())
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000, reasoning_tokens=1_000_000)

    assert runner._estimate(config(tmp_path), usage) == 8


def test_estimate_computes_alongside_native_cost(tmp_path):
    # Provider-reported cost must not suppress the list-price estimate:
    # both columns exist so divergence stays visible in summaries.
    local = ModelPrice(2, 3, reasoning_per_million_usd=3)

    class UnexpectedPricing:
        def price(self, provider, model):
            raise AssertionError("benchmark price should bypass Models.dev")

    runner = BenchmarkRunner(project(tmp_path, {"model": local}), pricing=UnexpectedPricing())
    usage = Usage(
        input_tokens=1_000_000,
        native_cost_usd=5,
    )

    assert usage.native_cost_usd is not None
    assert runner._estimate(config(tmp_path), usage) == 2


def test_estimate_falls_back_to_models_dev(tmp_path):
    class Pricing:
        def price(self, provider, model):
            assert (provider, model) == ("openai", "model")
            return ModelPrice(1, 2, 2, 0.1, 0.5)

    runner = BenchmarkRunner(project(tmp_path), pricing=Pricing())
    usage = Usage(
        input_tokens=1_000_000,
        output_tokens=2_000_000,
        reasoning_tokens=3_000_000,
        cache_read_tokens=4_000_000,
        cache_write_tokens=5_000_000,
    )

    assert runner._estimate(config(tmp_path), usage) == pytest.approx(13.9)


def test_openrouter_pricing_uses_catalog_identity_and_raw_model_id(tmp_path):
    class Pricing:
        def price(self, provider, model):
            assert (provider, model) == (
                "openrouter",
                "anthropic/claude-sonnet-4.6",
            )
            return ModelPrice(1, 2)

    openrouter = TreatmentConfig(
        **{
            **config(tmp_path).__dict__,
            "provider": "openrouter",
            "model": "anthropic/claude-sonnet-4.6",
        }
    )

    assert BenchmarkRunner(project(tmp_path), pricing=Pricing())._estimate(
        openrouter, Usage(input_tokens=1_000_000)
    ) == 1


def test_copilot_openrouter_pricing_uses_catalog_identity_and_plain_model_id(tmp_path):
    class Pricing:
        def price(self, provider, model):
            assert (provider, model) == (
                "openrouter",
                "anthropic/claude-sonnet-4.6",
            )
            return ModelPrice(1, 2)

    treatment = TreatmentConfig(
        root=tmp_path,
        id="copilot-openrouter",
        harness="copilot",
        provider="openrouter",
        model="anthropic/claude-sonnet-4.6",
        harness_config=tmp_path / "harness",
        workspace_config=tmp_path / "workspace",
        auth_profile="openrouter",
        arguments=[],
    )

    assert BenchmarkRunner(project(tmp_path), pricing=Pricing())._estimate(
        treatment, Usage(input_tokens=1_000_000)
    ) == 1


@pytest.mark.parametrize("harness", ["omp", "pi"])
def test_pi_family_openrouter_pricing_uses_catalog_identity(tmp_path, harness):
    class Pricing:
        def price(self, provider, model):
            assert (provider, model) == (
                "openrouter",
                "anthropic/claude-sonnet-4.6",
            )
            return ModelPrice(1, 2)

    treatment = TreatmentConfig(
        root=tmp_path,
        id=f"{harness}-openrouter",
        harness=harness,
        provider="openrouter",
        model="anthropic/claude-sonnet-4.6",
        harness_config=tmp_path / "harness",
        workspace_config=tmp_path / "workspace",
        auth_profile="openrouter",
        arguments=[],
    )

    assert BenchmarkRunner(project(tmp_path), pricing=Pricing())._estimate(
        treatment, Usage(input_tokens=1_000_000)
    ) == 1


def test_native_copilot_uses_github_copilot_estimate(tmp_path):
    class Pricing:
        def price(self, provider, model):
            assert (provider, model) == ("github-copilot", "model")
            return ModelPrice(1, 2, 2, 0.1, 0.5)

    copilot = TreatmentConfig(
        root=tmp_path,
        id="copilot-model",
        harness="copilot",
        model="model",
        harness_config=tmp_path / "harness",
        workspace_config=tmp_path / "workspace",
        auth_profile="copilot",
        arguments=[],
    )
    runner = BenchmarkRunner(project(tmp_path), pricing=Pricing())

    assert runner._estimate(copilot, Usage(input_tokens=1_000_000)) == 1


def test_pi_uses_selected_provider_estimate(tmp_path):
    class Pricing:
        def price(self, provider, model):
            assert (provider, model) == ("amazon-bedrock", "model")
            return ModelPrice(1, 2, 2, 0.1, 0.5)

    pi = TreatmentConfig(
        root=tmp_path,
        id="pi-model",
        harness="pi",
        provider="amazon-bedrock",
        model="model",
        harness_config=tmp_path / "harness",
        workspace_config=tmp_path / "workspace",
        auth_profile="bedrock",
        arguments=[],
    )
    runner = BenchmarkRunner(project(tmp_path), pricing=Pricing())

    assert runner._estimate(pi, Usage(input_tokens=1_000_000)) == 1


def test_codex_pricing_identity_comes_from_provider_catalog(tmp_path):
    class Pricing:
        def price(self, provider, model):
            assert (provider, model) == ("openai", "model")
            return ModelPrice(1, 2)

    codex = TreatmentConfig(
        root=tmp_path,
        id="pi-codex",
        harness="pi",
        provider="openai-codex",
        model="model",
        harness_config=tmp_path / "harness",
        workspace_config=tmp_path / "workspace",
        auth_profile="codex",
        arguments=[],
    )

    assert BenchmarkRunner(project(tmp_path), pricing=Pricing())._estimate(
        codex, Usage(input_tokens=1_000_000)
    ) == 1
