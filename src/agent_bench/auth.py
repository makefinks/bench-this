"""Closed authentication strategies for login, validation, staging, and secrets."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import getpass
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from types import MappingProxyType
from typing import Mapping, NoReturn, Optional

from .catalog import (
    AMAZON_BEDROCK_PROVIDER,
    HARNESS_CATALOG,
    AuthPolicy,
    HarnessSpec,
    ProviderSpec,
    resolve_selection,
)
from .docker import DockerEngine, Mount
from .errors import ConfigurationError, InfrastructureError
from .models import ProjectConfig, TreatmentConfig
from .workspace import _reject_symlinks, copy_contents


PROFILE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
BEDROCK_CREDENTIALS_FILE = Path("credentials.json")
BEDROCK_TOKEN_ENVIRONMENT_VARIABLE = "AWS_BEARER_TOKEN_BEDROCK"
OMP_NATIVE_DATABASE = Path(".omp/agent/agent.db")
OMP_PROVIDER_ENVIRONMENT = {
    "github-copilot": "COPILOT_GITHUB_TOKEN",
    "openai-codex": "OPENAI_CODEX_OAUTH_TOKEN",
    AMAZON_BEDROCK_PROVIDER: BEDROCK_TOKEN_ENVIRONMENT_VARIABLE,
}
PI_AUTH_FILE = Path(".pi/agent/auth.json")
OPENCODE_AUTH_FILE = Path(".local/share/opencode/auth.json")


@dataclass(frozen=True)
class ValidatedAuth:
    """A profile validated once with any parsed secret environment retained."""

    profile: Path
    secret_environment: Mapping[str, str]


@dataclass(frozen=True)
class PreparedAuth:
    """One disposable harness home and its separately injected secrets."""

    home: Path
    profile: Path
    secret_environment: Mapping[str, str]


class AuthStrategy(ABC):
    """Complete lifecycle contract selected by one catalog auth policy."""

    @abstractmethod
    def login(
        self,
        project: ProjectConfig,
        harness: HarnessSpec,
        provider: ProviderSpec,
        profile_name: str,
        docker: DockerEngine,
    ) -> Path:
        raise NotImplementedError

    @abstractmethod
    def validate(
        self,
        config: TreatmentConfig,
        auth_root: Optional[Path] = None,
    ) -> ValidatedAuth:
        raise NotImplementedError

    @abstractmethod
    def stage(
        self,
        config: TreatmentConfig,
        validated: ValidatedAuth,
        destination: Path,
    ) -> None:
        raise NotImplementedError


def auth_profile_root(
    profile: str, harness: str, auth_root: Optional[Path] = None
) -> Path:
    """Resolve one narrowly scoped external credential profile."""

    base = auth_root or Path.home() / ".agent-bench" / "auth"
    return base.expanduser().resolve() / profile / harness


def _profile(config: TreatmentConfig, auth_root: Optional[Path]) -> Path:
    profile = auth_profile_root(config.auth_profile, config.harness, auth_root)
    if not profile.is_dir():
        raise InfrastructureError(
            f"authentication profile not found: {profile}; "
            "run `agent-bench auth login` first"
        )
    _reject_symlinks(profile, "auth_profile")
    return profile


def _files(profile: Path) -> list[Path]:
    return sorted(path.relative_to(profile) for path in profile.rglob("*") if path.is_file())


def _stage_file(validated: ValidatedAuth, destination: Path, relative_path: Path) -> None:
    target = destination / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(validated.profile / relative_path, target)


def _manual_oauth_login(
    destination: Path,
    agent_directory: Path,
    executable: str,
    display_name: str,
    provider: ProviderSpec,
) -> NoReturn:
    agent_dir = destination / agent_directory
    raise ConfigurationError(
        f"{display_name} OAuth login must be completed in the user's terminal. Run:\n"
        f"PI_CODING_AGENT_DIR={agent_dir} {executable}\n"
        f"Then run /login {provider.id} inside {display_name} and retry."
    )


def _one_line_secret(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.isspace()
        or "\n" in value
        or "\r" in value
    ):
        raise ConfigurationError(f"{label} must be one non-empty line")
    return value


def _atomic_json_profile(
    profile: Path,
    relative_path: Path,
    value: Mapping[str, str],
) -> Path:
    if profile.exists():
        _reject_symlinks(profile, "auth_profile")
        existing = _files(profile)
        if existing not in ([], [relative_path]):
            raise ConfigurationError(
                f"refusing to replace broadened authentication profile: {profile}"
            )
    profile.mkdir(parents=True, exist_ok=True)
    profile.chmod(0o700)
    destination = profile / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, separators=(",", ":"))
            handle.write("\n")
        temporary.chmod(0o600)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return profile


def store_bedrock_credential(
    profile_name: str,
    harness_id: str,
    token: str,
    auth_root: Optional[Path] = None,
) -> Path:
    """Atomically store one harness-scoped Bedrock bearer credential."""

    token = _one_line_secret(token, "Amazon Bedrock API key")
    try:
        provider = HARNESS_CATALOG[harness_id].provider(AMAZON_BEDROCK_PROVIDER)
    except KeyError as exc:
        raise ConfigurationError(
            f"unsupported Bedrock bearer-token harness: {harness_id}"
        ) from exc
    if provider.auth_policy is not AuthPolicy.BEDROCK_BEARER:
        raise ConfigurationError(
            f"unsupported Bedrock bearer-token harness: {harness_id}"
        )
    profile = auth_profile_root(profile_name, harness_id, auth_root)
    environment_name = OMP_PROVIDER_ENVIRONMENT[AMAZON_BEDROCK_PROVIDER]
    return _atomic_json_profile(
        profile,
        BEDROCK_CREDENTIALS_FILE,
        {environment_name: token},
    )


def narrow_opencode_profile(destination: Path, provider: str) -> None:
    """Retain only one selected OpenCode credential after interactive login."""

    auth_path = destination / OPENCODE_AUTH_FILE
    try:
        credentials = json.loads(auth_path.read_text(encoding="utf-8"))
        selected = credentials[provider]
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise InfrastructureError(
            f"OpenCode login did not create a valid {provider!r} credential"
        ) from exc
    shutil.rmtree(destination)
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(
        json.dumps({provider: selected}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    auth_path.chmod(0o600)


class NativeCopilotAuth(AuthStrategy):
    """Opaque native Copilot device-login profile lifecycle."""

    def login(self, project, harness, provider, profile_name, docker):
        destination = auth_profile_root(profile_name, harness.id)
        destination.mkdir(parents=True, exist_ok=True)
        print("In Copilot CLI, run /login, finish the device flow, then exit with Ctrl-D.")
        docker.run_interactive(
            project.image.name,
            ["copilot"],
            [Mount(destination, "/home/bench")],
            {
                "HOME": "/home/bench",
                "COPILOT_HOME": "/home/bench/.copilot",
                "NO_COLOR": "1",
            },
        )
        return destination

    def validate(self, config, auth_root=None):
        return ValidatedAuth(_profile(config, auth_root), MappingProxyType({}))

    def stage(self, config, validated, destination):
        copy_contents(validated.profile, destination, "auth_profile")


class OpenCodeProviderAuth(AuthStrategy):
    """Provider-scoped OpenCode OAuth or API credential lifecycle."""

    def login(self, project, harness, provider, profile_name, docker):
        destination = auth_profile_root(profile_name, harness.id)
        destination.mkdir(parents=True, exist_ok=True)
        docker.run_interactive(
            project.image.name,
            ["opencode", "auth", "login", "--provider", provider.id],
            [Mount(destination, "/home/bench")],
            {
                "HOME": "/home/bench",
                "NO_COLOR": "1",
                "XDG_CONFIG_HOME": "/home/bench/.config",
                "XDG_DATA_HOME": "/home/bench/.local/share",
            },
        )
        narrow_opencode_profile(destination, str(provider.id))
        return destination

    def validate(self, config, auth_root=None):
        profile = _profile(config, auth_root)
        if _files(profile) != [OPENCODE_AUTH_FILE]:
            raise ConfigurationError(
                f"OpenCode auth profile contains unexpected files: {profile}; "
                "run auth login again"
            )
        try:
            credentials = json.loads(
                (profile / OPENCODE_AUTH_FILE).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"invalid OpenCode credential file: {profile / OPENCODE_AUTH_FILE}"
            ) from exc
        credential = (
            credentials.get(config.provider) if isinstance(credentials, dict) else None
        )
        if (
            not isinstance(credentials, dict)
            or set(credentials) != {config.provider}
            or not isinstance(credential, dict)
        ):
            raise ConfigurationError(
                f"OpenCode auth profile must contain only provider {config.provider!r}"
            )
        return ValidatedAuth(profile, MappingProxyType({}))

    def stage(self, config, validated, destination):
        _stage_file(validated, destination, OPENCODE_AUTH_FILE)


class OmpOAuthAuth(AuthStrategy):
    """OMP native OAuth database lifecycle with provider narrowing checks."""

    def login(self, project, harness, provider, profile_name, docker):
        destination = auth_profile_root(profile_name, harness.id)
        _manual_oauth_login(
            destination, Path(".omp/agent"), "omp", harness.display_name, provider
        )

    def validate(self, config, auth_root=None):
        profile = _profile(config, auth_root)
        database = profile / OMP_NATIVE_DATABASE
        if not database.is_file():
            raise ConfigurationError(
                f"OMP OAuth profile is missing {OMP_NATIVE_DATABASE}: {profile}"
            )
        try:
            with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
                rows = connection.execute(
                    "SELECT provider, credential_type, disabled_cause "
                    "FROM auth_credentials"
                ).fetchall()
        except sqlite3.Error as exc:
            raise ConfigurationError(f"invalid OMP OAuth database: {database}") from exc
        if rows != [(config.provider, "oauth", None)]:
            raise ConfigurationError(
                f"OMP auth profile must contain only enabled OAuth provider "
                f"{config.provider!r}"
            )
        return ValidatedAuth(profile, MappingProxyType({}))

    def stage(self, config, validated, destination):
        _stage_file(validated, destination, OMP_NATIVE_DATABASE)


class PiOAuthAuth(AuthStrategy):
    """Pi provider-scoped OAuth JSON lifecycle."""

    def login(self, project, harness, provider, profile_name, docker):
        destination = auth_profile_root(profile_name, harness.id)
        _manual_oauth_login(
            destination, Path(".pi/agent"), "pi", harness.display_name, provider
        )

    def validate(self, config, auth_root=None):
        profile = _profile(config, auth_root)
        auth_path = profile / PI_AUTH_FILE
        if not auth_path.is_file():
            raise ConfigurationError(
                f"Pi OAuth profile is missing {PI_AUTH_FILE}: {profile}"
            )
        try:
            credentials = json.loads(auth_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"invalid Pi credential file: {auth_path}") from exc
        credential = credentials.get(config.provider) if isinstance(credentials, dict) else None
        if (
            not isinstance(credentials, dict)
            or set(credentials) != {config.provider}
            or not isinstance(credential, dict)
            or credential.get("type") != "oauth"
        ):
            raise ConfigurationError(
                f"Pi auth profile must contain only OAuth provider {config.provider!r}"
            )
        return ValidatedAuth(profile, MappingProxyType({}))

    def stage(self, config, validated, destination):
        _stage_file(validated, destination, PI_AUTH_FILE)


class BedrockBearerAuth(AuthStrategy):
    """Runner-owned Bedrock bearer-token lifecycle for every supported harness."""

    def login(self, project, harness, provider, profile_name, docker):
        token = getpass.getpass("Amazon Bedrock API key: ")
        return store_bedrock_credential(profile_name, harness.id, token)

    def validate(self, config, auth_root=None):
        profile = _profile(config, auth_root)
        if _files(profile) != [BEDROCK_CREDENTIALS_FILE]:
            raise ConfigurationError(
                f"Amazon Bedrock auth profile contains unexpected files: {profile}; "
                "run auth login again"
            )
        credential_path = profile / BEDROCK_CREDENTIALS_FILE
        try:
            credentials = json.loads(credential_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"invalid Amazon Bedrock credential file: {credential_path}"
            ) from exc
        environment_name = OMP_PROVIDER_ENVIRONMENT[AMAZON_BEDROCK_PROVIDER]
        token = credentials.get(environment_name) if isinstance(credentials, dict) else None
        if not isinstance(credentials, dict) or set(credentials) != {environment_name}:
            raise ConfigurationError(
                "Amazon Bedrock auth profile must contain one valid bearer token"
            )
        try:
            token = _one_line_secret(token, "Amazon Bedrock auth profile bearer token")
        except ConfigurationError as exc:
            raise ConfigurationError(
                "Amazon Bedrock auth profile must contain one valid bearer token"
            ) from exc
        return ValidatedAuth(
            profile,
            MappingProxyType({environment_name: token}),
        )

    def stage(self, config, validated, destination):
        return None


AUTH_STRATEGIES: Mapping[AuthPolicy, AuthStrategy] = MappingProxyType(
    {
        AuthPolicy.NATIVE_COPILOT: NativeCopilotAuth(),
        AuthPolicy.OPENCODE_PROVIDER: OpenCodeProviderAuth(),
        AuthPolicy.OMP_OAUTH: OmpOAuthAuth(),
        AuthPolicy.PI_OAUTH: PiOAuthAuth(),
        AuthPolicy.BEDROCK_BEARER: BedrockBearerAuth(),
    }
)


def auth_strategy_for(config: TreatmentConfig) -> AuthStrategy:
    """Resolve the complete strategy selected by a validated treatment."""

    try:
        return AUTH_STRATEGIES[config.auth_policy]
    except KeyError as exc:
        raise ConfigurationError(
            f"unregistered authentication policy: {config.auth_policy}"
        ) from exc


def validate_auth_profile(
    config: TreatmentConfig,
    auth_root: Optional[Path] = None,
) -> Path:
    """Validate one complete profile lifecycle and return its source directory."""

    return auth_strategy_for(config).validate(config, auth_root).profile


def prepare_home(
    config: TreatmentConfig,
    destination: Path,
    auth_root: Optional[Path] = None,
) -> PreparedAuth:
    """Validate once, stage approved state, overlay config, and retain secrets."""

    strategy = auth_strategy_for(config)
    validated = strategy.validate(config, auth_root)
    destination.mkdir(parents=True, exist_ok=True)
    strategy.stage(config, validated, destination)
    copy_contents(
        config.harness_config,
        destination / config.harness_spec.config_home,
        "harness_config",
    )
    return PreparedAuth(
        home=destination,
        profile=validated.profile,
        secret_environment=validated.secret_environment,
    )


def login(
    project: ProjectConfig,
    harness_id: str,
    profile_name: str,
    provider_id: Optional[str] = None,
    docker: Optional[DockerEngine] = None,
) -> Path:
    """Execute the catalog-selected login lifecycle for one profile."""

    if not PROFILE_PATTERN.fullmatch(profile_name):
        raise ConfigurationError(
            "profile must use lowercase letters, digits, and hyphens"
        )
    try:
        harness, provider = resolve_selection(harness_id, provider_id)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc
    try:
        strategy = AUTH_STRATEGIES[provider.auth_policy]
    except KeyError as exc:
        raise ConfigurationError(
            f"unregistered authentication policy: {provider.auth_policy}"
        ) from exc
    return strategy.login(
        project,
        harness,
        provider,
        profile_name,
        docker or DockerEngine(),
    )
