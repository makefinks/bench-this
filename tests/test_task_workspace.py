import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path("skills/bench-this/scripts/task_workspace.py").resolve()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def run(*args: object, check: bool = True):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
    )
    if check:
        result.check_returncode()
    return result


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "fixture@example.com")
    git(repo, "config", "user.name", "Fixture")
    (repo / "source.txt").write_text("base\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "source.txt").write_text("reference\n")
    git(repo, "commit", "-qam", "reference")
    reference = git(repo, "rev-parse", "HEAD")
    benchmark = repo / "benchmarks"
    benchmark.mkdir()
    (benchmark / "run.py").write_text("runner\n")
    (benchmark / "setup.sh").write_text("setup\n")
    (repo / "sentinel.txt").write_text("untracked\n")
    return repo, base, reference


def prepare(repository, task="demo"):
    repo, base, reference = repository
    return json.loads(run("prepare", repo, task, base, reference).stdout)


def valid_bundle(info, task="demo"):
    output = Path(info["output"])
    manifest = output / "task.yaml"
    lines = manifest.read_text().splitlines()
    rendered = []
    for line in lines:
        if line.startswith("id:"):
            rendered.append(f"id: {task}")
        elif line == "public_test_groups: []":
            rendered.extend(("public_test_groups:", "  - public-basic"))
        elif line == "requirement_groups: []":
            rendered.extend(("requirement_groups:", "  - core-behavior"))
        else:
            rendered.append(line)
    manifest.write_text("\n".join(rendered) + "\n")
    (output / "prompt.md").write_text("## core-behavior\n\nDo the thing.\n")
    (output / "public-tests/run.sh").write_text(
        "#!/bin/sh\nprintf '%s\\n' 'AGENT_BENCH_RESULT: {\"version\":1,\"groups\":{\"public-basic\":true}}'\nexit 0\n"
    )
    (output / "hidden-tests/run.sh").write_text(
        "#!/bin/sh\nprintf '%s\\n' 'AGENT_BENCH_RESULT: {\"version\":1,\"groups\":{\"core-behavior\":true}}'\nexit 0\n"
    )


def test_prepare_creates_deterministic_task_skeleton(repository):
    _, base, reference = repository
    info = prepare(repository)
    output = Path(info["output"])

    assert (output / "public").is_dir()
    assert (output / "public-tests").is_dir()
    assert (output / "hidden-tests").is_dir()
    assert (output / "prompt.md").read_text() == ""
    assert (output / "public-tests/run.sh").read_text() == ""
    assert (output / "hidden-tests/run.sh").read_text() == ""
    assert (output / "public-tests/run.sh").stat().st_mode & 0o100
    assert (output / "hidden-tests/run.sh").stat().st_mode & 0o100
    assert (output / "task.yaml").read_text() == (
        "version: 1\n"
        "id: demo\n"
        f"base_commit: {base}\n"
        f"reference_commit: {reference}\n"
        "prompt: prompt.md\n"
        "public_directory: public\n"
        "public_tests_directory: public-tests\n"
        "public_test_command: /bin/sh /public-tests/run.sh /workspace\n"
        "public_test_groups: []\n"
        "hidden_tests_directory: hidden-tests\n"
        "test_command: /bin/sh /evaluator/run.sh /workspace\n"
        "requirement_groups: []\n"
    )
    assert git(Path(info["base_repository"]), "rev-parse", "HEAD") == base
    assert git(Path(info["reference_repository"]), "rev-parse", "HEAD") == reference
    assert not (Path(info["base_repository"]) / "benchmarks").exists()
    assert not (Path(info["reference_repository"]) / "benchmarks").exists()


def test_accept_rejects_unfinished_skeleton(repository):
    info = prepare(repository)

    result = run("accept", info["scratch"], check=False)

    assert result.returncode == 2
    assert "task prompt is empty" in result.stderr

    (Path(info["output"]) / "prompt.md").write_text("Do the thing.\n")
    result = run("accept", info["scratch"], check=False)

    assert result.returncode == 2
    assert "previous accept attempt failed" in result.stderr

    info = prepare(repository, "empty-public-evaluator")
    (Path(info["output"]) / "prompt.md").write_text("Do the thing.\n")
    result = run("accept", info["scratch"], check=False)

    assert result.returncode == 2
    assert "public test entrypoint is empty" in result.stderr

    info = prepare(repository, "empty-hidden-evaluator")
    output = Path(info["output"])
    (output / "prompt.md").write_text("Do the thing.\n")
    (output / "public-tests/run.sh").write_text("#!/bin/sh\nexit 1\n")
    result = run("accept", info["scratch"], check=False)

    assert result.returncode == 2
    assert "hidden evaluator entrypoint is empty" in result.stderr


def test_check_can_be_repeated_and_repaired_before_accept(repository):
    repo, _, _ = repository
    info = prepare(repository)
    metadata_path = Path(info["scratch"]) / "metadata.json"
    metadata_before = metadata_path.read_bytes()

    first = run("check", info["scratch"], check=False)

    assert first.returncode == 2
    assert "task prompt is empty" in first.stderr
    metadata = json.loads(metadata_path.read_text())
    assert metadata["accept_failed"] is False
    assert metadata_path.read_bytes() == metadata_before
    assert not (repo / "benchmarks/tasks/demo").exists()

    valid_bundle(info)
    checked = json.loads(run("check", info["scratch"]).stdout)
    checked_again = json.loads(run("check", info["scratch"]).stdout)

    assert checked["checked"] is checked_again["checked"] is True
    assert checked["task"] == "demo"
    assert not (repo / "benchmarks/tasks/demo").exists()
    assert json.loads(run("accept", info["scratch"]).stdout)["accepted"] is True


def test_check_rejects_generated_python_cache_files(repository):
    repo, _, _ = repository
    info = prepare(repository)
    valid_bundle(info)
    cache = Path(info["output"]) / "hidden-tests/__pycache__/evaluate.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"generated")

    rejected = run("check", info["scratch"], check=False)

    assert rejected.returncode == 2
    assert "generated Python cache files" in rejected.stderr
    assert not (repo / "benchmarks/tasks/demo").exists()

    cache.unlink()
    cache.parent.rmdir()
    assert json.loads(run("check", info["scratch"]).stdout)["checked"] is True


def test_accept_requires_declared_group_scoring(repository):
    info = prepare(repository, "missing-groups")
    output = Path(info["output"])
    (output / "prompt.md").write_text("Do the thing.\n")
    (output / "public-tests/run.sh").write_text("#!/bin/sh\nexit 1\n")
    (output / "hidden-tests/run.sh").write_text("#!/bin/sh\nexit 1\n")

    result = run("accept", info["scratch"], check=False)

    assert result.returncode == 2
    assert "requirement_groups" in result.stderr


def test_accept_requires_public_suite_protocol(repository):
    info = prepare(repository, "public-tests")
    valid_bundle(info, "public-tests")
    output = Path(info["output"])
    (output / "public-tests/run.sh").write_text("#!/bin/sh\nexit 1\n")

    result = run("accept", info["scratch"], check=False)

    assert result.returncode == 2
    assert "AGENT_BENCH_RESULT" in result.stderr


def test_accept_requires_public_test_manifest_fields(repository):
    info = prepare(repository, "missing-public-config")
    valid_bundle(info, "missing-public-config")
    manifest = Path(info["output"]) / "task.yaml"
    manifest.write_text(
        manifest.read_text().replace("public_test_command: /bin/sh /public-tests/run.sh /workspace\n", "")
    )

    result = run("accept", info["scratch"], check=False)

    assert result.returncode == 2
    assert "authored tasks require public tests" in result.stderr


def test_accept_requires_prompt_section_for_every_group(repository):
    info = prepare(repository, "missing-prompt-group")
    valid_bundle(info, "missing-prompt-group")
    (Path(info["output"]) / "prompt.md").write_text("## Requirements\n\nDo the thing.\n")

    result = run("accept", info["scratch"], check=False)

    assert result.returncode == 2
    assert "exact Markdown heading" in result.stderr
    assert "core-behavior" in result.stderr


def test_validation_git_operations_preserve_authoring_infrastructure(repository):
    repo, _, reference = repository
    first = prepare(repository, "first")
    second = prepare(repository, "second")
    worker = Path(first["worker_repository"])
    base_repository = Path(first["base_repository"])
    (base_repository / "scratch.txt").write_text("scratch\n")
    git(base_repository, "clean", "-fd")
    git(base_repository, "checkout", "--detach", reference)
    valid_bundle(first, "first")
    assert json.loads(run("accept", first["scratch"]).stdout)["accepted"]
    assert (worker / "benchmarks/run.py").exists()
    assert git(repo, "stash", "list") == ""
    assert (repo / "sentinel.txt").read_text() == "untracked\n"
    assert (repo / "benchmarks/run.py").exists()
    assert Path(second["worker_repository"]).exists()


def test_prepare_rejects_inverted_commit_order_before_creating_scratch(repository, tmp_path):
    repo, base, reference = repository

    result = run(
        "prepare",
        repo,
        "inverted",
        reference,
        base,
        "--scratch-root",
        tmp_path,
        check=False,
    )

    assert result.returncode == 2
    assert "reference commit must descend from base commit" in result.stderr
    assert list(tmp_path.glob("agent-bench-*")) == []


def test_accept_copies_only_assigned_bundle(repository):
    repo, _, _ = repository
    info = prepare(repository)
    valid_bundle(info)
    result = json.loads(run("accept", info["scratch"]).stdout)
    assert result["accepted"]
    assert (repo / "benchmarks/tasks/demo/prompt.md").exists()
    assert (repo / "source.txt").read_text() == "reference\n"


def test_accept_fails_on_target_drift_and_preserves_workspace(repository):
    repo, _, _ = repository
    info = prepare(repository)
    valid_bundle(info)
    (repo / "source.txt").write_text("user change\n")
    result = run("accept", info["scratch"], check=False)
    assert result.returncode == 2
    assert "protected state changed" in result.stderr
    assert "never copy the task bundle manually" in result.stderr
    assert Path(info["scratch"]).exists()
    assert (repo / "source.txt").read_text() == "user change\n"


def test_accept_rejects_infrastructure_changes_and_symlinks(repository):
    info = prepare(repository)
    valid_bundle(info)
    (Path(info["worker_repository"]) / "benchmarks/run.py").write_text("changed\n")
    assert run("accept", info["scratch"], check=False).returncode == 2
    info = prepare(repository, "linked")
    valid_bundle(info, "linked")
    (Path(info["output"]) / "link").symlink_to("prompt.md")
    assert run("accept", info["scratch"], check=False).returncode == 2


@pytest.mark.parametrize("pattern", ["inspect.getsource(value)", "sys.modules['sdk'] = fake"])
def test_accept_rejects_forbidden_evaluator_techniques(repository, pattern):
    info = prepare(repository)
    valid_bundle(info)
    evaluator = Path(info["output"]) / "hidden-tests" / "evaluator.py"
    evaluator.write_text(f"{pattern}\n")

    result = run("accept", info["scratch"], check=False)

    assert result.returncode == 2
    assert "forbidden evaluator technique" in result.stderr


def test_failed_accept_cannot_be_retried_after_scratch_repair(repository):
    info = prepare(repository)
    valid_bundle(info)
    runner = Path(info["worker_repository"]) / "benchmarks/run.py"
    original = runner.read_text()
    runner.write_text("changed\n")

    first = run("accept", info["scratch"], check=False)
    runner.write_text(original)
    second = run("accept", info["scratch"], check=False)

    assert first.returncode == 2
    assert "worker modified shared benchmark infrastructure" in first.stderr
    assert second.returncode == 2
    assert "previous accept attempt failed" in second.stderr


def test_accept_rejects_wrong_task_id(repository):
    info = prepare(repository)
    valid_bundle(info, "wrong")
    assert run("accept", info["scratch"], check=False).returncode == 2


def test_discard_requires_exact_marker(tmp_path):
    arbitrary = tmp_path / "arbitrary"
    arbitrary.mkdir()
    result = run("discard", arbitrary, check=False)
    assert result.returncode == 2
    assert arbitrary.exists()
