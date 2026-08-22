import json
import os
import subprocess
import sys
from pathlib import Path

from agent_bench.scaffold import scaffold
from agent_bench.auth import (
    BEDROCK_CREDENTIALS_FILE,
    BEDROCK_TOKEN_ENVIRONMENT_VARIABLE,
)


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "bench-this"
    / "scripts"
    / "provision_auth.py"
)


def run_provision(
    repository: Path,
    home: Path,
    token: str | None,
    profile: str = "bedrock",
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    if token is not None:
        environment["AGENT_BENCH_BEDROCK_API_KEY"] = token
    else:
        environment.pop("AGENT_BENCH_BEDROCK_API_KEY", None)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(repository),
            "--harness",
            "opencode",
            "--provider",
            "amazon-bedrock",
            "--profile",
            profile,
        ],
        capture_output=True,
        text=True,
        env=environment,
    )

def run_pi_provision(
    repository: Path,
    home: Path,
    token: str | None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    if token is None:
        environment.pop("AGENT_BENCH_BEDROCK_API_KEY", None)
    else:
        environment["AGENT_BENCH_BEDROCK_API_KEY"] = token
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(repository),
            "--harness",
            "pi",
            "--provider",
            "amazon-bedrock",
            "--profile",
            "bedrock",
        ],
        capture_output=True,
        text=True,
        env=environment,
    )


def test_provisions_bedrock_profile_without_interactive_input(tmp_path: Path) -> None:
    repository = tmp_path / "project"
    repository.mkdir()
    scaffold(repository)
    home = tmp_path / "home"

    result = run_provision(repository, home, "fixture-token")

    assert result.returncode == 0, result.stderr
    credentials = json.loads(
        (
            home
            / ".agent-bench/auth"
            / "bedrock/opencode"
            / BEDROCK_CREDENTIALS_FILE
        ).read_text(encoding="utf-8")
    )
    assert credentials == {
        BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: "fixture-token"
    }
    assert "fixture-token" not in result.stdout
    assert "fixture-token" not in result.stderr


def test_uses_skill_runner_instead_of_target_repository_code(tmp_path: Path) -> None:
    repository = tmp_path / "project"
    repository.mkdir()
    scaffold(repository)
    target_auth = repository / "benchmarks/_vendor/agent_bench/auth.py"
    target_auth.write_text(
        "raise RuntimeError('target runner must not be imported')\n",
        encoding="utf-8",
    )

    result = run_provision(repository, tmp_path / "home", "fixture-token")

    assert result.returncode == 0, result.stderr
    assert (
        tmp_path
        / "home/.agent-bench/auth/bedrock/opencode"
        / BEDROCK_CREDENTIALS_FILE
    ).is_file()

def test_provisions_pi_bearer_profile_without_interactive_input(tmp_path: Path) -> None:
    repository = tmp_path / "pi-bearer-project"
    repository.mkdir()
    scaffold(repository)
    home = tmp_path / "pi-bearer-home"

    result = run_pi_provision(repository, home, "fixture-token")

    assert result.returncode == 0, result.stderr
    credentials = json.loads(
        (
            home
            / ".agent-bench/auth"
            / "bedrock/pi"
            / BEDROCK_CREDENTIALS_FILE
        ).read_text(encoding="utf-8")
    )
    assert credentials == {BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: "fixture-token"}
    assert "fixture-token" not in result.stdout
    assert "fixture-token" not in result.stderr


def test_rejects_missing_pi_bedrock_token_without_waiting(tmp_path: Path) -> None:
    repository = tmp_path / "pi-project"
    repository.mkdir()
    scaffold(repository)

    result = run_pi_provision(repository, tmp_path / "pi-home", None)

    assert result.returncode != 0
    assert "AGENT_BENCH_BEDROCK_API_KEY must be supplied" in result.stderr


def test_rejects_missing_bedrock_token_without_waiting(tmp_path: Path) -> None:
    repository = tmp_path / "project"
    repository.mkdir()
    scaffold(repository)

    result = run_provision(repository, tmp_path / "home", None)

    assert result.returncode != 0
    assert "AGENT_BENCH_BEDROCK_API_KEY must be supplied" in result.stderr


def test_rejects_unsafe_profile_before_writing_token(tmp_path: Path) -> None:
    repository = tmp_path / "project"
    repository.mkdir()
    scaffold(repository)

    result = run_provision(
        repository,
        tmp_path / "home",
        "fixture-token",
        "../../escape",
    )

    assert result.returncode != 0
    assert "profile must use lowercase letters" in result.stderr
    assert not (tmp_path / "escape").exists()
