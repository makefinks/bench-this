"""Closed authentication strategies for login, validation, staging, and secrets."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
import urllib.error
import urllib.request
from types import MappingProxyType
from typing import Callable, Mapping, Optional

from .catalog import (
    AMAZON_BEDROCK_PROVIDER,
    HARNESS_CATALOG,
    AuthPolicy,
    HarnessSpec,
    ProviderSpec,
    resolve_selection,
    shared_api_key_providers,
)
from .docker import DockerEngine, Mount
from .errors import BenchmarkError, ConfigurationError, InfrastructureError
from .models import ProjectConfig, TreatmentConfig
from .workspace import _reject_symlinks, copy_contents


PROFILE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
PROVIDER_NAMESPACE = "providers"
PROVIDER_CREDENTIALS_FILE = Path("credentials.json")
API_KEY_FIELD = "api_key"
OMP_NATIVE_DATABASE = Path(".omp/agent/agent.db")
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
    """Resolve one narrowly scoped external harness credential profile."""

    base = auth_root or Path.home() / ".agent-bench" / "auth"
    return base.expanduser().resolve() / profile / harness


def provider_auth_profile_root(
    profile: str, provider: str, auth_root: Optional[Path] = None
) -> Path:
    """Resolve one provider-owned credential profile shared by every harness."""

    base = auth_root or Path.home() / ".agent-bench" / "auth"
    return base.expanduser().resolve() / profile / PROVIDER_NAMESPACE / provider


def _auth_login_command(config: TreatmentConfig) -> str:
    provider = f" --provider {config.provider}" if config.provider is not None else ""
    return (
        f"./benchmarks/run.py auth login --harness {config.harness}{provider} "
        f"--profile {config.auth_profile}"
    )


def _auth_set_key_command(provider: str, profile: str) -> str:
    return (
        f"./benchmarks/run.py auth set-key --provider {provider} "
        f"--profile {profile} --api-key <api-key>"
    )


def _auth_setup_command(config: TreatmentConfig) -> tuple[str, str]:
    if config.auth_policy is AuthPolicy.SHARED_API_KEY:
        return (
            _auth_set_key_command(str(config.provider), config.auth_profile),
            "auth-set-key",
        )
    return _auth_login_command(config), "auth-login"


def _profile(config: TreatmentConfig, auth_root: Optional[Path]) -> Path:
    profile = auth_profile_root(config.auth_profile, config.harness, auth_root)
    if not profile.is_dir():
        raise InfrastructureError(
            f"authentication profile not found: {profile}; "
            f"run `{_auth_login_command(config)}`"
        )
    _reject_symlinks(profile, "auth_profile")
    return profile


def _files(profile: Path) -> list[Path]:
    return sorted(path.relative_to(profile) for path in profile.rglob("*") if path.is_file())


def _replace_profile(pending: Path, destination: Path) -> None:
    """Swap a validated pending profile in while preserving the old profile on failure."""

    if not destination.exists():
        pending.rename(destination)
        return
    _reject_symlinks(destination, "auth_profile")
    backup = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-previous-", dir=destination.parent)
    )
    backup.rmdir()
    destination.rename(backup)
    try:
        pending.rename(destination)
    except BaseException:
        backup.rename(destination)
        raise
    shutil.rmtree(backup)


def _interactive_profile_login(
    destination: Path,
    image: str,
    command: list[str],
    environment: Mapping[str, str],
    docker: DockerEngine,
    finalize: Callable[[Path], None],
) -> Path:
    """Run login in a fresh home and publish only its validated credential artifact."""

    if not docker.image_exists(image):
        raise InfrastructureError(
            f"benchmark image {image!r} is not built; run `./benchmarks/run.py build` "
            "before `auth login`"
        )
    print(
        "Choose the CLI's headless/device-code authentication option. "
        "Browser/localhost callback authentication cannot return to this container."
    )
    for seconds in range(3, 0, -1):
        print(f"Opening interactive login in {seconds}...", flush=True)
        time.sleep(1)
    print("----------------------- DOCKER -----------------------", flush=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-pending-", dir=destination.parent)
    )
    pending.chmod(0o700)
    try:
        docker.run_interactive(
            image,
            command,
            [Mount(pending, "/home/bench")],
            dict(environment),
        )
        finalize(pending)
        _replace_profile(pending, destination)
    finally:
        shutil.rmtree(pending, ignore_errors=True)
    return destination


def _stage_file(validated: ValidatedAuth, destination: Path, relative_path: Path) -> None:
    target = destination / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(validated.profile / relative_path, target)


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


def _read_provider_api_key(profile: Path, provider: str) -> str:
    credential_path = profile / PROVIDER_CREDENTIALS_FILE
    try:
        credentials = json.loads(credential_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(
            f"invalid {provider} API-key credential file: {credential_path}"
        ) from exc
    api_key = credentials.get(API_KEY_FIELD) if isinstance(credentials, dict) else None
    if not isinstance(credentials, dict) or set(credentials) != {API_KEY_FIELD}:
        raise ConfigurationError(
            f"{provider} API-key profile must contain only {API_KEY_FIELD!r}"
        )
    try:
        return _one_line_secret(api_key, f"{provider} API key")
    except ConfigurationError as exc:
        raise ConfigurationError(
            f"{provider} API-key profile must contain one valid API key"
        ) from exc


def set_provider_api_key(
    profile_name: str,
    provider_id: str,
    api_key: str,
    auth_root: Optional[Path] = None,
) -> Path:
    """Atomically store one catalog-declared provider API key."""

    if not PROFILE_PATTERN.fullmatch(profile_name):
        raise ConfigurationError(
            "profile must use lowercase letters, digits, and hyphens"
        )
    api_key = _one_line_secret(api_key, "API key")
    if provider_id not in shared_api_key_providers():
        supported = ", ".join(shared_api_key_providers())
        raise ConfigurationError(
            f"provider must use shared API-key authentication; supported providers: {supported}"
        )
    profile = provider_auth_profile_root(profile_name, provider_id, auth_root)
    profile_root = profile.parents[1]
    if profile_root.exists():
        _reject_symlinks(profile_root, "authentication profile")
    if profile.exists():
        _reject_symlinks(profile, "provider_auth_profile")
        if not profile.is_dir():
            raise ConfigurationError(
                f"provider authentication profile must be a directory: {profile}"
            )
        credential_path = profile / PROVIDER_CREDENTIALS_FILE
        entries = set(profile.iterdir())
        if entries not in (set(), {credential_path}):
            raise ConfigurationError(
                f"refusing to replace broadened authentication profile: {profile}"
            )
        if entries:
            _read_provider_api_key(profile, provider_id)
    for directory in (profile_root, profile.parent):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
    return _atomic_json_profile(
        profile,
        PROVIDER_CREDENTIALS_FILE,
        {API_KEY_FIELD: api_key},
    )


def _write_only_profile_file(
    profile: Path, relative_path: Path, content: bytes
) -> None:
    shutil.rmtree(profile)
    destination = profile / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    profile.chmod(0o700)
    destination.write_bytes(content)
    destination.chmod(0o600)


def narrow_opencode_profile(destination: Path, provider: str) -> None:
    """Retain only one selected OpenCode credential after interactive login."""

    auth_path = destination / OPENCODE_AUTH_FILE
    try:
        credentials = json.loads(auth_path.read_text(encoding="utf-8"))
        selected = credentials[provider]
        if not isinstance(selected, dict):
            raise TypeError
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise InfrastructureError(
            f"OpenCode login did not create a valid {provider!r} credential"
        ) from exc
    content = (json.dumps({provider: selected}, separators=(",", ":")) + "\n").encode()
    _write_only_profile_file(destination, OPENCODE_AUTH_FILE, content)


def _narrow_pi_profile(profile: Path, provider: str) -> None:
    auth_path = profile / PI_AUTH_FILE
    try:
        credentials = json.loads(auth_path.read_text(encoding="utf-8"))
        selected = credentials[provider]
        if not isinstance(selected, dict) or selected.get("type") != "oauth":
            raise TypeError
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise InfrastructureError(
            f"Pi login did not create a valid {provider!r} OAuth credential"
        ) from exc
    content = (json.dumps({provider: selected}, separators=(",", ":")) + "\n").encode()
    _write_only_profile_file(profile, PI_AUTH_FILE, content)


def _narrow_omp_profile(profile: Path, provider: str) -> None:
    database = profile / OMP_NATIVE_DATABASE
    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot = Path(temporary_directory) / "agent.db"
            with (
                sqlite3.connect(f"file:{database}?mode=ro", uri=True) as source,
                sqlite3.connect(snapshot) as destination,
            ):
                source.backup(destination)
            with sqlite3.connect(snapshot) as connection:
                connection.execute("PRAGMA journal_mode=DELETE")
                rows = connection.execute(
                    "SELECT provider, credential_type, disabled_cause FROM auth_credentials"
                ).fetchall()
            content = snapshot.read_bytes()
    except (OSError, sqlite3.Error) as exc:
        raise InfrastructureError("OMP login did not create a valid OAuth database") from exc
    if rows != [(provider, "oauth", None)]:
        raise InfrastructureError(
            f"OMP login did not create only an enabled {provider!r} OAuth credential"
        )
    _write_only_profile_file(profile, OMP_NATIVE_DATABASE, content)


def _narrow_copilot_profile(profile: Path) -> None:
    bundle = profile / ".copilot"
    _reject_symlinks(bundle, "Copilot authentication bundle")
    if not bundle.is_dir() or not _files(bundle):
        raise InfrastructureError("Copilot login did not create a credential bundle")
    for path in profile.iterdir():
        if path != bundle:
            shutil.rmtree(path) if path.is_dir() else path.unlink()


class NativeCopilotAuth(AuthStrategy):
    """Opaque native Copilot device-login profile lifecycle."""

    def login(self, project, harness, provider, profile_name, docker):
        destination = auth_profile_root(profile_name, harness.id)
        print("In Copilot CLI, run /login, finish the device flow, then exit with Ctrl-D.")
        return _interactive_profile_login(
            destination,
            project.image.name,
            ["copilot"],
            {
                "HOME": "/home/bench",
                "COPILOT_HOME": "/home/bench/.copilot",
            },
            docker,
            _narrow_copilot_profile,
        )

    def validate(self, config, auth_root=None):
        profile = _profile(config, auth_root)
        files = _files(profile)
        if not files or any(path.parts[0] != ".copilot" for path in files):
            raise ConfigurationError(
                f"Copilot auth profile contains files outside .copilot: {profile}; "
                f"run `{_auth_login_command(config)}`"
            )
        return ValidatedAuth(profile, MappingProxyType({}))

    def stage(self, config, validated, destination):
        copy_contents(validated.profile, destination, "auth_profile")


class OpenCodeProviderAuth(AuthStrategy):
    """Provider-scoped OpenCode OAuth or API credential lifecycle."""

    def login(self, project, harness, provider, profile_name, docker):
        destination = auth_profile_root(profile_name, harness.id)
        return _interactive_profile_login(
            destination,
            project.image.name,
            ["opencode", "auth", "login", "--provider", provider.id],
            {"HOME": "/home/bench"},
            docker,
            lambda pending: narrow_opencode_profile(pending, str(provider.id)),
        )

    def validate(self, config, auth_root=None):
        profile = _profile(config, auth_root)
        if _files(profile) != [OPENCODE_AUTH_FILE]:
            raise ConfigurationError(
                f"OpenCode auth profile contains unexpected files: {profile}; "
                f"run `{_auth_login_command(config)}`"
            )
        try:
            credentials = json.loads(
                (profile / OPENCODE_AUTH_FILE).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
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
        if provider.id == "openai-codex":
            print(
                "In Oh My Pi, run /login, select ChatGPT, then choose the headless option. "
                "Finish login, then exit."
            )
        else:
            print(
                "In Oh My Pi, run /login, select GitHub Copilot, then choose the "
                "headless/device-code option. Finish login, then exit."
            )
        return _interactive_profile_login(
            destination,
            project.image.name,
            ["omp"],
            {
                "HOME": "/home/bench",
                "PI_CODING_AGENT_DIR": "/home/bench/.omp/agent",
            },
            docker,
            lambda pending: _narrow_omp_profile(pending, str(provider.id)),
        )

    def validate(self, config, auth_root=None):
        profile = _profile(config, auth_root)
        if _files(profile) != [OMP_NATIVE_DATABASE]:
            raise ConfigurationError(
                f"OMP auth profile contains unexpected files: {profile}; "
                f"run `{_auth_login_command(config)}`"
            )
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
        print(f"In {harness.display_name}, run /login {provider.id}, finish login, then exit.")
        return _interactive_profile_login(
            destination,
            project.image.name,
            ["pi"],
            {
                "HOME": "/home/bench",
                "PI_CODING_AGENT_DIR": "/home/bench/.pi/agent",
            },
            docker,
            lambda pending: _narrow_pi_profile(pending, str(provider.id)),
        )

    def validate(self, config, auth_root=None):
        profile = _profile(config, auth_root)
        if _files(profile) != [PI_AUTH_FILE]:
            raise ConfigurationError(
                f"Pi auth profile contains unexpected files: {profile}; "
                f"run `{_auth_login_command(config)}`"
            )
        auth_path = profile / PI_AUTH_FILE
        if not auth_path.is_file():
            raise ConfigurationError(
                f"Pi OAuth profile is missing {PI_AUTH_FILE}: {profile}"
            )
        try:
            credentials = json.loads(auth_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
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


class SharedApiKeyAuth(AuthStrategy):
    """Provider-owned API-key lifecycle shared across supported harnesses."""

    def login(self, project, harness, provider, profile_name, docker):
        raise ConfigurationError(
            f"{provider.id} uses provider-scoped API keys; run "
            f"`{_auth_set_key_command(str(provider.id), profile_name)}`"
        )

    def validate(self, config, auth_root=None):
        provider = str(config.provider)
        profile = provider_auth_profile_root(config.auth_profile, provider, auth_root)
        if not profile.is_dir():
            legacy = auth_profile_root(config.auth_profile, config.harness, auth_root)
            guidance = _auth_set_key_command(provider, config.auth_profile)
            if legacy.is_dir():
                raise ConfigurationError(
                    f"harness-scoped {provider} authentication profiles are no longer "
                    f"supported: {legacy}; run `{guidance}`"
                )
            raise InfrastructureError(
                f"authentication profile not found: {profile}; run `{guidance}`"
            )
        _reject_symlinks(profile, "provider_auth_profile")
        if _files(profile) != [PROVIDER_CREDENTIALS_FILE]:
            raise ConfigurationError(
                f"{provider} API-key profile contains unexpected files: {profile}; "
                f"run `{_auth_set_key_command(provider, config.auth_profile)}`"
            )
        environment_name = config.provider_spec.api_key_environment
        if environment_name is None:
            raise ConfigurationError(
                f"shared API-key provider {provider!r} has no environment mapping"
            )
        return ValidatedAuth(
            profile,
            MappingProxyType(
                {environment_name: _read_provider_api_key(profile, provider)}
            ),
        )

    def stage(self, config, validated, destination):
        return None


AUTH_STRATEGIES: Mapping[AuthPolicy, AuthStrategy] = MappingProxyType(
    {
        AuthPolicy.NATIVE_COPILOT: NativeCopilotAuth(),
        AuthPolicy.OPENCODE_PROVIDER: OpenCodeProviderAuth(),
        AuthPolicy.OMP_OAUTH: OmpOAuthAuth(),
        AuthPolicy.PI_OAUTH: PiOAuthAuth(),
        AuthPolicy.SHARED_API_KEY: SharedApiKeyAuth(),
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


def _authentication_required(config: TreatmentConfig, cause: BenchmarkError) -> BenchmarkError:
    command, action = _auth_setup_command(config)
    error_type = ConfigurationError if isinstance(cause, ConfigurationError) else InfrastructureError
    return error_type(
        f"authentication required for harness={config.harness}, provider={config.provider}, "
        f"profile={config.auth_profile}: {cause}; run `{command}`\n"
        f"ACTION_REQUIRED: {action}"
    )


def prepare_home(
    config: TreatmentConfig,
    destination: Path,
    auth_root: Optional[Path] = None,
) -> PreparedAuth:
    """Validate once, stage approved state, overlay config, and retain secrets."""

    strategy = auth_strategy_for(config)
    try:
        validated = strategy.validate(config, auth_root)
    except (ConfigurationError, InfrastructureError) as exc:
        raise _authentication_required(config, exc) from exc
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


def probe_bedrock_wire_api(
    profile_name: str,
    harness_id: str,
    model: str,
    region: str,
    auth_root: Optional[Path] = None,
    timeout: int = 20,
) -> dict:
    """Probe Mantle for one model to determine supported wire APIs."""

    if not PROFILE_PATTERN.fullmatch(profile_name):
        raise ConfigurationError(
            "profile must use lowercase letters, digits, and hyphens"
        )
    if harness_id not in HARNESS_CATALOG:
        raise ConfigurationError(f"unknown harness: {harness_id}")
    try:
        HARNESS_CATALOG[harness_id].provider(AMAZON_BEDROCK_PROVIDER)
    except KeyError as exc:
        raise ConfigurationError(
            f"unsupported Bedrock bearer-token harness: {harness_id}"
        ) from exc
    if not isinstance(model, str) or not model.strip():
        raise ConfigurationError("model must be a non-empty string")
    if not isinstance(region, str) or not re.fullmatch(
        r"^[a-z]{2}(?:-[a-z0-9]+)+-[0-9]+$", region
    ):
        raise ConfigurationError(f"invalid Bedrock region: {region!r}")
    profile = provider_auth_profile_root(
        profile_name, AMAZON_BEDROCK_PROVIDER, auth_root
    )
    if not profile.is_dir():
        legacy = auth_profile_root(profile_name, harness_id, auth_root)
        guidance = _auth_set_key_command(AMAZON_BEDROCK_PROVIDER, profile_name)
        if legacy.is_dir():
            raise ConfigurationError(
                f"harness-scoped {AMAZON_BEDROCK_PROVIDER} authentication profiles "
                f"are no longer supported: {legacy}; run `{guidance}`"
            )
        raise InfrastructureError(
            f"authentication profile not found: {profile}; run `{guidance}`"
        )
    _reject_symlinks(profile, "provider_auth_profile")
    if _files(profile) != [PROVIDER_CREDENTIALS_FILE]:
        raise ConfigurationError(
            f"Amazon Bedrock API-key profile contains unexpected files: {profile}"
        )
    token = _read_provider_api_key(profile, AMAZON_BEDROCK_PROVIDER)

    def _probe(url: str, payload: dict) -> tuple[bool, int | None, str | None]:
        """Return support flag; raise only on transport/auth failures."""

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                response.read()
                return True, response.status, None
        except urllib.error.HTTPError as exc:  # noqa: PERF203
            body = exc.read().decode("utf-8", "replace")
            lower = body.lower()
            if exc.code == 400 and (
                "does not support" in lower or "isn't supported" in lower
            ):
                return False, exc.code, body[:500]
            # Surface auth/region/config errors directly.
            raise InfrastructureError(
                f"Bedrock probe failed for {url}: HTTP {exc.code}: {body[:500]}"
            ) from exc
        except OSError as exc:
            raise InfrastructureError(
                f"Bedrock probe failed for {url}: {exc}"
            ) from exc

    completions_ok, completions_status, completions_error = _probe(
        f"https://bedrock-mantle.{region}.api.aws/v1/chat/completions",
        {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 16},
    )
    responses_ok, responses_status, responses_error = _probe(
        f"https://bedrock-mantle.{region}.api.aws/v1/responses",
        {"model": model, "input": "ping", "max_output_tokens": 16},
    )
    if completions_ok and responses_ok:
        recommended = "completions"
    elif completions_ok:
        recommended = "completions"
    elif responses_ok:
        recommended = "responses"
    else:
        recommended = None
    return {
        "model": model,
        "region": region,
        "profile": profile_name,
        "harness": harness_id,
        "completions": completions_ok,
        "responses": responses_ok,
        "wire_api": recommended,
        "details": {
            "completions": {
                "ok": completions_ok,
                "status": completions_status,
                "error": completions_error,
            },
            "responses": {
                "ok": responses_ok,
                "status": responses_status,
                "error": responses_error,
            },
        },
    }


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
