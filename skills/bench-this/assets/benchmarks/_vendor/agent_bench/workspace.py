"""Create sanitized historical workspaces and disposable harness homes."""

import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Dict

from .errors import ConfigurationError, InfrastructureError
from .models import ProjectConfig, TaskConfig, TreatmentConfig


PUBLIC_TESTS_WORKSPACE_DIRECTORY = ".agent-bench-public-tests"


def _reject_symlinks(root: Path, label: str) -> None:
    """Prevent benchmark-owned files from smuggling host paths into a container."""

    if not root.exists():
        return
    if root.is_symlink():
        raise ConfigurationError(f"{label} is a symlink: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ConfigurationError(f"{label} contains a symlink: {path}")


def copy_contents(source: Path, destination: Path, label: str) -> None:
    """Overlay a trusted directory while rejecting symlink-based path escapes."""

    if not source.exists():
        return
    if not source.is_dir():
        raise ConfigurationError(f"{label} must be a directory: {source}")
    _reject_symlinks(source, label)
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        # Git placeholders preserve intentionally empty configuration directories but
        # must not become solver-visible workspace or harness files.
        if child.name == ".gitkeep":
            continue
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(
                child,
                target,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".gitkeep"),
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)


def export_commit(repository: Path, commit: str, destination: Path) -> None:
    """Export a commit without Git metadata and remove historical benchmark files."""

    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar") as archive:
        result = subprocess.run(
            ["git", "archive", "--format=tar", f"--output={archive.name}", commit],
            cwd=str(repository),
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise InfrastructureError(
                f"git archive failed for {commit}: {result.stderr.strip()}"
            )
        with tarfile.open(archive.name) as tar:
            # Validate every member before extraction so a partial unsafe tree is
            # never left behind if a malformed archive path is encountered.
            root = destination.resolve()
            for member in tar.getmembers():
                target = (destination / member.name).resolve()
                if os.path.commonpath((str(root), str(target))) != str(root):
                    raise InfrastructureError(f"unsafe archive member: {member.name}")
            tar.extractall(destination)
    shutil.rmtree(destination / "benchmarks", ignore_errors=True)
    assert_sanitized_workspace(destination)


def assert_sanitized_workspace(workspace: Path) -> None:
    """Fail closed if source history or benchmark-private files survived export."""

    forbidden = []
    for path in workspace.rglob("*"):
        if path.name == ".git" or path.relative_to(workspace).parts[0] == "benchmarks":
            forbidden.append(path)
    if forbidden:
        names = ", ".join(str(path.relative_to(workspace)) for path in forbidden[:5])
        raise InfrastructureError(f"snapshot contains private benchmark metadata: {names}")


def prepare_workspace(project: ProjectConfig, task: TaskConfig, config: TreatmentConfig, destination: Path) -> None:
    """Build the exact solver-visible tree from history plus public overlays."""

    export_commit(project.root, task.base_commit, destination)
    copy_contents(config.workspace_config, destination, "workspace_config")
    copy_contents(task.public_directory, destination, "public_directory")
    assert_sanitized_workspace(destination)


def stage_public_tests(task: TaskConfig, destination: Path) -> None:
    """Expose an exact public-test copy after setup and immediately before solving."""

    public_tests = destination / PUBLIC_TESTS_WORKSPACE_DIRECTORY
    if public_tests.exists():
        raise ConfigurationError(
            f"reserved public test path already exists: {PUBLIC_TESTS_WORKSPACE_DIRECTORY}"
        )
    copy_contents(task.public_tests_directory, public_tests, "public_tests_directory")


def prepare_evaluator_workspace(candidate: Path, destination: Path) -> None:
    """Create a disposable candidate copy for isolated evaluator setup."""

    # Preserve links rather than following a solver-created link outside the workspace.
    shutil.copytree(candidate, destination, symlinks=True)
    shutil.rmtree(destination / PUBLIC_TESTS_WORKSPACE_DIRECTORY, ignore_errors=True)


def public_test_snapshot(task: TaskConfig, workspace: Path) -> Dict[str, bytes]:
    """Capture supplied test files immediately before the solver can edit them."""

    visible = workspace / PUBLIC_TESTS_WORKSPACE_DIRECTORY
    return {
        path.relative_to(visible).as_posix(): path.read_bytes()
        for path in sorted(visible.rglob("*"))
        if path.is_file()
    }


def public_test_mutations(
    snapshot: Dict[str, bytes], workspace: Path
) -> tuple[list[str], list[str]]:
    """Report supplied public test files changed or deleted by the solver."""

    visible = workspace / PUBLIC_TESTS_WORKSPACE_DIRECTORY
    modified = []
    deleted = []
    for relative, content in snapshot.items():
        target = visible / relative
        if not target.is_file():
            deleted.append(relative)
        elif content != target.read_bytes():
            modified.append(relative)
    return modified, deleted


