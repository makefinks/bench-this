import pytest

from agent_bench.catalog import (
    HARNESS_CATALOG,
    AdapterKind,
    AuthPolicy,
    ModelReferenceForm,
    WriterKind,
    resolve_selection,
    supported_selections,
)
from agent_bench.auth import AUTH_STRATEGIES
from agent_bench.harnesses import ADAPTER_REGISTRY


def test_catalog_declares_complete_supported_matrix():
    selections = {
        (harness.id, provider.id)
        for harness, provider in supported_selections()
    }

    assert selections == {
        ("copilot", None),
        ("opencode", "amazon-bedrock"),
        ("opencode", "github-copilot"),
        ("opencode", "openai"),
        ("opencode", "opencode"),
        ("opencode", "opencode-go"),
        ("omp", "amazon-bedrock"),
        ("omp", "github-copilot"),
        ("omp", "openai-codex"),
        ("pi", "amazon-bedrock"),
        ("pi", "github-copilot"),
        ("pi", "openai-codex"),
    }


def test_pi_github_copilot_reuses_oauth_and_requires_a_pinned_model():
    harness, provider = resolve_selection("pi", "github-copilot")

    assert harness.model_reference is ModelReferenceForm.QUALIFIED
    assert provider.auth_policy is AuthPolicy.PI_OAUTH
    assert provider.pricing_provider == "github-copilot"
    assert not provider.allow_automatic_model


def test_every_harness_has_complete_generic_metadata():
    assert set(HARNESS_CATALOG) == {kind.value for kind in AdapterKind}
    for harness_id, harness in HARNESS_CATALOG.items():
        assert harness.id == harness_id
        assert harness.display_name
        assert harness.model_reference in ModelReferenceForm
        assert harness.config_home
        assert harness.installer.arguments
        assert harness.installer.commands
        assert harness.adapter in AdapterKind
        assert harness.writer in WriterKind
        assert harness.providers
        assert harness.required_fields <= harness.allowed_fields
        assert set(harness.generator_defaults) <= harness.allowed_fields

    assert HARNESS_CATALOG["opencode"].generator_defaults == {"agent": "build"}


def test_every_provider_has_closed_auth_and_valid_field_contract():
    for harness, provider in supported_selections():
        assert provider.auth_policy in AuthPolicy
        assert provider.pricing_provider
        assert provider.required_fields <= provider.allowed_fields
        assert provider.id in harness.providers


def test_only_copilot_selections_allow_automatic_model():
    automatic = {
        (harness.id, provider.id)
        for harness, provider in supported_selections()
        if provider.allow_automatic_model
    }

    assert automatic == {
        ("copilot", None),
        ("opencode", "github-copilot"),
        ("omp", "github-copilot"),
    }


def test_adapter_registry_is_complete_and_has_no_orphans():
    selected = {harness.adapter for harness in HARNESS_CATALOG.values()}

    assert set(ADAPTER_REGISTRY) == set(AdapterKind) == selected


def test_auth_registry_is_complete_and_every_policy_is_selected():
    selected = {
        provider.auth_policy
        for _, provider in supported_selections()
    }

    assert set(AUTH_STRATEGIES) == set(AuthPolicy) == selected


def test_catalog_resolves_provider_contracts_for_all_consumers():
    harness, provider = resolve_selection("opencode", "openai")
    assert (harness.id, provider.id) == ("opencode", "openai")

    harness, provider = resolve_selection("copilot")
    assert (harness.id, provider.id) == ("copilot", None)

    with pytest.raises(ValueError, match="provider does not apply"):
        resolve_selection("copilot", "github-copilot")
    with pytest.raises(ValueError, match="Pi requires provider"):
        resolve_selection("pi")
