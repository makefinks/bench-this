"""Tests for reducing interactive login output to narrowly scoped credentials."""

import json
import sqlite3

import pytest

from agent_bench.auth import (
    auth_strategy_for,
    BEDROCK_CREDENTIALS_FILE,
    BEDROCK_TOKEN_ENVIRONMENT_VARIABLE,
    PI_AUTH_FILE,
    login,
    narrow_opencode_profile,
    prepare_home,
    store_bedrock_credential,
    validate_auth_profile,
)
from agent_bench.errors import ConfigurationError
from agent_bench.models import TreatmentConfig


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


def test_bedrock_profile_injects_token_without_staging_secret_file(tmp_path):
    auth_root = tmp_path / "auth"
    profile = store_bedrock_credential(
        "bedrock", "opencode", "fixture-token", auth_root
    )
    config = bedrock_config(tmp_path)

    assert profile.stat().st_mode & 0o777 == 0o700
    credential = profile / BEDROCK_CREDENTIALS_FILE
    assert credential.stat().st_mode & 0o777 == 0o600
    prepared = prepare_home(config, tmp_path / "home", auth_root)
    home = prepared.home
    assert dict(prepared.secret_environment) == {
        BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: "fixture-token"
    }
    assert not (home / BEDROCK_CREDENTIALS_FILE).exists()


def test_bedrock_profile_rejects_broadened_or_invalid_credentials(tmp_path):
    auth_root = tmp_path / "auth"
    profile = auth_root / "bedrock/opencode"
    profile.mkdir(parents=True)
    (profile / BEDROCK_CREDENTIALS_FILE).write_text(
        json.dumps({BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: ""}),
        encoding="utf-8",
    )
    config = bedrock_config(tmp_path)

    with pytest.raises(ConfigurationError, match="valid bearer token"):
        validate_auth_profile(config, auth_root)

    (profile / "unexpected").write_text("fixture", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="unexpected files"):
        validate_auth_profile(config, auth_root)


def test_bedrock_login_stores_runner_managed_token(tmp_path, monkeypatch):
    auth_root = tmp_path / "auth"
    monkeypatch.setattr(
        "agent_bench.auth.auth_profile_root",
        lambda profile, harness, _root=None: auth_root / profile / harness,
    )
    monkeypatch.setattr(
        "agent_bench.auth.getpass.getpass", lambda _prompt: "fixture-token"
    )
    project = type("Project", (), {"image": type("Image", (), {"name": "unused"})()})()

    login(project, "opencode", "bedrock", "amazon-bedrock")

    credentials = json.loads(
        (
            auth_root
            / "bedrock/opencode"
            / BEDROCK_CREDENTIALS_FILE
        ).read_text(encoding="utf-8")
    )
    assert credentials == {BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: "fixture-token"}


def test_omp_bedrock_profile_injects_only_selected_provider_token(tmp_path):
    auth_root = tmp_path / "auth"
    root = tmp_path / "configuration"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    config = TreatmentConfig(
        root=root,
        id="omp-codex",
        harness="omp",
        provider="amazon-bedrock",
        model="gpt-fixed",
        harness_config=root / "harness",
        workspace_config=root / "workspace",
        auth_profile="codex",
        arguments=[],
    )

    profile = store_bedrock_credential(
        "bedrock", "omp", "fixture-token", auth_root
    )

    config = TreatmentConfig(**{**config.__dict__, "auth_profile": "bedrock"})
    credentials = json.loads(
        (profile / BEDROCK_CREDENTIALS_FILE).read_text(encoding="utf-8")
    )
    assert credentials == {BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: "fixture-token"}
    prepared = prepare_home(config, tmp_path / "home", auth_root)
    home = prepared.home
    assert dict(prepared.secret_environment) == {
        BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: "fixture-token"
    }
    assert not (home / ".omp/agent/agent.db").exists()
    assert not (home / "credentials.json").exists()


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
    (auth.parent / "settings.json").write_text('{"theme":"fixture"}', encoding="utf-8")
    (auth.parent / "models-store.json").write_text("{}", encoding="utf-8")
    session = auth.parent / "sessions" / "project" / "session.jsonl"
    session.parent.mkdir(parents=True)
    session.write_text('{"type":"session"}\n', encoding="utf-8")
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


def test_pi_bedrock_bearer_profile_injects_token_without_staging_secret_file(tmp_path):
    auth_root = tmp_path / "auth"
    profile = store_bedrock_credential(
        "pi-auth",
        "pi",
        "fixture-token",
        auth_root,
    )
    config = pi_config(tmp_path, "amazon-bedrock")

    assert profile.stat().st_mode & 0o777 == 0o700
    credentials = profile / BEDROCK_CREDENTIALS_FILE
    assert credentials.stat().st_mode & 0o777 == 0o600
    assert validate_auth_profile(config, auth_root) == profile
    prepared = prepare_home(config, tmp_path / "pi-bedrock-home", auth_root)
    assert dict(prepared.secret_environment) == {
        BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: "fixture-token"
    }
    home = prepared.home
    assert not (home / BEDROCK_CREDENTIALS_FILE).exists()

    (profile / "unexpected").write_text("fixture", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="unexpected files"):
        validate_auth_profile(config, auth_root)
    (profile / "unexpected").unlink()

    credentials.write_text(json.dumps({"unrelated": "shape"}) + "\n")
    with pytest.raises(ConfigurationError, match="bearer token"):
        validate_auth_profile(config, auth_root)


def test_pi_bedrock_login_stores_runner_managed_token(tmp_path, monkeypatch):
    auth_root = tmp_path / "auth"
    monkeypatch.setattr(
        "agent_bench.auth.auth_profile_root",
        lambda profile, harness, _root=None: auth_root / profile / harness,
    )
    monkeypatch.setattr(
        "agent_bench.auth.getpass.getpass", lambda _prompt: "fixture-api-key"
    )
    project = type("Project", (), {"image": type("Image", (), {"name": "unused"})()})()

    login(project, "pi", "bedrock", "amazon-bedrock")

    credentials = json.loads(
        (auth_root / "bedrock" / "pi" / BEDROCK_CREDENTIALS_FILE).read_text(
            encoding="utf-8"
        )
    )
    assert credentials == {BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: "fixture-api-key"}

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
