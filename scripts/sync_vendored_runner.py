#!/usr/bin/env python3
"""Synchronize canonical runner sources and scaffold files into skill assets."""

import argparse
import filecmp
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "agent_bench"
VENDOR = ROOT / "skills/bench-this/assets/benchmarks/_vendor/agent_bench"
SCAFFOLD = ROOT / "skills/bench-this/assets/benchmarks"
IGNORED = {"__pycache__", ".pytest_cache"}


def _files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file()
        and not any(part in IGNORED for part in path.relative_to(root).parts)
        and path.suffix not in {".pyc", ".pyo"}
    }


def _different(source: Path, destination: Path) -> list[str]:
    source_files = _files(source)
    destination_files = _files(destination) if destination.exists() else set()
    changed = [str(path) for path in sorted(source_files ^ destination_files)]
    changed.extend(
        str(path)
        for path in sorted(source_files & destination_files)
        if not filecmp.cmp(source / path, destination / path, shallow=False)
    )
    return changed


def _replace_tree(source: Path, destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}-", dir=destination.parent) as temp:
        staged = Path(temp) / destination.name
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns(*IGNORED, "*.pyc", "*.pyo"))
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(staged, destination)


def _sync_scaffold(check: bool) -> list[str]:
    source = SOURCE / "template" / "benchmarks"
    changes = []
    for relative in sorted(_files(source)):
        destination = SCAFFOLD / relative
        if not destination.is_file() or not filecmp.cmp(source / relative, destination, shallow=False):
            changes.append(f"scaffold/{relative}")
            if not check:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, destination)
    expected = _files(source)
    for relative in sorted(_files(SCAFFOLD)):
        if relative.parts[0] == "_vendor":
            continue
        if relative not in expected:
            changes.append(f"scaffold/{relative}")
            if not check:
                (SCAFFOLD / relative).unlink()
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changes = [f"vendor/{path}" for path in _different(SOURCE, VENDOR)]
    changes.extend(_sync_scaffold(args.check))
    if args.check:
        if changes:
            print("vendored runner drift:\n" + "\n".join(changes), file=sys.stderr)
            return 1
        return 0
    if changes:
        _replace_tree(SOURCE, VENDOR)
        _sync_scaffold(False)
    print(f"Synchronized {len(changes)} changed path(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
