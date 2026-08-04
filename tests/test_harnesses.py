import pytest

from agent_bench.errors import IdentityMismatch
from agent_bench.harnesses import CopilotAdapter, OpenCodeAdapter
from agent_bench.models import HarnessConfig


def config(tmp_path, harness="copilot"):
    return HarnessConfig(
        root=tmp_path,
        id=f"{harness}-fixture",
        harness=harness,
        model="gpt-fixed",
        provider="github-copilot" if harness == "opencode" else None,
        agent="build" if harness == "opencode" else None,
        harness_config=tmp_path / "harness",
        workspace_config=tmp_path / "workspace",
        auth_profile="work",
        arguments=[],
    )


def test_copilot_command_pins_model_and_disables_remote(tmp_path):
    command = CopilotAdapter(config(tmp_path)).command("fix it")
    assert command[command.index("--model") + 1] == "gpt-fixed"
    assert "--no-ask-user" in command
    assert "--no-remote" in command
    assert "--output-format=json" in command


def test_opencode_identity_requires_provider_and_model(tmp_path):
    adapter = OpenCodeAdapter(config(tmp_path, "opencode"))
    adapter.verify_identity('{"providerID":"github-copilot","modelID":"gpt-fixed"}')
    with pytest.raises(IdentityMismatch):
        adapter.verify_identity('{"providerID":"openai","modelID":"gpt-fixed"}')


def test_opencode_preflight_enables_identity_logs(tmp_path):
    command = OpenCodeAdapter(config(tmp_path, "opencode")).preflight_command()
    assert "--print-logs" in command
    assert command[command.index("--log-level") + 1] == "INFO"


def test_opencode_rejects_unpinned_auxiliary_model(tmp_path):
    adapter = OpenCodeAdapter(config(tmp_path, "opencode"))
    logs = """message=stream providerID=github-copilot modelID=title-model small=true
message=stream providerID=github-copilot modelID=gpt-fixed small=false
"""
    with pytest.raises(IdentityMismatch, match="title-model"):
        adapter.verify_identity(logs)


def test_model_mismatch_is_fail_closed(tmp_path):
    adapter = CopilotAdapter(config(tmp_path))
    with pytest.raises(IdentityMismatch):
        adapter.verify_identity('{"model":"fallback-model"}')


def test_opencode_openai_identity_is_accepted_when_pinned(tmp_path):
    value = config(tmp_path, "opencode")
    value = HarnessConfig(**{**value.__dict__, "provider": "openai"})
    OpenCodeAdapter(value).verify_identity(
        '{"providerID":"openai","modelID":"gpt-fixed"}'
    )
