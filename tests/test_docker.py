import os
import stat

import pytest

from agent_bench.docker import DockerEngine, Mount
from agent_bench.errors import CommandTimeout, InfrastructureError


def test_streamed_logs_survive_timeout_and_report_quota(tmp_path):
    """Partial provider output must remain available after forced container removal."""

    docker = tmp_path / "fake-docker"
    docker.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = rm ]; then exit 0; fi\n"
        "echo started\n"
        "echo 'usage limit reached' >&2\n"
        "sleep 2\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"

    with pytest.raises(CommandTimeout, match="quota or usage limit detected"):
        DockerEngine(str(docker)).run(
            "fixture",
            ["command"],
            [],
            {},
            timeout_seconds=1,
            stdout_path=stdout,
            stderr_path=stderr,
        )

    assert stdout.read_text(encoding="utf-8") == "started\n"
    assert stderr.read_text(encoding="utf-8") == "usage limit reached\n"


def test_image_check_reports_missing_docker_executable(tmp_path):
    with pytest.raises(InfrastructureError, match="Docker executable not found"):
        DockerEngine(str(tmp_path / "missing-docker")).image_exists("fixture")


@pytest.mark.parametrize(
    ("image_output", "expected"),
    [("", False), ("sha256:fixture\n", True)],
)
def test_image_check_uses_image_list_output(tmp_path, monkeypatch, image_output, expected):
    docker = tmp_path / "fake-docker"
    docker.write_text(
        "#!/bin/sh\n"
        "set -e\n"
        "test \"$1\" = image\n"
        "test \"$2\" = ls\n"
        "test \"$3\" = --quiet\n"
        "printf '%s' \"$IMAGE_OUTPUT\"\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("IMAGE_OUTPUT", image_output)

    assert DockerEngine(str(docker)).image_exists("fixture") is expected


def test_image_check_reports_docker_failure(tmp_path):
    docker = tmp_path / "fake-docker"
    docker.write_text(
        "#!/bin/sh\nprintf '%s\n' 'daemon unavailable' >&2\nexit 1\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)

    with pytest.raises(InfrastructureError, match="Docker image lookup failed") as raised:
        DockerEngine(str(docker)).image_exists("fixture")

    assert "daemon unavailable" in str(raised.value)


def test_interactive_login_uses_normal_container_hardening(tmp_path, monkeypatch):
    docker = tmp_path / "fake-docker"
    arguments = tmp_path / "arguments"
    docker.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$ARGUMENTS_FILE\"\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("ARGUMENTS_FILE", str(arguments))
    home = tmp_path / "home"
    home.mkdir()

    DockerEngine(str(docker)).run_interactive(
        "fixture-image",
        ["pi"],
        [Mount(home, "/home/bench")],
        {"HOME": "/home/bench"},
    )

    args = arguments.read_text(encoding="utf-8").splitlines()
    assert "--cap-drop=ALL" in args
    assert "--security-opt=no-new-privileges" in args
    assert "--pids-limit=512" in args
    assert args[args.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"
    assert args[args.index("--workdir") + 1] == "/home/bench"
    assert args[args.index("--network") + 1] == "bridge"
    assert "-it" in args
    assert args[-2:] == ["fixture-image", "pi"]


def test_secret_environment_value_is_not_placed_in_docker_arguments(tmp_path):
    """Forward provider secrets by name so process arguments cannot expose values."""

    docker = tmp_path / "fake-docker"
    docker.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in *fixture-secret*) exit 9;; esac\n"
        "test \"$AWS_BEARER_TOKEN_BEDROCK\" = fixture-secret\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)

    result = DockerEngine(str(docker)).run(
        "fixture",
        ["command"],
        [],
        {},
        timeout_seconds=5,
        secret_environment={"AWS_BEARER_TOKEN_BEDROCK": "fixture-secret"},
    )

    assert result.returncode == 0
