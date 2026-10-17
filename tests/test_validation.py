import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from agent_bench.config import load_project
from agent_bench.errors import CommandTimeout
from agent_bench.models import CommandResult, Defaults, ImageConfig, ProjectConfig, TaskConfig
from agent_bench.runner import BenchmarkRunner


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


class FakeDocker:
    def __init__(
        self,
        outcomes=(1, 1, 0, 0),
        setup_timeout=False,
        evaluator_error=False,
        evaluator_output="",
        required_setup_session=None,
    ):
        self.outcomes = iter(outcomes)
        self.setup_timeout = setup_timeout
        self.evaluator_error = evaluator_error
        self.evaluator_output = evaluator_output
        self.required_setup_session = required_setup_session
        self.calls = []
        self.environments = []
        self.secret_environments = []
        self.setup_sources = []

    def image_id(self, image):
        return "sha256:" + "a" * 64

    def run(self, image, command, mounts, environment, timeout_seconds, network=None,
            workdir="/workspace", stdout_path=None, stderr_path=None, stream_output=False,
            secret_environment=None):
        self.calls.append((network, timeout_seconds, list(mounts), stream_output))
        self.environments.append(environment)
        self.secret_environments.append(secret_environment or {})
        if network == "bridge":
            workspace = next(mount.source for mount in mounts if mount.target == "/workspace")
            self.setup_sources.append((workspace / "source.txt").read_text())
            if self.setup_timeout:
                self.setup_timeout = False
                raise CommandTimeout("setup timed out")
            if self.required_setup_session and (
                not secret_environment
                or secret_environment.get("REGISTRY_SESSION") != self.required_setup_session
            ):
                return CommandResult(1, "", "registry authentication rejected", 0.1)
            return CommandResult(0, "", "", 0.1)
        outcome = 2 if self.evaluator_error else next(self.outcomes)
        targets = {mount.target for mount in mounts}
        group = "public-basic" if "/public-tests" in targets else "hidden-edge"
        passed = "true" if outcome == 0 else "false"
        output = self.evaluator_output + (
            'AGENT_BENCH_RESULT: {"version":1,"groups":'
            f'{{"{group}":{passed}}}}}\n'
        )
        return CommandResult(outcome, output, "", 0.1)


