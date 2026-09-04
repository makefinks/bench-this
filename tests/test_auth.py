"""Tests for reducing interactive login output to narrowly scoped credentials."""

import json
from pathlib import Path
import sqlite3

import pytest

from agent_bench.auth import (
    PROVIDER_CREDENTIALS_FILE,
    OMP_NATIVE_DATABASE,
    OPENCODE_AUTH_FILE,
    PI_AUTH_FILE,
    auth_strategy_for,
    login,
    narrow_opencode_profile,
    prepare_home,
    provider_auth_profile_root,
    set_provider_api_key,
    validate_auth_profile,
)
from agent_bench.docker import Mount
from agent_bench.errors import ConfigurationError, InfrastructureError
from agent_bench.models import TreatmentConfig


@pytest.fixture(autouse=True)
def login_countdown_delays(monkeypatch):
    delays = []
    monkeypatch.setattr("agent_bench.auth.time.sleep", delays.append)
    return delays


def write_omp_auth_database(path, provider):
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE auth_credentials ("
            "provider TEXT, credential_type TEXT, disabled_cause TEXT)"
        )
        connection.execute(
            "INSERT INTO auth_credentials VALUES (?, 'oauth', NULL)",
            (provider,),
        )


def test_narrow_opencode_profile_removes_unrelated_state(tmp_path):
    """Keep only the selected provider while deleting caches and plugin symlinks."""

    profile = tmp_path / "profile"
    auth = profile / ".local/share/opencode/auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(
        json.dumps(
            {
                "openai": {"type": "oauth", "access": "fixture"},
                "github-copilot": {"type": "oauth", "access": "unrelated"},
            }
        ),
        encoding="utf-8",
    )
    plugin = profile / ".config/opencode/node_modules/.bin/plugin"
    plugin.parent.mkdir(parents=True)
    plugin.symlink_to("../plugin/index.js")

    narrow_opencode_profile(profile, "openai")

    assert json.loads(auth.read_text(encoding="utf-8")) == {
        "openai": {"type": "oauth", "access": "fixture"}
    }
    assert not (profile / ".config").exists()


def test_validate_opencode_profile_rejects_login_state(tmp_path):
    """Doctor should identify profiles broadened by an unsafe writable-home diagnostic."""

    profile = tmp_path / "auth/personal/opencode"
    auth = profile / ".local/share/opencode/auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(json.dumps({"openai": {"type": "oauth"}}), encoding="utf-8")
    cache = profile / ".cache/opencode/state"
    cache.parent.mkdir(parents=True)
    cache.write_text("unexpected", encoding="utf-8")
    config = TreatmentConfig(
        root=tmp_path,
        id="openai",
        harness="opencode",
        provider="openai",
        model="gpt-fixed",
        agent="build",
        harness_config=tmp_path,
        workspace_config=tmp_path,
        auth_profile="personal",
        arguments=[],
    )

    with pytest.raises(ConfigurationError, match="unexpected files"):
        validate_auth_profile(config, tmp_path / "auth")


def bedrock_config(tmp_path):
    root = tmp_path / "configuration"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    return TreatmentConfig(
        root=root,
        id="bedrock",
        harness="opencode",
        provider="amazon-bedrock",
        model="eu.anthropic.claude-sonnet-4-5-v1:0",
        agent="build",
        harness_config=root / "harness",
        workspace_config=root / "workspace",
        auth_profile="bedrock",
        arguments=[],
    )


@pytest.mark.parametrize(
    "harness,expected_environment",
    [
        ("copilot", "COPILOT_PROVIDER_API_KEY"),
        ("opencode", "AWS_BEARER_TOKEN_BEDROCK"),
        ("omp", "AWS_BEARER_TOKEN_BEDROCK"),
        ("pi", "AWS_BEARER_TOKEN_BEDROCK"),
    ],
)
def test_one_bedrock_provider_profile_injects_key_for_every_harness_without_staging(
    tmp_path, harness, expected_environment
):
    auth_root = tmp_path / "auth"
    profile = set_provider_api_key(
        "bedrock", "amazon-bedrock", "fixture-token", auth_root
    )
    config = TreatmentConfig(
        **{
            **bedrock_config(tmp_path).__dict__,
            "harness": harness,
            "agent": "build" if harness == "opencode" else None,
        }
    )

    prepared = prepare_home(config, tmp_path / f"{harness}-home", auth_root)

    assert profile == provider_auth_profile_root(
        "bedrock", "amazon-bedrock", auth_root
    )
    assert json.loads(
        (profile / PROVIDER_CREDENTIALS_FILE).read_text(encoding="utf-8")
    ) == {"api_key": "fixture-token"}
    assert dict(prepared.secret_environment) == {
        expected_environment: "fixture-token"
    }
    assert not (prepared.home / PROVIDER_CREDENTIALS_FILE).exists()


