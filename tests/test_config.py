from pathlib import Path

import pytest

from agent_bench.config import load_configuration, load_project, load_task
from agent_bench.cli import _parser
from agent_bench.errors import ConfigurationError


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def treatment_manifest(tmp_path: Path, config_id: str, selection: str) -> Path:
    root = tmp_path / config_id
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    return write(
        root / "configuration.yaml",
        f"""id: {config_id}
{selection}
harness_config: harness
workspace_config: workspace
auth_profile: work
""",
    )


def project(tmp_path: Path):
    benchmark = tmp_path / "benchmarks"
    write(benchmark / "Dockerfile", "FROM scratch\n")
    write(benchmark / "setup.sh", "#!/bin/sh\n")
    write(
        benchmark / "benchmark.yaml",
        """version: 1
image:
  name: fixture
  dockerfile: benchmarks/Dockerfile
setup_command: /bin/sh /benchmark/setup.sh /workspace
compose_file: null
defaults:
  solver_timeout_seconds: 10
  evaluator_timeout_seconds: 5
  repetitions: 1
""",
    )
    return load_project(benchmark)


def test_project_rejects_missing_setup_script(tmp_path):
    project(tmp_path)
    setup_script = tmp_path / "benchmarks/setup.sh"
    setup_script.unlink()

    with pytest.raises(ConfigurationError, match=r"setup\.sh does not exist"):
        load_project(tmp_path / "benchmarks")


def test_schema_rejects_missing_task_field(tmp_path):
    cfg = project(tmp_path)
    path = write(
        tmp_path / "benchmarks/tasks/demo/task.yaml",
        "version: 1\nid: demo\nbase_commit: 0123456\n",
    )
    with pytest.raises(ConfigurationError, match="missing"):
        load_task(path, cfg)


def test_solver_timeout_accepts_null_for_unlimited_runs(tmp_path):
    cfg = project(tmp_path)
    project_path = tmp_path / "benchmarks/benchmark.yaml"
    project_path.write_text(
        project_path.read_text().replace(
            "solver_timeout_seconds: 10", "solver_timeout_seconds: null"
        )
    )
    cfg = load_project(tmp_path / "benchmarks")

    root = tmp_path / "benchmarks/tasks/demo"
    write(root / "prompt.md", "Do the thing.\n")
    (root / "hidden-tests").mkdir()
    (root / "public-tests").mkdir()
    task_path = write(
        root / "task.yaml",
        """version: 1
id: demo
base_commit: aaaaaaa
reference_commit: bbbbbbb
prompt: prompt.md
public_tests_directory: public-tests
public_test_command: public
public_test_groups:
  - public-basic
hidden_tests_directory: hidden-tests
test_command: test
requirement_groups:
  - hidden-basic
""",
    )

    assert cfg.defaults.solver_timeout_seconds is None
    assert load_task(task_path, cfg).solver_timeout_seconds is None

    task_path.write_text(task_path.read_text() + "solver_timeout_seconds: 30\n")
    assert load_task(task_path, cfg).solver_timeout_seconds == 30


@pytest.mark.parametrize("value", [0, -1, False, "none"])
def test_solver_timeout_rejects_nonpositive_nonnull_values(tmp_path, value):
    project(tmp_path)
    path = tmp_path / "benchmarks/benchmark.yaml"
    path.write_text(
        path.read_text().replace(
            "solver_timeout_seconds: 10", f"solver_timeout_seconds: {value!r}"
        )
    )

    with pytest.raises(ConfigurationError, match="positive integer"):
        load_project(tmp_path / "benchmarks")


