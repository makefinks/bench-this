"""Load YAML into strict v1 models and reject ambiguous or unsafe inputs."""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import yaml

from .errors import ConfigurationError
from .models import (
    Defaults,
    HarnessConfig,
    ImageConfig,
    ModelPrice,
    ProjectConfig,
    TaskConfig,
)


ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{7,64}$")
AMAZON_BEDROCK_PROVIDER = "amazon-bedrock"
SUPPORTED_OPENCODE_PROVIDERS = {
    AMAZON_BEDROCK_PROVIDER,
    "github-copilot",
    "openai",
    "opencode",
    "opencode-go",
}


def _load_mapping(path: Path) -> Dict[str, Any]:
    """Read one YAML document while normalizing parse and shape failures."""

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"missing configuration file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"{path} must contain a YAML mapping")
    return data


def _require(data: Mapping[str, Any], keys: Iterable[str], path: Path) -> None:
    """Report all absent required keys together for actionable validation errors."""

    missing = [key for key in keys if key not in data]
    if missing:
        raise ConfigurationError(f"{path} is missing: {', '.join(missing)}")


def _positive_int(value: Any, label: str) -> int:
    """Accept positive integers but explicitly exclude booleans, which subclass int."""

    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigurationError(f"{label} must be a positive integer")
    return value


def _optional_positive_int(value: Any, label: str) -> Optional[int]:
    """Accept null for an unlimited phase or otherwise require a positive integer."""

    if value is None:
        return None
    return _positive_int(value, label)


def _id(value: Any, label: str) -> str:
    """Constrain IDs so they are safe in directory and run identifiers."""

    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ConfigurationError(f"{label} must use lowercase letters, digits, and hyphens")
    return value


def _relative_path(root: Path, value: Any, label: str) -> Path:
    """Resolve a declared path without allowing it to escape its owning directory."""

    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{label} must be a non-empty relative path")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ConfigurationError(f"{label} must stay inside {root}")
    return root / candidate


def _existing_file(path: Path, label: str) -> Path:
    """Require a regular file early instead of failing deep in a benchmark run."""

    if not path.is_file():
        raise ConfigurationError(f"{label} does not exist or is not a file: {path}")
    return path


def _existing_directory(path: Path, label: str) -> Path:
    """Require a directory early instead of silently treating a typo as empty input."""

    if not path.is_dir():
        raise ConfigurationError(f"{label} does not exist or is not a directory: {path}")
    return path


def load_project(benchmark_dir: Path) -> ProjectConfig:
    """Load the single v1 project environment and optional pricing table."""

    benchmark_dir = benchmark_dir.resolve()
    project_root = benchmark_dir.parent
    path = benchmark_dir / "benchmark.yaml"
    data = _load_mapping(path)
    _require(data, ("version", "image", "setup_command"), path)
    if data["version"] != 1:
        raise ConfigurationError(f"{path}: only version 1 is supported")
    if data.get("compose_file") is not None:
        raise ConfigurationError("compose_file is reserved for a future version")
    image = data["image"]
    if not isinstance(image, dict):
        raise ConfigurationError(f"{path}: image must be a mapping")
    _require(image, ("name", "dockerfile"), path)
    image_name = image["name"]
    if not isinstance(image_name, str) or not image_name.strip():
        raise ConfigurationError("image.name must be a non-empty string")
    defaults_data = data.get("defaults", {})
    if not isinstance(defaults_data, dict):
        raise ConfigurationError("defaults must be a mapping")
    evaluator_timeout = _positive_int(
        defaults_data.get("evaluator_timeout_seconds", 300),
        "defaults.evaluator_timeout_seconds",
    )
    defaults = Defaults(
        solver_timeout_seconds=_optional_positive_int(
            defaults_data.get("solver_timeout_seconds"),
            "defaults.solver_timeout_seconds",
        ),
        evaluator_timeout_seconds=evaluator_timeout,
        setup_timeout_seconds=_positive_int(
            defaults_data.get("setup_timeout_seconds", evaluator_timeout),
            "defaults.setup_timeout_seconds",
        ),
        repetitions=_positive_int(defaults_data.get("repetitions", 1), "defaults.repetitions"),
    )
    prices = {}
    price_data = data.get("prices", {})
    if not isinstance(price_data, dict):
        raise ConfigurationError("prices must be a mapping")
    for model, values in price_data.items():
        if not isinstance(model, str) or not isinstance(values, dict):
            raise ConfigurationError("each price entry must map a model to rates")
        try:
            prices[model] = ModelPrice(**{key: float(value) for key, value in values.items()})
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"invalid price entry for {model}: {exc}") from exc
        if any(value < 0 for value in prices[model].__dict__.values()):
            raise ConfigurationError(f"price rates cannot be negative for {model}")
    setup_command = data["setup_command"]
    if not isinstance(setup_command, str) or not setup_command.strip():
        raise ConfigurationError("setup_command must be a non-empty string")
    return ProjectConfig(
        root=project_root,
        benchmark_dir=benchmark_dir,
        image=ImageConfig(
            name=image_name,
            dockerfile=_existing_file(
                _relative_path(project_root, image["dockerfile"], "image.dockerfile"),
                "image.dockerfile",
            ),
        ),
        setup_command=setup_command,
        defaults=defaults,
        prices=prices,
    )


