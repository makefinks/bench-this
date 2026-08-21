"""Tests for reducing interactive login output to narrowly scoped credentials."""

import json

import pytest

from agent_bench.cli import _login, _narrow_opencode_profile
from agent_bench.errors import ConfigurationError
from agent_bench.models import HarnessConfig
from agent_bench.workspace import (
    BEDROCK_CREDENTIALS_FILE,
    BEDROCK_TOKEN_ENVIRONMENT_VARIABLE,
    auth_environment,
    stage_home,
    store_bedrock_api_key,
    store_omp_credential,
    validate_auth_profile,
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

    _narrow_opencode_profile(profile, "openai")

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
    config = HarnessConfig(
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
    return HarnessConfig(
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
    profile = store_bedrock_api_key("bedrock", "fixture-token", auth_root)
    config = bedrock_config(tmp_path)

    assert profile.stat().st_mode & 0o777 == 0o700
    credential = profile / BEDROCK_CREDENTIALS_FILE
    assert credential.stat().st_mode & 0o777 == 0o600
    assert auth_environment(config, auth_root) == {
        BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: "fixture-token"
    }

    home = tmp_path / "home"
    stage_home(config, home, auth_root)
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
        "agent_bench.cli.auth_profile_root",
        lambda profile, harness: auth_root / profile / harness,
    )
    monkeypatch.setattr(
        "agent_bench.workspace.auth_profile_root",
        lambda profile, harness, auth_root=None: (
            tmp_path / "auth" / profile / harness
        ),
    )
    monkeypatch.setattr("agent_bench.cli.getpass.getpass", lambda _prompt: "fixture-token")
    project = type("Project", (), {"image": type("Image", (), {"name": "unused"})()})()

    _login(project, "opencode", "bedrock", "amazon-bedrock")

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
    config = HarnessConfig(
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

    profile = store_omp_credential(
        "bedrock", "amazon-bedrock", "fixture-token", auth_root
    )

    config = HarnessConfig(**{**config.__dict__, "auth_profile": "bedrock"})
    credentials = json.loads(
        (profile / BEDROCK_CREDENTIALS_FILE).read_text(encoding="utf-8")
    )
    assert credentials == {BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: "fixture-token"}
    assert auth_environment(auth_root=auth_root, config=config) == {
        BEDROCK_TOKEN_ENVIRONMENT_VARIABLE: "fixture-token"
    }
    home = tmp_path / "home"
    stage_home(config, home, auth_root)
    assert not (home / ".omp/agent/agent.db").exists()
    assert not (home / "credentials.json").exists()


def test_omp_oauth_profile_stages_native_database_without_environment_token(tmp_path):
    auth_root = tmp_path / "auth"
    profile = auth_root / "codex" / "omp" / ".omp" / "agent"
    profile.mkdir(parents=True)
    (profile / "agent.db").write_bytes(b"fixture-database")
    root = tmp_path / "configuration"
    (root / "harness").mkdir(parents=True)
    (root / "workspace").mkdir()
    (root / "harness/config.yaml").write_text("theme: fixture\n", encoding="utf-8")
    config = HarnessConfig(
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

    assert auth_environment(auth_root=auth_root, config=config) == {}
    home = tmp_path / "home"
    stage_home(config, home, auth_root)
    assert (home / ".omp/agent/agent.db").read_bytes() == b"fixture-database"
    assert (home / ".omp/agent/config.yaml").read_text(encoding="utf-8") == "theme: fixture\n"
    assert not (home / ".omp/config.yaml").exists()


def test_login_rejects_provider_not_supported_by_selected_harness(tmp_path, monkeypatch):
    destination = tmp_path / "auth"
    monkeypatch.setattr(
        "agent_bench.cli.auth_profile_root",
        lambda profile, harness: destination / profile / harness,
    )
    project = type("Project", (), {"image": type("Image", (), {"name": "unused"})()})()

    with pytest.raises(ConfigurationError, match="OpenCode login requires --provider"):
        _login(project, "opencode", "work", "openai-codex")

    assert not destination.exists()