def test_task_requirement_groups_are_validated(tmp_path):
    cfg = project(tmp_path)
    root = tmp_path / "benchmarks/tasks/demo"
    write(root / "prompt.md", "Do the thing.\n")
    (root / "hidden-tests").mkdir()
    (root / "public-tests").mkdir()
    path = write(
        root / "task.yaml",
        """version: 1
id: demo
base_commit: aaaaaaa
reference_commit: bbbbbbb
prompt: prompt.md
public_tests_directory: public-tests
public_test_command: public
public_test_groups:
  - public-basic
hidden_tests_directory: hidden-tests
test_command: test
requirement_groups:
  - first-group
  - second-group
""",
    )

    assert load_task(path, cfg).requirement_groups == ["first-group", "second-group"]
    valid = path.read_text()
    path.write_text(
        valid.replace(
            "requirement_groups:\n  - first-group\n  - second-group",
            "requirement_groups: []",
        )
    )
    with pytest.raises(ConfigurationError, match="non-empty list"):
        load_task(path, cfg)
    path.write_text(valid.replace("second-group", "first-group"))
    with pytest.raises(ConfigurationError, match="unique"):
        load_task(path, cfg)


def test_task_rejects_missing_public_test_configuration(tmp_path):
    cfg = project(tmp_path)
    root = tmp_path / "benchmarks/tasks/demo"
    write(root / "prompt.md", "Do the thing.\n")
    (root / "hidden-tests").mkdir()
    path = write(
        root / "task.yaml",
        """version: 1
id: demo
base_commit: aaaaaaa
reference_commit: bbbbbbb
prompt: prompt.md
hidden_tests_directory: hidden-tests
test_command: hidden
requirement_groups:
  - hidden-basic
""",
    )

    with pytest.raises(ConfigurationError, match="public_tests_directory"):
        load_task(path, cfg)


def test_task_requires_complete_valid_public_test_configuration(tmp_path):
    cfg = project(tmp_path)
    root = tmp_path / "benchmarks/tasks/demo"
    write(root / "prompt.md", "Do the thing.\n")
    (root / "hidden-tests").mkdir()
    (root / "public-tests").mkdir()
    path = write(
        root / "task.yaml",
        """version: 1
id: demo
base_commit: aaaaaaa
reference_commit: bbbbbbb
prompt: prompt.md
hidden_tests_directory: hidden-tests
test_command: hidden
public_tests_directory: public-tests
public_test_command: public
public_test_groups:
  - basic-behavior
requirement_groups:
  - hidden-basic
""",
    )

    task = load_task(path, cfg)
    assert task.public_tests_directory == root / "public-tests"
    assert task.public_test_command == "public"
    assert task.public_test_groups == ["basic-behavior"]

    path.write_text(path.read_text().replace("public_test_command: public\n", ""))
    with pytest.raises(ConfigurationError, match="is missing: public_test_command"):
        load_task(path, cfg)


def test_task_public_and_hidden_test_directories_must_be_separate(tmp_path):
    cfg = project(tmp_path)
    root = tmp_path / "benchmarks/tasks/demo"
    write(root / "prompt.md", "Do the thing.\n")
    (root / "tests").mkdir()
    path = write(
        root / "task.yaml",
        """version: 1
id: demo
base_commit: aaaaaaa
reference_commit: bbbbbbb
prompt: prompt.md
hidden_tests_directory: tests
test_command: hidden
public_tests_directory: tests
public_test_command: public
public_test_groups:
  - basic
requirement_groups:
  - hidden-basic
""",
    )

    with pytest.raises(ConfigurationError, match="must be separate"):
        load_task(path, cfg)


def test_task_public_test_groups_must_be_nonempty_and_unique(tmp_path):
    cfg = project(tmp_path)
    root = tmp_path / "benchmarks/tasks/demo"
    write(root / "prompt.md", "Do the thing.\n")
    (root / "hidden-tests").mkdir()
    (root / "public-tests").mkdir()
    path = write(
        root / "task.yaml",
        """version: 1
id: demo
base_commit: aaaaaaa
reference_commit: bbbbbbb
prompt: prompt.md
hidden_tests_directory: hidden-tests
test_command: hidden
public_tests_directory: public-tests
public_test_command: public
public_test_groups: []
requirement_groups:
  - hidden-basic
""",
    )

    with pytest.raises(ConfigurationError, match="non-empty list"):
        load_task(path, cfg)
    path.write_text(
        path.read_text().replace(
            "public_test_groups: []",
            "public_test_groups:\n  - basic\n  - basic",
        )
    )
    with pytest.raises(ConfigurationError, match="unique"):
        load_task(path, cfg)


