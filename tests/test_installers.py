from pathlib import Path

import pytest

from agent_bench.installers import render_dockerfile, render_harness_installs
from agent_bench.models import Defaults, ImageConfig, ProjectConfig
from agent_bench.runner import BenchmarkRunner


def test_render_omp_installs_only_omp_dependencies():
    block = render_harness_installs(["omp"])
    assert "ARG BUN_VERSION=1.3.14" in block
    assert "@oh-my-pi/pi-coding-agent@${OMP_VERSION}" in block
    assert "opencode-ai" not in block
    assert "@github/copilot" not in block

def test_render_pi_installs_pinned_upstream_package():
    block = render_harness_installs(["pi"])
    assert "ARG PI_VERSION=0.84.2" in block
    assert (
        'npm install --global --ignore-scripts '
        '"@earendil-works/pi-coding-agent@${PI_VERSION}"'
    ) in block
    assert "@oh-my-pi/pi-coding-agent" not in block


def test_render_combines_selected_harnesses_deterministically():
    block = render_harness_installs(["omp", "opencode", "omp"])
    assert block.index("@oh-my-pi/pi-coding-agent") < block.index("opencode-ai")
    assert block.count("ARG BUN_VERSION") == 1


def test_render_rejects_unknown_harness():
    with pytest.raises(ValueError, match="unsupported harness installers"):
        render_harness_installs(["unknown"])


def test_render_replaces_dockerfile_marker_without_mutating_source(tmp_path: Path):
    source = tmp_path / "Dockerfile"
    source.write_text("FROM node\n# BEGIN GENERATED HARNESS INSTALLS\nold\n# END GENERATED HARNESS INSTALLS\n")

    rendered = render_dockerfile(source, ["copilot"])

    assert "old" not in rendered
    assert "@github/copilot@${COPILOT_CLI_VERSION}" in rendered
    assert source.read_text() == "FROM node\n# BEGIN GENERATED HARNESS INSTALLS\nold\n# END GENERATED HARNESS INSTALLS\n"


def test_build_passes_rendered_dockerfile_to_engine(tmp_path: Path, monkeypatch):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "FROM node\n# BEGIN GENERATED HARNESS INSTALLS\n# END GENERATED HARNESS INSTALLS\n"
    )
    configurations = tmp_path / "configurations" / "omp"
    configurations.mkdir(parents=True)
    (configurations / "configuration.yaml").write_text("placeholder\n")
    project = ProjectConfig(
        root=tmp_path,
        benchmark_dir=tmp_path,
        image=ImageConfig("fixture", dockerfile),
        setup_command="true",
        defaults=Defaults(),
    )

    class FakeDocker:
        def build(self, image, rendered_path, context):
            self.image = image
            self.rendered = rendered_path.read_text()
            self.context = context

    engine = FakeDocker()
    monkeypatch.setattr(
        "agent_bench.runner.discover_harnesses",
        lambda _project: {"omp": type("Config", (), {"harness": "omp"})()},
    )

    BenchmarkRunner(project, docker=engine).build()

    assert "@oh-my-pi/pi-coding-agent@${OMP_VERSION}" in engine.rendered
    assert "opencode-ai" not in engine.rendered
    assert engine.context == tmp_path
