"""Create deterministic identities for effective task and treatment inputs."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from .models import HarnessConfig, ProjectConfig, TaskConfig


def _frame(digest: "hashlib._Hash", label: str, payload: bytes) -> None:
    """Hash labeled, length-delimited bytes so different input layouts cannot collide."""

    digest.update(label.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(len(payload)).encode("ascii"))
    digest.update(b"\0")
    digest.update(payload)


def _hash_tree(digest: "hashlib._Hash", label: str, root: Path) -> None:
    """Hash a file or directory by relative paths, entry types, and contents."""

    if not root.exists() and not root.is_symlink():
        _frame(digest, label, b"missing")
        return
    entries = [root] if not root.is_dir() else [root, *sorted(root.rglob("*"))]
    for path in entries:
        relative = "." if path == root else path.relative_to(root).as_posix()
        entry_label = f"{label}/{relative}"
        if path.is_symlink():
            _frame(digest, entry_label, b"symlink\0" + path.readlink().as_posix().encode())
        elif path.is_dir():
            _frame(digest, entry_label, b"directory")
        else:
            _frame(digest, entry_label, b"file\0" + path.read_bytes())


def _digest(metadata: Dict[str, Any], trees: Dict[str, Path]) -> str:
    digest = hashlib.sha256()
    _frame(
        digest,
        "metadata",
        json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    )
    for label, root in sorted(trees.items()):
        _hash_tree(digest, label, root)
    return digest.hexdigest()


def task_digest(task: TaskConfig) -> str:
    """Identify every effective task input, including private evaluation artifacts."""

    return _digest(
        {
            "id": task.id,
            "base_commit": task.base_commit,
            "reference_commit": task.reference_commit,
            "test_command": task.test_command,
            "solver_timeout_seconds": task.solver_timeout_seconds,
            "requirement_groups": task.requirement_groups,
            "public_test_command": task.public_test_command,
            "public_test_groups": task.public_test_groups,
        },
        {
            "prompt": task.prompt_path,
            "public": task.public_directory,
            "public_tests": task.public_tests_directory,
            "hidden_tests": task.hidden_tests_directory,
        },
    )


def configuration_digest(config: HarnessConfig) -> str:
    """Identify the complete effective treatment without hashing credential contents."""

    return _digest(
        {
            "id": config.id,
            "harness": config.harness,
            "provider": config.provider,
            "model": config.model,
            "agent": config.agent,
            "region": config.region,
            "auth_profile": config.auth_profile,
            "arguments": config.arguments,
        },
        {
            "harness": config.harness_config,
            "workspace": config.workspace_config,
        },
    )


def validation_environment_digest(project: ProjectConfig, image_id: str) -> str:
    """Identify immutable validation runtime inputs without hashing credentials."""

    return _digest(
        {
            "image_id": image_id,
            "setup_command": project.setup_command,
            "setup_timeout_seconds": project.defaults.setup_timeout_seconds,
            "evaluator_timeout_seconds": project.defaults.evaluator_timeout_seconds,
        },
        {"setup": project.benchmark_dir / "setup.sh"},
    )
