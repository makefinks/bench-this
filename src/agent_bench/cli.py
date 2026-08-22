"""Command-line entry point for scaffolding, validation, auth, and benchmark runs."""

import argparse
import json
import sys
from statistics import mean
from pathlib import Path

from .auth import login
from .catalog import HARNESS_CATALOG
from .config import (
    discover_configurations,
    discover_tasks,
    load_project,
)
from .errors import BenchmarkError, ConfigurationError, InfrastructureError
from .runner import DEFAULT_JOBS, BenchmarkRunner
from .scaffold import scaffold


def _benchmark_dir(value: str) -> Path:
    """Accept either a project root or the benchmark directory itself."""

    path = Path(value).resolve()
    return path if path.name == "benchmarks" else path / "benchmarks"


def _parser() -> argparse.ArgumentParser:
    """Define the narrow v1 command surface in one place."""

    parser = argparse.ArgumentParser(prog="agent-bench")
    parser.add_argument("--benchmark-dir", default="benchmarks")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a benchmark scaffold")
    init.add_argument("project", nargs="?", default=".")

    commands.add_parser("build", help="build the benchmark image")
    commands.add_parser("validate", help="validate benchmark YAML and paths")
    commands.add_parser("doctor", help="check Docker, profiles, and pinned model identity")

    validate_task = commands.add_parser("validate-task")
    validate_task.add_argument("task")
    validate_task.add_argument("--verbose", action="store_true")

    validate_tasks = commands.add_parser("validate-tasks")
    validate_tasks.add_argument("--jobs", type=int, default=DEFAULT_JOBS)

    run = commands.add_parser("run")
    run.add_argument(
        "--task",
        action="append",
        help="select an exact task ID; repeat to run a subset",
    )
    run.add_argument(
        "--configuration",
        action="append",
        help="select an exact configuration ID; repeat to run a subset",
    )
    run.add_argument("--repetitions", type=int)
    run.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    run.add_argument("--build", action="store_true")
    output = run.add_mutually_exclusive_group()
    output.add_argument(
        "--verbose",
        action="store_true",
        help="stream raw phase output and execute cells sequentially",
    )
    output.add_argument(
        "--json",
        action="store_true",
        help="print one machine-readable result per line without progress output",
    )

    auth = commands.add_parser("auth")
    auth_commands = auth.add_subparsers(dest="auth_command", required=True)
    login = auth_commands.add_parser("login")
    login.add_argument(
        "--harness", choices=sorted(HARNESS_CATALOG), required=True
    )
    login.add_argument("--profile", required=True)
    login.add_argument(
        "--provider",
        choices=sorted(
            provider_id
            for harness in HARNESS_CATALOG.values()
            for provider_id in harness.providers
            if provider_id is not None
        ),
    )
    verify = auth_commands.add_parser("verify")
    verify.add_argument("--profile", required=True)
    verify.add_argument("--harness", choices=sorted(HARNESS_CATALOG))
    return parser




def main(argv=None) -> int:
    """Dispatch commands and render expected failures without tracebacks."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            destination = scaffold(Path(args.project))
            print(f"Created {destination}")
            return 0

        project = load_project(_benchmark_dir(args.benchmark_dir))
        runner = BenchmarkRunner(project)
        if args.command == "build":
            runner.build()
            print(f"Built {project.image.name}")
        elif args.command == "validate":
            task_files = list((project.benchmark_dir / "tasks").glob("*/task.yaml"))
            config_files = list(
                (project.benchmark_dir / "configurations").glob("*/configuration.yaml")
            )
            tasks = discover_tasks(project) if task_files else {}
            configs = (
                discover_configurations(project)
                if config_files
                else {}
            )
            print(f"Valid project configuration; {len(tasks)} task(s), {len(configs)} configuration(s)")
        elif args.command == "doctor":
            checks = runner.doctor()
            for label, passed, detail in checks:
                print(f"[{'ok' if passed else 'fail'}] {label}: {detail}")
            return 0 if all(passed for _, passed, _ in checks) else 2
        elif args.command == "validate-task":
            tasks = discover_tasks(project)
            if args.task not in tasks:
                raise ConfigurationError(f"unknown task: {args.task}")
            receipt = runner.validate_task(tasks[args.task], verbose=args.verbose)
            print(f"Receipt: {project.benchmark_dir / receipt.receipt_path}")
            if receipt.status != "validated":
                raise InfrastructureError(
                    f"task validation ended with {receipt.status}"
                )
            print(f"Validated {args.task}: base fails and reference passes")
        elif args.command == "validate-tasks":
            if args.jobs <= 0:
                raise ConfigurationError("--jobs must be positive")
            failed = []

            def progress(message):
                """Flush phase updates immediately even when stdout is redirected."""

                print(message, flush=True)

            for receipt in runner.validate_tasks(jobs=args.jobs, progress=progress):
                print(f"Receipt: {project.benchmark_dir / receipt.receipt_path}", flush=True)
                if receipt.status == "validated":
                    print(f"[ok] {receipt.task}: base fails and reference passes", flush=True)
                else:
                    failed.append(receipt.task)
                    print(
                        f"[fail] {receipt.task}: validation ended with {receipt.status}",
                        flush=True,
                    )
            if failed:
                raise InfrastructureError(
                    f"{len(failed)} task validation(s) failed: {', '.join(sorted(failed))}"
                )
        elif args.command == "run":
            if args.repetitions is not None and args.repetitions <= 0:
                raise ConfigurationError("--repetitions must be positive")
            if args.jobs <= 0:
                raise ConfigurationError("--jobs must be positive")
            if args.build:
                runner.build()
            results = []

            def progress(message):
                """Flush complete runner updates so redirected output remains timely."""

                print(message, flush=True)

            for result in runner.run(
                args.task,
                args.configuration,
                args.repetitions,
                jobs=args.jobs,
                verbose=args.verbose,
                progress=None if args.json else progress,
            ):
                results.append(result)
                if args.json:
                    print(json.dumps(result.__dict__, sort_keys=True))
            if not args.json:
                passed = sum(result.passed for result in results)
                average = mean(result.duration_seconds for result in results)
                experiment_id = results[0].experiment_id
                print()
                print(
                    f"Completed: {passed}/{len(results)} passed · {average:.1f}s average"
                )
                print(f"Results: {project.benchmark_dir / 'results' / 'summary.md'}")
                print(
                    "Logs: "
                    f"{project.benchmark_dir / 'results' / 'raw' / experiment_id}/"
                )
        elif args.command == "auth" and args.auth_command == "login":
            destination = login(
                project,
                args.harness,
                args.profile,
                args.provider,
            )
            print(f"Saved {args.harness} profile under {destination}")
        elif args.command == "auth" and args.auth_command == "verify":
            configs = [
                config
                for config in discover_configurations(project).values()
                if config.auth_profile == args.profile
                and (args.harness is None or config.harness == args.harness)
            ]
            if not configs:
                raise ConfigurationError(
                    "no configuration uses the selected profile and harness"
                )
            for config in configs:
                runner.verify_auth(config)
                print(
                    f"Verified {config.auth_profile}/{config.harness}: "
                    f"{config.qualified_model}"
                )
        return 0
    except (BenchmarkError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
