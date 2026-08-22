#!/usr/bin/env python3
"""Create a disposable, skill-ready repository for the full-flow E2E workflow."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/full-flow-taskbox"
SKILL = ROOT / "skills/bench-this"
COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache")


def _git(repository: Path, *arguments: str, environment=None) -> str:
    """Run Git and retain enough output to diagnose fixture preparation failures."""

    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout.strip()


def _commit(repository: Path, commit: dict, author: dict) -> str:
    """Create one reproducible commit from the currently staged fixture tree."""

    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": author["name"],
        "GIT_AUTHOR_EMAIL": author["email"],
        "GIT_AUTHOR_DATE": commit["date"],
        "GIT_COMMITTER_NAME": author["name"],
        "GIT_COMMITTER_EMAIL": author["email"],
        "GIT_COMMITTER_DATE": commit["date"],
    }
    _git(repository, "add", "--all")
    _git(
        repository,
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        commit["title"],
        environment=environment,
    )
    return _git(repository, "rev-parse", "HEAD")


def _install_skill(repository: Path) -> Path:
    """Install the current skill without adding developer tooling to project history."""

    destination = repository / ".agents/skills/bench-this"
    shutil.copytree(SKILL, destination, ignore=COPY_IGNORE)
    exclude = repository / ".git/info/exclude"
    existing = exclude.read_text(encoding="utf-8")
    rule = "/.agents/\n"
    if rule not in existing.splitlines(keepends=True):
        exclude.write_text(existing + rule, encoding="utf-8")
    return destination


def create_fixture(destination: Path) -> dict:
    """Materialize Taskbox history and return its path and stable commit identities."""

    destination = destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"refusing to overwrite non-empty {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((FIXTURE / "commits.json").read_text(encoding="utf-8"))
    commits = manifest["commits"]
    shutil.copytree(
        FIXTURE / "initial",
        destination,
        dirs_exist_ok=True,
        ignore=COPY_IGNORE,
    )
    _git(destination, "init", "-q", "--initial-branch=main")
    _git(destination, "config", "core.autocrlf", "false")
    _git(destination, "config", "core.filemode", "true")

    identities = {commits[0]["id"]: _commit(destination, commits[0], manifest["author"])}
    for commit in commits[1:]:
        patch = FIXTURE / commit["patch"]
        _git(destination, "apply", "--whitespace=error-all", str(patch))
        identities[commit["id"]] = _commit(destination, commit, manifest["author"])

    skill = _install_skill(destination)

    return {
        "repository": str(destination),
        "commits": identities,
        "head": identities[commits[-1]["id"]],
        "skill": str(skill),
    }


def main() -> int:
    """Parse the bootstrap interface and print its machine-readable handoff."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    arguments = parser.parse_args()
    destination = arguments.destination
    if destination is None:
        destination = Path(tempfile.mkdtemp(prefix="bench-this-full-flow-"))
    try:
        metadata = create_fixture(destination)
    except (OSError, RuntimeError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"error preparing {destination.expanduser().resolve()}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(metadata))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
