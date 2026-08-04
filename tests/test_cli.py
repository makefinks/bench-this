from types import SimpleNamespace

from agent_bench import cli
from agent_bench.models import RunResult


def test_validate_tasks_reports_every_receipt_before_failing(tmp_path, monkeypatch, capsys):
    benchmark = tmp_path / "benchmarks"
    project = SimpleNamespace(benchmark_dir=benchmark)

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


def test_run_prints_progress_summary_and_log_locations(tmp_path, monkeypatch, capsys):
    benchmark = tmp_path / "benchmarks"
    project = SimpleNamespace(benchmark_dir=benchmark)

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
    output = capsys.readouterr().out
    assert "[r1] PASS · 1.2s" in output
    assert "Completed: 1/1 passed · 1.2s average" in output
    assert f"Results: {benchmark / 'results/summary.md'}" in output
    assert f"Logs: {benchmark / 'results/raw/experiment-fixture'}/" in output


def test_run_json_preserves_machine_readable_rows(tmp_path, monkeypatch, capsys):
    benchmark = tmp_path / "benchmarks"
    project = SimpleNamespace(benchmark_dir=benchmark)

    class FakeRunner:
        def __init__(self, _project):
            pass

        def run(self, *_args, progress, **_kwargs):
            assert progress is None
            yield RunResult("demo", "fixture", 1, True, 0.1)

    monkeypatch.setattr(cli, "load_project", lambda _path: project)
    monkeypatch.setattr(cli, "BenchmarkRunner", FakeRunner)

    assert cli.main(["--benchmark-dir", str(benchmark), "run", "--json"]) == 0
    output = capsys.readouterr().out
    assert '"configuration": "fixture"' in output
    assert "Completed:" not in output


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