def test_schema_rejects_unpinned_opencode_provider(tmp_path):
    path = write(
        tmp_path / "opencode/configuration.yaml",
        """id: opencode
harness: opencode
provider: anthropic
model: fixed-model
agent: build
harness_config: harness
workspace_config: workspace
auth_profile: work
""",
    )
    with pytest.raises(ConfigurationError, match="provider must be one of"):
        load_configuration(path)


def test_schema_accepts_openai_opencode_provider(tmp_path):
    root = tmp_path / "opencode-openai"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    path = write(
        root / "configuration.yaml",
        """id: opencode-openai
harness: opencode
provider: openai
model: fixed-model
agent: build
harness_config: harness
workspace_config: workspace
auth_profile: openai
""",
    )
    assert load_configuration(path).provider == "openai"


def test_schema_accepts_opencode_go_provider(tmp_path):
    root = tmp_path / "opencode-go"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    path = write(
        root / "configuration.yaml",
        """id: opencode-go
harness: opencode
provider: opencode-go
model: glm-5.2
agent: build
harness_config: harness
workspace_config: workspace
auth_profile: opencode-go
""",
    )
    config = load_configuration(path)

    assert config.provider == "opencode-go"
    assert config.qualified_model == "opencode-go/glm-5.2"



def test_schema_accepts_opencode_zen_provider(tmp_path):
    root = tmp_path / "opencode-zen"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    path = write(
        root / "configuration.yaml",
        """id: opencode-zen
harness: opencode
provider: opencode
model: deepseek-v4-flash-free
agent: build
harness_config: harness
workspace_config: workspace
auth_profile: opencode-zen
""",
    )
    config = load_configuration(path)

    assert config.provider == "opencode"
    assert config.qualified_model == "opencode/deepseek-v4-flash-free"


def test_schema_accepts_amazon_bedrock_provider(tmp_path):
    root = tmp_path / "amazon-bedrock"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    path = write(
        root / "configuration.yaml",
        """id: amazon-bedrock
harness: opencode
provider: amazon-bedrock
model: eu.anthropic.claude-sonnet-4-5-v1:0
agent: build
region: eu-central-1
harness_config: harness
workspace_config: workspace
auth_profile: bedrock
""",
    )
    config = load_configuration(path)

    assert config.provider == "amazon-bedrock"
    assert config.region == "eu-central-1"
    assert (
        config.qualified_model
        == "amazon-bedrock/eu.anthropic.claude-sonnet-4-5-v1:0"
    )


@pytest.mark.parametrize("region", [None, "", "us-east", 1])
def test_schema_requires_valid_region_for_amazon_bedrock(tmp_path, region):
    root = tmp_path / "amazon-bedrock"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    region_line = "" if region is None else f"region: {region}\n"
    path = write(
        root / "configuration.yaml",
        """id: amazon-bedrock
harness: omp
provider: amazon-bedrock
model: fixed-model
"""
        + region_line
        + """harness_config: harness
workspace_config: workspace
auth_profile: bedrock
""",
    )

    with pytest.raises(ConfigurationError, match="region"):
        load_configuration(path)

def test_schema_accepts_pi_codex_provider(tmp_path):
    root = tmp_path / "pi-codex"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    path = write(
        root / "configuration.yaml",
        """id: pi-codex
harness: pi
provider: openai-codex
model: gpt-5.4
harness_config: harness
workspace_config: workspace
auth_profile: codex
""",
    )

    config = load_configuration(path)

    assert config.provider == "openai-codex"
    assert config.qualified_model == "openai-codex/gpt-5.4"
    assert config.agent is None


def test_pi_provider_allowlist_rejects_unrelated_provider(tmp_path):
    root = tmp_path / "pi-invalid"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    path = write(
        root / "configuration.yaml",
        """id: pi-invalid
harness: pi
provider: github-copilot
model: gpt-fixed
harness_config: harness
workspace_config: workspace
auth_profile: work
""",
    )

    with pytest.raises(ConfigurationError, match="pi provider must be one of"):
        load_configuration(path)


