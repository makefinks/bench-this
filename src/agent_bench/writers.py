"""Closed registry for harness-native treatment configuration files."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
from types import MappingProxyType
from typing import Iterable, Mapping

from .catalog import AMAZON_BEDROCK_PROVIDER, WriterKind
from .errors import ConfigurationError
from .models import TreatmentConfig


GITHUB_COPILOT_BUSINESS_BASE_URL = "https://api.business.githubcopilot.com"


class NativeConfigurationWriter(ABC):
    """Write harness-native files after the canonical manifest has validated."""

    @abstractmethod
    def write(self, config: TreatmentConfig, skill_names: Iterable[str]) -> None:
        raise NotImplementedError


class NoOpWriter(NativeConfigurationWriter):
    """Explicit writer for harnesses with no generated native files."""

    def write(self, config: TreatmentConfig, skill_names: Iterable[str]) -> None:
        return None


class OpenCodeWriter(NativeConfigurationWriter):
    """Render native OpenCode provider, auxiliary-model, and permission policy."""

    def write(self, config: TreatmentConfig, skill_names: Iterable[str]) -> None:
        opencode: dict[str, object] = {
            "$schema": "https://opencode.ai/config.json",
            "policies": [
                {"action": "provider.use", "resource": "*", "effect": "deny"},
                {"action": "provider.use", "resource": config.provider, "effect": "allow"},
            ],
            "agents": {"title": {"model": config.qualified_model}},
            "update": "disable",
        }
        if config.github_copilot_business:
            opencode["providers"] = {
                "github-copilot": {
                    "settings": {"baseURL": GITHUB_COPILOT_BUSINESS_BASE_URL}
                }
            }
        elif config.provider == AMAZON_BEDROCK_PROVIDER:
            opencode["providers"] = {
                AMAZON_BEDROCK_PROVIDER: {
                    "settings": {"region": config.region}
                }
            }
        if tuple(skill_names):
            opencode["permissions"] = [
                {"action": "skill", "resource": "*", "effect": "allow"}
            ]
        destination = config.harness_config / "opencode.json"
        destination.write_text(
            json.dumps(opencode, indent=2) + "\n",
            encoding="utf-8",
        )


WRITER_REGISTRY: Mapping[WriterKind, NativeConfigurationWriter] = MappingProxyType(
    {
        WriterKind.NONE: NoOpWriter(),
        WriterKind.OPENCODE: OpenCodeWriter(),
    }
)


def writer_for(config: TreatmentConfig) -> NativeConfigurationWriter:
    """Resolve the catalog-selected writer and fail closed if it is unregistered."""

    try:
        return WRITER_REGISTRY[config.harness_spec.writer]
    except KeyError as exc:
        raise ConfigurationError(
            f"unregistered native configuration writer: {config.harness_spec.writer}"
        ) from exc


def write_native_configuration(
    config: TreatmentConfig,
    skill_names: Iterable[str] = (),
) -> None:
    """Write only the native files selected by the harness catalog."""

    writer_for(config).write(config, skill_names)