def test_bedrock_provider_profile_rejects_broadened_or_invalid_credentials(tmp_path):
    auth_root = tmp_path / "auth"
    profile = provider_auth_profile_root(
        "bedrock", "amazon-bedrock", auth_root
    )
    profile.mkdir(parents=True)
    (profile / PROVIDER_CREDENTIALS_FILE).write_text(
        json.dumps({"api_key": ""}),
        encoding="utf-8",
    )
    config = bedrock_config(tmp_path)

    with pytest.raises(ConfigurationError, match="valid API key"):
        validate_auth_profile(config, auth_root)
    with pytest.raises(ConfigurationError, match="valid API key"):
        set_provider_api_key(
            "bedrock", "amazon-bedrock", "replacement", auth_root
        )

    (profile / PROVIDER_CREDENTIALS_FILE).write_text(
        json.dumps({"api_key": "old-key"}), encoding="utf-8"
    )
    (profile / "unexpected").write_text("fixture", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="unexpected files"):
        validate_auth_profile(config, auth_root)
    with pytest.raises(ConfigurationError, match="broadened"):
        set_provider_api_key(
            "bedrock", "amazon-bedrock", "replacement", auth_root
        )


def test_bedrock_auth_login_rejects_with_set_key_guidance(tmp_path):
    project = type("Project", (), {"image": type("Image", (), {"name": "unused"})()})()

    with pytest.raises(ConfigurationError, match=r"auth set-key.*--api-key"):
        login(project, "opencode", "bedrock", "amazon-bedrock")

    assert not (tmp_path / "auth").exists()


def test_omp_oauth_profile_stages_native_database_without_environment_token(tmp_path):
    auth_root = tmp_path / "auth"
    database = auth_root / "codex" / "omp" / ".omp" / "agent" / "agent.db"
    write_omp_auth_database(database, "openai-codex")
    root = tmp_path / "configuration"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    (root / "harness/config.yaml").write_text("theme: fixture\n", encoding="utf-8")
    config = TreatmentConfig(
        root=root,
        id="omp-codex",
        harness="omp",
        provider="openai-codex",
        model="gpt-fixed",
        harness_config=root / "harness",
        workspace_config=root / "workspace",
        auth_profile="codex",
        arguments=[],
    )

    prepared = prepare_home(config, tmp_path / "home", auth_root)
    home = prepared.home
    assert dict(prepared.secret_environment) == {}
    assert (home / ".omp/agent/agent.db").read_bytes() == database.read_bytes()
    assert (home / ".omp/agent/config.yaml").read_text(encoding="utf-8") == "theme: fixture\n"
    assert not (home / ".omp/config.yaml").exists()


def pi_config(tmp_path, provider="openai-codex"):
    root = tmp_path / "pi-configuration"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    return TreatmentConfig(
        root=root,
        id=f"pi-{provider}",
        harness="pi",
        provider=provider,
        model="gpt-fixed",
        region="eu-west-1" if provider == "amazon-bedrock" else None,
        harness_config=root / "harness",
        workspace_config=root / "workspace",
        auth_profile="pi-auth",
        arguments=[],
    )


