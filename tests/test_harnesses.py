import json

import pytest

from agent_bench.errors import IdentityMismatch, InfrastructureError
from agent_bench.harnesses import (
    CopilotAdapter,
    OmpAdapter,
    OpenCodeAdapter,
    PiAdapter,
)
from agent_bench.models import TreatmentConfig


def config(tmp_path, harness="copilot"):
    return TreatmentConfig(
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
    assert "--no-remote-export" in command
    assert "--disable-builtin-mcps" in command
    assert "--output-format=json" in command


def test_copilot_auto_approves_tools_without_implicitly_trusting_workspace_hooks(tmp_path):
    environment = CopilotAdapter(config(tmp_path)).environment()

    assert environment["COPILOT_ALLOW_ALL"] == "1"


def test_copilot_bedrock_uses_mantle_responses_without_exposing_secret(tmp_path):
    value = TreatmentConfig(
        **{
            **config(tmp_path).__dict__,
            "provider": "amazon-bedrock",
            "model": "zai.glm-4.7-flash",
            "region": "eu-west-1",
        }
    )

    environment = CopilotAdapter(value).environment()

    assert environment["COPILOT_PROVIDER_BASE_URL"] == (
        "https://bedrock-mantle.eu-west-1.api.aws/v1"
    )
    assert environment["COPILOT_PROVIDER_TYPE"] == "openai"
    assert environment["COPILOT_PROVIDER_WIRE_API"] == "completions"
    assert environment["COPILOT_OFFLINE"] == "true"
    assert "COPILOT_PROVIDER_API_KEY" not in environment


def test_copilot_openrouter_uses_official_endpoint_without_exposing_secret(tmp_path):
    value = TreatmentConfig(
        **{
            **config(tmp_path).__dict__,
            "provider": "openrouter",
            "model": "anthropic/claude-sonnet-4.6",
        }
    )
    adapter = CopilotAdapter(value)

    command = adapter.command("fix it")
    assert command[command.index("--model") + 1] == "anthropic/claude-sonnet-4.6"

    environment = adapter.environment()

    assert environment["COPILOT_PROVIDER_BASE_URL"] == "https://openrouter.ai/api/v1"
    assert environment["COPILOT_PROVIDER_TYPE"] == "openai"
    assert environment["COPILOT_OFFLINE"] == "true"
    assert "COPILOT_PROVIDER_WIRE_API" not in environment
    assert "COPILOT_PROVIDER_API_KEY" not in environment


def test_opencode_identity_requires_provider_and_model(tmp_path):
    adapter = OpenCodeAdapter(config(tmp_path, "opencode"))
    adapter.verify_identity('{"providerID":"github-copilot","modelID":"gpt-fixed"}')
    with pytest.raises(IdentityMismatch):
        adapter.verify_identity('{"providerID":"openai","modelID":"gpt-fixed"}')


def test_opencode_v2_identity_verifies_nested_provider_and_model(tmp_path):
    adapter = OpenCodeAdapter(config(tmp_path, "opencode"))
    response = (
        '{"type":"assistant","model":{"providerID":"github-copilot",'
        '"id":"gpt-fixed"}}'
    )

    assert adapter.verify_identity(response) == ("github-copilot", "gpt-fixed")
    with pytest.raises(IdentityMismatch):
        adapter.verify_identity(response.replace("gpt-fixed", "fallback"))
    with pytest.raises(IdentityMismatch):
        adapter.verify_identity(response.replace("github-copilot", "openai"))


@pytest.mark.parametrize("method", ["verify_preflight", "verify_solver"])
def test_opencode_v2_rejects_structured_provider_failures(tmp_path, method):
    adapter = OpenCodeAdapter(config(tmp_path, "opencode"))
    response = (
        '{"message":{"type":"assistant","finish":"error",'
        '"error":{"type":"api","message":"provider unavailable"}}}'
    )

    with pytest.raises(InfrastructureError, match="provider unavailable"):
        getattr(adapter, method)(response)


def test_opencode_v2_tool_failures_do_not_fail_the_entire_solver(tmp_path):
    adapter = OpenCodeAdapter(config(tmp_path, "opencode"))

    adapter.verify_solver(
        '{"type":"bench_opencode_message","message":{"type":"assistant",'
        '"model":{"providerID":"github-copilot","id":"gpt-fixed"},'
        '"content":[{"type":"tool",'
        '"state":{"status":"error","error":{"type":"error",'
        '"message":"command failed"}}}]}}\n'
        '{"type":"bench_opencode_end","outcome":"succeeded"}'
    )


def test_opencode_solver_checks_exported_identity_not_tool_metadata(tmp_path):
    adapter = OpenCodeAdapter(config(tmp_path, "opencode"))
    message = {
        "type": "assistant", "model": {"providerID": "github-copilot", "id": "gpt-fixed"},
        "content": [{"metadata": {"model": "unrelated-tool-model"}}],
    }
    record = json.dumps({"type": "bench_opencode_message", "message": message})
    ending = json.dumps({"type": "bench_opencode_end", "outcome": "succeeded"})

    adapter.verify_solver(record + "\n" + ending)
    with pytest.raises(IdentityMismatch):
        adapter.verify_solver(record.replace("gpt-fixed", "fallback") + "\n" + ending)
    with pytest.raises(InfrastructureError):
        adapter.verify_solver(record + "\n" + ending.replace("succeeded", "interrupted"))
    with pytest.raises(InfrastructureError):
        adapter.verify_solver('{"type":"text","sessionID":"session-only"}')


def test_opencode_uses_a_private_server_and_disposable_state(tmp_path):
    adapter = OpenCodeAdapter(config(tmp_path, "opencode"))

    command = adapter.command("fix it", "/fixture-workspace")
    assert command[:2] == ["python3", "-c"]
    assert command[3] == "/fixture-workspace"
    assert "--standalone" in command
    assert "--auto" in command
    assert "--dir" not in command
    assert "--standalone" in adapter.preflight_command()
    assert adapter.environment()["XDG_STATE_HOME"] == "/home/bench/.local/state"


def test_opencode_openrouter_command_and_identity_use_pinned_provider_model(tmp_path):
    value = TreatmentConfig(
        **{
            **config(tmp_path, "opencode").__dict__,
            "provider": "openrouter",
            "model": "anthropic/claude-sonnet-4.6",
        }
    )
    adapter = OpenCodeAdapter(value)

    command = adapter.command("fix it")
    assert command[command.index("--model") + 1] == (
        "openrouter/anthropic/claude-sonnet-4.6"
    )
    adapter.verify_identity(
        '{"providerID":"openrouter","modelID":"anthropic/claude-sonnet-4.6"}'
    )
    with pytest.raises(IdentityMismatch):
        adapter.verify_identity(
            '{"providerID":"openrouter","modelID":"anthropic/claude-sonnet-4"}'
        )


def test_opencode_variant_reference_does_not_duplicate_model_flag(tmp_path):
    value = config(tmp_path, "opencode")
    value = TreatmentConfig(**{
        **value.__dict__, "arguments": ["--model=github-copilot/gpt-fixed#high"],
    })
    adapter = OpenCodeAdapter(value)

    command = adapter.command("fix it")

    assert "--model" not in command
    assert "--model=github-copilot/gpt-fixed#high" in command
    adapter.verify_identity('{"model":{"providerID":"github-copilot","id":"gpt-fixed","variant":"high"}}')
    with pytest.raises(IdentityMismatch):
        adapter.verify_identity('{"model":{"providerID":"github-copilot","id":"fallback","variant":"high"}}')


@pytest.mark.parametrize("harness,adapter_class", [("omp", OmpAdapter), ("pi", PiAdapter)])
def test_pi_family_openrouter_command_and_identity_use_pinned_provider_model(
    tmp_path, harness, adapter_class
):
    value = TreatmentConfig(
        **{
            **config(tmp_path, harness).__dict__,
            "provider": "openrouter",
            "model": "anthropic/claude-sonnet-4.6",
        }
    )
    adapter = adapter_class(value)

    command = adapter.command("fix it")
    assert command[command.index("--model") + 1] == (
        "openrouter/anthropic/claude-sonnet-4.6"
    )
    adapter.verify_identity(
        '{"type":"message_end","message":{"role":"assistant",'
        '"provider":"openrouter","model":"anthropic/claude-sonnet-4.6"}}'
    )
    with pytest.raises(IdentityMismatch):
        adapter.verify_identity(
            '{"type":"message_end","message":{"role":"assistant",'
            '"provider":"openrouter","model":"anthropic/claude-sonnet-4"}}'
        )


def test_opencode_preflight_uses_structured_identity_without_log_flags(tmp_path):
    command = OpenCodeAdapter(config(tmp_path, "opencode")).preflight_command()
    assert "--format=json" in command
    assert "--print-logs" not in command
    assert "--log-level" not in command


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
    value = TreatmentConfig(**{**value.__dict__, "provider": "openai"})
    OpenCodeAdapter(value).verify_identity(
        '{"providerID":"openai","modelID":"gpt-fixed"}'
    )


def test_omp_command_is_single_shot_and_provider_qualified(tmp_path):
    value = config(tmp_path, "omp")
    value = TreatmentConfig(**{**value.__dict__, "provider": "openai-codex"})
    command = OmpAdapter(value).command("fix it")
    assert command[:4] == ["omp", "--print", "--mode", "json"]
    assert "--no-session" in command
    assert command[command.index("--model") + 1] == "openai-codex/gpt-fixed"


def test_omp_identity_requires_provider_and_model(tmp_path):
    value = config(tmp_path, "omp")
    value = TreatmentConfig(**{**value.__dict__, "provider": "openai-codex"})
    adapter = OmpAdapter(value)
    adapter.verify_identity(
        '{"type":"message_end","message":{"role":"assistant","provider":"openai-codex","model":"gpt-fixed"}}'
    )

    with pytest.raises(IdentityMismatch):
        adapter.verify_identity(
            '{"type":"message_end","message":{"role":"assistant","provider":"github-copilot","model":"gpt-fixed"}}'
        )


def test_omp_environment_isolated_and_supports_bedrock_region(tmp_path):
    value = config(tmp_path, "omp")
    value = TreatmentConfig(**{**value.__dict__, "provider": "amazon-bedrock", "region": "eu-west-1"})
    environment = OmpAdapter(value).environment()
    assert environment["PI_CONFIG_DIR"] == ".omp"
    assert environment["PI_CODING_AGENT_DIR"] == "/home/bench/.omp/agent"
    assert environment["AWS_REGION"] == "eu-west-1"

def test_pi_command_and_environment_are_isolated(tmp_path):
    value = config(tmp_path, "pi")
    value = TreatmentConfig(**{**value.__dict__, "provider": "openai-codex"})
    adapter = PiAdapter(value)

    command = adapter.command("fix it")
    assert command[:4] == ["pi", "--print", "--mode", "json"]
    assert "--no-session" in command
    assert "--approve" in command
    assert command[command.index("--model") + 1] == "openai-codex/gpt-fixed"

    environment = adapter.environment()
    assert environment["PI_CODING_AGENT_DIR"] == "/home/bench/.pi/agent"
    assert environment["PI_OFFLINE"] == "1"
    assert environment["PI_TELEMETRY"] == "0"
    assert "AWS_PROFILE" not in environment


def test_pi_bedrock_uses_default_aws_profile_and_pinned_region(tmp_path):
    value = config(tmp_path, "pi")
    value = TreatmentConfig(
        **{
            **value.__dict__,
            "provider": "amazon-bedrock",
            "region": "eu-west-1",
        }
    )

    environment = PiAdapter(value).environment()

    assert "AWS_PROFILE" not in environment
    assert environment["AWS_REGION"] == "eu-west-1"


def test_pi_preflight_requires_matching_identity_and_exact_response(tmp_path):
    value = config(tmp_path, "pi")
    value = TreatmentConfig(**{**value.__dict__, "provider": "openai-codex"})
    adapter = PiAdapter(value)
    successful = """{"type":"message_end","message":{"role":"assistant","provider":"openai-codex","model":"gpt-fixed","content":[{"type":"text","text":"BENCH_PREFLIGHT_OK"}],"stopReason":"stop"}}
"""

    adapter.verify_preflight(successful)
    with pytest.raises(IdentityMismatch):
        adapter.verify_preflight(successful.replace("openai-codex", "amazon-bedrock"))


def test_omp_preflight_requires_successful_exact_response(tmp_path):
    value = config(tmp_path, "omp")
    value = TreatmentConfig(**{**value.__dict__, "provider": "amazon-bedrock"})
    adapter = OmpAdapter(value)
    successful = """{"type":"message_end","message":{"role":"assistant","provider":"amazon-bedrock","model":"gpt-fixed","content":[{"type":"text","text":"\\nBENCH_PREFLIGHT_OK"}],"stopReason":"stop"}}
"""
    adapter.verify_preflight(successful)

    with pytest.raises(InfrastructureError, match="did not return exactly"):
        adapter.verify_preflight(successful.replace("BENCH_PREFLIGHT_OK", "not ready"))


def test_omp_rejects_embedded_provider_error_but_not_tool_error(tmp_path):
    value = config(tmp_path, "omp")
    value = TreatmentConfig(**{**value.__dict__, "provider": "amazon-bedrock"})
    adapter = OmpAdapter(value)
    adapter.verify_solver(
        '{"type":"tool_execution_end","isError":true,"result":{"details":{"response":{"model":"image-inspection-model"}}}}\n'
        '{"type":"message_end","message":{"role":"assistant","provider":"amazon-bedrock","model":"gpt-fixed","content":[],"stopReason":"stop"}}\n'
    )

    transcript = """{"type":"message_end","message":{"role":"assistant","provider":"amazon-bedrock","model":"gpt-fixed","content":[],"stopReason":"error","errorMessage":"Bedrock HTTP 404"}}
"""
    with pytest.raises(InfrastructureError, match="Bedrock HTTP 404"):
        adapter.verify_solver(transcript)

    terminal_only = """{"type":"agent_end","messages":[{"role":"assistant","stopReason":"error","errorMessage":"nested provider failure"}]}
"""
    with pytest.raises(InfrastructureError, match="nested provider failure"):
        adapter.verify_solver(terminal_only)


def test_omp_rejects_terminal_deadline_abort_despite_zero_exit(tmp_path):
    # oh-my-pi#7635: JSON-mode deadline aborts exit 0 and only the terminal
    # assistant message carries stopReason "aborted".
    value = config(tmp_path, "omp")
    value = TreatmentConfig(**{**value.__dict__, "provider": "amazon-bedrock"})
    adapter = OmpAdapter(value)
    transcript = (
        '{"type":"message_end","message":{"role":"assistant","provider":"amazon-bedrock",'
        '"model":"gpt-fixed","content":[],"stopReason":"stop"}}\n'
        '{"type":"agent_end","messages":[{"role":"assistant","provider":"amazon-bedrock",'
        '"model":"gpt-fixed","content":[],"stopReason":"aborted","errorMessage":"Deadline exceeded"}]}\n'
    )
    with pytest.raises(InfrastructureError, match="Deadline exceeded"):
        adapter.verify_solver(transcript)


def test_omp_ignores_midstream_abort_after_recovery(tmp_path):
    value = config(tmp_path, "omp")
    value = TreatmentConfig(**{**value.__dict__, "provider": "amazon-bedrock"})
    adapter = OmpAdapter(value)
    recovered = (
        '{"type":"message_end","message":{"role":"assistant","provider":"amazon-bedrock",'
        '"model":"gpt-fixed","content":[],"stopReason":"aborted"}}\n'
        '{"type":"message_end","message":{"role":"assistant","provider":"amazon-bedrock",'
        '"model":"gpt-fixed","content":[],"stopReason":"stop"}}\n'
    )
    adapter.verify_solver(recovered)


def test_omp_catches_truncated_stream_terminal_abort(tmp_path):
    # Truncated streams (oh-my-pi#7635 class) end at turn_end with no agent_end;
    # the turn-boundary message is then the terminal state.
    value = config(tmp_path, "omp")
    value = TreatmentConfig(**{**value.__dict__, "provider": "amazon-bedrock"})
    adapter = OmpAdapter(value)
    truncated = (
        '{"type":"message_end","message":{"role":"assistant","provider":"amazon-bedrock",'
        '"model":"gpt-fixed","content":[],"stopReason":"stop"}}\n'
        '{"type":"turn_end","message":{"role":"assistant","provider":"amazon-bedrock",'
        '"model":"gpt-fixed","content":[],"stopReason":"aborted","errorMessage":"Deadline exceeded"},'
        '"toolResults":[]}\n'
    )
    with pytest.raises(InfrastructureError, match="Deadline exceeded"):
        adapter.verify_solver(truncated)
