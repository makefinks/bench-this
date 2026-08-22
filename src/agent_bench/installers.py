"""Render the allowlisted harness tools required by a benchmark matrix."""

from pathlib import Path
from typing import Iterable

from .catalog import HARNESS_CATALOG


HARNESS_START = "# BEGIN GENERATED HARNESS INSTALLS"
HARNESS_END = "# END GENERATED HARNESS INSTALLS"




def render_harness_installs(harnesses: Iterable[str]) -> str:
    """Render only known harness installers in deterministic order."""

    selected = sorted(set(harnesses))
    arguments = {}

    unknown = [harness for harness in selected if harness not in HARNESS_CATALOG]
    if unknown:
        raise ValueError("unsupported harness installers: " + ", ".join(unknown))
    arguments = {}
    commands = []
    for harness in selected:
        install = HARNESS_CATALOG[harness].installer
        for name, value in install.arguments.items():
            previous = arguments.get(name)
            if previous is not None and previous != value:
                raise ValueError(
                    f"conflicting generated build argument {name}: "
                    f"{previous!r} != {value!r}"
                )
            arguments[name] = value
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
