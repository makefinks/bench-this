"""Minimal Docker CLI wrapper with explicit mounts, environment, and cleanup."""

import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .errors import CommandTimeout, InfrastructureError
from .models import CommandResult


def diagnose_output(stdout: str, stderr: str) -> Optional[str]:
    """Recognize common provider failures without echoing credential-bearing logs."""

    combined = f"{stdout}\n{stderr}".lower()
    if "usage limit" in combined or "quota" in combined:
        return "quota or usage limit detected"
    if "rate limit" in combined or "too many requests" in combined:
        return "rate limit detected"
    if "unauthorized" in combined or "authentication" in combined or "invalid api key" in combined:
        return "authentication failure detected"
    if "model not found" in combined or "unknown model" in combined:
        return "configured model is unavailable"
    return None


@dataclass(frozen=True)
class Mount:
    """One bind mount whose host path is resolved immediately before use."""

    source: Path
    target: str
    readonly: bool = False


class DockerEngine:
    """Run short-lived hardened containers without mounting the Docker socket."""

    def __init__(self, executable: str = "docker"):
        self.executable = executable

    def build(self, image: str, dockerfile: Path, context: Path) -> None:
        """Build the single project image and preserve Docker's diagnostic output."""

        result = subprocess.run(
            [self.executable, "build", "-t", image, "-f", str(dockerfile), str(context)],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise InfrastructureError(f"Docker build failed: {result.stderr.strip()}")

    def server_version(self) -> str:
        """Return the Docker server version or raise an actionable availability error."""

        try:
            result = subprocess.run(
                [self.executable, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise InfrastructureError(f"Docker executable not found: {self.executable}") from exc
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or "Docker is not responding"
            raise InfrastructureError(f"Docker is unavailable: {detail}")
        return result.stdout.strip()

    def image_exists(self, image: str) -> bool:
        """Check whether the configured benchmark image exists locally."""

        try:
            result = subprocess.run(
                [self.executable, "image", "ls", "--quiet", image],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise InfrastructureError(
                f"Docker executable not found: {self.executable}"
            ) from exc
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or "Docker image lookup failed"
            raise InfrastructureError(f"Docker image lookup failed for {image!r}: {detail}")
        return bool(result.stdout.strip())

    def image_id(self, image: str) -> str:
        """Resolve a mutable image name to Docker's immutable content identity."""

        result = subprocess.run(
            [self.executable, "image", "inspect", "--format", "{{.Id}}", image],
            capture_output=True,
            text=True,
        )
        if result.returncode or not result.stdout.strip().startswith("sha256:"):
            detail = result.stderr.strip() or result.stdout.strip() or "image not found"
            raise InfrastructureError(f"cannot resolve image identity for {image!r}: {detail}")
        return result.stdout.strip()

    def run(
        self,
        image: str,
        command: List[str],
        mounts: Iterable[Mount],
        environment: Dict[str, str],
        timeout_seconds: Optional[int],
        network: Optional[str] = None,
        workdir: str = "/workspace",
        stdout_path: Optional[Path] = None,
        stderr_path: Optional[Path] = None,
        stream_output: bool = False,
        secret_environment: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """Run a container while teeing output to durable logs and optional live output."""

        name = f"agent-bench-{uuid.uuid4().hex[:12]}"
        # The solver still needs normal process and filesystem access inside its
        # mounts, but it does not need Linux capabilities or privilege escalation.
        args = [
            self.executable,
            "run",
            "--rm",
            "--name",
            name,
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=512",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--workdir",
            workdir,
        ]
        if network:
            args.extend(["--network", network])
        for mount in mounts:
            source = mount.source.resolve()
            if not source.exists():
                raise InfrastructureError(f"mount source does not exist: {source}")
            suffix = ",readonly" if mount.readonly else ""
            args.extend(
                ["--mount", f"type=bind,source={source},target={mount.target}{suffix}"]
            )
        # Docker receives an explicit allowlist; host API keys are never inherited.
        for key, value in sorted(environment.items()):
            args.extend(["--env", f"{key}={value}"])
        secret_environment = secret_environment or {}
        overlap = set(environment) & set(secret_environment)
        if overlap:
            raise InfrastructureError(
                "secret environment duplicates ordinary environment: "
                + ", ".join(sorted(overlap))
            )
        # Passing only the variable name keeps secret values out of Docker's
        # process arguments while forwarding them from the controlled CLI process.
        for key in sorted(secret_environment):
            args.extend(["--env", key])
        args.append(image)
        args.extend(command)
        for path in (stdout_path, stderr_path):
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        stdout_chunks: List[str] = []
        stderr_chunks: List[str] = []
        stdout_handle = stdout_path.open("w", encoding="utf-8") if stdout_path else None
        stderr_handle = stderr_path.open("w", encoding="utf-8") if stderr_path else None

        def consume(pipe, chunks, log_handle, live_handle) -> None:
            """Drain one process pipe so stdout and stderr cannot block each other."""

            for line in iter(pipe.readline, ""):
                chunks.append(line)
                if log_handle is not None:
                    log_handle.write(line)
                    log_handle.flush()
                if stream_output:
                    live_handle.write(line)
                    live_handle.flush()
            pipe.close()

        try:
            process_environment = None
            if secret_environment:
                process_environment = os.environ.copy()
                process_environment.update(secret_environment)
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=process_environment,
            )
        except (FileNotFoundError, OSError) as exc:
            if stdout_handle:
                stdout_handle.close()
            if stderr_handle:
                stderr_handle.close()
            raise InfrastructureError(f"failed to start Docker: {exc}") from exc

        stdout_thread = threading.Thread(
            target=consume,
            args=(process.stdout, stdout_chunks, stdout_handle, sys.stdout),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=consume,
            args=(process.stderr, stderr_chunks, stderr_handle, sys.stderr),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        timed_out = False
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            # `--rm` only acts after normal termination, so timed-out containers
            # require an explicit removal before the evaluator may start.
            try:
                removal = subprocess.run(
                    [self.executable, "rm", "-f", name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                process.kill()
            else:
                if removal.returncode:
                    process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        finally:
            stdout_thread.join()
            stderr_thread.join()
            if stdout_handle:
                stdout_handle.close()
            if stderr_handle:
                stderr_handle.close()

        stdout = "".join(stdout_chunks)
        stderr = "".join(stderr_chunks)
        if timed_out:
            diagnosis = diagnose_output(stdout, stderr) or "no specific provider error detected"
            locations = ", ".join(str(path) for path in (stdout_path, stderr_path) if path)
            suffix = f"; logs: {locations}" if locations else ""
            raise CommandTimeout(
                f"container exceeded {timeout_seconds} seconds; {diagnosis}{suffix}"
            )
        return CommandResult(
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=time.monotonic() - started,
        )

    def run_interactive(
        self,
        image: str,
        command: List[str],
        mounts: Iterable[Mount],
        environment: Dict[str, str],
    ) -> None:
        """Run source-free device login while persisting only the selected home."""

        args = [
            self.executable,
            "run",
            "--rm",
            "-it",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=512",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--workdir",
            "/home/bench",
            "--network",
            "bridge",
        ]
        for mount in mounts:
            source = mount.source.resolve()
            if not source.exists():
                raise InfrastructureError(f"mount source does not exist: {source}")
            args.extend(["--mount", f"type=bind,source={source},target={mount.target}"])
        for key, value in sorted(environment.items()):
            args.extend(["--env", f"{key}={value}"])
        args.extend([image, *command])
        if subprocess.call(args) != 0:
            raise InfrastructureError("interactive authentication command failed")
