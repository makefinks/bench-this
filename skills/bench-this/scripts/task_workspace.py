#!/usr/bin/env python3
"""Prepare and safely accept isolated benchmark task-authoring workspaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


VERSION = 1
MARKER = ".agent-bench-task-workspace"
METADATA = "metadata.json"
EXCLUDED_INFRA = {"tasks", "configurations", "results", ".cache", "cache"}
TASK_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
DEFAULT_PUBLIC_TEST_COMMAND = "/bin/sh /public-tests/run.sh /workspace"
DEFAULT_TEST_COMMAND = "/bin/sh /evaluator/run.sh /workspace"
FORBIDDEN_EVALUATOR_PATTERNS = {
    "inspect.getsource": "product source inspection",
    "inspect.getsourcelines": "product source inspection",
    "sys.modules": "module-resolution reconstruction",
}


class WorkspaceError(RuntimeError):
    """Report a fail-closed workspace lifecycle error without a traceback."""


def _git(repo: Path, *args: str, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False
    )
    if check and result.returncode:
        raise WorkspaceError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def _validate_repository(repo: Path) -> Path:
    repo = repo.expanduser().resolve()
    if _git(repo, "rev-parse", "--is-inside-work-tree", check=False).strip() != b"true":
        raise WorkspaceError(f"not a Git worktree: {repo}")
    return repo


def _resolve(repo: Path, commit: str) -> str:
    return _git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}").decode().strip()


def _validate_commit_order(repo: Path, base: str, reference: str) -> None:
    """Reject inverted or unrelated task history before creating any scratch state."""

    if base == reference:
        raise WorkspaceError("base and reference commits must differ")
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", base, reference],
        capture_output=True,
        check=False,
    )
    if result.returncode == 1:
        raise WorkspaceError("reference commit must descend from base commit")
    if result.returncode:
        raise WorkspaceError(result.stderr.decode(errors="replace").strip())


def _hash_path(digest, label: bytes, path: Path) -> None:
    digest.update(len(label).to_bytes(8, "big") + label)
    data = path.read_bytes()
    digest.update(len(data).to_bytes(8, "big") + data)


def _protected_state(repo: Path) -> tuple[str, list[str]]:
    """Hash Git-visible target state without inspecting ignored files or secret values."""

    digest = hashlib.sha256()
    head = _git(repo, "rev-parse", "HEAD").strip()
    digest.update(b"HEAD\0" + head + b"\0")
    paths: list[str] = []
    for label, args in (
        (b"staged", ("diff", "--cached", "--binary")),
        (b"unstaged", ("diff", "--binary")),
    ):
        payload = _git(repo, *args)
        digest.update(label + len(payload).to_bytes(8, "big") + payload)
    raw = _git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    for item in sorted(filter(None, raw.split(b"\0"))):
        relative = item.decode("utf-8", errors="surrogateescape")
        if relative == "benchmarks/tasks" or relative.startswith("benchmarks/tasks/"):
            continue
        path = repo / relative
        if path.is_symlink() or not path.is_file():
            data = b"symlink:" + os.readlink(path).encode() if path.is_symlink() else b"other"
            digest.update(item + b"\0" + data)
        else:
            _hash_path(digest, item, path)
        paths.append(relative)
    status = _git(repo, "status", "--porcelain=v1", "-z").split(b"\0")
    paths.extend(
        entry[3:].decode("utf-8", errors="replace")
        for entry in status
        if entry and not entry[3:].startswith(b"benchmarks/tasks/")
    )
    return digest.hexdigest(), sorted(set(paths))


def _tree_digest(root: Path, excluded_top_level: set[str] | None = None) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return digest.hexdigest()
    excluded_top_level = excluded_top_level or set()
    for path in sorted(root.rglob("*")):
        if path.relative_to(root).parts[0] in excluded_top_level:
            continue
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            raise WorkspaceError(f"benchmark infrastructure contains symlink: {path}")
        digest.update(relative + (b"/" if path.is_dir() else b"\0"))
        if path.is_file():
            _hash_path(digest, relative, path)
    return digest.hexdigest()


def _copy_infrastructure(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise WorkspaceError(f"benchmark scaffold is missing: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if child.name in EXCLUDED_INFRA:
            continue
        target = destination / child.name
        if child.is_symlink():
            raise WorkspaceError(f"benchmark infrastructure contains symlink: {child}")
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def _initialize_task_bundle(output: Path, task: str, base: str, reference: str) -> None:
    """Create the deterministic task structure so workers author content, not boilerplate."""

    output.mkdir(parents=True)
    (output / "public").mkdir()
    public_tests = output / "public-tests"
    public_tests.mkdir()
    hidden = output / "hidden-tests"
    hidden.mkdir()
    (output / "prompt.md").write_text("", encoding="utf-8")
    for suite in (public_tests, hidden):
        evaluator = suite / "run.sh"
        evaluator.write_text("", encoding="utf-8")
        evaluator.chmod(0o755)
    (output / "task.yaml").write_text(
        "\n".join(
            (
                "version: 1",
                f"id: {task}",
                f"base_commit: {base}",
                f"reference_commit: {reference}",
                "prompt: prompt.md",
                "public_directory: public",
                "public_tests_directory: public-tests",
                f"public_test_command: {DEFAULT_PUBLIC_TEST_COMMAND}",
                "public_test_groups: []",
                "hidden_tests_directory: hidden-tests",
                f"test_command: {DEFAULT_TEST_COMMAND}",
                "requirement_groups: []",
                "",
            )
        ),
        encoding="utf-8",
    )


def _add_validation_worktree(worker: Path, destination: Path, commit: str) -> None:
    """Create a commit-specific checkout without disturbing the authoring clone."""

    result = subprocess.run(
        ["git", "-C", str(worker), "worktree", "add", "--detach", str(destination), commit],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise WorkspaceError(result.stderr.decode(errors="replace").strip())


def prepare(repo: Path, task: str, base: str, reference: str, scratch_root: Path | None) -> dict:
    if not TASK_PATTERN.fullmatch(task):
        raise WorkspaceError("task ID must use lowercase letters, digits, and hyphens")
    repo = _validate_repository(repo)
    base = _resolve(repo, base)
    reference = _resolve(repo, reference)
    _validate_commit_order(repo, base, reference)
    head = _resolve(repo, "HEAD")
    protected_digest, _ = _protected_state(repo)
    root = Path(tempfile.mkdtemp(prefix=f"agent-bench-{task}-", dir=scratch_root)).resolve()
    worker = root / "repository"
    try:
        subprocess.run(["git", "clone", "--shared", "--no-checkout", str(repo), str(worker)], check=True)
        _git(worker, "checkout", "--detach", head)
        shutil.rmtree(worker / "benchmarks", ignore_errors=True)
        _copy_infrastructure(repo / "benchmarks", worker / "benchmarks")
        output = worker / "benchmarks" / "tasks" / task
        _initialize_task_bundle(output, task, base, reference)
        base_repository = root / "base"
        reference_repository = root / "reference"
        _add_validation_worktree(worker, base_repository, base)
        _add_validation_worktree(worker, reference_repository, reference)
        infra_digest = _tree_digest(worker / "benchmarks", {"tasks"})
        metadata = {
            "version": VERSION,
            "repository": str(repo),
            "scratch": str(root),
            "worker_repository": str(worker),
            "base_repository": str(base_repository),
            "reference_repository": str(reference_repository),
            "output": str(output),
            "task": task,
            "base_commit": base,
            "reference_commit": reference,
            "head": head,
            "protected_digest": protected_digest,
            "infrastructure_digest": infra_digest,
            "accept_failed": False,
        }
        (root / MARKER).write_text("agent-bench-task-workspace-v1\n", encoding="utf-8")
        (root / METADATA).write_text(json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "worker_repository": str(worker),
            "base_repository": str(base_repository),
            "reference_repository": str(reference_repository),
            "output": str(output),
            "scratch": str(root),
        }
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


def _load_scratch(root: Path) -> dict:
    root = root.expanduser().resolve()
    if (root / MARKER).read_text(encoding="utf-8") != "agent-bench-task-workspace-v1\n":
        raise WorkspaceError(f"refusing unmarked scratch directory: {root}")
    data = json.loads((root / METADATA).read_text(encoding="utf-8"))
    if data.get("scratch") != str(root) or data.get("version") != VERSION:
        raise WorkspaceError("scratch metadata does not match this directory")
    return data


def _reject_symlinks(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            raise WorkspaceError(f"task bundle contains symlink: {path.relative_to(root)}")


def _reject_generated_cache_files(root: Path) -> None:
    """Keep interpreter caches out of the immutable task bundle accepted into the target."""

    generated = [
        path.relative_to(root)
        for path in root.rglob("*")
        if "__pycache__" in path.relative_to(root).parts
        or (path.is_file() and path.suffix in {".pyc", ".pyo"})
    ]
    if generated:
        rendered = ", ".join(str(path) for path in generated[:5])
        raise WorkspaceError(
            f"task bundle contains generated Python cache files: {rendered}; "
            "remove them before the final check"
        )


def _reject_forbidden_evaluator_techniques(evaluator_directory: Path) -> None:
    """Reject high-confidence implementation checks and synthetic module environments."""

    findings: list[str] = []
    for path in sorted(evaluator_directory.rglob("*")):
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern, reason in FORBIDDEN_EVALUATOR_PATTERNS.items():
            if pattern in content:
                findings.append(f"{path.relative_to(evaluator_directory)}: {reason} ({pattern})")
    if findings:
        raise WorkspaceError("forbidden evaluator technique: " + "; ".join(findings))


def _manifest_groups(manifest: Path, key: str = "requirement_groups") -> list[str]:
    """Read and validate the small manifest subset needed by acceptance guards."""

    lines = manifest.read_text(encoding="utf-8").splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.startswith(f"{key}:"))
    except StopIteration as exc:
        raise WorkspaceError(f"task manifest is missing {key}") from exc
    groups = []
    for line in lines[start + 1 :]:
        if not line.startswith("  - "):
            break
        groups.append(line[4:].strip())
    if not groups or any(not TASK_PATTERN.fullmatch(group) for group in groups):
        raise WorkspaceError(f"{key} must contain lowercase hyphenated IDs")
    if len(groups) != len(set(groups)):
        raise WorkspaceError(f"{key} must be unique")
    return groups


def _require_prompt_group_sections(prompt: Path, groups: list[str]) -> None:
    """Make each scored outcome findable as an explicit public-contract section."""

    headings = set()
    for line in prompt.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"#{2,6}\s+`?([a-z0-9][a-z0-9-]{0,62})`?", line.strip())
        if match:
            headings.add(match.group(1))
    missing = [group for group in groups if group not in headings]
    if missing:
        raise WorkspaceError(
            "prompt must contain an exact Markdown heading for every requirement group: "
            + ", ".join(missing)
        )


def _require_group_scoring(test_directory: Path, label: str) -> None:
    """Require each scored suite to emit the structured result protocol."""

    if not any(
        "AGENT_BENCH_RESULT:" in path.read_text(encoding="utf-8", errors="ignore")
        for path in test_directory.rglob("*")
        if path.is_file()
    ):
        raise WorkspaceError(f"{label} must emit the AGENT_BENCH_RESULT protocol")


def _write_metadata(data: dict) -> None:
    """Persist lifecycle state inside the helper-owned scratch directory."""

    root = Path(data["scratch"])
    (root / METADATA).write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


def _check(data: dict) -> dict:
    """Validate a bundle and its acceptance guards without changing either workspace."""

    repo = _validate_repository(Path(data["repository"]))
    current, changed = _protected_state(repo)
    if current != data["protected_digest"]:
        details = ", ".join(changed) or "Git state"
        raise WorkspaceError(
            f"target protected state changed: {details}; preserve this scratch workspace and "
            "restore or re-prepare the protected target state, never copy the task bundle manually"
        )
    output = Path(data["output"])
    _reject_symlinks(output)
    _reject_generated_cache_files(output)
    for name in ("task.yaml", "prompt.md", "public", "public-tests", "hidden-tests"):
        path = output / name
        if not path.exists() or (
            name in {"public", "public-tests", "hidden-tests"} and not path.is_dir()
        ):
            raise WorkspaceError(f"task bundle is missing required path: {name}")
    manifest = output / "task.yaml"
    if not (output / "prompt.md").read_text(encoding="utf-8").strip():
        raise WorkspaceError("task prompt is empty")
    for relative, label in (
        ("public-tests/run.sh", "public test entrypoint"),
        ("hidden-tests/run.sh", "hidden evaluator entrypoint"),
    ):
        evaluator = output / relative
        if not evaluator.is_file() or not evaluator.read_text(encoding="utf-8").strip():
            raise WorkspaceError(f"{label} is empty: {relative}")
    public_test_keys = (
        "public_tests_directory:",
        "public_test_command:",
        "public_test_groups:",
    )
    manifest_text = manifest.read_text(encoding="utf-8")
    missing_public_test_keys = [key for key in public_test_keys if key not in manifest_text]
    if missing_public_test_keys:
        raise WorkspaceError(
            "authored tasks require public tests; missing " + ", ".join(missing_public_test_keys)
        )
    groups = _manifest_groups(manifest)
    _manifest_groups(manifest, "public_test_groups")
    _require_prompt_group_sections(output / "prompt.md", groups)
    for directory, label in (
        (output / "public-tests", "public test suite"),
        (output / "hidden-tests", "hidden evaluator"),
    ):
        _reject_forbidden_evaluator_techniques(directory)
        _require_group_scoring(directory, label)
    task_line = next((line for line in manifest.read_text().splitlines() if line.startswith("id:")), "")
    if task_line.partition(":")[2].strip().strip("'\"") != data["task"]:
        raise WorkspaceError("task manifest ID does not match assigned task")
    worker_bench = Path(data["worker_repository"]) / "benchmarks"
    if _tree_digest(worker_bench, {"tasks"}) != data["infrastructure_digest"]:
        raise WorkspaceError(
            "worker modified shared benchmark infrastructure; preserve this scratch workspace and "
            "fix the worker bundle, never copy the task bundle manually"
        )
    destination = repo / "benchmarks" / "tasks" / data["task"]
    if destination.exists() and any(destination.iterdir()):
        raise WorkspaceError(f"refusing to overwrite existing task: {destination}")
    return {
        "checked": True,
        "task": data["task"],
        "scratch": data["scratch"],
        "destination": str(destination),
    }


def check(root: Path) -> dict:
    """Run repeatable, read-only validation before the one-shot acceptance attempt."""

    return _check(_load_scratch(root))


def _accept_once(data: dict) -> dict:
    checked = _check(data)
    output = Path(data["output"])
    destination = Path(checked["destination"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{data['task']}-", dir=destination.parent) as temp:
        staged = Path(temp) / data["task"]
        shutil.copytree(output, staged)
        os.replace(staged, destination)
    return {"accepted": True, "task": data["task"], "changed_paths": [], "destination": str(destination)}


def accept(root: Path) -> dict:
    """Accept a reviewed bundle once; any failed attempt permanently closes the guard."""

    data = _load_scratch(root)
    if data.get("accept_failed"):
        raise WorkspaceError(
            "a previous accept attempt failed; preserve this scratch workspace for diagnosis and "
            "prepare a new workspace instead of repairing or retrying it"
        )
    try:
        return _accept_once(data)
    except (WorkspaceError, OSError, ValueError, subprocess.SubprocessError):
        data["accept_failed"] = True
        _write_metadata(data)
        raise


def discard(root: Path) -> dict:
    data = _load_scratch(root)
    shutil.rmtree(data["scratch"])
    return {"discarded": True, "scratch": data["scratch"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("repository", type=Path)
    prep.add_argument("task")
    prep.add_argument("base_commit")
    prep.add_argument("reference_commit")
    prep.add_argument("--scratch-root", type=Path)
    for command in ("check", "accept", "discard"):
        child = commands.add_parser(command)
        child.add_argument("scratch", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.repository, args.task, args.base_commit, args.reference_commit, args.scratch_root)
        elif args.command == "check":
            result = check(args.scratch)
        elif args.command == "accept":
            result = accept(args.scratch)
        else:
            result = discard(args.scratch)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (WorkspaceError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
