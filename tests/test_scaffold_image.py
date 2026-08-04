from pathlib import Path

import yaml

from agent_bench.config import load_project
from agent_bench.scaffold import scaffold


def test_scaffolds_use_checkout_specific_image_names(tmp_path: Path) -> None:
    first = tmp_path / "one" / "project"
    second = tmp_path / "two" / "project"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    scaffold(first)
    scaffold(second)

    first_name = load_project(first / "benchmarks").image.name
    second_name = load_project(second / "benchmarks").image.name
    assert first_name.startswith("agent-bench-project-")
    assert second_name.startswith("agent-bench-project-")
    assert first_name != second_name


def test_scaffold_preserves_pyyaml_license_and_provenance(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    benchmark = scaffold(project)

    license_text = (benchmark / "_vendor" / "yaml" / "LICENSE").read_text(encoding="utf-8")
    notice = (benchmark / "_vendor" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "Permission is hereby granted, free of charge" in license_text
    assert f"PyYAML {yaml.__version__}" in notice
    assert "https://github.com/yaml/pyyaml" in notice
    assert "`yaml/LICENSE`" in notice
