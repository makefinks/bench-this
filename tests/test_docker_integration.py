"""Opt-in tests for security properties that require a running Docker daemon."""

import os
from pathlib import Path

import pytest

from agent_bench.docker import DockerEngine, Mount


IMAGE = os.environ.get("AGENT_BENCH_TEST_IMAGE", "project-agent-benchmark-smoke")


@pytest.mark.skipif(
    os.environ.get("AGENT_BENCH_DOCKER_TESTS") != "1",
    reason="set AGENT_BENCH_DOCKER_TESTS=1 to exercise the local Docker daemon",
)
def test_hidden_tests_are_mounted_only_after_solver_exit(tmp_path: Path):
    """Prove the real solver mount cannot see files introduced for evaluation."""

    workspace = tmp_path / "workspace"
    evaluator = tmp_path / "evaluator"
    workspace.mkdir()
    evaluator.mkdir()
    (evaluator / "hidden-marker").write_text("private\n", encoding="utf-8")
    engine = DockerEngine()

    solver = engine.run(
        IMAGE,
        [
            "/bin/sh",
            "-lc",
            "test ! -e /evaluator/hidden-marker && printf solved > /workspace/answer.txt",
        ],
        [Mount(workspace, "/workspace")],
        {"HOME": "/tmp/solver-home"},
        30,
        network="none",
    )
    assert solver.returncode == 0, solver.stderr

    evaluator_run = engine.run(
        IMAGE,
        [
            "/bin/sh",
            "-lc",
            "test -f /evaluator/hidden-marker && test -f /workspace/answer.txt",
        ],
        [
            Mount(workspace, "/workspace"),
            Mount(evaluator, "/evaluator", readonly=True),
        ],
        {"HOME": "/tmp/evaluator-home"},
        30,
        network="none",
    )
    assert evaluator_run.returncode == 0, evaluator_run.stderr

