"""Behavioral coverage for the skill-ready full-flow E2E fixture."""

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/create_full_flow_fixture.py"
COMMIT_TITLES = [
    "Create taskbox with add and list commands",
    "Add complete and remove operations",
    "Harden task state persistence",
    "Add transactional task editing",
    "Add task title search",
    "Add task summary reporting",
]


def run(*command: str, cwd: Path | None = None, env=None) -> subprocess.CompletedProcess:
    """Run a fixture command with captured output for useful assertion failures."""

    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def create(destination: Path) -> dict:
    """Create one fixture through its public command-line interface."""

    result = run(sys.executable, str(SCRIPT), "--destination", str(destination))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_generator_creates_deterministic_skill_ready_repository(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_metadata = create(first)
    second_metadata = create(second)

    assert first_metadata["repository"] == str(first)
    assert list(first_metadata["commits"]) == [
        "create-taskbox",
        "add-mutations",
        "harden-persistence",
        "transactional-editing",
        "add-search",
        "add-summary",
    ]
    assert first_metadata["commits"] == second_metadata["commits"]
    assert not (first / "benchmarks").exists()
    skill = Path(first_metadata["skill"])
    assert skill == first / ".agents/skills/bench-this"
    assert (skill / "SKILL.md").is_file()

    titles = run(
        "git", "log", "--reverse", "--format=%s", cwd=first
    )
    assert titles.returncode == 0, titles.stderr
    assert titles.stdout.splitlines() == COMMIT_TITLES
    assert run("git", "remote", cwd=first).stdout == ""
    assert run("git", "status", "--porcelain", cwd=first).stdout == ""
    assert (
        run(
            "git",
            "check-ignore",
            ".agents/skills/bench-this/SKILL.md",
            cwd=first,
        ).returncode
        == 0
    )
    assert run("git", "grep", "-i", "benchmark", cwd=first).returncode == 1
    tracked = run("git", "ls-files", cwd=first)
    assert tracked.returncode == 0, tracked.stderr
    assert not any(
        "__pycache__" in path or path.endswith((".pyc", ".pyo"))
        for path in tracked.stdout.splitlines()
    )

    project_tests = run(
        sys.executable, "-m", "unittest", "discover", "-s", "tests", cwd=first
    )
    assert project_tests.returncode == 0, project_tests.stderr

    store = tmp_path / "tasks.json"
    for arguments in (
        ("add", "first"),
        ("transaction", "begin"),
        ("transaction", "add", "second"),
        ("transaction", "complete", "1"),
        ("transaction", "commit"),
    ):
        result = run(
            sys.executable,
            "-m",
            "taskbox",
            "--store",
            str(store),
            *arguments,
            cwd=first,
        )
        assert result.returncode == 0, result.stderr

    listed = run(
        sys.executable,
        "-m",
        "taskbox",
        "--store",
        str(store),
        "list",
        "--json",
        cwd=first,
    )
    assert json.loads(listed.stdout) == [
        {"id": 1, "title": "first", "completed": True},
        {"id": 2, "title": "second", "completed": False},
    ]

    base = tmp_path / "candidate-base"
    reference = tmp_path / "candidate-reference"
    for path, revision in (
        (base, first_metadata["commits"]["harden-persistence"]),
        (reference, first_metadata["commits"]["transactional-editing"]),
    ):
        worktree = run(
            "git", "worktree", "add", "--detach", str(path), revision, cwd=first
        )
        assert worktree.returncode == 0, worktree.stderr

    base_probe = run(
        sys.executable,
        "-m",
        "taskbox",
        "--store",
        str(tmp_path / "base.json"),
        "transaction",
        "begin",
        cwd=base,
    )
    reference_probe = run(
        sys.executable,
        "-m",
        "taskbox",
        "--store",
        str(tmp_path / "reference.json"),
        "transaction",
        "begin",
        cwd=reference,
    )
    assert base_probe.returncode != 0
    assert reference_probe.returncode == 0, reference_probe.stderr


def test_generator_allocates_default_destination_and_refuses_nonempty(tmp_path):
    environment = {**os.environ, "TMPDIR": str(tmp_path)}
    generated = run(sys.executable, str(SCRIPT), env=environment)
    assert generated.returncode == 0, generated.stderr
    repository = Path(json.loads(generated.stdout)["repository"])
    assert repository.parent == tmp_path
    assert repository.is_dir()

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("keep\n", encoding="utf-8")
    rejected = run(
        sys.executable, str(SCRIPT), "--destination", str(occupied)
    )
    assert rejected.returncode != 0
    assert "refusing to overwrite non-empty" in rejected.stderr
    assert (occupied / "keep.txt").read_text(encoding="utf-8") == "keep\n"