@pytest.mark.parametrize("provider", ["openai-codex", "github-copilot"])
def test_pi_oauth_profile_stages_only_selected_native_auth_file(tmp_path, provider):
    auth_root = tmp_path / "auth"
    auth = auth_root / "pi-auth" / "pi" / PI_AUTH_FILE
    auth.parent.mkdir(parents=True)
    credential = {
        "type": "oauth",
        "access": "fixture-access",
        "refresh": "fixture-refresh",
    }
    auth.write_text(
        json.dumps({provider: credential}),
        encoding="utf-8",
    )
    config = pi_config(tmp_path, provider)

    assert validate_auth_profile(config, auth_root) == auth_root / "pi-auth" / "pi"
    prepared = prepare_home(config, tmp_path / "pi-home", auth_root)
    home = prepared.home
    assert dict(prepared.secret_environment) == {}
    assert json.loads((home / PI_AUTH_FILE).read_text(encoding="utf-8")) == {
        provider: credential
    }
    assert not (home / ".pi/agent/settings.json").exists()
    assert not (home / ".pi/agent/models-store.json").exists()
    assert not (home / ".pi/agent/sessions").exists()


def test_cli_profile_validation_rejects_state_outside_credential_artifact(tmp_path):
    auth_root = tmp_path / "auth"

    pi_auth = auth_root / "pi-auth/pi" / PI_AUTH_FILE
    pi_auth.parent.mkdir(parents=True)
    pi_auth.write_text(
        json.dumps({"openai-codex": {"type": "oauth"}}), encoding="utf-8"
    )
    (pi_auth.parent / "settings.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="unexpected files"):
        validate_auth_profile(pi_config(tmp_path), auth_root)

    omp_database = auth_root / "omp-auth/omp" / OMP_NATIVE_DATABASE
    write_omp_auth_database(omp_database, "openai-codex")
    (omp_database.parent / "session.json").write_text("{}", encoding="utf-8")
    omp_config = TreatmentConfig(
        root=tmp_path,
        id="omp",
        harness="omp",
        provider="openai-codex",
        model="gpt-fixed",
        harness_config=tmp_path,
        workspace_config=tmp_path,
        auth_profile="omp-auth",
        arguments=[],
    )
    with pytest.raises(ConfigurationError, match="unexpected files"):
        validate_auth_profile(omp_config, auth_root)

    copilot_profile = auth_root / "copilot-auth/copilot"
    token = copilot_profile / ".copilot/token.json"
    token.parent.mkdir(parents=True)
    token.write_text("fixture", encoding="utf-8")
    (copilot_profile / "history.json").write_text("{}", encoding="utf-8")
    copilot_config = TreatmentConfig(
        root=tmp_path,
        id="copilot",
        harness="copilot",
        model="gpt-fixed",
        harness_config=tmp_path,
        workspace_config=tmp_path,
        auth_profile="copilot-auth",
        arguments=[],
    )
    with pytest.raises(ConfigurationError, match="outside .copilot"):
        validate_auth_profile(copilot_config, auth_root)


def test_harness_scoped_bedrock_profile_is_rejected_with_set_key_guidance(tmp_path):
    auth_root = tmp_path / "auth"
    legacy = auth_root / "pi-auth/pi"
    legacy.mkdir(parents=True)
    (legacy / "credentials.json").write_text(
        json.dumps({"AWS_BEARER_TOKEN_BEDROCK": "fixture-token"}),
        encoding="utf-8",
    )
    config = pi_config(tmp_path, "amazon-bedrock")

    with pytest.raises(ConfigurationError) as raised:
        prepare_home(config, tmp_path / "pi-bedrock-home", auth_root)

    message = str(raised.value)
    assert "harness-scoped amazon-bedrock" in message
    assert (
        "auth set-key --provider amazon-bedrock --profile pi-auth --api-key <api-key>"
        in message
    )
    assert "ACTION_REQUIRED: auth-set-key" in message


class FakeInteractiveDocker:
    def __init__(self, populate=None, image_exists=True, error=None):
        self.populate = populate
        self.image_available = image_exists
        self.error = error
        self.calls = []

    def image_exists(self, image):
        self.checked_image = image
        return self.image_available

    def run_interactive(self, image, command, mounts, environment):
        self.calls.append((image, command, list(mounts), environment))
        if self.populate:
            self.populate(self.calls[-1][2][0].source)
        if self.error:
            raise self.error


def _project_with_benchmark_image():
    return type("Project", (), {"image": type("Image", (), {"name": "bench-image"})()})()


def test_pi_login_runs_pinned_cli_in_temporary_home_and_replaces_profile(tmp_path, monkeypatch):
    auth_root = tmp_path / "auth"
    durable = auth_root / "work/pi"
    durable.mkdir(parents=True)
    (durable / "old-token").write_text("preserve until success", encoding="utf-8")

    def populate(home):
        auth = home / PI_AUTH_FILE
        auth.parent.mkdir(parents=True)
        auth.write_text(
            json.dumps(
                {
                    "openai-codex": {"type": "oauth", "access": "new"},
                    "github-copilot": {"type": "oauth", "access": "unrelated"},
                }
            ),
            encoding="utf-8",
        )
        (auth.parent / "settings.json").write_text("{}", encoding="utf-8")

    docker = FakeInteractiveDocker(populate)
    monkeypatch.setattr(
        "agent_bench.auth.auth_profile_root",
        lambda profile, harness, _root=None: auth_root / profile / harness,
    )

    assert login(_project_with_benchmark_image(), "pi", "work", "openai-codex", docker) == durable

    _, command, mounts, environment = docker.calls[0]
    assert command == ["pi"]
    assert mounts == [Mount(mounts[0].source, "/home/bench")]
    assert mounts[0].source != durable
    assert environment == {
        "HOME": "/home/bench",
        "PI_CODING_AGENT_DIR": "/home/bench/.pi/agent",
    }
    assert json.loads((durable / PI_AUTH_FILE).read_text(encoding="utf-8")) == {
        "openai-codex": {"type": "oauth", "access": "new"}
    }
    assert [path.relative_to(durable) for path in durable.rglob("*") if path.is_file()] == [
        PI_AUTH_FILE
    ]
    assert not list(durable.parent.glob(".pi-pending-*"))


@pytest.mark.parametrize(
    "harness,provider,command,artifact",
    [
        ("opencode", "openai", ["opencode", "auth", "login", "--provider", "openai"], OPENCODE_AUTH_FILE),
        ("omp", "openai-codex", ["omp"], OMP_NATIVE_DATABASE),
        ("copilot", None, ["copilot"], Path(".copilot/token.json")),
    ],
)
def test_cli_logins_retain_only_their_credential_artifact(
    tmp_path,
    monkeypatch,
    login_countdown_delays,
    harness,
    provider,
    command,
    artifact,
):
    auth_root = tmp_path / "auth"

    def populate(home):
        if harness == "opencode":
            path = home / OPENCODE_AUTH_FILE
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({provider: {"type": "oauth"}}), encoding="utf-8")
        elif harness == "omp":
            write_omp_auth_database(home / OMP_NATIVE_DATABASE, provider)
        else:
            path = home / artifact
            path.parent.mkdir(parents=True)
            path.write_text("fixture", encoding="utf-8")
        cache = home / ".cache/login-state"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("discard", encoding="utf-8")

    docker = FakeInteractiveDocker(populate)
    monkeypatch.setattr(
        "agent_bench.auth.auth_profile_root",
        lambda profile, selected_harness, _root=None: auth_root / profile / selected_harness,
    )

    durable = login(_project_with_benchmark_image(), harness, "work", provider, docker)

    assert login_countdown_delays == [1, 1, 1]
    assert docker.calls[0][1] == command
    assert docker.calls[0][3]["HOME"] == "/home/bench"
    assert sorted(
        path.relative_to(durable) for path in durable.rglob("*") if path.is_file()
    ) == [artifact]


