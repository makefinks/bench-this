import json
import subprocess
import sys
from pathlib import Path

from agent_bench.config import load_harness


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "bench-this"
    / "scripts"
    / "configure.py"
)


def scaffold(tmp_path: Path) -> Path:
    repository = tmp_path / "project"
    benchmarks = repository / "benchmarks"
    benchmarks.mkdir(parents=True)
    (benchmarks / "benchmark.yaml").write_text("version: 1\n", encoding="utf-8")
    return repository


def run_configure(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(repository), *arguments],
        capture_output=True,
        text=True,
    )


def test_creates_minimal_openai_configuration(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--provider",
        "openai",
        "--model",
        "gpt-5.4-mini",
        "--auth-profile",
        "openai",
    )

    assert result.returncode == 0, result.stderr
    root = repository / "benchmarks/configurations/opencode-openai-gpt-5-4-mini"
    assert "model: gpt-5.4-mini" in (root / "configuration.yaml").read_text()
    config = json.loads((root / "harness/opencode.json").read_text())
    assert config["small_model"] == "openai/gpt-5.4-mini"
    assert config["enabled_providers"] == ["openai"]
    assert list((root / "workspace").iterdir()) == []


def test_creates_opencode_go_configuration(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--provider",
        "opencode-go",
        "--model",
        "glm-5.2",
        "--auth-profile",
        "opencode-go",
    )

    assert result.returncode == 0, result.stderr
    root = repository / "benchmarks/configurations/opencode-opencode-go-glm-5-2"
    assert "provider: opencode-go" in (root / "configuration.yaml").read_text()
    config = json.loads((root / "harness/opencode.json").read_text())
    assert config["small_model"] == "opencode-go/glm-5.2"
    assert config["enabled_providers"] == ["opencode-go"]


def test_creates_opencode_zen_configuration(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--provider",
        "opencode",
        "--model",
        "deepseek-v4-flash-free",
        "--auth-profile",
        "opencode-zen",
    )

    assert result.returncode == 0, result.stderr
    root = repository / "benchmarks/configurations/opencode-opencode-deepseek-v4-flash-free"
    manifest = (root / "configuration.yaml").read_text()
    assert "provider: opencode" in manifest
    config = json.loads((root / "harness/opencode.json").read_text())
    assert config["small_model"] == "opencode/deepseek-v4-flash-free"
    assert config["enabled_providers"] == ["opencode"]


def test_creates_amazon_bedrock_configuration(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--provider",
        "amazon-bedrock",
        "--bedrock-region",
        "eu-central-1",
        "--model",
        "eu.anthropic.claude-sonnet-4-5-v1:0",
        "--auth-profile",
        "bedrock",
    )

    assert result.returncode == 0, result.stderr
    root = (
        repository
        / "benchmarks/configurations/"
        "opencode-amazon-bedrock-eu-anthropic-claude-sonnet-4-5-v1-0"
    )
    assert "provider: amazon-bedrock" in (
        root / "configuration.yaml"
    ).read_text()
    assert "region: eu-central-1" in (root / "configuration.yaml").read_text()
    assert load_harness(root / "configuration.yaml").region == "eu-central-1"
    config = json.loads((root / "harness/opencode.json").read_text())
    assert config["enabled_providers"] == ["amazon-bedrock"]
    assert config["provider"] == {
        "amazon-bedrock": {"options": {"region": "eu-central-1"}}
    }


def test_amazon_bedrock_configuration_requires_region(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--provider",
        "amazon-bedrock",
        "--model",
        "eu.anthropic.claude-sonnet-4-5-v1:0",
        "--auth-profile",
        "bedrock",
    )

    assert result.returncode != 0
    assert "require a valid --bedrock-region" in result.stderr


def test_amazon_bedrock_configuration_rejects_invalid_region(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--provider",
        "amazon-bedrock",
        "--bedrock-region",
        "somewhere",
        "--model",
        "eu.anthropic.claude-sonnet-4-5-v1:0",
        "--auth-profile",
        "bedrock",
    )

    assert result.returncode != 0
    assert "require a valid --bedrock-region" in result.stderr


def test_rejects_bedrock_region_for_other_providers(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--provider",
        "openai",
        "--bedrock-region",
        "eu-central-1",
        "--model",
        "gpt-5.4-mini",
        "--auth-profile",
        "openai",
    )

    assert result.returncode != 0
    assert "applies only to Amazon Bedrock" in result.stderr


def test_creates_github_copilot_business_configuration(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--provider",
        "github-copilot",
        "--github-copilot-business",
        "--model",
        "gpt-5.4-mini",
        "--auth-profile",
        "copilot-auth",
    )

    assert result.returncode == 0, result.stderr
    root = repository / "benchmarks/configurations/opencode-github-copilot-gpt-5-4-mini"
    config = json.loads((root / "harness/opencode.json").read_text())
    assert config["provider"] == {
        "github-copilot": {
            "options": {"baseURL": "https://api.business.githubcopilot.com"}
        }
    }


def test_rejects_github_copilot_business_for_other_providers(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--provider",
        "openai",
        "--github-copilot-business",
        "--model",
        "gpt-5.4-mini",
        "--auth-profile",
        "work",
    )

    assert result.returncode != 0
    assert "requires --harness opencode --provider github-copilot" in result.stderr


