import stat

import pytest

from agent_bench.docker import DockerEngine
from agent_bench.errors import CommandTimeout


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
