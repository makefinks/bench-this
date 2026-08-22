import json

import pytest

from agent_bench.catalog import HARNESS_CATALOG, WriterKind
from agent_bench.errors import ConfigurationError
from agent_bench.models import TreatmentConfig
from agent_bench.writers import (
    WRITER_REGISTRY,
    write_native_configuration,
    writer_for,
)


def configuration(tmp_path, harness="opencode", provider="openai", **values):
    root = tmp_path / "configuration"
    harness_config = root / "harness"
    harness_config.mkdir(parents=True)
    workspace_config = root / "workspace"
    workspace_config.mkdir()
    return TreatmentConfig(
        root=root,
        id="configuration",
        harness=harness,
        provider=provider,
        model="model-fixed",
        agent="build" if harness == "opencode" else None,
        harness_config=harness_config,
        workspace_config=workspace_config,
        auth_profile="work",
        arguments=[],
        **values,
    )


def test_writer_registry_is_complete_and_selected_by_catalog():
    selected = {harness.writer for harness in HARNESS_CATALOG.values()}
    assert set(WRITER_REGISTRY) == set(WriterKind) == selected


def test_opencode_writer_sets_provider_model_and_skill_permission(tmp_path):
    config = configuration(tmp_path)

    write_native_configuration(config, ["skill-one"])

    native = json.loads((config.harness_config / "opencode.json").read_text())
    assert native == {
        "$schema": "https://opencode.ai/config.json",
        "enabled_providers": ["openai"],
        "small_model": "openai/model-fixed",
        "share": "disabled",
        "permission": {"skill": {"*": "allow"}},
    }


def test_opencode_writer_sets_bedrock_region(tmp_path):
    config = configuration(
        tmp_path,
        provider="amazon-bedrock",
        region="us-east-1",
    )

    write_native_configuration(config)

    native = json.loads((config.harness_config / "opencode.json").read_text())
    assert native["provider"] == {
        "amazon-bedrock": {"options": {"region": "us-east-1"}}
    }


def test_opencode_writer_sets_fixed_copilot_business_endpoint(tmp_path):
    config = configuration(
        tmp_path,
        provider="github-copilot",
        github_copilot_business=True,
    )

    write_native_configuration(config)

    native = json.loads((config.harness_config / "opencode.json").read_text())
    assert native["provider"] == {
        "github-copilot": {
            "options": {"baseURL": "https://api.business.githubcopilot.com"}
        }
    }


@pytest.mark.parametrize(
    ("harness", "provider"),
    [("copilot", None), ("omp", "openai-codex"), ("pi", "openai-codex")],
)
def test_noop_writers_create_no_native_files(tmp_path, harness, provider):
    config = configuration(tmp_path, harness=harness, provider=provider)

    write_native_configuration(config)

    assert list(config.harness_config.iterdir()) == []


def test_missing_writer_registration_fails_closed(tmp_path, monkeypatch):
    config = configuration(tmp_path)
    monkeypatch.setattr("agent_bench.writers.WRITER_REGISTRY", {})

    with pytest.raises(ConfigurationError, match="unregistered native configuration writer"):
        writer_for(config)
