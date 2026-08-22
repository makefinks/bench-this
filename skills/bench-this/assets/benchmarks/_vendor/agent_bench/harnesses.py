"""Construct pinned non-interactive commands and verify resolved model identity."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from .catalog import AdapterKind
from .errors import ConfigurationError, IdentityMismatch, InfrastructureError
from .models import TreatmentConfig, Usage
from .telemetry import (
    extract_identities,
    extract_identity,
    extract_pi_identities,
    extract_pi_terminal_message,
    parse_json_events,
    parse_pi_transcript,
    parse_usage,
)


PREFLIGHT_PROMPT = "Reply with exactly BENCH_PREFLIGHT_OK. Do not read or write files."


class HarnessAdapter(ABC):
    """Shared harness contract for command construction and telemetry handling."""

    def __init__(self, config: TreatmentConfig):
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
        if self.config.model != "auto" and model != self.config.model:
            raise IdentityMismatch(
                f"expected model {self.config.model!r}, harness reported {model!r}"
            )
        return provider, model

    def verify_preflight(self, stdout: str, stderr: str = "") -> None:
        """Verify that a source-free canary resolved the pinned identity."""

        self.verify_identity(stdout, stderr)

    def verify_solver(self, stdout: str, stderr: str = "") -> None:
        """Reject successful process exits that contain harness-level failures."""


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
            if provider != self.config.provider
            or (self.config.model != "auto" and model != self.config.model)
        ]
        if unexpected:
            raise IdentityMismatch(
                f"expected only {self.config.qualified_model!r}, harness also resolved: "
                + ", ".join(unexpected)
            )
        return identities[-1]


class _PiJsonAdapter(HarnessAdapter):
    """Shared verification for Pi and forks that emit Pi JSON events."""

    display_name = "Pi"

    def parse_usage(self, stdout: str, stderr: str = "", telemetry: str = "") -> Usage:
        """Aggregate the final transcript instead of triple-counting replayed events."""

        return parse_pi_transcript(telemetry or f"{stdout}\n{stderr}")

    def verify_identity(self, stdout: str, stderr: str = "") -> Tuple[Optional[str], str]:
        """Verify every provider/model identity reported by the harness."""

        identities = extract_pi_identities(f"{stdout}\n{stderr}")
        if not identities:
            raise IdentityMismatch(
                f"{self.display_name} did not report a resolved provider/model identity"
            )
        unexpected = [
            f"{provider}/{model}"
            for provider, model in identities
            if provider != self.config.provider
            or (self.config.model != "auto" and model != self.config.model)
        ]
        if unexpected:
            raise IdentityMismatch(
                f"expected only {self.config.qualified_model!r}, harness also resolved: "
                + ", ".join(unexpected)
            )
        return identities[-1]

    def _verify_transcript(self, stdout: str, stderr: str = "") -> List[dict]:
        """Reject provider errors reported in JSON despite a successful process exit."""

        events = parse_json_events(f"{stdout}\n{stderr}")
        pending = list(events)
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                if value.get("stopReason") == "error":
                    detail = (
                        value.get("errorMessage")
                        or f"{self.display_name} reported a provider error"
                    )
                    raise InfrastructureError(str(detail))
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        return events

    def verify_preflight(self, stdout: str, stderr: str = "") -> None:
        """Require a successful provider response and the pinned model identity."""

        events = self._verify_transcript(stdout, stderr)
        self.verify_identity(stdout, stderr)
        responses = []
        for event in events:
            message = event.get("message") if isinstance(event, dict) else None
            if event.get("type") != "message_end" or not isinstance(message, dict):
                continue
            if message.get("role") != "assistant" or not isinstance(
                message.get("content"), list
            ):
                continue
            responses.append(
                "".join(
                    part.get("text", "")
                    for part in message["content"]
                    if isinstance(part, dict) and part.get("type") == "text"
                ).strip()
            )
        if not responses or responses[-1] != "BENCH_PREFLIGHT_OK":
            raise InfrastructureError(
                f"{self.display_name} preflight did not return exactly BENCH_PREFLIGHT_OK"
            )

    def verify_solver(self, stdout: str, stderr: str = "") -> None:
        """Fail runs that embed a provider error or terminal abort in exit-zero JSON."""

        self._verify_transcript(stdout, stderr)
        terminal = extract_pi_terminal_message(f"{stdout}\n{stderr}")
        if isinstance(terminal, dict) and terminal.get("stopReason") == "aborted":
            detail = terminal.get("errorMessage") or "no provider detail"
            raise InfrastructureError(
                f"{self.display_name} turn aborted before completion: {detail}"
            )
        self.verify_identity(stdout, stderr)


class OmpAdapter(_PiJsonAdapter):
    """Oh My Pi single-shot JSON adapter."""

    display_name = "OMP"

    def command(self, prompt: str, workspace: str = "/workspace") -> List[str]:
        """Run one autonomous turn without persisting session state."""

        return [
            "omp",
            "--print",
            "--mode",
            "json",
            "--no-session",
            "--auto-approve",
            "--no-title",
            "--cwd",
            workspace,
            "--model",
            self.config.qualified_model,
            *self.config.arguments,
            prompt,
        ]

    def environment(self) -> Dict[str, str]:
        """Keep OMP settings, credentials, and caches inside the staged home."""

        environment = {
            "HOME": "/home/bench",
            "PI_CONFIG_DIR": ".omp",
            "PI_CODING_AGENT_DIR": "/home/bench/.omp/agent",
            "NO_COLOR": "1",
        }
        if self.config.region:
            environment["AWS_REGION"] = self.config.region
        return environment


class PiAdapter(_PiJsonAdapter):
    """Upstream Pi single-shot JSON adapter."""

    def command(self, prompt: str, workspace: str = "/workspace") -> List[str]:
        """Run one trusted autonomous turn without persisting session state."""

        return [
            "pi",
            "--print",
            "--mode",
            "json",
            "--no-session",
            "--approve",
            "--model",
            self.config.qualified_model,
            *self.config.arguments,
            prompt,
        ]

    def environment(self) -> Dict[str, str]:
        """Keep Pi state local and suppress unrelated update and telemetry requests."""

        environment = {
            "HOME": "/home/bench",
            "PI_CODING_AGENT_DIR": "/home/bench/.pi/agent",
            "PI_OFFLINE": "1",
            "PI_TELEMETRY": "0",
            "NO_COLOR": "1",
        }
        if self.config.region:
            environment["AWS_REGION"] = self.config.region
        return environment


ADAPTER_REGISTRY: Mapping[AdapterKind, type[HarnessAdapter]] = {
    AdapterKind.COPILOT: CopilotAdapter,
    AdapterKind.OPENCODE: OpenCodeAdapter,
    AdapterKind.OMP: OmpAdapter,
    AdapterKind.PI: PiAdapter,
}


def adapter_for(config: TreatmentConfig) -> HarnessAdapter:
    """Resolve the catalog-selected adapter and fail closed if it is unregistered."""

    try:
        adapter = ADAPTER_REGISTRY[config.harness_spec.adapter]
    except KeyError as exc:
        raise ConfigurationError(
            f"unsupported or unregistered harness adapter: {config.harness}"
        ) from exc
    return adapter(config)
