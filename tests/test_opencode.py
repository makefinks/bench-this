import json
import os
import subprocess
import sys

import pytest

from agent_bench.harnesses import OpenCodeAdapter
from agent_bench.models import TreatmentConfig


def invoke(tmp_path, *, run_code=0, export_code=0, session_id="session-fixture", export=None,
           newline=True, extra_session_id=""):
    workspace = tmp_path / "workspace with spaces"
    workspace.mkdir()
    binary = tmp_path / "opencode"
    binary.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['CALLS'], 'a') as out:\n"
        "    out.write(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')\n"
        "if sys.argv[1] == 'run':\n"
        "    print(json.dumps({'type': 'text', 'sessionID': os.environ['SESSION_ID']}), end=os.environ['NEWLINE'])\n"
        "    if os.environ['EXTRA_SESSION_ID']:\n"
        "        print(json.dumps({'type': 'text', 'sessionID': os.environ['EXTRA_SESSION_ID']}))\n"
        "    raise SystemExit(int(os.environ['RUN_CODE']))\n"
        "print(os.environ['EXPORT'])\n"
        "raise SystemExit(int(os.environ['EXPORT_CODE']))\n"
    )
    binary.chmod(0o755)
    config = TreatmentConfig(
        root=tmp_path, id="fixture", harness="opencode", provider="openai", model="fixed",
        agent="build", harness_config=tmp_path, workspace_config=tmp_path,
        auth_profile="fixture", arguments=[],
    )
    adapter = OpenCodeAdapter(config)
    assistant = {
        "id": "assistant-1", "type": "assistant", "finish": "stop",
        "time": {"created": 1, "completed": 2},
        "model": {"providerID": "openai", "id": "fixed"},
        "tokens": {"input": 10, "output": 4}, "cost": 0,
    }
    session = export if export is not None else {
        "info": {"id": "session-fixture", "outcome": "succeeded", "tokens": {"input": 1000}},
        "messages": [{"type": "user", "text": "prompt"}, assistant],
    }
    calls = tmp_path / "calls.jsonl"
    environment = {
        **os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "CALLS": str(calls), "SESSION_ID": session_id,
        "RUN_CODE": str(run_code), "EXPORT_CODE": str(export_code),
        "EXPORT": session if isinstance(session, str) else json.dumps(session),
        "NEWLINE": "\n" if newline else "",
        "EXTRA_SESSION_ID": extra_session_id,
    }
    result = subprocess.run(
        adapter.command("a prompt with spaces", str(workspace)), env=environment,
        capture_output=True, text=True, timeout=10,
    )
    return adapter, result, [json.loads(line) for line in calls.read_text().splitlines()]


def test_private_run_exports_one_session_and_preserves_measurements(tmp_path):
    adapter, result, calls = invoke(tmp_path)

    assert result.returncode == 0, result.stderr
    assert calls[0]["args"][-1] == "a prompt with spaces"
    assert "--standalone" in calls[0]["args"]
    assert "--dir" not in calls[0]["args"]
    assert calls[1]["args"] == ["session", "export", "--standalone", "session-fixture"]
    assert {call["cwd"] for call in calls} == {str(tmp_path / "workspace with spaces")}
    assert '"type": "text"' in result.stdout
    assert '"type": "bench_opencode_message"' in result.stdout
    adapter.verify_preflight(result.stdout, result.stderr)
    adapter.verify_solver(result.stdout, result.stderr)
    usage = adapter.parse_usage(result.stdout, result.stderr)
    assert (usage.input_tokens, usage.output_tokens, usage.turns) == (10, 4, 1)


@pytest.mark.parametrize("values", [
    {"session_id": ""},
    {"extra_session_id": "different-session"},
    {"export_code": 7},
    {"export": "not json"},
    {"export": {"info": {"id": "wrong-session"}, "messages": []}},
    {"export": {"info": {"id": "session-fixture"}, "messages": []}},
])
def test_missing_or_invalid_export_fails_closed(tmp_path, values):
    _, result, _ = invoke(tmp_path, **values)

    assert result.returncode != 0
    assert '"type": "bench_opencode_end"' not in result.stdout


def test_failed_run_still_exports_partial_usage_without_hiding_exit_status(tmp_path):
    adapter, result, calls = invoke(tmp_path, run_code=9)

    assert result.returncode == 9
    assert len(calls) == 2
    assert adapter.parse_usage(result.stdout).input_tokens == 10


def test_client_output_without_final_newline_does_not_swallow_export_record(tmp_path):
    adapter, result, _ = invoke(tmp_path, newline=False)

    assert result.returncode == 0
    adapter.verify_solver(result.stdout)
    assert adapter.parse_usage(result.stdout).input_tokens == 10
