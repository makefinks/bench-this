from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_bench.catalog import HARNESS_CATALOG
from agent_bench.installers import render_dockerfile, render_harness_installs
from agent_bench.models import Defaults, ImageConfig, ProjectConfig
from agent_bench.runner import BenchmarkRunner


@pytest.mark.parametrize("harness", HARNESS_CATALOG.values(), ids=lambda item: item.id)
def test_render_preserves_catalog_pins_and_commands(harness):
    block = render_harness_installs([harness.id])

    for name, version in harness.installer.arguments.items():
        assert f"ARG {name}={version}\n" in block
    for command in harness.installer.commands:
        assert command in block


def test_render_omp_installs_only_omp_dependencies():
    block = render_harness_installs(["omp"])
    version = HARNESS_CATALOG["omp"].installer.arguments["BUN_VERSION"]
    assert f"ARG BUN_VERSION={version}" in block
    assert "@oh-my-pi/pi-coding-agent@${OMP_VERSION}" in block
    assert "@opencode/cli" not in block
    assert "@github/copilot" not in block


def test_render_pi_installs_upstream_with_native_mcp_and_no_external_adapter():
    block = render_harness_installs(["pi"])
    versions = HARNESS_CATALOG["pi"].installer.arguments
    assert f"ARG PI_VERSION={versions['PI_VERSION']}" in block
    assert (
        'npm install --global --ignore-scripts '
        '"@earendil-works/pi-coding-agent@${PI_VERSION}"'
    ) in block
    assert "PI_MCP_ADAPTER_VERSION" not in block
    assert "pi-mcp-adapter" not in block
    assert "@oh-my-pi/pi-coding-agent" not in block


def test_render_opencode_installs_v2_package_with_native_binary_postinstall():
    block = render_harness_installs(["opencode"])

    assert 'npm install --global "@opencode/cli@${OPENCODE_VERSION}"' in block
    assert block.index("npm uninstall --global opencode-ai") < block.index(
        'npm install --global "@opencode/cli'
    )
    assert 'npm install --global "opencode-ai' not in block
    assert "--ignore-scripts" not in block


def test_render_combines_selected_harnesses_deterministically():
    block = render_harness_installs(["omp", "opencode", "omp"])
    assert block.index("@oh-my-pi/pi-coding-agent") < block.index("@opencode/cli")
    assert block.count("ARG BUN_VERSION") == 1


def test_render_all_harnesses_shares_runtime_pins_without_dropping_installers():
    block = render_harness_installs(HARNESS_CATALOG)
    arguments = {
        name
        for harness in HARNESS_CATALOG.values()
        for name in harness.installer.arguments
    }

    for name in arguments:
        assert block.count(f"ARG {name}=") == 1
    for harness in HARNESS_CATALOG.values():
        for command in harness.installer.commands:
            assert command in block


def test_render_rejects_unknown_harness():
    with pytest.raises(ValueError, match="unsupported harness installers"):
        render_harness_installs(["unknown"])


def test_render_rejects_conflicting_catalog_build_arguments(monkeypatch):
    monkeypatch.setattr(
        "agent_bench.installers.HARNESS_CATALOG",
        {
            "a": SimpleNamespace(
                installer=SimpleNamespace(
                    arguments={"SHARED": "one"}, commands=("install-a",)
                )
            ),
            "b": SimpleNamespace(
                installer=SimpleNamespace(
                    arguments={"SHARED": "two"}, commands=("install-b",)
                )
            ),
        },
    )

    with pytest.raises(ValueError, match="conflicting generated build argument SHARED"):
        render_harness_installs(["a", "b"])


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
        "agent_bench.runner.discover_configurations",
        lambda _project: {"omp": type("Config", (), {"harness": "omp"})()},
    )

    BenchmarkRunner(project, docker=engine).build()

    assert "@oh-my-pi/pi-coding-agent@${OMP_VERSION}" in engine.rendered
    assert "@opencode/cli" not in engine.rendered
    assert engine.context == tmp_path
