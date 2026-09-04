#!/usr/bin/env python3
"""Copy the skill's self-contained benchmark template into a repository."""

import argparse
import hashlib
import re
import shutil
from pathlib import Path


def _asset_root() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "benchmarks"


def _image_name(project_root: Path) -> str:
    """Create a stable local image tag that cannot collide with another checkout."""

    slug = re.sub(r"[^a-z0-9]+", "-", project_root.name.lower()).strip("-") or "project"
    digest = hashlib.sha256(str(project_root).encode()).hexdigest()[:8]
    return f"agent-bench-{slug[:40].rstrip('-')}-{digest}"


def _set_image_name(destination: Path, project_root: Path) -> None:
    manifest = destination / "benchmark.yaml"
    text = manifest.read_text(encoding="utf-8")
    marker = "  name: project-agent-benchmark\n"
    if text.count(marker) != 1:
        raise RuntimeError(f"benchmark template has an unexpected image declaration: {manifest}")
    manifest.write_text(text.replace(marker, f"  name: {_image_name(project_root)}\n"), encoding="utf-8")


def scaffold(project_root: Path) -> Path:
    """Create benchmarks/ without depending on an installed agent-bench package."""

    project_root = project_root.expanduser().resolve()
    source = _asset_root()
    destination = project_root / "benchmarks"
    if not source.is_dir():
        raise RuntimeError(f"bundled benchmark template is missing: {source}")
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"refusing to overwrite non-empty {destination}")

    shutil.copytree(source, destination, dirs_exist_ok=True)
    _set_image_name(destination, project_root)
    for relative in (
        "run.py",
        "setup.sh",
        "tasks/example/hidden-tests/run.sh",
    ):
        path = destination / relative
        if path.exists():
            path.chmod(0o755)
    return destination


def remove_scaffold_example(project_root: Path) -> bool:
    """Remove the example only while its complete tree still matches the bundled scaffold."""

    project_root = project_root.expanduser().resolve()
    expected = _asset_root() / "tasks" / "example"
    actual = project_root / "benchmarks" / "tasks" / "example"
    if not actual.exists():
        return False
    expected_files = {
        path.relative_to(expected): path.read_bytes()
        for path in expected.rglob("*")
        if path.is_file()
    }
    actual_files = {
        path.relative_to(actual): path.read_bytes()
        for path in actual.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise RuntimeError(
            f"refusing to remove modified or partial scaffold example: {actual}"
        )
    shutil.rmtree(actual)
    return True


def main() -> int:
    """Parse the target repository and report the created benchmark path."""

    parser = argparse.ArgumentParser()
    parser.add_argument("project", nargs="?", default=".", type=Path)
    parser.add_argument("--remove-example", action="store_true")
    arguments = parser.parse_args()
    if arguments.remove_example:
        action = "Removed" if remove_scaffold_example(arguments.project) else "No example at"
        print(f"{action} {arguments.project.expanduser().resolve() / 'benchmarks/tasks/example'}")
    else:
        print(f"Created {scaffold(arguments.project)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
