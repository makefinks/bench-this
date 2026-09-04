import subprocess
import sys
from pathlib import Path


SCRIPT = Path("skills/bench-this/scripts/scaffold.py").resolve()


def run(*args: object):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
    )


def test_remove_example_requires_complete_unchanged_scaffold(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    assert run(project).returncode == 0
    example = project / "benchmarks/tasks/example"

    removed = run("--remove-example", project)

    assert removed.returncode == 0
    assert not example.exists()

    second = tmp_path / "modified"
    second.mkdir()
    assert run(second).returncode == 0
    modified_example = second / "benchmarks/tasks/example"
    (modified_example / "prompt.md").write_text("user content\n", encoding="utf-8")

    rejected = run("--remove-example", second)

    assert rejected.returncode != 0
    assert (modified_example / "prompt.md").read_text(encoding="utf-8") == "user content\n"
