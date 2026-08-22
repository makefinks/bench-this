"""Typed configuration and result records shared across runner components."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .catalog import (
    HARNESS_CATALOG,
    AuthPolicy,
    HarnessSpec,
    ModelReferenceForm,
    ProviderSpec,
)


@dataclass(frozen=True)
class ImageConfig:
    """Docker image identity and the project-relative file used to build it."""

    name: str
    dockerfile: Path


@dataclass(frozen=True)
class Defaults:
    """Project-wide limits used when a task does not provide an override."""

    solver_timeout_seconds: Optional[int] = None
    evaluator_timeout_seconds: int = 300
    repetitions: int = 1
    setup_timeout_seconds: int = 300


@dataclass
class ValidationPhase:
    """Durable state for one setup and evaluator phase."""

    commit: str
    setup: str = "pending"
    evaluator_exit: Optional[int] = None
    logs: Dict[str, str] = field(default_factory=dict)
    public_evaluator_exit: Optional[int] = None
    phase_durations: Dict[str, float] = field(default_factory=dict)


@dataclass
class ValidationReceipt:
    """Versioned authoritative evidence for one integrated task validation."""

    version: int
    attempt_id: str
    task: str
    task_digest: str
    environment_digest: str
    image: Dict[str, str]
    status: str
    base: ValidationPhase
    reference: ValidationPhase
    receipt_path: Optional[str] = None
    error_category: Optional[str] = None


@dataclass(frozen=True)
class ModelPrice:
    """USD rates per million tokens for non-authoritative cost estimates."""

    input_per_million_usd: float
    output_per_million_usd: float
    reasoning_per_million_usd: float = 0.0
    cache_read_per_million_usd: float = 0.0
    cache_write_per_million_usd: float = 0.0


@dataclass(frozen=True)
class ProjectConfig:
    """Validated project-wide benchmark settings with resolved host paths."""

    root: Path
    benchmark_dir: Path
    image: ImageConfig
    setup_command: str
    defaults: Defaults
    prices: Dict[str, ModelPrice] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskConfig:
    """One historical task and its private evaluator contract."""

    root: Path
    id: str
    base_commit: str
    reference_commit: str
    prompt_path: Path
    public_directory: Path
    hidden_tests_directory: Path
    test_command: str
    solver_timeout_seconds: Optional[int]
    public_tests_directory: Path
    public_test_command: str
    public_test_groups: List[str]
    requirement_groups: List[str]


@dataclass(frozen=True)
class TreatmentConfig:
    """One selected treatment resolved against the static support catalog."""

    root: Path
    id: str
    harness: str
    model: str
    harness_config: Path
    workspace_config: Path
    auth_profile: str
    arguments: List[str]
    provider: Optional[str] = None
    agent: Optional[str] = None
    region: Optional[str] = None
    github_copilot_business: bool = False

    @property
    def harness_spec(self) -> HarnessSpec:
        """Return the catalog definition selected by this treatment."""

        return HARNESS_CATALOG[self.harness]

    @property
    def provider_spec(self) -> ProviderSpec:
        """Return the harness-scoped provider definition without fallback."""

        return self.harness_spec.provider(self.provider)

    @property
    def auth_policy(self) -> AuthPolicy:
        """Expose the complete authentication lifecycle selected by the catalog."""

        return self.provider_spec.auth_policy

    @property
    def qualified_model(self) -> str:
        """Render the selected model through the harness catalog policy."""

        if self.harness_spec.model_reference is ModelReferenceForm.QUALIFIED:
            return f"{self.provider}/{self.model}"
        return self.model


@dataclass(frozen=True)
class Usage:
    """Normalized token and native-cost telemetry from either harness."""

    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: Optional[int] = None
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    native_cost_usd: Optional[float] = None


@dataclass(frozen=True)
class CommandResult:
    """Captured outcome of a single container invocation."""

    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


@dataclass
class RunResult:
    """Stable JSONL schema emitted once per task/configuration/repetition."""

    task: str
    configuration: str
    repetition: int
    passed: bool
    duration_seconds: float
    task_digest: Optional[str] = None
    configuration_digest: Optional[str] = None
    experiment_id: Optional[str] = None
    run_id: Optional[str] = None
    log_directory: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: Optional[int] = None
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    native_cost_usd: Optional[float] = None
    estimated_cost_usd: Optional[float] = None
    failure_kind: Optional[str] = None
    error: Optional[str] = None
    group_results: Dict[str, bool] = field(default_factory=dict)
    public_test_results: Dict[str, bool] = field(default_factory=dict)
    public_test_mutation_detected: Optional[bool] = None
    public_test_modified_files: List[str] = field(default_factory=list)
    public_test_deleted_files: List[str] = field(default_factory=list)
    solver_duration_seconds: Optional[float] = None
    phase_durations: Dict[str, float] = field(default_factory=dict)
