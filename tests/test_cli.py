import json
import subprocess
from types import SimpleNamespace

import pytest
import yaml

from agent_bench import cli
from agent_bench.auth import PROVIDER_CREDENTIALS_FILE
from agent_bench.models import RunResult
from agent_bench.scaffold import scaffold


@pytest.mark.parametrize("provider", ["amazon-bedrock", "openrouter"])
def test_auth_set_key_works_without_project_and_atomically_replaces_key(
    tmp_path, monkeypatch, capsys, provider
):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        cli,
        "load_project",
        lambda _path: pytest.fail("auth set-key must not load a benchmark project"),
    )
    arguments = [
        "auth",
        "set-key",
        "--provider",
        provider,
        "--profile",
        "shared",
        "--api-key",
    ]

    assert cli.main([*arguments, "first-secret"]) == 0
    assert cli.main([*arguments, "replacement-secret"]) == 0

    captured = capsys.readouterr()
    assert "first-secret" not in captured.out + captured.err
    assert "replacement-secret" not in captured.out + captured.err
    profile = home / f".agent-bench/auth/shared/providers/{provider}"
    credential = profile / PROVIDER_CREDENTIALS_FILE
    assert json.loads(credential.read_text(encoding="utf-8")) == {
        "api_key": "replacement-secret"
    }
    assert profile.parent.parent.stat().st_mode & 0o777 == 0o700
    assert profile.parent.stat().st_mode & 0o777 == 0o700
    assert profile.stat().st_mode & 0o777 == 0o700
    assert credential.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "api_key", ["", " ", "line-one\nline-two", "line-one\rline-two"]
)
def test_auth_set_key_rejects_invalid_key_without_changing_state(
    tmp_path, monkeypatch, api_key
):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    arguments = [
        "auth",
        "set-key",
        "--provider",
        "amazon-bedrock",
        "--profile",
        "shared",
        "--api-key",
    ]

    assert cli.main([*arguments, api_key]) == 2
    assert not (home / ".agent-bench").exists()


