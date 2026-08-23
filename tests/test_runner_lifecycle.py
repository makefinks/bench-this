import subprocess
import threading
import time
from pathlib import Path

import pytest

from agent_bench.docker import Mount
from agent_bench.errors import CommandTimeout, InfrastructureError
from agent_bench.models import (
    CommandResult,
    Defaults,
    TreatmentConfig,
    ImageConfig,
    ProjectConfig,
    RunResult,
    TaskConfig,
)
from agent_bench.runner import BenchmarkRunner


class FakeDocker:
    def __init__(self):
        self.calls = []
        self.timeouts = []
        self.secret_environments = []

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
        self.timeouts.append(timeout_seconds)
        self.secret_environments.append(secret_environment)
        self.calls.append((command, mounts, network, stdout_path, stderr_path, stream_output))
        targets = {mount.target: mount for mount in mounts}
        if any("BENCH_PREFLIGHT_OK" in part for part in command):
            assert set(targets) == {"/workspace", "/home/bench"}
            assert not any("repo" in str(mount.source) for mount in mounts)
            return CommandResult(0, '{"model":"gpt-fixed"}\n', "", 0.1)
        if command[:2] == ["/bin/sh", "-lc"] and "/benchmark" in targets:
            setup_mount = targets["/benchmark"]
            assert setup_mount.readonly
            assert (setup_mount.source / "setup.sh").is_file()
            assert {path.name for path in setup_mount.source.iterdir()} == {"setup.sh"}
            assert not (targets["/workspace"].source / ".agent-bench-public-tests").exists()
            python = targets["/workspace"].source / ".venv/bin/python"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("prepared\n")
            return CommandResult(0, "", "", 0.1)
        if command and command[0] == "copilot":
            assert "/evaluator" not in targets
            workspace = targets["/workspace"].source
            (targets["/home/bench"].source / "copilot-otel.jsonl").write_text(
                '{"attributes":{"gen_ai.operation.name":"chat",'
                '"gen_ai.usage.input_tokens":13,"gen_ai.usage.output_tokens":4,'
                '"gen_ai.usage.reasoning.output_tokens":2,'
                '"gen_ai.usage.cache_read.input_tokens":3}}\n'
            )
            assert not (workspace / ".git").exists()
            assert not (workspace / "benchmarks").exists()
            (workspace / "answer.txt").write_text("solved\n")
            (workspace / ".venv").rename(workspace / ".venv-replaced-by-solver")
            public_tests = workspace / ".agent-bench-public-tests"
            assert (public_tests / "run.sh").read_text() == "public tests\n"
            (public_tests / "run.sh").write_text("modified by solver\n")
            return CommandResult(
                0,
                '{"model":"gpt-fixed","usage":{"input":10,"output":2}}\n',
                "",
                0.2,
            )
        assert network == "none"
        workspace = targets["/workspace"].source
        passed = (workspace / "answer.txt").exists()
        assert (workspace / ".venv/bin/python").read_text() == "prepared\n"
        assert not (workspace / ".agent-bench-public-tests").exists()
        if "/public-tests" in targets:
            assert targets["/public-tests"].readonly
            assert (targets["/public-tests"].source / "run.sh").read_text() == "public tests\n"
            output = (
                'AGENT_BENCH_RESULT: {"version":1,"groups":{"public-basic":true}}\n'
            )
        else:
            assert targets["/evaluator"].readonly
            output = (
                'AGENT_BENCH_RESULT: {"version":1,"groups":{"hidden-edge":true}}\n'
            )
        return CommandResult(0 if passed else 1, output, "", 0.1)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def test_preflight_happens_before_source_and_hidden_tests_follow_solver(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "fixture@example.com")
    git(repo, "config", "user.name", "Fixture")
    (repo / "source.txt").write_text("base\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    commit = git(repo, "rev-parse", "HEAD")

    benchmark = repo / "benchmarks"
    task_root = benchmark / "tasks/demo"
    hidden = task_root / "hidden-tests"
    hidden.mkdir(parents=True)
    (hidden / "run.sh").write_text("#!/bin/sh\n")
    public_tests = task_root / "public-tests"
    public_tests.mkdir()
    (public_tests / "run.sh").write_text("public tests\n")
    (task_root / "prompt.md").write_text("Create answer.txt")
    (benchmark / "setup.sh").parent.mkdir(parents=True, exist_ok=True)
    (benchmark / "setup.sh").write_text("#!/bin/sh\n")
    config_root = benchmark / "configurations/copilot"
    (config_root / "harness").mkdir(parents=True)
    (config_root / "workspace").mkdir()
    auth = tmp_path / "auth/work/copilot/.copilot"
    auth.mkdir(parents=True)
    (auth / "token.json").write_text("secret")

    project = ProjectConfig(
        root=repo,
        benchmark_dir=benchmark,
        image=ImageConfig("fixture", benchmark / "Dockerfile"),
        setup_command="/bin/sh /benchmark/setup.sh /workspace",
        defaults=Defaults(None, 5, 1),
    )
    task = TaskConfig(
        root=task_root,
        id="demo",
        base_commit=commit,
        reference_commit=commit,
        prompt_path=task_root / "prompt.md",
        public_directory=task_root / "public",
        hidden_tests_directory=hidden,
        test_command="/bin/sh /evaluator/run.sh /workspace",
        solver_timeout_seconds=None,
        requirement_groups=["hidden-edge"],
        public_tests_directory=public_tests,
        public_test_command="/bin/sh /public-tests/run.sh /workspace",
        public_test_groups=["public-basic"],
    )
    config = TreatmentConfig(
        root=config_root,
        id="copilot",
        harness="copilot",
        model="gpt-fixed",
        harness_config=config_root / "harness",
        workspace_config=config_root / "workspace",
        auth_profile="work",
        arguments=[],
    )
    docker = FakeDocker()
    progress = []
    result = BenchmarkRunner(project, docker=docker, auth_root=tmp_path / "auth").run_one(
        task, config, 1, progress=progress.append
    )
    assert result.passed
    assert result.input_tokens == 10
    assert result.output_tokens == 2
    assert result.reasoning_tokens == 2
    assert result.cache_read_tokens == 3
    assert result.turns == 1
    assert Path(result.log_directory, "solver.telemetry.jsonl").is_file()
    assert result.experiment_id.startswith("experiment-")
    assert result.run_id.startswith("demo--copilot--r1--")
    assert result.run_id in result.log_directory
    assert len(result.task_digest) == 64
    assert len(result.configuration_digest) == 64
    injected = [
        environment
        for environment in docker.secret_environments
        if environment is not None
    ]
    assert len(injected) == 2
    assert injected[0] is injected[1]
    assert result.public_test_results == {"public-basic": True}
    assert result.group_results == {"hidden-edge": True}
    assert result.public_test_mutation_detected
    assert result.public_test_modified_files == ["run.sh"]
    assert result.public_test_deleted_files == []
    assert result.solver_duration_seconds == 0.2
    assert set(result.phase_durations) == {
        "preflight",
        "workspace",
        "solver_setup",
        "solver",
        "evaluator_setup",
        "public_evaluator",
        "hidden_evaluator",
    }
    assert result.phase_durations["solver"] == 0.2
    assert progress == ["started", "solving", "evaluating"]
    assert [call[2] for call in docker.calls] == [
        "bridge",
        "bridge",
        "bridge",
        "bridge",
        "none",
        "none",
    ]
    assert docker.timeouts == [180, 300, None, 300, 5, 5]
    assert all(call[3] is not None and call[4] is not None and call[5] for call in docker.calls)
    solver_mounts = {mount.target: mount.source for mount in docker.calls[2][1]}
    evaluator_setup_mounts = {mount.target: mount.source for mount in docker.calls[3][1]}
    public_evaluator_mounts = {mount.target: mount.source for mount in docker.calls[4][1]}
    assert solver_mounts["/workspace"] != evaluator_setup_mounts["/workspace"]
    assert public_evaluator_mounts["/workspace"] == evaluator_setup_mounts["/workspace"]


@pytest.mark.parametrize(
    "phase,error,expected",
    [
        ("preflight", InfrastructureError("bad credentials"), "preflight"),
        ("solver_setup", InfrastructureError("dependency failed"), "solver_setup"),
        (
            "evaluator_setup",
            InfrastructureError("dependency failed"),
            "evaluator_setup",
        ),
        ("evaluator", InfrastructureError("bad protocol"), "evaluator"),
        ("solver", CommandTimeout("container exceeded 10 seconds"), "solver_timeout"),
        ("solver", CommandTimeout("quota or usage limit detected"), "quota"),
    ],
)
def test_lifecycle_failures_keep_their_phase(phase, error, expected):
    assert BenchmarkRunner._failure_kind(error, phase) == expected


def test_digests_change_with_effective_inputs(tmp_path):
    from agent_bench.identity import configuration_digest, task_digest

    task_root = tmp_path / "task"
    hidden = task_root / "hidden"
    public = task_root / "public"
    public_tests = task_root / "public-tests"
    hidden.mkdir(parents=True)
    public.mkdir()
    public_tests.mkdir()
    prompt = task_root / "prompt.md"
    prompt.write_text("first")
    task = TaskConfig(
        task_root,
        "demo",
        "a" * 40,
        "b" * 40,
        prompt,
        public,
        hidden,
        "test",
        10,
        public_tests,
        "public-test",
        ["public-basic"],
        ["hidden-basic"],
    )

    config_root = tmp_path / "config"
    harness = config_root / "harness"
    workspace = config_root / "workspace"
    harness.mkdir(parents=True)
    workspace.mkdir()
    config = TreatmentConfig(config_root, "demo", "copilot", "model", harness, workspace, "work", [])

    first_task = task_digest(task)
    first_config = configuration_digest(config)
    prompt.write_text("second")
    (workspace / "instructions.md").write_text("changed")

    assert task_digest(task) != first_task
    assert configuration_digest(config) != first_config


def test_matrix_uses_bounded_workers_and_serializes_reporting(tmp_path, monkeypatch):
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path / "benchmarks",
        image=ImageConfig("fixture", tmp_path / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
    )
    tasks = {
        f"task-{index}": type("Task", (), {"id": f"task-{index}"})()
        for index in range(3)
    }
    configs = {
        f"config-{index}": type(
            "Config", (), {"id": f"config-{index}", "harness": "fixture"}
        )()
        for index in range(2)
    }
    monkeypatch.setattr("agent_bench.runner.discover_tasks", lambda _project: tasks)
    monkeypatch.setattr("agent_bench.runner.discover_configurations", lambda _project: configs)

    active = 0
    maximum_active = 0
    stream_values = []
    lock = threading.Lock()

    def run_one(
        task, config, repetition, experiment_id, stream_output=True, progress=None
    ):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            stream_values.append(stream_output)
        progress("started")
        progress("solving")
        time.sleep(0.02)
        with lock:
            active -= 1
        return RunResult(
            task=next(key for key, value in tasks.items() if value is task),
            configuration=next(key for key, value in configs.items() if value is config),
            repetition=repetition,
            passed=True,
            duration_seconds=0.02,
            experiment_id=experiment_id,
        )

    runner = BenchmarkRunner(project)
    monkeypatch.setattr(runner, "run_one", run_one)
    progress_messages = []
    results = list(runner.run(jobs=3, progress=progress_messages.append))

    assert len(results) == 6
    assert maximum_active == 3
    assert stream_values == [False] * 6
    assert progress_messages[0] == "Running 6 benchmark cells · 3 workers"
    assert any(message.startswith("[1/6 task-0 · config-0 · r1]") for message in progress_messages)
    assert sum(" PASS · " in message for message in progress_messages) == 6
    assert (project.benchmark_dir / "results/runs.jsonl").read_text().count("\n") == 6
    assert (project.benchmark_dir / "results/summary.md").read_text().count("3/3") == 2


def test_matrix_rejects_nonpositive_jobs(tmp_path, monkeypatch):
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path / "benchmarks",
        image=ImageConfig("fixture", tmp_path / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
    )
    monkeypatch.setattr("agent_bench.runner.discover_tasks", lambda _project: {"task": object()})
    monkeypatch.setattr(
        "agent_bench.runner.discover_configurations", lambda _project: {"config": object()}
    )

    with pytest.raises(InfrastructureError, match="jobs must be a positive integer"):
        list(BenchmarkRunner(project).run(jobs=0))


def test_matrix_runs_an_exact_configuration_subset_in_requested_order(tmp_path, monkeypatch):
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path / "benchmarks",
        image=ImageConfig("fixture", tmp_path / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
    )
    task = type("Task", (), {"id": "task"})()
    configs = {
        config_id: type(
            "Config", (), {"id": config_id, "harness": "fixture"}
        )()
        for config_id in ("config-a", "config-b", "config-c")
    }
    monkeypatch.setattr("agent_bench.runner.discover_tasks", lambda _project: {"task": task})
    monkeypatch.setattr("agent_bench.runner.discover_configurations", lambda _project: configs)

    def run_one(
        _task, config, repetition, experiment_id, stream_output=True, progress=None
    ):
        return RunResult(
            task="task",
            configuration=config.id,
            repetition=repetition,
            passed=True,
            duration_seconds=0.01,
            experiment_id=experiment_id,
        )

    runner = BenchmarkRunner(project)
    monkeypatch.setattr(runner, "run_one", run_one)

    results = list(
        runner.run(configuration_filter=["config-c", "config-a", "config-c"], jobs=1)
    )
    assert [result.configuration for result in results] == ["config-c", "config-a"]


def test_matrix_rejects_any_unknown_configuration_in_subset(tmp_path, monkeypatch):
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path / "benchmarks",
        image=ImageConfig("fixture", tmp_path / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
    )
    config = type("Config", (), {"id": "known", "harness": "fixture"})()
    monkeypatch.setattr(
        "agent_bench.runner.discover_tasks",
        lambda _project: {"task": type("Task", (), {"id": "task"})()},
    )
    monkeypatch.setattr(
        "agent_bench.runner.discover_configurations", lambda _project: {"known": config}
    )

    with pytest.raises(InfrastructureError, match=r"unknown configuration\(s\): missing"):
        list(
            BenchmarkRunner(project).run(
                configuration_filter=["known", "missing"]
            )
        )


def test_matrix_runs_an_exact_task_subset_in_requested_order(tmp_path, monkeypatch):
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path / "benchmarks",
        image=ImageConfig("fixture", tmp_path / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
    )
    tasks = {
        task_id: type("Task", (), {"id": task_id})()
        for task_id in ("task-a", "task-b", "task-c")
    }
    config = type("Config", (), {"id": "config", "harness": "fixture"})()
    monkeypatch.setattr("agent_bench.runner.discover_tasks", lambda _project: tasks)
    monkeypatch.setattr(
        "agent_bench.runner.discover_configurations", lambda _project: {"config": config}
    )

    def run_one(
        task, _config, repetition, experiment_id, stream_output=True, progress=None
    ):
        return RunResult(
            task=task.id,
            configuration="config",
            repetition=repetition,
            passed=True,
            duration_seconds=0.01,
            experiment_id=experiment_id,
        )

    runner = BenchmarkRunner(project)
    monkeypatch.setattr(runner, "run_one", run_one)

    results = list(runner.run(task_filter=["task-c", "task-a", "task-c"], jobs=1))
    assert [result.task for result in results] == ["task-c", "task-a"]


def test_matrix_rejects_any_unknown_task_in_subset(tmp_path, monkeypatch):
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path / "benchmarks",
        image=ImageConfig("fixture", tmp_path / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
    )
    task = type("Task", (), {"id": "known"})()
    monkeypatch.setattr(
        "agent_bench.runner.discover_tasks", lambda _project: {"known": task}
    )
    monkeypatch.setattr(
        "agent_bench.runner.discover_configurations",
        lambda _project: {
            "config": type("Config", (), {"id": "config", "harness": "fixture"})()
        },
    )

    with pytest.raises(InfrastructureError, match=r"unknown task\(s\): missing"):
        list(BenchmarkRunner(project).run(task_filter=["known", "missing"]))


def test_task_validation_uses_bounded_workers(tmp_path, monkeypatch):
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path / "benchmarks",
        image=ImageConfig("fixture", tmp_path / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
    )
    tasks = {f"task-{index}": object() for index in range(5)}
    monkeypatch.setattr("agent_bench.runner.discover_tasks", lambda _project: tasks)

    active = 0
    maximum_active = 0
    stream_values = []
    progress_messages = []
    lock = threading.Lock()

    def validate_task(task, verbose=False, progress=None):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            stream_values.append(verbose)
        if progress is not None:
            progress(f"[fake] {next(key for key, value in tasks.items() if value is task)}")
        time.sleep(0.02)
        with lock:
            active -= 1
        return task

    runner = BenchmarkRunner(project)
    monkeypatch.setattr(runner, "validate_task", validate_task)

    assert len(list(runner.validate_tasks(jobs=3, progress=progress_messages.append))) == 5
    assert maximum_active == 3
    assert stream_values == [False] * 5
    assert progress_messages[0] == "Validating 5 tasks with 3 workers"
    assert set(progress_messages[1:]) == {f"[fake] task-{index}" for index in range(5)}


def test_single_task_validation_keeps_live_output(tmp_path, monkeypatch):
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path / "benchmarks",
        image=ImageConfig("fixture", tmp_path / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
    )
    task = object()
    monkeypatch.setattr("agent_bench.runner.discover_tasks", lambda _project: {"task": task})
    stream_values = []

    def validate_task(_task, verbose=False, progress=None):
        stream_values.append(verbose)
        if progress is not None:
            progress("[fake] task")
        return _task

    runner = BenchmarkRunner(project)
    monkeypatch.setattr(runner, "validate_task", validate_task)

    progress_messages = []
    assert list(runner.validate_tasks(progress=progress_messages.append)) == [task]
    assert stream_values == [True]
    assert progress_messages == [
        "Validating 1 task with 1 worker",
        "[fake] task",
    ]


def test_task_validation_rejects_nonpositive_jobs(tmp_path, monkeypatch):
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path / "benchmarks",
        image=ImageConfig("fixture", tmp_path / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
    )
    monkeypatch.setattr("agent_bench.runner.discover_tasks", lambda _project: {"task": object()})

    with pytest.raises(InfrastructureError, match="jobs must be a positive integer"):
        list(BenchmarkRunner(project).validate_tasks(jobs=0))


def test_single_cell_is_quiet_by_default_and_verbose_runs_serially(tmp_path, monkeypatch):
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path / "benchmarks",
        image=ImageConfig("fixture", tmp_path / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
    )
    task = type("Task", (), {"id": "task"})()
    config = type("Config", (), {"id": "config", "harness": "fixture"})()
    monkeypatch.setattr("agent_bench.runner.discover_tasks", lambda _project: {"task": task})
    monkeypatch.setattr(
        "agent_bench.runner.discover_configurations", lambda _project: {"config": config}
    )
    stream_values = []

    def run_one(
        _task, _config, repetition, experiment_id, stream_output=True, progress=None
    ):
        stream_values.append(stream_output)
        progress("started")
        return RunResult(
            task="task",
            configuration="config",
            repetition=repetition,
            passed=True,
            duration_seconds=0.01,
            experiment_id=experiment_id,
        )

    runner = BenchmarkRunner(project)
    monkeypatch.setattr(runner, "run_one", run_one)

    messages = []
    assert len(list(runner.run(progress=messages.append))) == 1
    assert stream_values == [False]
    assert messages[:5] == [
        "Running task",
        "Configuration: config",
        "Harness: fixture · 1 repetition · 1 worker",
        "",
        "[r1] started",
    ]
    assert messages[-1] == "[r1] PASS · 0.0s"

    stream_values.clear()
    assert len(list(runner.run(repetitions=2, jobs=2, verbose=True))) == 2
    assert stream_values == [True, True]


def test_incorrect_result_is_not_labeled_as_evaluator_failure(tmp_path, monkeypatch):
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path / "benchmarks",
        image=ImageConfig("fixture", tmp_path / "Dockerfile"),
        setup_command="setup",
        defaults=Defaults(),
    )
    task = type("Task", (), {"id": "task"})()
    config = type("Config", (), {"id": "config", "harness": "fixture"})()
    monkeypatch.setattr("agent_bench.runner.discover_tasks", lambda _project: {"task": task})
    monkeypatch.setattr(
        "agent_bench.runner.discover_configurations", lambda _project: {"config": config}
    )

    def run_one(
        _task, _config, repetition, experiment_id, stream_output=True, progress=None
    ):
        return RunResult(
            task="task",
            configuration="config",
            repetition=repetition,
            passed=False,
            duration_seconds=0.01,
            failure_kind="incorrect",
            group_results={"first": True, "second": False},
            experiment_id=experiment_id,
        )

    runner = BenchmarkRunner(project)
    monkeypatch.setattr(runner, "run_one", run_one)
    messages = []

    assert len(list(runner.run(progress=messages.append))) == 1
    assert messages[-1] == "[r1] FAIL · 0.0s · hidden 1/2 · requirements failed"
