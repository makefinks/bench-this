"""Orchestrate the fail-closed preflight, solver, and hidden evaluator lifecycle."""

import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

from .auth import PreparedAuth, prepare_home

from .config import discover_configurations, discover_tasks
from .docker import DockerEngine, Mount, diagnose_output
from .errors import BenchmarkError, CommandTimeout, InfrastructureError
from .evaluator import EvaluatorReport, parse_evaluator_report, validate_evaluator_exit
from .harnesses import PREFLIGHT_PROMPT, adapter_for
from .identity import configuration_digest, task_digest, validation_environment_digest
from .installers import render_dockerfile
from .models import (
    ProjectConfig,
    RunResult,
    TaskConfig,
    TreatmentConfig,
    Usage,
    ValidationPhase,
    ValidationReceipt,
)
from .pricing import ModelsDevPricing
from .report import append_result, write_summary
from .workspace import (
    export_commit,
    prepare_evaluator_workspace,
    prepare_workspace,
    public_test_mutations,
    public_test_snapshot,
    stage_public_tests,
)


DEFAULT_JOBS = 3

_VALIDATION_INFRASTRUCTURE_PATTERNS = (
    ("missing module", re.compile(r"(?im)^\s*(?:error:\s*)?cannot find module\b")),
    ("unresolved import", re.compile(r"(?im)^\s*(?:error:\s*)?could not resolve\b")),
    ("syntax error", re.compile(r"(?im)^\s*syntaxerror:")),
    (
        "missing command",
        re.compile(r"(?im)^[^\n]*\bcommand not found(?::[^\n]*)?\s*$"),
    ),
    (
        "test initialization error",
        re.compile(r"(?im)^\s*(?:#\s*)?unhandled error between tests\s*$"),
    ),
    (
        "zero discovered tests",
        re.compile(r"(?im)^\s*(?:ran\s+)?0 tests?(?:\s+across[^\n]*)?\.?\s*$"),
    ),
)


