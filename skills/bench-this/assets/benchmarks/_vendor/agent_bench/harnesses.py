"""Construct pinned non-interactive commands and verify resolved model identity."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .errors import ConfigurationError, IdentityMismatch
from .models import HarnessConfig, Usage
from .telemetry import extract_identities, extract_identity, parse_usage


PREFLIGHT_PROMPT = "Reply with exactly BENCH_PREFLIGHT_OK. Do not read or write files."


class HarnessAdapter(ABC):
    """Shared harness contract for command construction and telemetry handling."""

    def __init__(self, config: HarnessConfig):
        self.config = config

    @abstractmethod
    def command(self, prompt: str, workspace: str = "/workspace") -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def environment(self) -> Dict[str, str]:
        raise NotImplementedError

    def preflight_command(self) -> List[str]:
        """Build the source-free canary command used for identity verification."""

        return self.command(PREFLIGHT_PROMPT)

    def parse_usage(self, stdout: str, stderr: str = "", telemetry: str = "") -> Usage:
        """Normalize telemetry from both output streams because CLIs use either."""

        return parse_usage(telemetry or f"{stdout}\n{stderr}")

    def telemetry_path(self, home: Path) -> Optional[Path]:
        """Return an optional harness-owned telemetry file inside the staged home."""

        return None

    def verify_identity(self, stdout: str, stderr: str = "") -> Tuple[Optional[str], str]:
        """Abort when the resolved model is missing or differs from the pin."""

        provider, model = extract_identity(f"{stdout}\n{stderr}")
        if model != self.config.model:
            raise IdentityMismatch(
                f"expected model {self.config.model!r}, harness reported {model!r}"
            )
        return provider, model


class CopilotAdapter(HarnessAdapter):
    """GitHub Copilot CLI programmatic-mode adapter."""

    def command(self, prompt: str, workspace: str = "/workspace") -> List[str]:
        """Grant autonomous local tools while disabling GitHub MCP and remote export."""

        return [
            "copilot",
            "--prompt",
            prompt,
            "--model",
            self.config.model,
            "--no-ask-user",
            "--output-format=json",
            "--allow-all-tools",
            "--allow-all-paths",
            "--deny-tool=github",
            "--no-remote",
            "--no-auto-update",
            *self.config.arguments,
        ]

    def environment(self) -> Dict[str, str]:
        """Return an allowlist rather than inheriting host provider credentials."""

        return {
            "HOME": "/home/bench",
            "COPILOT_HOME": "/home/bench/.copilot",
            "COPILOT_MODEL": self.config.model,
            "COPILOT_ALLOW_ALL": "true",
            "COPILOT_OTEL_FILE_EXPORTER_PATH": "/home/bench/copilot-otel.jsonl",
            "NO_COLOR": "1",
        }

    def telemetry_path(self, home: Path) -> Optional[Path]:
        """Locate Copilot's file exporter output after the container exits."""

        return home / "copilot-otel.jsonl"


class OpenCodeAdapter(HarnessAdapter):
    """OpenCode JSON-event adapter for explicitly allowlisted v1 providers."""

    def command(self, prompt: str, workspace: str = "/workspace") -> List[str]:
        """Build the provider-qualified, non-interactive OpenCode command."""

        return [
            "opencode",
            "run",
            "--format=json",
            "--model",
            self.config.qualified_model,
            "--agent",
            self.config.agent or "build",
            "--dir",
            workspace,
            *self.config.arguments,
            prompt,
        ]

    def environment(self) -> Dict[str, str]:
        """Point every OpenCode state directory at the disposable run home."""

        return {
            "HOME": "/home/bench",
            "XDG_CONFIG_HOME": "/home/bench/.config",
            "XDG_DATA_HOME": "/home/bench/.local/share",
            "XDG_CACHE_HOME": "/home/bench/.cache",
            "NO_COLOR": "1",
        }

    def preflight_command(self) -> List[str]:
        """Enable INFO logs because OpenCode JSON events omit resolved identity."""

        command = self.command(PREFLIGHT_PROMPT)
        return [*command[:-1], "--print-logs", "--log-level", "INFO", command[-1]]

    def verify_identity(self, stdout: str, stderr: str = "") -> Tuple[Optional[str], str]:
        """Verify provider as well as model to detect silent provider fallback."""

        identities = extract_identities(f"{stdout}\n{stderr}")
        if not identities:
            raise IdentityMismatch("OpenCode did not report a resolved provider/model identity")
        unexpected = [
            f"{provider}/{model}"
            for provider, model in identities
            if provider != self.config.provider or model != self.config.model
        ]
        if unexpected:
            raise IdentityMismatch(
                f"expected only {self.config.qualified_model!r}, harness also resolved: "
                + ", ".join(unexpected)
            )
        return identities[-1]


def adapter_for(config: HarnessConfig) -> HarnessAdapter:
    """Select one of the two deliberately direct v1 harness branches."""

    if config.harness == "copilot":
        return CopilotAdapter(config)
    if config.harness == "opencode":
        return OpenCodeAdapter(config)
    raise ConfigurationError(f"unsupported harness: {config.harness}")