def test_auth_set_key_rejects_unsafe_profile_before_writing(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    assert (
        cli.main(
            [
                "auth",
                "set-key",
                "--provider",
                "amazon-bedrock",
                "--profile",
                "../../escape",
                "--api-key",
                "fixture-secret",
            ]
        )
        == 2
    )

    assert not (tmp_path / "escape").exists()
    assert not (home / ".agent-bench").exists()


def test_auth_set_key_rejects_unsupported_provider_before_writing(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    with pytest.raises(SystemExit):
        cli.main(
            [
                "auth",
                "set-key",
                "--provider",
                "openai",
                "--profile",
                "shared",
                "--api-key",
                "fixture-secret",
            ]
        )

    assert not (home / ".agent-bench").exists()


def test_auth_set_key_rejects_credential_directory_without_traceback(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    credential = (
        home
        / ".agent-bench/auth/shared/providers/amazon-bedrock"
        / PROVIDER_CREDENTIALS_FILE
    )
    credential.mkdir(parents=True)

    assert (
        cli.main(
            [
                "auth",
                "set-key",
                "--provider",
                "amazon-bedrock",
                "--profile",
                "shared",
                "--api-key",
                "replacement-secret",
            ]
        )
        == 2
    )
    assert credential.is_dir()


def test_auth_set_key_preserves_malformed_provider_profile(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    credential = (
        home
        / ".agent-bench/auth/shared/providers/amazon-bedrock"
        / PROVIDER_CREDENTIALS_FILE
    )
    credential.parent.mkdir(parents=True)
    credential.write_text("not-json\n", encoding="utf-8")

    assert (
        cli.main(
            [
                "auth",
                "set-key",
                "--provider",
                "amazon-bedrock",
                "--profile",
                "shared",
                "--api-key",
                "replacement-secret",
            ]
        )
        == 2
    )

    assert credential.read_text(encoding="utf-8") == "not-json\n"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--profile", "shared", "--api-key", "fixture-secret"],
        ["--provider", "amazon-bedrock", "--api-key", "fixture-secret"],
        ["--provider", "amazon-bedrock", "--profile", "shared"],
    ],
)
def test_auth_set_key_requires_provider_profile_and_key(
    tmp_path, monkeypatch, arguments
):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    with pytest.raises(SystemExit):
        cli.main(["auth", "set-key", *arguments])

    assert not (home / ".agent-bench").exists()


@pytest.mark.parametrize("missing_setup", [False, True])
def test_validate_tasks_reports_every_receipt_before_failing(
    tmp_path, monkeypatch, capsys, missing_setup
):
    benchmark = tmp_path / "benchmarks"
    project = SimpleNamespace(benchmark_dir=benchmark, setup_environment=["SETUP_SESSION"])
    if missing_setup:
        monkeypatch.delenv("SETUP_SESSION", raising=False)
    else:
        monkeypatch.setenv("SETUP_SESSION", "synthetic-session")

    class FakeRunner:
        def __init__(self, loaded_project):
            assert loaded_project is project

        def validate_tasks(self, jobs, progress=None):
            assert jobs == 4
            assert progress is not None
            progress("Validating 2 tasks with 2 workers")
            progress("[start] passing")
            yield SimpleNamespace(
                task="passing",
                status="validated",
                receipt_path="results/validation/passing/latest.json",
            )
            yield SimpleNamespace(
                task="failing",
                status="invalid",
                receipt_path="results/validation/failing/latest.json",
            )

    monkeypatch.setattr(cli, "load_project", lambda _path: project)
    monkeypatch.setattr(cli, "BenchmarkRunner", FakeRunner)

    assert cli.main(["--benchmark-dir", str(benchmark), "validate-tasks", "--jobs", "4"]) == 2
    captured = capsys.readouterr()
    assert "Validating 2 tasks with 2 workers" in captured.out
    assert "[start] passing" in captured.out
    assert "[ok] passing" in captured.out
    assert "[fail] failing" in captured.out
    assert "1 task validation(s) failed: failing" in captured.err
    assert ("SETUP_SESSION" in captured.err) == missing_setup
    assert "synthetic-session" not in captured.err


@pytest.mark.parametrize("missing_setup", [False, True])
def test_run_prints_progress_summary_and_log_locations(
    tmp_path, monkeypatch, capsys, missing_setup
):
    benchmark = tmp_path / "benchmarks"
    project = SimpleNamespace(benchmark_dir=benchmark, setup_environment=["SETUP_SESSION"])
    if missing_setup:
        monkeypatch.delenv("SETUP_SESSION", raising=False)
    else:
        monkeypatch.setenv("SETUP_SESSION", "synthetic-session")

    class FakeRunner:
        def __init__(self, loaded_project):
            assert loaded_project is project

        def run(
            self,
            task,
            configuration,
            repetitions,
            jobs,
            verbose,
            progress,
        ):
            assert (task, configuration, repetitions, jobs, verbose) == (
                ["demo"],
                ["fixture"],
                None,
                3,
                False,
            )
            progress("Running demo")
            progress("[r1] PASS · 1.2s · 10 input · 2 output")
            yield RunResult(
                task="demo",
                configuration="fixture",
                repetition=1,
                passed=True,
                duration_seconds=1.2,
                experiment_id="experiment-fixture",
            )

    monkeypatch.setattr(cli, "load_project", lambda _path: project)
    monkeypatch.setattr(cli, "BenchmarkRunner", FakeRunner)

    assert (
        cli.main(
            [
                "--benchmark-dir",
                str(benchmark),
                "run",
                "--task",
                "demo",
                "--configuration",
                "fixture",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    output = captured.out
    assert "[r1] PASS · 1.2s" in output
    assert "Completed: 1/1 passed · 1.2s average" in output
    assert f"Results: {benchmark / 'results/summary.md'}" in output
    assert f"Logs: {benchmark / 'results/raw/experiment-fixture'}/" in output
    assert ("SETUP_SESSION" in captured.err) == missing_setup
    assert "synthetic-session" not in captured.err


@pytest.mark.parametrize("setup_state", ["disabled", "present", "missing"])
def test_run_json_preserves_machine_readable_rows(tmp_path, monkeypatch, capsys, setup_state):
    benchmark = tmp_path / "benchmarks"
    project = SimpleNamespace(
        benchmark_dir=benchmark,
        setup_environment=(
            [] if setup_state == "disabled"
            else ["SETUP_TOKEN", "SETUP_REGION", "SETUP_ACCOUNT", "SETUP_OPTION"]
        ),
    )
    monkeypatch.setenv("SETUP_TOKEN", "synthetic-present-secret")
    monkeypatch.setenv("SETUP_REGION", "synthetic-region")
    monkeypatch.setenv("SETUP_ACCOUNT", "synthetic-account")
    monkeypatch.setenv("SETUP_OPTION", "")
    if setup_state == "missing":
        monkeypatch.delenv("SETUP_REGION")
        monkeypatch.delenv("SETUP_ACCOUNT")

    class FakeRunner:
        def __init__(self, _project):
            pass

        def run(self, *_args, progress, **_kwargs):
            assert progress is None
            yield RunResult("demo", "fixture", 1, True, 0.1)

    monkeypatch.setattr(cli, "load_project", lambda _path: project)
    monkeypatch.setattr(cli, "BenchmarkRunner", FakeRunner)

    assert cli.main(["--benchmark-dir", str(benchmark), "run", "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["configuration"] == "fixture"
    assert "Completed:" not in captured.out
    if setup_state == "missing":
        assert "SETUP_REGION" in captured.err and "SETUP_ACCOUNT" in captured.err
        assert "SETUP_TOKEN" not in captured.err and "SETUP_OPTION" not in captured.err
        assert "synthetic-present-secret" not in captured.err
    else:
        assert captured.err == ""


@pytest.fixture
def setup_environment_project(tmp_path, monkeypatch):
    benchmark = scaffold(tmp_path)
    manifest = benchmark / "benchmark.yaml"
    data = yaml.safe_load(manifest.read_text())
    data["setup_environment"] = ["SETUP_SESSION"]
    manifest.write_text(yaml.safe_dump(data))
    monkeypatch.delenv("SETUP_SESSION", raising=False)
    return benchmark


def test_validate_task_warns_without_suppressing_the_receipt(
    setup_environment_project, monkeypatch, capsys
):
    repo = setup_environment_project.parent
    (repo / "source.txt").write_text("base\n")
    for arguments in (
        ["init", "-q"],
        ["config", "user.name", "Fixture"],
        ["config", "user.email", "fixture@example.com"],
        ["add", "source.txt"],
        ["commit", "-qm", "base"],
    ):
        subprocess.run(["git", *arguments], cwd=repo, check=True, capture_output=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    task_root = setup_environment_project / "tasks/example"
    task_data = yaml.safe_load((task_root / "task.yaml.example").read_text())
    task_data.update(base_commit=commit, reference_commit=commit)
    (task_root / "task.yaml").write_text(yaml.safe_dump(task_data))

    class FakeDocker:
        def image_id(self, _image):
            return "sha256:" + "a" * 64

    monkeypatch.setattr("agent_bench.runner.DockerEngine", FakeDocker)

    status = cli.main([
        "--benchmark-dir", str(setup_environment_project), "validate-task", "example"
    ])

    captured = capsys.readouterr()
    assert status == 2
    assert "SETUP_SESSION" in captured.err
    latest = setup_environment_project / "results/validation/example/latest.json"
    receipt = json.loads(latest.read_text())
    assert receipt["status"] == "infrastructure_error"
    assert receipt["base"]["setup"] == "failed"
    assert "Receipt:" in captured.out


@pytest.mark.parametrize("command", ["validate", "build", "doctor"])
def test_commands_without_setup_do_not_warn_about_missing_setup_environment(
    setup_environment_project, monkeypatch, capsys, command
):
    class FakeDocker:
        def build(self, *_args):
            pass

        def server_version(self):
            return "fixture"

        def image_exists(self, _image):
            return False

    monkeypatch.setattr("agent_bench.runner.DockerEngine", FakeDocker)

    cli.main(["--benchmark-dir", str(setup_environment_project), command])

    assert capsys.readouterr().err == ""


def test_run_parser_collects_repeated_configurations():
    args = cli._parser().parse_args(
        [
            "run",
            "--configuration",
            "config-a",
            "--configuration",
            "config-b",
        ]
    )
    assert args.configuration == ["config-a", "config-b"]


def test_run_parser_collects_repeated_tasks():
    args = cli._parser().parse_args(
        ["run", "--task", "task-a", "--task", "task-b"]
    )
    assert args.task == ["task-a", "task-b"]
