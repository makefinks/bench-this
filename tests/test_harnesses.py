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
    assert "--output-format=json" in command


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
