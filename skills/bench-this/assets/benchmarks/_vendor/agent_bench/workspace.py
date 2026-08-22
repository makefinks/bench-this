"""Create sanitized historical workspaces and disposable harness homes."""

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, Optional

from .config import AMAZON_BEDROCK_PROVIDER
from .errors import ConfigurationError, InfrastructureError
from .models import HarnessConfig, ProjectConfig, TaskConfig


PUBLIC_TESTS_WORKSPACE_DIRECTORY = ".agent-bench-public-tests"
BEDROCK_CREDENTIALS_FILE = Path("credentials.json")
BEDROCK_TOKEN_ENVIRONMENT_VARIABLE = "AWS_BEARER_TOKEN_BEDROCK"
OMP_CREDENTIALS_FILE = Path("credentials.json")
OMP_NATIVE_DATABASE = Path(".omp/agent/agent.db")
OMP_PROVIDER_ENVIRONMENT = {
    "github-copilot": "COPILOT_GITHUB_TOKEN",
    "openai-codex": "OPENAI_CODEX_OAUTH_TOKEN",
    "amazon-bedrock": "AWS_BEARER_TOKEN_BEDROCK",
}
PI_AUTH_FILE = Path(".pi/agent/auth.json")


def _reject_symlinks(root: Path, label: str) -> None:
    """Prevent benchmark-owned files from smuggling host paths into a container."""

    if not root.exists():
        return
    if root.is_symlink():
        raise ConfigurationError(f"{label} is a symlink: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ConfigurationError(f"{label} contains a symlink: {path}")


def copy_contents(source: Path, destination: Path, label: str) -> None:
    """Overlay a trusted directory while rejecting symlink-based path escapes."""

    if not source.exists():
        return
    if not source.is_dir():
        raise ConfigurationError(f"{label} must be a directory: {source}")
    _reject_symlinks(source, label)
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        # Git placeholders preserve intentionally empty configuration directories but
        # must not become solver-visible workspace or harness files.
        if child.name == ".gitkeep":
            continue
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(
                child,
                target,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".gitkeep"),
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)


def export_commit(repository: Path, commit: str, destination: Path) -> None:
    """Export a commit without Git metadata and remove historical benchmark files."""

    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar") as archive:
        result = subprocess.run(
            ["git", "archive", "--format=tar", f"--output={archive.name}", commit],
            cwd=str(repository),
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise InfrastructureError(
                f"git archive failed for {commit}: {result.stderr.strip()}"
            )
        with tarfile.open(archive.name) as tar:
            # Validate every member before extraction so a partial unsafe tree is
            # never left behind if a malformed archive path is encountered.
            root = destination.resolve()
            for member in tar.getmembers():
                target = (destination / member.name).resolve()
                if os.path.commonpath((str(root), str(target))) != str(root):
                    raise InfrastructureError(f"unsafe archive member: {member.name}")
            tar.extractall(destination)
    shutil.rmtree(destination / "benchmarks", ignore_errors=True)
    assert_sanitized_workspace(destination)


def assert_sanitized_workspace(workspace: Path) -> None:
    """Fail closed if source history or benchmark-private files survived export."""

    forbidden = []
    for path in workspace.rglob("*"):
        if path.name == ".git" or path.relative_to(workspace).parts[0] == "benchmarks":
            forbidden.append(path)
    if forbidden:
        names = ", ".join(str(path.relative_to(workspace)) for path in forbidden[:5])
        raise InfrastructureError(f"snapshot contains private benchmark metadata: {names}")


def prepare_workspace(project: ProjectConfig, task: TaskConfig, config: HarnessConfig, destination: Path) -> None:
    """Build the exact solver-visible tree from history plus public overlays."""

    export_commit(project.root, task.base_commit, destination)
    copy_contents(config.workspace_config, destination, "workspace_config")
    copy_contents(task.public_directory, destination, "public_directory")
    assert_sanitized_workspace(destination)


def stage_public_tests(task: TaskConfig, destination: Path) -> None:
    """Expose an exact public-test copy after setup and immediately before solving."""

    public_tests = destination / PUBLIC_TESTS_WORKSPACE_DIRECTORY
    if public_tests.exists():
        raise ConfigurationError(
            f"reserved public test path already exists: {PUBLIC_TESTS_WORKSPACE_DIRECTORY}"
        )
    copy_contents(task.public_tests_directory, public_tests, "public_tests_directory")


def prepare_evaluator_workspace(candidate: Path, destination: Path) -> None:
    """Create a disposable candidate copy for isolated evaluator setup."""

    # Preserve links rather than following a solver-created link outside the workspace.
    shutil.copytree(candidate, destination, symlinks=True)
    shutil.rmtree(destination / PUBLIC_TESTS_WORKSPACE_DIRECTORY, ignore_errors=True)


def public_test_snapshot(task: TaskConfig, workspace: Path) -> Dict[str, bytes]:
    """Capture supplied test files immediately before the solver can edit them."""

    visible = workspace / PUBLIC_TESTS_WORKSPACE_DIRECTORY
    return {
        path.relative_to(visible).as_posix(): path.read_bytes()
        for path in sorted(visible.rglob("*"))
        if path.is_file()
    }


def public_test_mutations(
    snapshot: Dict[str, bytes], workspace: Path
) -> tuple[list[str], list[str]]:
    """Report supplied public test files changed or deleted by the solver."""

    visible = workspace / PUBLIC_TESTS_WORKSPACE_DIRECTORY
    modified = []
    deleted = []
    for relative, content in snapshot.items():
        target = visible / relative
        if not target.is_file():
            deleted.append(relative)
        elif content != target.read_bytes():
            modified.append(relative)
    return modified, deleted


def auth_profile_root(profile: str, harness: str, auth_root: Optional[Path] = None) -> Path:
    """Resolve one narrowly scoped external credential profile."""

    base = auth_root or Path.home() / ".agent-bench" / "auth"
    return base.expanduser().resolve() / profile / harness


def store_bedrock_api_key(
    profile_name: str,
    token: str,
    auth_root: Optional[Path] = None,
    *,
    harness: str = "opencode",
) -> Path:
    """Atomically replace one runner-owned Bedrock bearer-token profile."""

    if not token or token.isspace() or "\n" in token or "\r" in token:
        raise ConfigurationError("Amazon Bedrock API key must be one non-empty line")
    if harness not in {"opencode", "pi"}:
        raise ConfigurationError(f"unsupported Bedrock API-key harness: {harness}")
    profile = auth_profile_root(profile_name, harness, auth_root)
    if profile.exists():
        _reject_symlinks(profile, "auth_profile")
        files = sorted(
            path.relative_to(profile) for path in profile.rglob("*") if path.is_file()
        )
        if files not in ([], [BEDROCK_CREDENTIALS_FILE]):
            raise ConfigurationError(
                f"refusing to replace broadened authentication profile: {profile}"
            )
    profile.mkdir(parents=True, exist_ok=True)
    profile.chmod(0o700)
    destination = profile / BEDROCK_CREDENTIALS_FILE
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=profile,
            prefix=".credentials-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(
                {BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: token},
                handle,
                separators=(",", ":"),
            )
            handle.write("\n")
        temporary.chmod(0o600)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return profile