def load_task(path: Path, project: ProjectConfig) -> TaskConfig:
    """Load a historical task and resolve every task-owned path."""

    data = _load_mapping(path)
    _require(
        data,
        (
            "version",
            "id",
            "base_commit",
            "reference_commit",
            "prompt",
            "public_tests_directory",
            "public_test_command",
            "public_test_groups",
            "hidden_tests_directory",
            "test_command",
            "requirement_groups",
        ),
        path,
    )
    if data["version"] != 1:
        raise ConfigurationError(f"{path}: only version 1 is supported")
    task_id = _id(data["id"], "task id")
    if path.parent.name != task_id:
        raise ConfigurationError(f"task id {task_id!r} must match directory {path.parent.name!r}")
    for key in ("base_commit", "reference_commit"):
        if not isinstance(data[key], str) or not COMMIT_PATTERN.fullmatch(data[key]):
            raise ConfigurationError(f"{path}: {key} must be a 7-64 character commit hash")
    test_command = data["test_command"]
    if not isinstance(test_command, str) or not test_command.strip():
        raise ConfigurationError(f"{path}: test_command must be a non-empty string")
    prompt_path = _existing_file(
        _relative_path(path.parent, data["prompt"], "prompt"), "prompt"
    )
    hidden_tests_directory = _existing_directory(
        _relative_path(
            path.parent, data["hidden_tests_directory"], "hidden_tests_directory"
        ),
        "hidden_tests_directory",
    )
    requirement_groups = data["requirement_groups"]
    if not isinstance(requirement_groups, list) or not requirement_groups or not all(
        isinstance(group, str) and ID_PATTERN.fullmatch(group) for group in requirement_groups
    ):
        raise ConfigurationError(
            f"{path}: requirement_groups must be a non-empty list of lowercase hyphenated IDs"
        )
    if len(requirement_groups) != len(set(requirement_groups)):
        raise ConfigurationError(f"{path}: requirement_groups must be unique")
    public_tests_directory = _existing_directory(
        _relative_path(
            path.parent,
            data["public_tests_directory"],
            "public_tests_directory",
        ),
        "public_tests_directory",
    )
    public_test_command = data["public_test_command"]
    if not isinstance(public_test_command, str) or not public_test_command.strip():
        raise ConfigurationError(f"{path}: public_test_command must be a non-empty string")
    public_test_groups = data["public_test_groups"]
    if not isinstance(public_test_groups, list) or not public_test_groups or not all(
        isinstance(group, str) and ID_PATTERN.fullmatch(group) for group in public_test_groups
    ):
        raise ConfigurationError(
            f"{path}: public_test_groups must be a non-empty list of lowercase hyphenated IDs"
        )
    if len(public_test_groups) != len(set(public_test_groups)):
        raise ConfigurationError(f"{path}: public_test_groups must be unique")
    if (
        public_tests_directory == hidden_tests_directory
        or public_tests_directory in hidden_tests_directory.parents
        or hidden_tests_directory in public_tests_directory.parents
    ):
        raise ConfigurationError(
            f"{path}: public_tests_directory and hidden_tests_directory must be separate"
        )
    return TaskConfig(
        root=path.parent,
        id=task_id,
        base_commit=data["base_commit"],
        reference_commit=data["reference_commit"],
        prompt_path=prompt_path,
        public_directory=_relative_path(
            path.parent, data.get("public_directory", "public"), "public_directory"
        ),
        hidden_tests_directory=hidden_tests_directory,
        test_command=test_command,
        solver_timeout_seconds=_optional_positive_int(
            data.get("solver_timeout_seconds", project.defaults.solver_timeout_seconds),
            "solver_timeout_seconds",
        ),
        requirement_groups=requirement_groups,
        public_tests_directory=public_tests_directory,
        public_test_command=public_test_command,
        public_test_groups=public_test_groups,
    )