def test_rejects_github_copilot_business_for_native_copilot(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--harness",
        "copilot",
        "--github-copilot-business",
        "--model",
        "gpt-5.4-mini",
        "--auth-profile",
        "work",
    )

    assert result.returncode != 0
    assert "requires --harness opencode --provider github-copilot" in result.stderr


def test_creates_native_copilot_configuration(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--harness",
        "copilot",
        "--model",
        "gpt-5.4-mini",
        "--auth-profile",
        "copilot",
    )

    assert result.returncode == 0, result.stderr
    root = repository / "benchmarks/configurations/copilot-gpt-5-4-mini"
    manifest = (root / "configuration.yaml").read_text()
    assert "harness: copilot" in manifest
    assert "provider:" not in manifest
    assert "agent:" not in manifest
    assert not (root / "harness/opencode.json").exists()
    assert (root / "harness").is_dir()


def test_creates_omp_bedrock_configuration(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)
    result = run_configure(
        repository,
        "--harness",
        "omp",
        "--provider",
        "amazon-bedrock",
        "--bedrock-region",
        "eu-west-1",
        "--model",
        "eu.anthropic.claude-sonnet-4-6",
        "--auth-profile",
        "bedrock",
    )
    assert result.returncode == 0, result.stderr
    root = repository / "benchmarks/configurations/omp-amazon-bedrock-eu-anthropic-claude-sonnet-4-6"
    manifest = (root / "configuration.yaml").read_text()
    assert "harness: omp" in manifest
    assert "provider: amazon-bedrock" in manifest
    assert "region: eu-west-1" in manifest
    assert not (root / "harness/opencode.json").exists()
    assert (root / "workspace").is_dir()

def test_creates_pi_codex_configuration(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)
    result = run_configure(
        repository,
        "--harness",
        "pi",
        "--provider",
        "openai-codex",
        "--model",
        "gpt-5.4",
        "--auth-profile",
        "codex",
    )

    assert result.returncode == 0, result.stderr
    root = repository / "benchmarks/configurations/pi-openai-codex-gpt-5-4"
    manifest = (root / "configuration.yaml").read_text()
    assert "harness: pi" in manifest
    assert "provider: openai-codex" in manifest
    assert "agent:" not in manifest
    assert list((root / "harness").iterdir()) == []


def test_creates_pi_bedrock_configuration(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)
    result = run_configure(
        repository,
        "--harness",
        "pi",
        "--provider",
        "amazon-bedrock",
        "--bedrock-region",
        "eu-west-1",
        "--model",
        "eu.anthropic.claude-sonnet-4-6",
        "--auth-profile",
        "bedrock",
    )

    assert result.returncode == 0, result.stderr
    root = (
        repository
        / "benchmarks/configurations/pi-amazon-bedrock-eu-anthropic-claude-sonnet-4-6"
    )
    manifest = (root / "configuration.yaml").read_text()
    assert "harness: pi" in manifest
    assert "provider: amazon-bedrock" in manifest
    assert "region: eu-west-1" in manifest
    assert list((root / "harness").iterdir()) == []


def test_rejects_provider_for_native_copilot(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)

    result = run_configure(
        repository,
        "--harness",
        "copilot",
        "--provider",
        "openai",
        "--model",
        "gpt-5.4-mini",
        "--auth-profile",
        "copilot",
    )

    assert result.returncode != 0
    assert "applies only to OpenCode" in result.stderr


def test_refuses_to_overwrite_configuration(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)
    arguments = (
        "--provider",
        "openai",
        "--model",
        "gpt-5.4-mini",
        "--auth-profile",
        "openai",
    )

    assert run_configure(repository, *arguments).returncode == 0
    repeated = run_configure(repository, *arguments)

    assert repeated.returncode != 0
    assert "configuration already exists" in repeated.stderr


def create_skill(root: Path) -> Path:
    skill = root / "ponytail"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: ponytail\ndescription: Prefer minimal changes.\n---\n",
        encoding="utf-8",
    )
    return skill


def test_copies_approved_skill_for_opencode(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)
    skill = create_skill(tmp_path)

    result = run_configure(
        repository,
        "--id",
        "opencode-openai-gpt-5-4-mini-ponytail",
        "--provider",
        "openai",
        "--model",
        "gpt-5.4-mini",
        "--auth-profile",
        "openai",
        "--skill",
        str(skill),
    )

    assert result.returncode == 0, result.stderr
    root = repository / "benchmarks/configurations/opencode-openai-gpt-5-4-mini-ponytail"
    assert (root / "workspace/.agents/skills/ponytail/SKILL.md").is_file()
    config = json.loads((root / "harness/opencode.json").read_text())
    assert config["permission"]["skill"]["*"] == "allow"
    assert "instructions" not in config


def test_copies_approved_skill_for_copilot(tmp_path: Path) -> None:
    repository = scaffold(tmp_path)
    skill = create_skill(tmp_path)

    result = run_configure(
        repository,
        "--harness",
        "copilot",
        "--model",
        "gpt-5.4-mini",
        "--auth-profile",
        "copilot",
        "--skill",
        str(skill),
    )

    assert result.returncode == 0, result.stderr
    root = repository / "benchmarks/configurations/copilot-gpt-5-4-mini"
    assert (root / "workspace/.agents/skills/ponytail/SKILL.md").is_file()
    assert list((root / "harness").iterdir()) == []
