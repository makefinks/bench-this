#!/usr/bin/env python3
"""Copy the skill's self-contained benchmark template into a repository."""

import argparse
import hashlib
import re
import shutil
from pathlib import Path


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
    source = Path(__file__).resolve().parent.parent / "assets" / "benchmarks"
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


def main() -> int:
    """Parse the target repository and report the created benchmark path."""

    parser = argparse.ArgumentParser()
    parser.add_argument("project", nargs="?", default=".", type=Path)
    arguments = parser.parse_args()
    print(f"Created {scaffold(arguments.project)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
