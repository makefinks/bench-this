"""Static support catalog shared by runner and bundled skill tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Optional


class ModelReferenceForm(str, Enum):
    """How a harness expects a selected provider and model to be rendered."""

    PLAIN = "plain"
    QUALIFIED = "qualified"


class AdapterKind(str, Enum):
    """Closed set of harness wire-protocol implementations."""

    COPILOT = "copilot"
    OPENCODE = "opencode"
    OMP = "omp"
    PI = "pi"


class AuthPolicy(str, Enum):
    """Closed set of complete authentication profile lifecycles."""

    NATIVE_COPILOT = "native-copilot"
    OPENCODE_PROVIDER = "opencode-provider"
    OMP_OAUTH = "omp-oauth"
    PI_OAUTH = "pi-oauth"
    BEDROCK_BEARER = "bedrock-bearer"


class WriterKind(str, Enum):
    """Closed set of harness-native configuration writers."""

    NONE = "none"
    OPENCODE = "opencode"


AMAZON_BEDROCK_PROVIDER = "amazon-bedrock"


@dataclass(frozen=True)
class InstallerSpec:

    """Pinned build arguments and commands for one harness executable."""

    arguments: Mapping[str, str]
    commands: tuple[str, ...]


@dataclass(frozen=True)
class ProviderSpec:
    """Provider policy scoped to one harness catalog entry."""

    id: Optional[str]
    auth_policy: AuthPolicy
    pricing_provider: str
    allowed_fields: frozenset[str] = field(default_factory=frozenset)
    required_fields: frozenset[str] = field(default_factory=frozenset)
    allow_automatic_model: bool = False


@dataclass(frozen=True)
class HarnessSpec:
    """Cross-cutting metadata used by generic treatment consumers."""

    id: str
    display_name: str
    model_reference: ModelReferenceForm
    providers: Mapping[Optional[str], ProviderSpec]
    allowed_fields: frozenset[str]
    required_fields: frozenset[str]
    config_home: str
    installer: InstallerSpec
    adapter: AdapterKind
    writer: WriterKind
    generator_defaults: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def provider(self, provider_id: Optional[str]) -> ProviderSpec:
        """Resolve an explicit provider selection without a generic fallback."""

        return self.providers[provider_id]


COMMON_REQUIRED_FIELDS = frozenset(
    {
        "id",
        "harness",
        "model",
        "harness_config",
        "workspace_config",
        "auth_profile",
    }
)
COMMON_OPTIONAL_FIELDS = frozenset({"arguments"})
BEDROCK_REQUIRED_FIELDS = frozenset({"region"})
BEDROCK_OPTIONAL_FIELDS = frozenset({"wire_api"})
BEDROCK_FIELDS = BEDROCK_REQUIRED_FIELDS | BEDROCK_OPTIONAL_FIELDS
GITHUB_COPILOT_FIELDS = frozenset({"github_copilot_business"})


def _provider(
    provider_id: Optional[str],
    auth_policy: AuthPolicy,
    pricing_provider: str,
    *,
    allowed_fields: frozenset[str] = frozenset(),
    required_fields: frozenset[str] = frozenset(),
    allow_automatic_model: bool = False,
) -> ProviderSpec:
    return ProviderSpec(
        id=provider_id,
        auth_policy=auth_policy,
        pricing_provider=pricing_provider,
        allowed_fields=allowed_fields,
        required_fields=required_fields,
        allow_automatic_model=allow_automatic_model,
    )


BEDROCK_PROVIDER = _provider(
    AMAZON_BEDROCK_PROVIDER,
    AuthPolicy.BEDROCK_BEARER,
    AMAZON_BEDROCK_PROVIDER,
    allowed_fields=BEDROCK_FIELDS,
    required_fields=BEDROCK_REQUIRED_FIELDS,
)

HARNESS_CATALOG: Mapping[str, HarnessSpec] = MappingProxyType(
    {
        "copilot": HarnessSpec(
            id="copilot",
            display_name="GitHub Copilot CLI",
            model_reference=ModelReferenceForm.PLAIN,
            providers=MappingProxyType(
                {
                    None: _provider(
                        None,
                        AuthPolicy.NATIVE_COPILOT,
                        "github-copilot",
                    ),
                    AMAZON_BEDROCK_PROVIDER: BEDROCK_PROVIDER,
                }
            ),
            allowed_fields=COMMON_REQUIRED_FIELDS
            | COMMON_OPTIONAL_FIELDS
            | frozenset({"provider"}),
            required_fields=COMMON_REQUIRED_FIELDS,
            config_home=".copilot",
            installer=InstallerSpec(
                arguments=MappingProxyType({"COPILOT_CLI_VERSION": "1.0.73"}),
                commands=('npm install --global "@github/copilot@${COPILOT_CLI_VERSION}"',),
            ),
            adapter=AdapterKind.COPILOT,
            writer=WriterKind.NONE,
        ),
        "opencode": HarnessSpec(
            id="opencode",
            display_name="OpenCode",
            model_reference=ModelReferenceForm.QUALIFIED,
            providers=MappingProxyType(
                {
                    "amazon-bedrock": BEDROCK_PROVIDER,
                    "github-copilot": _provider(
                        "github-copilot",
                        AuthPolicy.OPENCODE_PROVIDER,
                        "github-copilot",
                        allowed_fields=GITHUB_COPILOT_FIELDS,
                    ),
                    "openai": _provider(
                        "openai", AuthPolicy.OPENCODE_PROVIDER, "openai"
                    ),
                    "opencode": _provider(
                        "opencode", AuthPolicy.OPENCODE_PROVIDER, "opencode"
                    ),
                    "opencode-go": _provider(
                        "opencode-go", AuthPolicy.OPENCODE_PROVIDER, "opencode-go"
                    ),
                }
            ),
            allowed_fields=COMMON_REQUIRED_FIELDS
            | COMMON_OPTIONAL_FIELDS
            | frozenset({"provider", "agent"}),
            required_fields=COMMON_REQUIRED_FIELDS | frozenset({"provider", "agent"}),
            config_home=".config/opencode",
            installer=InstallerSpec(
                arguments=MappingProxyType({"OPENCODE_VERSION": "1.17.18"}),
                commands=('npm install --global "opencode-ai@${OPENCODE_VERSION}"',),
            ),
            adapter=AdapterKind.OPENCODE,
            writer=WriterKind.OPENCODE,
            generator_defaults=MappingProxyType({"agent": "build"}),
        ),
        "omp": HarnessSpec(
            id="omp",
            display_name="Oh My Pi",
            model_reference=ModelReferenceForm.QUALIFIED,
            providers=MappingProxyType(
                {
                    "amazon-bedrock": BEDROCK_PROVIDER,
                    "github-copilot": _provider(
                        "github-copilot",
                        AuthPolicy.OMP_OAUTH,
                        "github-copilot",
                    ),
                    "openai-codex": _provider(
                        "openai-codex", AuthPolicy.OMP_OAUTH, "openai"
                    ),
                }
            ),
            allowed_fields=COMMON_REQUIRED_FIELDS
            | COMMON_OPTIONAL_FIELDS
            | frozenset({"provider"}),
            required_fields=COMMON_REQUIRED_FIELDS | frozenset({"provider"}),
            config_home=".omp/agent",
            installer=InstallerSpec(
                arguments=MappingProxyType(
                    {"BUN_VERSION": "1.3.14", "OMP_VERSION": "17.2.9"}
                ),
                commands=(
                    'npm install --global "bun@${BUN_VERSION}"',
                    'BUN_INSTALL=/usr/local bun install --global "@oh-my-pi/pi-coding-agent@${OMP_VERSION}"',
                ),
            ),
            adapter=AdapterKind.OMP,
            writer=WriterKind.NONE,
        ),
        "pi": HarnessSpec(
            id="pi",
            display_name="Pi",
            model_reference=ModelReferenceForm.QUALIFIED,
            providers=MappingProxyType(
                {
                    "amazon-bedrock": BEDROCK_PROVIDER,
                    "github-copilot": _provider(
                        "github-copilot", AuthPolicy.PI_OAUTH, "github-copilot"
                    ),
                    "openai-codex": _provider(
                        "openai-codex", AuthPolicy.PI_OAUTH, "openai"
                    ),
                }
            ),
            allowed_fields=COMMON_REQUIRED_FIELDS
            | COMMON_OPTIONAL_FIELDS
            | frozenset({"provider"}),
            required_fields=COMMON_REQUIRED_FIELDS | frozenset({"provider"}),
            config_home=".pi/agent",
            installer=InstallerSpec(
                arguments=MappingProxyType(
                    {
                        "PI_MCP_ADAPTER_VERSION": "2.27.0",
                        "PI_VERSION": "0.84.2",
                    }
                ),
                commands=(
                    'npm install --global --ignore-scripts "@earendil-works/pi-coding-agent@${PI_VERSION}"',
                    'npm install --prefix /opt/pi-mcp-adapter --ignore-scripts "pi-mcp-adapter@${PI_MCP_ADAPTER_VERSION}"',
                ),
            ),
            adapter=AdapterKind.PI,
            writer=WriterKind.NONE,
        ),
    }
)

KNOWN_TREATMENT_FIELDS = frozenset(
    field_name
    for harness in HARNESS_CATALOG.values()
    for provider in harness.providers.values()
    for field_name in harness.allowed_fields | provider.allowed_fields
)


def supported_selections() -> tuple[tuple[HarnessSpec, ProviderSpec], ...]:
    """Return every declared harness/provider pair in deterministic order."""

    return tuple(
        (harness, provider)
        for harness in HARNESS_CATALOG.values()
        for provider in harness.providers.values()
    )


def resolve_selection(
    harness_id: object,
    provider_id: object = None,
    *,
    provider_supplied: bool | None = None,
) -> tuple[HarnessSpec, ProviderSpec]:
    """Resolve one catalog selection and enforce its provider contract."""

    if not isinstance(harness_id, str) or harness_id not in HARNESS_CATALOG:
        supported = ", ".join(sorted(HARNESS_CATALOG))
        raise ValueError(f"harness must be one of: {supported}")
    harness = HARNESS_CATALOG[harness_id]
    supplied = provider_id is not None if provider_supplied is None else provider_supplied
    if supplied:
        if not isinstance(provider_id, str) or provider_id not in harness.providers:
            supported = ", ".join(
                sorted(provider for provider in harness.providers if provider is not None)
            )
            raise ValueError(f"{harness.id} provider must be one of: {supported}")
        return harness, harness.provider(provider_id)
    if None in harness.providers:
        return harness, harness.provider(None)
    raise ValueError(f"{harness.display_name} requires provider")