def test_omp_login_retains_uncheckpointed_wal_credentials(tmp_path, monkeypatch):
    auth_root = tmp_path / "auth"
    open_connections = []

    def populate(home):
        database = home / OMP_NATIVE_DATABASE
        database.parent.mkdir(parents=True)
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE auth_credential_refresh_leases (id INTEGER)")
        connection = sqlite3.connect(database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "CREATE TABLE auth_credentials ("
            "provider TEXT, credential_type TEXT, disabled_cause TEXT)"
        )
        connection.execute(
            "INSERT INTO auth_credentials VALUES ('openai-codex', 'oauth', NULL)"
        )
        connection.commit()
        open_connections.append(connection)

    monkeypatch.setattr(
        "agent_bench.auth.auth_profile_root",
        lambda profile, harness, _root=None: auth_root / profile / harness,
    )

    durable = login(
        _project_with_benchmark_image(),
        "omp",
        "work",
        "openai-codex",
        FakeInteractiveDocker(populate),
    )
    for connection in open_connections:
        connection.close()

    with sqlite3.connect(durable / OMP_NATIVE_DATABASE) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert connection.execute(
            "SELECT provider, credential_type, disabled_cause FROM auth_credentials"
        ).fetchall() == [("openai-codex", "oauth", None)]


