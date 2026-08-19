"""Render the allowlisted harness tools required by a benchmark matrix."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


HARNESS_START = "# BEGIN GENERATED HARNESS INSTALLS"
HARNESS_END = "# END GENERATED HARNESS INSTALLS"


@dataclass(frozen=True)
class HarnessInstall:
    """Pinned image arguments and shell commands for one harness executable."""

    arguments: Mapping[str, str]
    commands: tuple[str, ...]


HARNESS_INSTALLS = {
    "copilot": HarnessInstall(
        {"COPILOT_CLI_VERSION": "1.0.73"},
        ('npm install --global "@github/copilot@${COPILOT_CLI_VERSION}"',),
    ),
    "omp": HarnessInstall(
        {"BUN_VERSION": "1.3.14", "OMP_VERSION": "17.2.4"},
        (
            'npm install --global "bun@${BUN_VERSION}"',
            'BUN_INSTALL=/usr/local bun install --global "@oh-my-pi/pi-coding-agent@${OMP_VERSION}"',
        ),
    ),
    "opencode": HarnessInstall(
        {"OPENCODE_VERSION": "1.17.18"},
        ('npm install --global "opencode-ai@${OPENCODE_VERSION}"',),
    ),
}


def render_harness_installs(harnesses: Iterable[str]) -> str:
    """Render only known harness installers in deterministic order."""

    selected = sorted(set(harnesses))
    unknown = [harness for harness in selected if harness not in HARNESS_INSTALLS]
    if unknown:
        raise ValueError("unsupported harness installers: " + ", ".join(unknown))
    arguments = {}
    commands = []
    for harness in selected:
        install = HARNESS_INSTALLS[harness]
        arguments.update(install.arguments)
        commands.extend(install.commands)
    lines = [HARNESS_START]
    lines.extend(f"ARG {name}={value}" for name, value in sorted(arguments.items()))
    if commands:
        lines.append("RUN " + " \\\n    && ".join(commands))
    lines.append(HARNESS_END)
    return "\n".join(lines)


def render_dockerfile(path: Path, harnesses: Iterable[str]) -> str:
    """Inject the selected harness block without modifying the source Dockerfile."""

    source = path.read_text(encoding="utf-8")
    block = render_harness_installs(harnesses)
    if HARNESS_START in source and HARNESS_END in source:
        start = source.index(HARNESS_START)
        end = source.index(HARNESS_END, start) + len(HARNESS_END)
        return source[:start] + block + source[end:]
    marker = "WORKDIR "
    position = source.find(marker)
    if position < 0:
        return source.rstrip() + "\n\n" + block + "\n"
    return source[:position] + block + "\n\n" + source[position:]