def store_omp_credential(
    profile_name: str,
    provider: str,
    token: str,
    auth_root: Optional[Path] = None,
) -> Path:
    """Store one OMP provider token in an isolated runner-owned profile."""

    environment_name = OMP_PROVIDER_ENVIRONMENT.get(provider)
    if environment_name is None:
        raise ConfigurationError(f"unsupported OMP provider: {provider}")
    if not token or token.isspace() or "\n" in token or "\r" in token:
        raise ConfigurationError(f"{provider} credential must be one non-empty line")
    profile = auth_profile_root(profile_name, "omp", auth_root)
    if profile.exists():
        _reject_symlinks(profile, "auth_profile")
        files = sorted(path.relative_to(profile) for path in profile.rglob("*") if path.is_file())
        if files not in ([], [OMP_CREDENTIALS_FILE]):
            raise ConfigurationError(f"refusing to replace broadened authentication profile: {profile}")
    profile.mkdir(parents=True, exist_ok=True)
    profile.chmod(0o700)
    destination = profile / OMP_CREDENTIALS_FILE
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=profile, prefix=".credentials-", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({environment_name: token}, handle, separators=(",", ":"))
            handle.write("\n")
        temporary.chmod(0o600)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return profile

def _validated_bedrock_token(profile: Path) -> str:
    """Read and validate one runner-owned Bedrock bearer-token credential file."""

    try:
        credentials = json.loads(
            (profile / BEDROCK_CREDENTIALS_FILE).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(
            f"invalid Amazon Bedrock credential file: {profile / BEDROCK_CREDENTIALS_FILE}"
        ) from exc
    token = (
        credentials.get(BEDROCK_TOKEN_ENVIRONMENT_VARIABLE)
        if isinstance(credentials, dict)
        and set(credentials) == {BEDROCK_TOKEN_ENVIRONMENT_VARIABLE}
        else None
    )
    if (
        not isinstance(token, str)
        or not token
        or token.isspace()
        or "\n" in token
        or "\r" in token
    ):
        raise ConfigurationError(
            "Amazon Bedrock auth profile must contain one valid bearer token"
        )
    return token


def validate_auth_profile(config: HarnessConfig, auth_root: Optional[Path] = None) -> Path:
    """Reject missing, linked, or broadened credential profiles before a run."""

    profile = auth_profile_root(config.auth_profile, config.harness, auth_root)
    if not profile.is_dir():
        raise InfrastructureError(
            f"authentication profile not found: {profile}; run `agent-bench auth login` first"
        )
    _reject_symlinks(profile, "auth_profile")
    if (
        config.harness in {"opencode", "pi"}
        and config.provider == AMAZON_BEDROCK_PROVIDER
    ):
        files = sorted(
            path.relative_to(profile) for path in profile.rglob("*") if path.is_file()
        )
        if files != [BEDROCK_CREDENTIALS_FILE]:
            raise ConfigurationError(
                f"Amazon Bedrock auth profile contains unexpected files: {profile}; "
                "run auth login again"
            )
        _validated_bedrock_token(profile)
        return profile
    if config.harness == "pi":
        files = sorted(path.relative_to(profile) for path in profile.rglob("*") if path.is_file())
        if PI_AUTH_FILE not in files:
            raise ConfigurationError(
                f"Pi OAuth profile is missing {PI_AUTH_FILE}: {profile}; run auth login again"
            )
        try:
            credentials = json.loads((profile / PI_AUTH_FILE).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"invalid Pi credential file: {profile / PI_AUTH_FILE}") from exc
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
        return profile
    if config.harness == "opencode":
        relative_auth = Path(".local/share/opencode/auth.json")
        files = sorted(path.relative_to(profile) for path in profile.rglob("*") if path.is_file())
        if files != [relative_auth]:
            raise ConfigurationError(
                f"OpenCode auth profile contains unexpected files: {profile}; run auth login again"
            )
        try:
            credentials = json.loads(
                (profile / relative_auth).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"invalid OpenCode credential file: {profile / relative_auth}") from exc
        if not isinstance(credentials, dict) or set(credentials) != {config.provider}:
            raise ConfigurationError(
                f"OpenCode auth profile must contain only provider {config.provider!r}"
            )
    elif config.harness == "omp":
        files = sorted(path.relative_to(profile) for path in profile.rglob("*") if path.is_file())
        if config.provider == AMAZON_BEDROCK_PROVIDER:
            if files != [OMP_CREDENTIALS_FILE]:
                raise ConfigurationError(f"OMP auth profile contains unexpected files: {profile}")
            try:
                credentials = json.loads(
                    (profile / OMP_CREDENTIALS_FILE).read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigurationError(f"invalid OMP credential file: {profile}") from exc
            environment_name = OMP_PROVIDER_ENVIRONMENT[config.provider]
            token = credentials.get(environment_name) if isinstance(credentials, dict) else None
            if (
                not isinstance(credentials, dict)
                or set(credentials) != {environment_name}
                or not isinstance(token, str)
                or not token.strip()
                or "\n" in token
                or "\r" in token
            ):
                raise ConfigurationError(f"OMP auth profile does not match provider {config.provider!r}")
        elif OMP_NATIVE_DATABASE not in files:
            raise ConfigurationError(
                f"OMP OAuth profile is missing {OMP_NATIVE_DATABASE}: {profile}"
            )
    return profile


def auth_environment(
    config: HarnessConfig,
    auth_root: Optional[Path] = None,
) -> Dict[str, str]:
    """Return provider secrets that must be injected instead of staged as files."""

    if config.harness == "omp":
        if config.provider != AMAZON_BEDROCK_PROVIDER:
            validate_auth_profile(config, auth_root)
            return {}
        profile = validate_auth_profile(config, auth_root)
        credentials = json.loads((profile / OMP_CREDENTIALS_FILE).read_text(encoding="utf-8"))
        return credentials
    if (
        config.harness not in {"opencode", "pi"}
        or config.provider != AMAZON_BEDROCK_PROVIDER
    ):
        return {}
    profile = validate_auth_profile(config, auth_root)
    return {BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: _validated_bedrock_token(profile)}


def stage_home(
    config: HarnessConfig,
    destination: Path,
    auth_root: Optional[Path] = None,
    require_auth: bool = True,
) -> None:
    """Copy only selected credentials and harness config into a disposable home."""

    destination.mkdir(parents=True, exist_ok=True)
    profile = auth_profile_root(config.auth_profile, config.harness, auth_root)
    if require_auth:
        validate_auth_profile(config, auth_root)
    # Bearer-token profiles are injected as environment variables, not mounted into HOME.
    pi_oauth = config.harness == "pi" and config.provider != AMAZON_BEDROCK_PROVIDER
    bedrock_bearer = (
        config.harness in {"opencode", "omp", "pi"}
        and config.provider == AMAZON_BEDROCK_PROVIDER
    )
    if (
        profile.exists()
        and not bedrock_bearer
        and not pi_oauth
    ):
        copy_contents(profile, destination, "auth_profile")
    elif profile.exists() and pi_oauth:
        # Interactive Pi login creates settings, catalogs, and sessions beside auth.json.
        # Stage only the selected credential file into the disposable harness home.
        auth_target = destination / PI_AUTH_FILE
        auth_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(profile / PI_AUTH_FILE, auth_target)

    # Harness configuration overlays copied auth state so an auth profile cannot
    # silently replace the experiment's selected settings.
    if config.harness == "copilot":
        config_target = destination / ".copilot"
    elif config.harness == "omp":
        config_target = destination / ".omp" / "agent"
    elif config.harness == "pi":
        config_target = destination / ".pi" / "agent"
    else:
        config_target = destination / ".config" / "opencode"
    copy_contents(config.harness_config, config_target, "harness_config")