def test_schema_rejects_path_escape(tmp_path):
    path = write(
        tmp_path / "copilot/configuration.yaml",
        """id: copilot
harness: copilot
model: fixed-model
harness_config: ../../home
workspace_config: workspace
auth_profile: work
""",
    )
    with pytest.raises(ConfigurationError, match="stay inside"):
        load_configuration(path)


def test_setup_timeout_is_explicit_or_falls_back_to_evaluator(tmp_path):
    cfg = project(tmp_path)
    assert cfg.defaults.setup_timeout_seconds == 5
    path = tmp_path / "benchmarks/benchmark.yaml"
    path.write_text(path.read_text().replace("  repetitions: 1", "  setup_timeout_seconds: 17\n  repetitions: 1"))
    assert load_project(tmp_path / "benchmarks").defaults.setup_timeout_seconds == 17


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "true"])
def test_setup_timeout_must_be_a_positive_integer(tmp_path, value):
    project(tmp_path)
    path = tmp_path / "benchmarks/benchmark.yaml"
    path.write_text(path.read_text().replace("  repetitions: 1", f"  setup_timeout_seconds: {value}\n  repetitions: 1"))
    with pytest.raises(ConfigurationError, match="setup_timeout_seconds"):
        load_project(tmp_path / "benchmarks")


def test_run_jobs_default_and_override():
    assert _parser().parse_args(["run"]).jobs == 3
    assert _parser().parse_args(["run", "--jobs", "7"]).jobs == 7


def test_validate_tasks_jobs_default_and_override():
    assert _parser().parse_args(["validate-tasks"]).jobs == 3
    assert _parser().parse_args(["validate-tasks", "--jobs", "5"]).jobs == 5


def test_treatment_schema_rejects_unknown_fields(tmp_path):
    path = treatment_manifest(
        tmp_path,
        "unknown-field",
        """harness: pi
provider: openai-codex
model: gpt-fixed
modle: typo""",
    )

    with pytest.raises(ConfigurationError, match="unknown configuration fields: modle"):
        load_configuration(path)


def test_treatment_schema_reports_non_string_keys_as_unknown_fields(tmp_path):
    path = treatment_manifest(
        tmp_path,
        "non-string-key",
        """harness: pi
provider: openai-codex
model: gpt-fixed
42: typo""",
    )

    with pytest.raises(ConfigurationError, match="unknown configuration fields: 42"):
        load_configuration(path)


def test_treatment_schema_rejects_known_irrelevant_fields(tmp_path):
    path = treatment_manifest(
        tmp_path,
        "irrelevant-region",
        """harness: pi
provider: openai-codex
model: gpt-fixed
region: us-east-1""",
    )

    with pytest.raises(ConfigurationError, match="fields do not apply.*region"):
        load_configuration(path)


def test_treatment_schema_requires_and_forbids_provider_selection(tmp_path):
    missing = treatment_manifest(
        tmp_path,
        "missing-provider",
        """harness: pi
model: gpt-fixed""",
    )
    forbidden = treatment_manifest(
        tmp_path,
        "forbidden-provider",
        """harness: copilot
provider: github-copilot
model: auto""",
    )

    with pytest.raises(ConfigurationError, match="Pi requires provider"):
        load_configuration(missing)
    with pytest.raises(ConfigurationError, match="provider does not apply"):
        load_configuration(forbidden)


@pytest.mark.parametrize(
    ("config_id", "selection"),
    [
        (
            "copilot-auto",
            """harness: copilot
model: auto""",
        ),
        (
            "opencode-copilot-auto",
            """harness: opencode
provider: github-copilot
model: auto
agent: build""",
        ),
        (
            "omp-copilot-auto",
            """harness: omp
provider: github-copilot
model: auto""",
        ),
    ],
)
def test_treatment_schema_allows_auto_only_for_copilot_selections(
    tmp_path, config_id, selection
):
    assert load_configuration(
        treatment_manifest(tmp_path, config_id, selection)
    ).model == "auto"


def test_treatment_schema_rejects_auto_for_non_copilot_provider(tmp_path):
    path = treatment_manifest(
        tmp_path,
        "openai-auto",
        """harness: opencode
provider: openai
model: auto
agent: build""",
    )

    with pytest.raises(ConfigurationError, match="explicitly pinned"):
        load_configuration(path)