def test_failed_container_login_preserves_existing_profile(tmp_path, monkeypatch):
    auth_root = tmp_path / "auth"
    durable = auth_root / "work/omp"
    durable.mkdir(parents=True)
    old = durable / "old-token"
    old.write_text("still-valid", encoding="utf-8")
    docker = FakeInteractiveDocker(error=InfrastructureError("cancelled"))
    monkeypatch.setattr(
        "agent_bench.auth.auth_profile_root",
        lambda profile, harness, _root=None: auth_root / profile / harness,
    )

    with pytest.raises(InfrastructureError, match="cancelled"):
        login(_project_with_benchmark_image(), "omp", "work", "openai-codex", docker)

    assert old.read_text(encoding="utf-8") == "still-valid"
    assert not list(durable.parent.glob(".omp-pending-*"))


def test_invalid_login_artifact_preserves_existing_profile(tmp_path, monkeypatch):
    auth_root = tmp_path / "auth"
    durable = auth_root / "work/pi"
    durable.mkdir(parents=True)
    old = durable / "old-token"
    old.write_text("still-valid", encoding="utf-8")

    def populate(home):
        auth = home / PI_AUTH_FILE
        auth.parent.mkdir(parents=True)
        auth.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "agent_bench.auth.auth_profile_root",
        lambda profile, harness, _root=None: auth_root / profile / harness,
    )

    with pytest.raises(InfrastructureError, match="valid 'openai-codex'"):
        login(
            _project_with_benchmark_image(),
            "pi",
            "work",
            "openai-codex",
            FakeInteractiveDocker(populate),
        )

    assert old.read_text(encoding="utf-8") == "still-valid"
    assert not list(durable.parent.glob(".pi-pending-*"))


def test_cli_login_requires_prebuilt_image(tmp_path, monkeypatch):
    auth_root = tmp_path / "auth"
    monkeypatch.setattr(
        "agent_bench.auth.auth_profile_root",
        lambda profile, harness, _root=None: auth_root / profile / harness,
    )

    with pytest.raises(InfrastructureError, match="build.*before.*auth login"):
        login(
            _project_with_benchmark_image(),
            "opencode",
            "work",
            "openai",
            FakeInteractiveDocker(image_exists=False),
        )

    assert not auth_root.exists()


def test_missing_profile_reports_exact_user_action(tmp_path):
    config = pi_config(tmp_path, "openai-codex")

    with pytest.raises(InfrastructureError) as raised:
        prepare_home(config, tmp_path / "home", tmp_path / "auth")

    message = str(raised.value)
    assert "harness=pi" in message
    assert "provider=openai-codex" in message
    assert "profile=pi-auth" in message
    assert (
        "./benchmarks/run.py auth login --harness pi --provider openai-codex --profile pi-auth"
        in message
    )
    assert "ACTION_REQUIRED: auth-login" in message


def test_login_rejects_provider_not_supported_by_selected_harness(tmp_path, monkeypatch):
    destination = tmp_path / "auth"
    monkeypatch.setattr(
        "agent_bench.auth.auth_profile_root",
        lambda profile, harness, auth_root=None: destination / profile / harness,
    )
    project = type("Project", (), {"image": type("Image", (), {"name": "unused"})()})()

    with pytest.raises(ConfigurationError, match="opencode provider must be one of"):
        login(project, "opencode", "work", "openai-codex")

    assert not destination.exists()


def test_missing_auth_strategy_registration_fails_closed(tmp_path, monkeypatch):
    config = bedrock_config(tmp_path)
    monkeypatch.setattr("agent_bench.auth.AUTH_STRATEGIES", {})

    with pytest.raises(ConfigurationError, match="unregistered authentication policy"):
        auth_strategy_for(config)
