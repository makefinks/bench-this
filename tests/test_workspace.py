import subprocess
from pathlib import Path

import pytest

from agent_bench.auth import prepare_home

from agent_bench.errors import ConfigurationError
from agent_bench.models import Defaults, ImageConfig, ProjectConfig, TaskConfig, TreatmentConfig
from agent_bench.workspace import (
    PUBLIC_TESTS_WORKSPACE_DIRECTORY,
    copy_contents,
    export_commit,
    prepare_workspace,
    public_test_mutations,
    public_test_snapshot,
    stage_public_tests,
)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def test_snapshot_excludes_git_and_benchmarks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "fixture@example.com")
    git(repo, "config", "user.name", "Fixture")
    (repo / "app.txt").write_text("base\n")
    (repo / "benchmarks").mkdir()
    (repo / "benchmarks/secret.txt").write_text("hidden\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    commit = git(repo, "rev-parse", "HEAD")

    output = tmp_path / "output"
    export_commit(repo, commit, output)
    assert (output / "app.txt").exists()
    assert not (output / ".git").exists()
    assert not (output / "benchmarks").exists()


def test_copy_contents_ignores_gitkeep_placeholders(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / ".gitkeep").write_text("")
    (source / "settings.json").write_text("{}")
    (source / "nested").mkdir()
    (source / "nested/.gitkeep").write_text("")

    destination = tmp_path / "destination"
    copy_contents(source, destination, "fixture")

    assert not (destination / ".gitkeep").exists()
    assert (destination / "settings.json").read_text() == "{}"
    assert not (destination / "nested/.gitkeep").exists()


def test_copy_contents_rejects_symlinked_source_directory(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    source = tmp_path / "source"
    source.symlink_to(target, target_is_directory=True)

    with pytest.raises(ConfigurationError, match="is a symlink"):
        copy_contents(source, tmp_path / "destination", "fixture")


def test_public_tests_are_visible_and_final_mutations_are_reported(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "fixture@example.com")
    git(repo, "config", "user.name", "Fixture")
    (repo / "app.txt").write_text("base\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    commit = git(repo, "rev-parse", "HEAD")

    task_root = tmp_path / "task"
    public_tests = task_root / "public-tests"
    public_tests.mkdir(parents=True)
    (public_tests / "run.sh").write_text("original\n")
    (public_tests / "case.txt").write_text("case\n")
    public = task_root / "public"
    public.mkdir()
    hidden = task_root / "hidden"
    hidden.mkdir()
    prompt = task_root / "prompt.md"
    prompt.write_text("Solve it.\n")
    task = TaskConfig(
        root=task_root,
        id="demo",
        base_commit=commit,
        reference_commit=commit,
        prompt_path=prompt,
        public_directory=public,
        hidden_tests_directory=hidden,
        test_command="hidden",
        solver_timeout_seconds=None,
        public_tests_directory=public_tests,
        public_test_command="public",
        public_test_groups=["basic"],
        requirement_groups=["hidden-basic"],
    )
    config_root = tmp_path / "config"
    harness = config_root / "harness"
    overlay = config_root / "workspace"
    harness.mkdir(parents=True)
    overlay.mkdir()
    config = TreatmentConfig(
        config_root, "demo", "copilot", "model", harness, overlay, "work", []
    )
    project = ProjectConfig(
        repo,
        tmp_path / "benchmarks",
        ImageConfig("fixture", tmp_path / "Dockerfile"),
        "setup",
        Defaults(),
    )

    workspace = tmp_path / "workspace"
    prepare_workspace(project, task, config, workspace)
    stage_public_tests(task, workspace)
    visible = workspace / PUBLIC_TESTS_WORKSPACE_DIRECTORY
    assert (visible / "run.sh").read_text() == "original\n"
    snapshot = public_test_snapshot(task, workspace)
    (visible / "run.sh").write_text("changed\n")
    (visible / "case.txt").unlink()

    assert public_test_mutations(snapshot, workspace) == (["run.sh"], ["case.txt"])


def test_stage_home_uses_only_selected_profile_and_config(tmp_path):
    root = tmp_path / "config"
    (root / "harness").mkdir(parents=True)
    (root / "harness/settings.json").write_text("{}")
    auth = tmp_path / "auth"
    selected = auth / "work" / "copilot" / ".copilot"
    selected.mkdir(parents=True)
    (selected / "token.json").write_text("secret")
    other = auth / "personal" / "copilot" / ".copilot"
    other.mkdir(parents=True)
    (other / "personal-token.json").write_text("do-not-copy")
    config = TreatmentConfig(
        root=root,
        id="copilot",
        harness="copilot",
        model="fixed",
        harness_config=root / "harness",
        workspace_config=root / "workspace",
        auth_profile="work",
        arguments=[],
    )

    home = tmp_path / "home"
    prepare_home(config, home, auth)
    assert (home / ".copilot/token.json").read_text() == "secret"
    assert (home / ".copilot/settings.json").exists()
    assert not (home / ".copilot/personal-token.json").exists()


def test_stage_home_rejects_symlinked_auth(tmp_path):
    root = tmp_path / "config"
    (root / "harness").mkdir(parents=True)
    auth_dir = tmp_path / "auth/work/copilot"
    auth_dir.mkdir(parents=True)
    (auth_dir / "leak").symlink_to(Path.home())
    config = TreatmentConfig(
        root=root,
        id="copilot",
        harness="copilot",
        model="fixed",
        harness_config=root / "harness",
        workspace_config=root / "workspace",
        auth_profile="work",
        arguments=[],
    )
    with pytest.raises(ConfigurationError, match="symlink"):
        prepare_home(config, tmp_path / "home", tmp_path / "auth")
