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
    """Render the complete OpenCode-native provider and permission policy."""

    def write(self, config: TreatmentConfig, skill_names: Iterable[str]) -> None:
        opencode: dict[str, object] = {
            "$schema": "https://opencode.ai/config.json",
            "enabled_providers": [config.provider],
            "small_model": config.qualified_model,
            "share": "disabled",
        }
        if config.github_copilot_business:
            opencode["provider"] = {
                "github-copilot": {
                    "options": {"baseURL": GITHUB_COPILOT_BUSINESS_BASE_URL}
                }
            }
        elif config.provider == AMAZON_BEDROCK_PROVIDER:
            opencode["provider"] = {
                AMAZON_BEDROCK_PROVIDER: {
                    "options": {"region": config.region}
                }
            }
        if tuple(skill_names):
            opencode["permission"] = {"skill": {"*": "allow"}}
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
