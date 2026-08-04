"""Regression coverage for the reusable two-commit synthetic fixture."""

from agent_bench.config import discover_harnesses, discover_tasks, load_project
from scripts.create_synthetic_fixture import create_fixture


def test_generator_creates_valid_openai_fixture(tmp_path):
    """Ensure generated history and benchmark manifests agree on pinned identity."""

    repository = tmp_path / "fixture"
    metadata = create_fixture(repository, "fixture-image", "gpt-5.4-mini")
    project = load_project(repository / "benchmarks")
    task = discover_tasks(project)["normalize-email"]
    config = discover_harnesses(project)["opencode-openai-gpt-5-4-mini"]

    assert task.base_commit == metadata["base_commit"]
    assert task.reference_commit == metadata["reference_commit"]
    assert task.base_commit != task.reference_commit
    assert config.provider == "openai"
    assert config.model == "gpt-5.4-mini"
    opencode = (config.harness_config / "opencode.json").read_text(encoding="utf-8")
    assert '"small_model": "openai/gpt-5.4-mini"' in opencode