def _unique_id(prefix: str) -> str:
    """Create a sortable identity that remains unique across repeated invocations."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{prefix}-{timestamp}-{uuid.uuid4().hex[:8]}"


def _validation_infrastructure_signature(stdout: str, stderr: str) -> Optional[str]:
    """Recognize only high-confidence evaluator startup failures during task validation."""

    output = f"{stdout}\n{stderr}"
    for label, pattern in _VALIDATION_INFRASTRUCTURE_PATTERNS:
        if pattern.search(output):
            return label
    return None


class BenchmarkRunner:
    """Execute validated tasks in isolated cells using one configured project image."""

    def __init__(
        self,
        project: ProjectConfig,
        docker: Optional[DockerEngine] = None,
        auth_root: Optional[Path] = None,
        pricing: Optional[ModelsDevPricing] = None,
    ):
        self.project = project
        self.docker = docker or DockerEngine()
        self.auth_root = auth_root
        self.pricing = pricing or ModelsDevPricing()

    def build(self) -> None:
        """Build a project image with only the configured harness executables."""

        configuration_files = list((self.project.benchmark_dir / "configurations").glob("*/configuration.yaml"))
        harnesses = set()
        if configuration_files:
            harnesses = {config.harness for config in discover_configurations(self.project).values()}
        rendered = render_dockerfile(self.project.image.dockerfile, harnesses)
        with tempfile.NamedTemporaryFile("w", suffix=".Dockerfile", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            self.docker.build(self.project.image.name, Path(handle.name), self.project.benchmark_dir)

    def verify_auth(self, config: TreatmentConfig) -> Path:
        """Verify one profile/model pairing without exposing project source."""

        log_dir = (
            self.project.benchmark_dir
            / "results"
            / "auth"
            / config.id
            / _unique_id("verify")
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="agent-bench-auth-") as temp:
            prepared = prepare_home(
                config, Path(temp) / "home", self.auth_root
            )
            self._preflight(config, prepared, log_dir)
        return log_dir

    def doctor(self) -> List[Tuple[str, bool, str]]:
        """Check local runtime, manifests, profiles, and source-free model identity."""

        checks: List[Tuple[str, bool, str]] = []
        try:
            version = self.docker.server_version()
            checks.append(("docker", True, f"server {version}"))
        except BenchmarkError as exc:
            checks.append(("docker", False, str(exc)))
            return checks

        if not self.docker.image_exists(self.project.image.name):
            checks.append(
                (
                    "image",
                    False,
                    f"missing {self.project.image.name!r}; run `./benchmarks/run.py build`",
                )
            )
            return checks
        checks.append(("image", True, self.project.image.name))

        try:
            tasks = discover_tasks(self.project)
            configs = discover_configurations(self.project)
            checks.append(
                ("configuration", True, f"{len(tasks)} task(s), {len(configs)} treatment(s)")
            )
        except BenchmarkError as exc:
            checks.append(("configuration", False, str(exc)))
            return checks

        for config in configs.values():
            log_dir = (
                self.project.benchmark_dir
                / "results"
                / "auth"
                / config.id
                / _unique_id("doctor")
            )
            log_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="agent-bench-auth-") as temp:
                try:
                    prepared = prepare_home(
                        config, Path(temp) / "home", self.auth_root
                    )
                    checks.append(
                        (
                            f"auth:{config.id}",
                            True,
                            f"clean profile {config.auth_profile!r}",
                        )
                    )
                except BenchmarkError as exc:
                    checks.append((f"auth:{config.id}", False, str(exc)))
                    continue
                try:
                    self._preflight(config, prepared, log_dir)
                    checks.append(
                        (
                            f"identity:{config.id}",
                            True,
                            f"{config.qualified_model}; logs: {log_dir}",
                        )
                    )
                except BenchmarkError as exc:
                    checks.append((f"identity:{config.id}", False, str(exc)))
        return checks

    def _setup(
        self,
        workspace: Path,
        log_dir: Path,
        stream_output: bool = True,
        log_prefix: str = "setup",
    ) -> None:
        """Prepare one disposable workspace using the project image."""

        # A setup-only directory avoids unreliable single-file bind mounts without exposing tests.
        with tempfile.TemporaryDirectory(prefix="agent-bench-setup-") as temp:
            setup_root = Path(temp)
            shutil.copy2(self.project.benchmark_dir / "setup.sh", setup_root / "setup.sh")
            result = self.docker.run(
                self.project.image.name,
                ["/bin/sh", "-lc", self.project.setup_command],
                [Mount(workspace, "/workspace"), Mount(setup_root, "/benchmark", True)],
                {"HOME": "/tmp/benchmark-home"},
                self.project.defaults.setup_timeout_seconds,
                network="bridge",
                stdout_path=log_dir / f"{log_prefix}.stdout.log",
                stderr_path=log_dir / f"{log_prefix}.stderr.log",
                stream_output=stream_output,
            )
        if result.returncode:
            raise InfrastructureError(f"setup failed: {result.stderr.strip() or result.stdout.strip()}")

    def _preflight(
        self,
        config: TreatmentConfig,
        prepared: PreparedAuth,
        log_dir: Path,
        stream_output: bool = True,
    ) -> None:
        """Prove credentials and resolved identity in an empty workspace mount."""

        adapter = adapter_for(config)
        solver_timeout = self.project.defaults.solver_timeout_seconds
        preflight_timeout = 180 if solver_timeout is None else min(180, solver_timeout)
        with tempfile.TemporaryDirectory(prefix="agent-bench-preflight-") as empty:
            result = self.docker.run(
                self.project.image.name,
                adapter.preflight_command(),
                [
                    Mount(Path(empty), "/workspace"),
                    Mount(prepared.home, "/home/bench"),
                ],
                adapter.environment(),
                preflight_timeout,
                network="bridge",
                stdout_path=log_dir / "preflight.stdout.jsonl",
                stderr_path=log_dir / "preflight.stderr.log",
                stream_output=stream_output,
                secret_environment=prepared.secret_environment,
            )
        if result.returncode:
            diagnosis = diagnose_output(result.stdout, result.stderr)
            detail = f"; {diagnosis}" if diagnosis else ""
            raise InfrastructureError(
                f"credential/model preflight failed with exit {result.returncode}{detail}; "
                f"logs: {log_dir}"
            )
        try:
            adapter.verify_preflight(result.stdout, result.stderr)
        except InfrastructureError as exc:
            raise InfrastructureError(f"{exc}; logs: {log_dir}") from exc

    def _run_evaluator(
        self,
        task: TaskConfig,
        workspace: Path,
        log_dir: Path,
        public: bool,
        stream_output: bool,
    ):
        """Run one canonical evaluator suite without credentials or network."""

        if public:
            command = task.public_test_command
            evaluator_directory = task.public_tests_directory
            mount_target = "/public-tests"
            expected_groups = task.public_test_groups
            log_prefix = "public-evaluator"
        else:
            command = task.test_command
            evaluator_directory = task.hidden_tests_directory
            mount_target = "/evaluator"
            expected_groups = task.requirement_groups
            log_prefix = "evaluator"
        result = self.docker.run(
            self.project.image.name,
            ["/bin/sh", "-lc", command],
            [
                Mount(workspace, "/workspace"),
                Mount(evaluator_directory, mount_target, True),
            ],
            {"HOME": "/tmp/evaluator-home"},
            self.project.defaults.evaluator_timeout_seconds,
            network="none",
            stdout_path=log_dir / f"{log_prefix}.stdout.log",
            stderr_path=log_dir / f"{log_prefix}.stderr.log",
            stream_output=stream_output,
        )
        report = parse_evaluator_report(result.stdout, expected_groups)
        validate_evaluator_exit(result.returncode, report)
        return result, report

    def _evaluate(
        self,
        task: TaskConfig,
        workspace: Path,
        log_dir: Path,
        stream_output: bool = True,
        progress: Optional[Callable[[str], None]] = None,
        phase_durations: Optional[Dict[str, float]] = None,
    ):
        """Run public then hidden canonical suites and preserve both reports."""

        log_dir.mkdir(parents=True, exist_ok=True)
        if progress is not None:
            progress("public")
        public_started = time.monotonic()
        try:
            public_result, public_report = self._run_evaluator(
                task, workspace, log_dir, True, stream_output
            )
        finally:
            if phase_durations is not None:
                phase_durations["public_evaluator"] = time.monotonic() - public_started
        if progress is not None:
            progress("hidden")
        hidden_started = time.monotonic()
        try:
            hidden_result, hidden_report = self._run_evaluator(
                task, workspace, log_dir, False, stream_output
            )
        finally:
            if phase_durations is not None:
                phase_durations["hidden_evaluator"] = time.monotonic() - hidden_started
        return public_result, public_report, hidden_result, hidden_report

    @staticmethod
    def _failure_kind(exc: BenchmarkError, phase: str) -> str:
        """Classify the failed lifecycle phase without treating every error as infrastructure."""

        detail = str(exc).lower()
        if isinstance(exc, CommandTimeout):
            if "quota or usage limit" in detail:
                return "quota"
            return f"{phase}_timeout"
        if phase in {"preflight", "solver_setup", "evaluator_setup", "evaluator"}:
            return phase
        return "infrastructure"

    def _estimate(self, config: TreatmentConfig, usage: Usage) -> Optional[float]:
        """Estimate API-equivalent list-price cost alongside any provider-reported cost.

        Computed even when native_cost_usd exists so summaries expose
        divergence between provider self-reporting and list prices.
        """

        price = self.project.prices.get(config.model)
        if price is None:
            price = self.pricing.price(
                config.provider_spec.pricing_provider, config.model
            )
        if price is None:
            return None
        return (
            usage.input_tokens * price.input_per_million_usd
            + usage.output_tokens * price.output_per_million_usd
            + (usage.reasoning_tokens or 0) * price.reasoning_per_million_usd
            + usage.cache_read_tokens * price.cache_read_per_million_usd
            + usage.cache_write_tokens * price.cache_write_per_million_usd
        ) / 1_000_000

    def run_one(
        self,
        task: TaskConfig,
        config: TreatmentConfig,
        repetition: int,
        experiment_id: Optional[str] = None,
        stream_output: bool = True,
        progress: Optional[Callable[[str], None]] = None,
    ) -> RunResult:
        """Execute one isolated matrix cell and always return a normalized result."""

        experiment_id = experiment_id or _unique_id("experiment")
        run_id = f"{task.id}--{config.id}--r{repetition}--{uuid.uuid4().hex[:8]}"
        task_fingerprint = task_digest(task)
        configuration_fingerprint = configuration_digest(config)
        log_dir = self.project.benchmark_dir / "results" / "raw" / experiment_id / run_id
        log_dir.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        usage = Usage()
        solver_error = None
        public_test_mutation_detected = None
        public_test_modified_files = []
        public_test_deleted_files = []
        public_tests_before_solver = {}
        solver_duration_seconds = None
        phase_durations: Dict[str, float] = {}
        phase = "initialization"
        if progress is not None:
            progress("started")
        try:
            with tempfile.TemporaryDirectory(prefix="agent-bench-run-") as temp:
                temp_root = Path(temp)
                workspace = temp_root / "workspace"
                evaluator_workspace = temp_root / "evaluator-workspace"
                prepared = prepare_home(
                    config, temp_root / "home", self.auth_root
                )
                home = prepared.home

                # This must complete before any source directory is mounted in a model container.
                phase = "preflight"
                phase_started = time.monotonic()
                try:
                    self._preflight(
                        config, prepared, log_dir, stream_output=stream_output
                    )
                finally:
                    phase_durations["preflight"] = time.monotonic() - phase_started
                phase_started = time.monotonic()
                try:
                    prepare_workspace(self.project, task, config, workspace)
                finally:
                    phase_durations["workspace"] = time.monotonic() - phase_started
                phase = "solver_setup"
                phase_started = time.monotonic()
                try:
                    self._setup(
                        workspace,
                        log_dir,
                        stream_output=stream_output,
                        log_prefix="solver-setup",
                    )
                finally:
                    phase_durations["solver_setup"] = time.monotonic() - phase_started
                stage_public_tests(task, workspace)
                public_tests_before_solver = public_test_snapshot(task, workspace)

                adapter = adapter_for(config)
                telemetry_path = adapter.telemetry_path(home)
                if telemetry_path is not None:
                    telemetry_path.unlink(missing_ok=True)
                prompt = task.prompt_path.read_text(encoding="utf-8")
                if progress is not None:
                    progress("solving")
                phase = "solver"
                solver_started = time.monotonic()
                try:
                    solver = self.docker.run(
                        self.project.image.name,
                        adapter.command(prompt),
                        [Mount(workspace, "/workspace"), Mount(home, "/home/bench")],
                        adapter.environment(),
                        task.solver_timeout_seconds,
                        network="bridge",
                        stdout_path=log_dir / "solver.stdout.jsonl",
                        stderr_path=log_dir / "solver.stderr.log",
                        stream_output=stream_output,
                        secret_environment=prepared.secret_environment,
                    )
                    solver_duration_seconds = solver.duration_seconds
                finally:
                    if solver_duration_seconds is None:
                        solver_duration_seconds = time.monotonic() - solver_started
                    phase_durations["solver"] = solver_duration_seconds
                    (
                        public_test_modified_files,
                        public_test_deleted_files,
                    ) = public_test_mutations(public_tests_before_solver, workspace)
                    public_test_mutation_detected = bool(
                        public_test_modified_files or public_test_deleted_files
                    )
                telemetry = ""
                if telemetry_path is not None and telemetry_path.is_file():
                    telemetry = telemetry_path.read_text(encoding="utf-8")
                    shutil.copyfile(telemetry_path, log_dir / "solver.telemetry.jsonl")
                usage = adapter.parse_usage(solver.stdout, solver.stderr, telemetry)
                adapter.verify_solver(solver.stdout, solver.stderr)
                # Evaluate even after a nonzero solver exit: the workspace may
                # contain a correct completed change, but the run remains a solver failure.
                if solver.returncode:
                    solver_error = f"solver exited {solver.returncode}"

                if progress is not None:
                    progress("evaluating")
                phase = "evaluator_setup"
                phase_started = time.monotonic()
                try:
                    prepare_evaluator_workspace(workspace, evaluator_workspace)
                    self._setup(
                        evaluator_workspace,
                        log_dir,
                        stream_output=stream_output,
                        log_prefix="evaluator-setup",
                    )
                finally:
                    phase_durations["evaluator_setup"] = time.monotonic() - phase_started
                phase = "evaluator"
                (
                    public_evaluator,
                    public_evaluator_report,
                    evaluator,
                    evaluator_report,
                ) = self._evaluate(
                    task,
                    evaluator_workspace,
                    log_dir,
                    stream_output=stream_output,
                    phase_durations=phase_durations,
                )
                public_passed = public_evaluator.returncode == 0
                passed = public_passed and evaluator.returncode == 0 and solver.returncode == 0
                candidate_error = any(
                    report and report.candidate_error
                    for report in (public_evaluator_report, evaluator_report)
                )
                return RunResult(
                    task=task.id,
                    configuration=config.id,
                    repetition=repetition,
                    passed=passed,
                    duration_seconds=time.monotonic() - started,
                    task_digest=task_fingerprint,
                    configuration_digest=configuration_fingerprint,
                    experiment_id=experiment_id,
                    run_id=run_id,
                    log_directory=str(log_dir),
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    reasoning_tokens=usage.reasoning_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                    native_cost_usd=usage.native_cost_usd,
                    estimated_cost_usd=self._estimate(config, usage),
                    turns=usage.turns,
                    failure_kind=(
                        "solver"
                        if solver_error
                        else "candidate"
                        if candidate_error
                        else "incorrect"
                    )
                    if not passed
                    else None,
                    error=solver_error,
                    group_results=(evaluator_report.group_results if evaluator_report else {}),
                    public_test_results=(
                        public_evaluator_report.group_results
                        if public_evaluator_report
                        else {}
                    ),
                    public_test_mutation_detected=public_test_mutation_detected,
                    public_test_modified_files=public_test_modified_files,
                    public_test_deleted_files=public_test_deleted_files,
                    solver_duration_seconds=solver_duration_seconds,
                    phase_durations=phase_durations,
                )
        except BenchmarkError as exc:
            # Expected runner failures become data rows so the remaining matrix continues and
            # infrastructure failures remain distinguishable.
            return RunResult(
                task=task.id,
                configuration=config.id,
                repetition=repetition,
                passed=False,
                duration_seconds=time.monotonic() - started,
                task_digest=task_fingerprint,
                configuration_digest=configuration_fingerprint,
                experiment_id=experiment_id,
                run_id=run_id,
                log_directory=str(log_dir),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                reasoning_tokens=usage.reasoning_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
                native_cost_usd=usage.native_cost_usd,
                estimated_cost_usd=self._estimate(config, usage),
                turns=usage.turns,
                failure_kind=self._failure_kind(exc, phase),
                error=str(exc),
                public_test_mutation_detected=public_test_mutation_detected,
                public_test_modified_files=public_test_modified_files,
                public_test_deleted_files=public_test_deleted_files,
                solver_duration_seconds=solver_duration_seconds,
                phase_durations=phase_durations,
            )

    def run(
        self,
        task_filter: Optional[Union[str, Iterable[str]]] = None,
        configuration_filter: Optional[Union[str, Iterable[str]]] = None,
        repetitions: Optional[int] = None,
        jobs: int = DEFAULT_JOBS,
        verbose: bool = False,
        progress: Optional[Callable[[str], None]] = None,
    ) -> Iterable[RunResult]:
        """Execute matrix cells with bounded concurrency and emit atomic progress updates."""

        tasks = discover_tasks(self.project)
        configs = discover_configurations(self.project)
        if task_filter:
            requested_tasks = (
                [task_filter] if isinstance(task_filter, str) else list(task_filter)
            )
            requested_tasks = list(dict.fromkeys(requested_tasks))
            unknown_tasks = [task_id for task_id in requested_tasks if task_id not in tasks]
            if unknown_tasks:
                raise InfrastructureError(
                    "unknown task(s): " + ", ".join(unknown_tasks)
                )
            tasks = {task_id: tasks[task_id] for task_id in requested_tasks}
        if configuration_filter:
            requested = (
                [configuration_filter]
                if isinstance(configuration_filter, str)
                else list(configuration_filter)
            )
            requested = list(dict.fromkeys(requested))
            unknown = [config_id for config_id in requested if config_id not in configs]
            if unknown:
                raise InfrastructureError(
                    "unknown configuration(s): " + ", ".join(unknown)
                )
            configs = {config_id: configs[config_id] for config_id in requested}
        if not tasks:
            raise InfrastructureError("task filter matched no tasks")
        if not configs:
            raise InfrastructureError("configuration filter matched no configurations")
        if not isinstance(jobs, int) or isinstance(jobs, bool) or jobs <= 0:
            raise InfrastructureError("jobs must be a positive integer")
        count = repetitions or self.project.defaults.repetitions
        results_path = self.project.benchmark_dir / "results" / "runs.jsonl"
        experiment_id = _unique_id("experiment")
        experiment_results = []
        cells = [
            (task, config, repetition)
            for task in tasks.values()
            for config in configs.values()
            for repetition in range(1, count + 1)
        ]
        worker_count = 1 if verbose else min(jobs, len(cells))
        progress_lock = threading.Lock()

        def emit(message: str) -> None:
            """Serialize complete messages from workers before handing them to the caller."""

            if progress is None:
                return
            with progress_lock:
                progress(message)

        def label(index: int, task: TaskConfig, config: TreatmentConfig, repetition: int) -> str:
            """Keep compact labels for focused runs and unambiguous labels for matrices."""

            if len(tasks) == 1 and len(configs) == 1:
                return f"[r{repetition}]"
            return f"[{index}/{len(cells)} {task.id} · {config.id} · r{repetition}]"

        indexed_cells = [
            (index, task, config, repetition)
            for index, (task, config, repetition) in enumerate(cells, start=1)
        ]
        labels = {
            (task.id, config.id, repetition): label(index, task, config, repetition)
            for index, task, config, repetition in indexed_cells
        }

        def counted(value: int, singular: str) -> str:
            """Render compact counts without awkward parenthesized plurals."""

            suffix = "" if value == 1 else "s"
            return f"{value} {singular}{suffix}"

        if len(tasks) == 1 and len(configs) == 1:
            task = next(iter(tasks.values()))
            config = next(iter(configs.values()))
            emit(f"Running {task.id}")
            emit(f"Configuration: {config.id}")
            emit(
                f"Harness: {config.harness} · {counted(count, 'repetition')} · "
                f"{counted(worker_count, 'worker')}"
            )
        else:
            emit(
                f"Running {counted(len(cells), 'benchmark cell')} · "
                f"{counted(worker_count, 'worker')}"
            )
        emit("")

        def cell_progress(
            index: int, task: TaskConfig, config: TreatmentConfig, repetition: int
        ) -> Callable[[str], None]:
            """Attach stable cell identity to updates that may arrive out of order."""

            prefix = label(index, task, config, repetition)
            return lambda message: emit(f"{prefix} {message}")

        def record(result: RunResult) -> RunResult:
            """Keep shared result files on the coordinator thread to avoid write races."""

            append_result(results_path, result)
            experiment_results.append(result)
            prefix = labels[(result.task, result.configuration, result.repetition)]
            status = "PASS" if result.passed else "FAIL"
            detail = ""
            if not result.passed:
                reason = {
                    "incorrect": "requirements failed",
                    "solver": "solver",
                    "candidate": "candidate workspace",
                    "preflight": "preflight",
                    "setup": "setup",
                    "evaluator": "evaluator infrastructure",
                    "solver_timeout": "solver timeout",
                    "evaluator_timeout": "evaluator timeout",
                    "setup_timeout": "setup timeout",
                    "quota": "quota",
                }.get(
                    result.failure_kind or "incorrect",
                    result.failure_kind or "incorrect",
                )
                detail = f" · {reason}"
                if result.error:
                    detail += f": {result.error}"
            usage = ""
            if result.input_tokens or result.output_tokens:
                usage = (
                    f" · {result.input_tokens:,} input"
                    f" · {result.output_tokens:,} output"
                )
            group_detail = ""
            if result.public_test_results:
                group_detail += (
                    " · public "
                    f"{sum(result.public_test_results.values())}/{len(result.public_test_results)}"
                )
            if result.group_results:
                group_detail += (
                    f" · hidden {sum(result.group_results.values())}/{len(result.group_results)}"
                )
            if result.public_test_mutation_detected:
                group_detail += " · public tests modified"
            cost = result.native_cost_usd
            cost_kind = "native cost"
            if cost is None:
                cost = result.estimated_cost_usd
                cost_kind = "estimated cost"
            cost_detail = f" · ${cost:.4f} {cost_kind}" if cost is not None else ""
            emit(
                f"{prefix} {status} · {result.duration_seconds:.1f}s"
                f"{usage}{cost_detail}{group_detail}{detail}"
            )
            return result

        if worker_count == 1:
            for index, task, config, repetition in indexed_cells:
                yield record(
                    self.run_one(
                        task,
                        config,
                        repetition,
                        experiment_id,
                        verbose,
                        cell_progress(index, task, config, repetition),
                    )
                )

        else:
            # Concurrent container streams would interleave into unreadable terminal output. Each
            # cell still persists complete phase logs, while normalized results print as workers
            # finish.
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = [
                    executor.submit(
                        self.run_one,
                        task,
                        config,
                        repetition,
                        experiment_id,
                        False,
                        cell_progress(index, task, config, repetition),
                    )
                    for index, task, config, repetition in indexed_cells
                ]
                for future in as_completed(futures):
                    yield record(future.result())

        write_summary(
            self.project.benchmark_dir / "results" / "summary.md",
            experiment_id,
            experiment_results,
        )

    def validate_tasks(
        self,
        jobs: int = DEFAULT_JOBS,
        progress: Optional[Callable[[str], None]] = None,
    ) -> Iterable[ValidationReceipt]:
        """Validate distinct tasks concurrently while preserving each task's phase order."""

        tasks = discover_tasks(self.project)
        if not tasks:
            raise InfrastructureError("no tasks found")
        if not isinstance(jobs, int) or isinstance(jobs, bool) or jobs <= 0:
            raise InfrastructureError("jobs must be a positive integer")

        worker_count = min(jobs, len(tasks))
        progress_lock = threading.Lock()

        def emit(message: str) -> None:
            """Serialize progress callbacks emitted by concurrent validation workers."""

            if progress is not None:
                with progress_lock:
                    progress(message)

        task_label = "task" if len(tasks) == 1 else "tasks"
        worker_label = "worker" if worker_count == 1 else "workers"
        emit(f"Validating {len(tasks)} {task_label} with {worker_count} {worker_label}")
        if worker_count == 1:
            for task in tasks.values():
                yield self.validate_task(task, verbose=True, progress=emit)
            return

        # Each task owns a unique attempt tree and Docker container names are unique. Suppress live
        # output so concurrent setup and evaluator streams remain readable in their durable logs.
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(self.validate_task, task, False, emit)
                for task in tasks.values()
            ]
            for future in as_completed(futures):
                yield future.result()

    @staticmethod
    def _write_receipt(path: Path, receipt: ValidationReceipt) -> None:
        """Atomically replace a receipt so observers never parse partial JSON."""

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(asdict(receipt), sort_keys=True, indent=2) + "\n")
        os.replace(temporary, path)

    def validate_task(
        self,
        task: TaskConfig,
        verbose: bool = False,
        progress: Optional[Callable[[str], None]] = None,
    ) -> ValidationReceipt:
        """Persist fail-closed evidence for base failure and reference success."""

        if progress is not None:
            progress(f"[start] {task.id}")
        root = self.project.benchmark_dir / "results" / "validation" / task.id
        attempt_id = _unique_id("validation")
        attempt = root / attempt_id
        receipt_path = attempt / "receipt.json"
        image_id = self.docker.image_id(self.project.image.name)
        receipt = ValidationReceipt(
            version=1,
            attempt_id=attempt_id,
            task=task.id,
            task_digest=task_digest(task),
            environment_digest=validation_environment_digest(self.project, image_id),
            image={"name": self.project.image.name, "id": image_id},
            status="running",
            base=ValidationPhase(task.base_commit),
            reference=ValidationPhase(task.reference_commit),
            receipt_path=str(receipt_path.relative_to(self.project.benchmark_dir)),
        )
        self._write_receipt(receipt_path, receipt)
        try:
            for label, commit in (("base", task.base_commit), ("reference", task.reference_commit)):
                phase = getattr(receipt, label)
                phase_dir = attempt / label
                phase.logs = {
                    "setup_stdout": str((phase_dir / "setup.stdout.log").relative_to(attempt)),
                    "setup_stderr": str((phase_dir / "setup.stderr.log").relative_to(attempt)),
                    "evaluator_stdout": str((phase_dir / "evaluator.stdout.log").relative_to(attempt)),
                    "evaluator_stderr": str((phase_dir / "evaluator.stderr.log").relative_to(attempt)),
                }
                phase.logs.update(
                    {
                        "public_evaluator_stdout": str(
                            (phase_dir / "public-evaluator.stdout.log").relative_to(attempt)
                        ),
                        "public_evaluator_stderr": str(
                            (phase_dir / "public-evaluator.stderr.log").relative_to(attempt)
                        ),
                    }
                )
                with tempfile.TemporaryDirectory(prefix=f"agent-bench-{label}-") as temp:
                    workspace = Path(temp) / "workspace"
                    phase_started = time.monotonic()
                    try:
                        export_commit(self.project.root, commit, workspace)
                    finally:
                        phase.phase_durations["workspace"] = time.monotonic() - phase_started
                    try:
                        if progress is not None:
                            progress(f"[{label} setup] {task.id}")
                        phase_started = time.monotonic()
                        try:
                            self._setup(workspace, phase_dir, stream_output=verbose)
                        finally:
                            phase.phase_durations["setup"] = time.monotonic() - phase_started
                    except CommandTimeout:
                        phase.setup = "timed_out"
                        raise
                    except BenchmarkError:
                        phase.setup = "failed"
                        raise
                    phase.setup = "passed"
                    self._write_receipt(receipt_path, receipt)
                    (
                        public_result,
                        public_evaluator_report,
                        result,
                        evaluator_report,
                    ) = self._evaluate(
                        task,
                        workspace,
                        phase_dir,
                        stream_output=verbose,
                        progress=(
                            (
                                lambda suite: progress(
                                    f"[{label}{f' {suite}' if suite else ''} evaluator] {task.id}"
                                )
                            )
                            if progress is not None
                            else None
                        ),
                        phase_durations=phase.phase_durations,
                    )
                    reports = (public_evaluator_report, evaluator_report)
                    if label == "base" and any(
                        report and report.candidate_error for report in reports
                    ):
                        raise InfrastructureError(
                            "base evaluator reported a candidate workspace error instead of a "
                            "behavioral failure"
                        )
                    for suite_result in (public_result, result):
                        if suite_result is None or suite_result.returncode != 1:
                            continue
                        signature = _validation_infrastructure_signature(
                            suite_result.stdout, suite_result.stderr
                        )
                        if signature is not None:
                            raise InfrastructureError(
                                f"evaluator output indicates {signature}; "
                                "exit 1 cannot prove a behavioral failure"
                            )
                    phase.public_evaluator_exit = (
                        public_result.returncode if public_result is not None else None
                    )
                    phase.evaluator_exit = result.returncode
                    self._write_receipt(receipt_path, receipt)
            hidden_valid = (
                receipt.base.evaluator_exit == 1 and receipt.reference.evaluator_exit == 0
            )
            public_valid = (
                receipt.base.public_evaluator_exit == 1
                and receipt.reference.public_evaluator_exit == 0
            )
            receipt.status = "validated" if hidden_valid and public_valid else "invalid"
        except BaseException as exc:
            receipt.status = "infrastructure_error"
            receipt.error_category = (
                "timeout" if isinstance(exc, CommandTimeout) else "interrupted"
                if isinstance(exc, (KeyboardInterrupt, SystemExit))
                else "infrastructure"
            )
            self._write_receipt(receipt_path, receipt)
            self._write_receipt(root / "latest.json", receipt)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            return receipt
        self._write_receipt(receipt_path, receipt)
        self._write_receipt(root / "latest.json", receipt)
        return receipt