def load_harness(path: Path) -> HarnessConfig:
    """Load one pinned experimental treatment and enforce v1 provider limits."""

    data = _load_mapping(path)
    _require(
        data,
        ("id", "harness", "model", "harness_config", "workspace_config", "auth_profile"),
        path,
    )
    config_id = _id(data["id"], "configuration id")
    if path.parent.name != config_id:
        raise ConfigurationError(
            f"configuration id {config_id!r} must match directory {path.parent.name!r}"
        )
    harness = data["harness"]
    if harness not in {"copilot", "opencode"}:
        raise ConfigurationError(f"{path}: harness must be copilot or opencode")
    model = data["model"]
    if not isinstance(model, str) or not model.strip() or model == "auto":
        raise ConfigurationError(f"{path}: model must be explicitly pinned")
    provider = data.get("provider")
    agent = data.get("agent")
    if harness == "opencode":
        if provider not in SUPPORTED_OPENCODE_PROVIDERS:
            supported = ", ".join(sorted(SUPPORTED_OPENCODE_PROVIDERS))
            raise ConfigurationError(
                f"v1 OpenCode provider must be one of: {supported}"
            )
        if not isinstance(agent, str) or not agent:
            raise ConfigurationError("OpenCode configurations require an agent")
    arguments = data.get("arguments", [])
    if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
        raise ConfigurationError(f"{path}: arguments must be a list of strings")
    auth_profile = _id(data["auth_profile"], "auth_profile")
    harness_config = _existing_directory(
        _relative_path(path.parent, data["harness_config"], "harness_config"),
        "harness_config",
    )
    workspace_config = _existing_directory(
        _relative_path(path.parent, data["workspace_config"], "workspace_config"),
        "workspace_config",
    )
    return HarnessConfig(
        root=path.parent,
        id=config_id,
        harness=harness,
        model=model,
        provider=provider,
        agent=agent,
        harness_config=harness_config,
        workspace_config=workspace_config,
        auth_profile=auth_profile,
        arguments=arguments,
    )


def discover_tasks(project: ProjectConfig) -> Dict[str, TaskConfig]:
    """Discover task manifests one directory below the configured task root."""

    task_root = project.benchmark_dir / "tasks"
    tasks = {
        path.parent.name: load_task(path, project)
        for path in sorted(task_root.glob("*/task.yaml"))
    }
    if not tasks:
        raise ConfigurationError(f"no tasks found under {task_root}")
    return tasks


def discover_harnesses(project: ProjectConfig) -> Dict[str, HarnessConfig]:
    """Discover configuration manifests and index them by validated ID."""

    config_root = project.benchmark_dir / "configurations"
    configs = {
        path.parent.name: load_harness(path)
        for path in sorted(config_root.glob("*/configuration.yaml"))
    }
    if not configs:
        raise ConfigurationError(f"no configurations found under {config_root}")
    return configs