def fixture(tmp_path, docker):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "fixture@example.com")
    git(repo, "config", "user.name", "Fixture")
    (repo / "source.txt").write_text("base\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "source.txt").write_text("reference\n")
    git(repo, "commit", "-qam", "reference")
    reference = git(repo, "rev-parse", "HEAD")
    benchmark = repo / "benchmarks"
    task_root = benchmark / "tasks/demo"
    hidden = task_root / "hidden-tests"
    hidden.mkdir(parents=True)
    (hidden / "run.sh").write_text("#!/bin/sh\n")
    public_tests = task_root / "public-tests"
    public_tests.mkdir()
    (public_tests / "run.sh").write_text("#!/bin/sh\n")
    (task_root / "prompt.md").write_text("Change behavior.\n")
    (task_root / "public").mkdir()
    (benchmark / "setup.sh").write_text("#!/bin/sh\n")
    project = ProjectConfig(
        repo, benchmark, ImageConfig("fixture", benchmark / "Dockerfile"), "setup",
        Defaults(10, 5, 1, 19),
    )
    task = TaskConfig(
        task_root,
        "demo",
        base,
        reference,
        task_root / "prompt.md",
        task_root / "public",
        hidden,
        "/bin/sh /evaluator/run.sh",
        10,
        public_tests,
        "/bin/sh /public-tests/run.sh /workspace",
        ["public-basic"],
        ["hidden-edge"],
    )
    return BenchmarkRunner(project, docker=docker), task


def test_validation_receipt_schema_and_phase_contract(tmp_path):
    docker = FakeDocker()
    runner, task = fixture(tmp_path, docker)
    progress = []
    receipt = runner.validate_task(task, progress=progress.append)
    assert receipt.status == "validated"
    assert receipt.base.setup == receipt.reference.setup == "passed"
    assert (receipt.base.evaluator_exit, receipt.reference.evaluator_exit) == (1, 0)
    assert [call[0] for call in docker.calls] == [
        "bridge",
        "none",
        "none",
        "bridge",
        "none",
        "none",
    ]
    assert [call[1] for call in docker.calls] == [19, 5, 5, 19, 5, 5]
    latest = json.loads((runner.project.benchmark_dir / "results/validation/demo/latest.json").read_text())
    assert latest["version"] == 1 and latest["image"]["id"].startswith("sha256:")
    assert not any("hidden-tests" in value for value in latest["base"]["logs"].values())
    expected_phases = {"workspace", "setup", "public_evaluator", "hidden_evaluator"}
    assert set(latest["base"]["phase_durations"]) == expected_phases
    assert set(latest["reference"]["phase_durations"]) == expected_phases
    assert all(value >= 0 for value in latest["base"]["phase_durations"].values())
    assert progress == [
        "[start] demo",
        "[base setup] demo",
        "[base public evaluator] demo",
        "[base hidden evaluator] demo",
        "[reference setup] demo",
        "[reference public evaluator] demo",
        "[reference hidden evaluator] demo",
    ]


def test_validation_requires_public_and_hidden_base_reference_pairs(tmp_path):
    class PublicValidationDocker(FakeDocker):
        def __init__(self):
            super().__init__((1, 1, 0, 0))

        def run(
            self,
            image,
            command,
            mounts,
            environment,
            timeout_seconds,
            network=None,
            workdir="/workspace",
            stdout_path=None,
            stderr_path=None,
            stream_output=False,
            secret_environment=None,
        ):
            mounts = list(mounts)
            self.calls.append((network, timeout_seconds, mounts, stream_output))
            if network == "bridge":
                return CommandResult(0, "", "", 0.1)
            targets = {mount.target for mount in mounts}
            outcome = next(self.outcomes)
            group = "public-basic" if "/public-tests" in targets else "hidden-edge"
            passed = "true" if outcome == 0 else "false"
            output = (
                'AGENT_BENCH_RESULT: {"version":1,"groups":'
                f'{{"{group}":{passed}}}}}\n'
            )
            return CommandResult(outcome, output, "", 0.1)

    docker = PublicValidationDocker()
    runner, task = fixture(tmp_path, docker)
    task = replace(
        task,
        requirement_groups=["hidden-edge"],
        public_test_groups=["public-basic"],
    )
    progress = []

    receipt = runner.validate_task(task, progress=progress.append)

    assert receipt.status == "validated"
    assert (receipt.base.public_evaluator_exit, receipt.reference.public_evaluator_exit) == (1, 0)
    assert (receipt.base.evaluator_exit, receipt.reference.evaluator_exit) == (1, 0)
    assert [call[0] for call in docker.calls] == [
        "bridge",
        "none",
        "none",
        "bridge",
        "none",
        "none",
    ]
    assert progress == [
        "[start] demo",
        "[base setup] demo",
        "[base public evaluator] demo",
        "[base hidden evaluator] demo",
        "[reference setup] demo",
        "[reference public evaluator] demo",
        "[reference hidden evaluator] demo",
    ]


def test_wrong_evaluator_pair_is_invalid_and_attempts_are_unique(tmp_path):
    runner, task = fixture(tmp_path, FakeDocker((0, 0, 0, 0)))
    first = runner.validate_task(task)
    runner.docker = FakeDocker((0, 0, 0, 0))
    second = runner.validate_task(task)
    assert first.status == second.status == "invalid"
    assert first.attempt_id != second.attempt_id


def test_setup_timeout_writes_infrastructure_receipt(tmp_path):
    runner, task = fixture(tmp_path, FakeDocker(setup_timeout=True))
    receipt = runner.validate_task(task)
    assert receipt.status == "infrastructure_error"
    assert receipt.error_category == "timeout"
    assert receipt.base.setup == "timed_out"
    assert set(receipt.base.phase_durations) == {"workspace", "setup"}
    assert receipt.reference.evaluator_exit is None


def test_missing_setup_environment_stops_validation_before_setup(tmp_path, monkeypatch):
    docker = FakeDocker()
    runner, task = fixture(tmp_path, docker)
    runner.project = replace(
        runner.project,
        setup_environment=["REGISTRY_SESSION", "REGISTRY_REGION", "PACKAGE_INDEX_URL"],
    )
    monkeypatch.setenv("REGISTRY_SESSION", "synthetic-present-secret")
    monkeypatch.delenv("REGISTRY_REGION", raising=False)
    monkeypatch.delenv("PACKAGE_INDEX_URL", raising=False)

    receipt = runner.validate_task(task)

    assert receipt.status == "infrastructure_error"
    assert receipt.base.setup == "failed"
    assert receipt.base.evaluator_exit is receipt.reference.evaluator_exit is None
    assert docker.calls == []
    attempt = runner.project.benchmark_dir / receipt.receipt_path
    diagnostic = (attempt.parent / receipt.base.logs["setup_stderr"]).read_text()
    assert "REGISTRY_REGION" in diagnostic and "PACKAGE_INDEX_URL" in diagnostic
    assert "synthetic-present-secret" not in diagnostic


def test_bulk_validation_forwards_setup_environment_at_both_commits(tmp_path, monkeypatch):
    docker = FakeDocker()
    runner, task = fixture(tmp_path, docker)
    runner.project = replace(
        runner.project, setup_environment=["REGISTRY_SESSION", "REGISTRY_OPTION"]
    )
    monkeypatch.setenv("REGISTRY_SESSION", "synthetic-validation-session")
    monkeypatch.setenv("REGISTRY_OPTION", "")
    monkeypatch.setenv("UNRELATED_HOST_SECRET", "not-for-validation")
    (task.root / "task.yaml").write_text(yaml.safe_dump({
        "version": 1,
        "id": task.id,
        "base_commit": task.base_commit,
        "reference_commit": task.reference_commit,
        "prompt": "prompt.md",
        "public_tests_directory": "public-tests",
        "public_test_command": task.public_test_command,
        "public_test_groups": task.public_test_groups,
        "hidden_tests_directory": "hidden-tests",
        "test_command": task.test_command,
        "requirement_groups": task.requirement_groups,
    }))

    receipt, = runner.validate_tasks()

    assert receipt.status == "validated"
    assert docker.setup_sources == ["base\n", "reference\n"]
    selected = {"REGISTRY_SESSION": "synthetic-validation-session", "REGISTRY_OPTION": ""}
    assert docker.secret_environments == [selected, {}, {}, selected, {}, {}]
    assert docker.environments == [
        {"HOME": "/tmp/benchmark-home"},
        {"HOME": "/tmp/evaluator-home"},
        {"HOME": "/tmp/evaluator-home"},
        {"HOME": "/tmp/benchmark-home"},
        {"HOME": "/tmp/evaluator-home"},
        {"HOME": "/tmp/evaluator-home"},
    ]


def test_setup_authentication_failure_is_retryable_with_refreshed_host_environment(
    tmp_path, monkeypatch
):
    docker = FakeDocker(required_setup_session="synthetic-fresh-session")
    runner, task = fixture(tmp_path, docker)
    manifest = runner.project.benchmark_dir / "benchmark.yaml"
    manifest.write_text(yaml.safe_dump({
        "version": 1,
        "image": {"name": "fixture", "dockerfile": "benchmarks/Dockerfile"},
        "setup_command": "setup",
        "setup_environment": ["REGISTRY_SESSION"],
    }))
    (runner.project.benchmark_dir / "Dockerfile").write_text("FROM scratch\n")
    runner.project = load_project(manifest.parent)
    original_manifest = manifest.read_bytes()
    monkeypatch.setenv("REGISTRY_SESSION", "synthetic-expired-session")

    failed = runner.validate_task(task)

    assert failed.status == "infrastructure_error"
    assert failed.base.setup == "failed"
    assert failed.base.evaluator_exit is failed.reference.evaluator_exit is None
    latest_path = manifest.parent / "results/validation/demo/latest.json"
    assert json.loads(latest_path.read_text())["status"] == "infrastructure_error"
    monkeypatch.setenv("REGISTRY_SESSION", "synthetic-fresh-session")
    retry_runner = BenchmarkRunner(load_project(manifest.parent), docker=docker)

    refreshed = retry_runner.validate_task(task)

    assert refreshed.status == "validated"
    assert refreshed.attempt_id != failed.attempt_id
    assert refreshed.environment_digest == failed.environment_digest
    assert docker.setup_sources == ["base\n", "base\n", "reference\n"]
    assert [values["REGISTRY_SESSION"] for values in docker.secret_environments if values] == [
        "synthetic-expired-session", "synthetic-fresh-session", "synthetic-fresh-session"
    ]
    assert manifest.read_bytes() == original_manifest
    assert json.loads(latest_path.read_text())["status"] == "validated"


def test_validation_environment_identity_tracks_names_but_not_host_values(tmp_path, monkeypatch):
    runner, task = fixture(tmp_path, FakeDocker())
    original = runner.validate_task(task)
    runner.project = replace(runner.project, setup_environment=["REGISTRY_SESSION"])
    monkeypatch.setenv("REGISTRY_SESSION", "synthetic-session-one")
    runner.docker = FakeDocker()

    configured = runner.validate_task(task)

    assert original.status == configured.status == "validated"
    assert original.environment_digest != configured.environment_digest
    monkeypatch.setenv("REGISTRY_SESSION", "synthetic-session-two")
    runner.docker = FakeDocker()
    refreshed = runner.validate_task(task)
    assert refreshed.environment_digest == configured.environment_digest


def test_evaluator_infrastructure_exit_never_validates(tmp_path):
    runner, task = fixture(tmp_path, FakeDocker(evaluator_error=True))
    receipt = runner.validate_task(task)
    assert receipt.status == "infrastructure_error"
    assert receipt.reference.evaluator_exit is None


@pytest.mark.parametrize(
    "output",
    [
        "error: Cannot find module 'src/new-api'\n0 pass\n1 error\n",
        "error: Could not resolve './fixture'\n",
        "SyntaxError: unexpected token\n",
        "bash: missing-tool: command not found\n",
        "# Unhandled error between tests\n",
        "Ran 0 tests across 0 files.\n",
    ],
)
def test_validation_rejects_high_confidence_infrastructure_output(tmp_path, output):
    runner, task = fixture(tmp_path, FakeDocker(evaluator_output=output))

    receipt = runner.validate_task(task)

    assert receipt.status == "infrastructure_error"
    assert receipt.error_category == "infrastructure"
    assert receipt.base.evaluator_exit is None
    assert receipt.reference.setup == "pending"


def test_validation_does_not_reclassify_normal_assertion_output(tmp_path):
    output = "1 test failed: expected child process to be terminated\n"
    runner, task = fixture(tmp_path, FakeDocker(evaluator_output=output))

    receipt = runner.validate_task(task)

    assert receipt.status == "validated"
