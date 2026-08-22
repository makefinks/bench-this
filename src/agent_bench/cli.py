"""Command-line entry point for scaffolding, validation, auth, and benchmark runs."""

import argparse
import getpass
import json
import shutil
import sys
from statistics import mean
from pathlib import Path

from .config import (
    AMAZON_BEDROCK_PROVIDER,
    SUPPORTED_OMP_PROVIDERS,
    SUPPORTED_OPENCODE_PROVIDERS,
    SUPPORTED_PI_PROVIDERS,
    discover_harnesses,
    discover_tasks,
    load_project,
)
from .docker import DockerEngine, Mount
from .errors import BenchmarkError, ConfigurationError, InfrastructureError
from .harnesses import adapter_for
from .runner import DEFAULT_JOBS, BenchmarkRunner
from .scaffold import scaffold
from .workspace import (
    auth_profile_root,
    store_bedrock_api_key,
    store_omp_credential,
)


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
        "--harness", choices=("copilot", "omp", "opencode", "pi"), required=True
    )
    login.add_argument("--profile", required=True)
    login.add_argument(
        "--provider",
        choices=sorted(
            SUPPORTED_OPENCODE_PROVIDERS
            | SUPPORTED_OMP_PROVIDERS
            | SUPPORTED_PI_PROVIDERS
        ),
    )
    verify = auth_commands.add_parser("verify")
    verify.add_argument("--profile", required=True)
    verify.add_argument("--harness", choices=("copilot", "omp", "opencode", "pi"))
    return parser


def _login(project, harness: str, profile: str, provider=None) -> None:
    """Create one runner profile through the provider-specific authentication flow."""

    if not profile.replace("-", "").isalnum() or profile.lower() != profile:
        raise ConfigurationError("profile must use lowercase letters, digits, and hyphens")
    if harness == "copilot" and provider is not None:
        raise ConfigurationError("--provider applies only to OpenCode, OMP, and Pi")
    if harness == "opencode" and provider not in SUPPORTED_OPENCODE_PROVIDERS:
        raise ConfigurationError(
            "OpenCode login requires --provider "
            + ", ".join(sorted(SUPPORTED_OPENCODE_PROVIDERS))
        )
    if harness == "omp" and provider not in SUPPORTED_OMP_PROVIDERS:
        raise ConfigurationError(
            "OMP login requires --provider "
            + ", ".join(sorted(SUPPORTED_OMP_PROVIDERS))
        )
    if harness == "pi" and provider not in SUPPORTED_PI_PROVIDERS:
        raise ConfigurationError(
            "Pi login requires --provider "
            + ", ".join(sorted(SUPPORTED_PI_PROVIDERS))
        )
    destination = auth_profile_root(profile, harness)
    destination.mkdir(parents=True, exist_ok=True)
    if harness in {"omp", "pi"}:
        if provider == AMAZON_BEDROCK_PROVIDER:
            if harness == "omp":
                token = getpass.getpass(f"{provider} API token: ")
                store_omp_credential(profile, provider, token)
            else:
                token = getpass.getpass("Amazon Bedrock API key: ")
                store_bedrock_api_key(profile, token, harness="pi")
        else:
            agent_dir = (
                destination / ".omp" / "agent"
                if harness == "omp"
                else destination / ".pi" / "agent"
            )
            executable = "omp" if harness == "omp" else "pi"
            raise ConfigurationError(
                f"{harness.upper()} OAuth login must be completed in the user's terminal. Run:\n"
                f"PI_CODING_AGENT_DIR={agent_dir} {executable}\n"
                f"Then run /login {provider} inside {harness.upper()} and retry."
            )
        print(f"Saved {harness} profile under {destination}")
        return
    engine = DockerEngine()
    environment = {"HOME": "/home/bench", "NO_COLOR": "1"}
    if harness == "copilot":
        environment["COPILOT_HOME"] = "/home/bench/.copilot"
        command = ["copilot"]
        print("In Copilot CLI, run /login, finish the device flow, then exit with Ctrl-D.")
    else:
        if provider == AMAZON_BEDROCK_PROVIDER:
            token = getpass.getpass("Amazon Bedrock API key: ")
            store_bedrock_api_key(profile, token)
            print(f"Saved {harness} profile under {destination}")
            return
        environment.update(
            {
                "XDG_CONFIG_HOME": "/home/bench/.config",
                "XDG_DATA_HOME": "/home/bench/.local/share",
            }
        )
        # Pinning the provider prevents an interactive selection mistake from
        # producing credentials for a different experimental treatment.
        command = ["opencode", "auth", "login", "--provider", provider]
    engine.run_interactive(
        project.image.name,
        command,
        [Mount(destination, "/home/bench")],
        environment,
    )
    if harness == "opencode":
        _narrow_opencode_profile(destination, provider)
    print(f"Saved {harness} profile under {destination}")


def _narrow_opencode_profile(destination: Path, provider: str) -> None:
    """Retain only one provider credential and discard login-generated state."""

    auth_path = destination / ".local" / "share" / "opencode" / "auth.json"
    try:
        credentials = json.loads(auth_path.read_text(encoding="utf-8"))
        selected = credentials[provider]
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise InfrastructureError(
            f"OpenCode login did not create a valid {provider!r} credential"
        ) from exc

    # OpenCode login also creates caches, logs, databases, npm state, and plugin
    # symlinks. None are credentials, and retaining them broadens the run profile.
    shutil.rmtree(destination)
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(
        json.dumps({provider: selected}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    auth_path.chmod(0o600)


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
                discover_harnesses(project)
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
            _login(project, args.harness, args.profile, args.provider)
        elif args.command == "auth" and args.auth_command == "verify":
            configs = [
                config
                for config in discover_harnesses(project).values()
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
