#!/usr/bin/env python3
"""Wrap repository Markdown prose at 100 columns without disturbing structure."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


DEFAULT_WIDTH = 100
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
LIST_RE = re.compile(r"^(\s*(?:[-+*]|\d+[.)])\s+)(.*)$")
STRUCTURAL_RE = re.compile(
    r"^(?:\s{4}|\s*#|\s*\||\s*<|\s*\[.+\]:|\s*<!--|\s*[-*_]{3,}\s*$)"
)


def repository_markdown(root: Path) -> List[Path]:
    """Return tracked and unignored untracked Markdown files under *root*."""

    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.md",
        ],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [root / line for line in result.stdout.splitlines() if line and (root / line).is_file()]


def _wrap_line(line: str, width: int) -> List[str]:
    if len(line) <= width or not line.strip() or STRUCTURAL_RE.match(line):
        return [line]

    hard_break = line.endswith("  ")
    content = line[:-2] if hard_break else line
    list_match = LIST_RE.match(content)
    if list_match:
        prefix, body = list_match.groups()
        wrapped = textwrap.wrap(
            body,
            width=width,
            initial_indent=prefix,
            subsequent_indent=" " * len(prefix),
            break_long_words=False,
            break_on_hyphens=False,
        )
    else:
        indentation = content[: len(content) - len(content.lstrip())]
        wrapped = textwrap.wrap(
            content.strip(),
            width=width,
            initial_indent=indentation,
            subsequent_indent=indentation,
            break_long_words=False,
            break_on_hyphens=False,
        )
    if not wrapped:
        return [line]
    if hard_break:
        wrapped[-1] += "  "
    return wrapped


def format_markdown(text: str, width: int = DEFAULT_WIDTH) -> str:
    """Wrap prose lines while preserving frontmatter, fences, and Markdown structure."""

    had_final_newline = text.endswith("\n")
    lines = text.splitlines()
    output: List[str] = []
    in_frontmatter = bool(lines and lines[0].strip() == "---")
    in_fence = False
    fence_marker = ""

    for index, line in enumerate(lines):
        if in_frontmatter:
            output.append(line)
            if index > 0 and line.strip() == "---":
                in_frontmatter = False
            continue

        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            output.append(line)
            continue

        if in_fence:
            output.append(line)
            continue
        output.extend(_wrap_line(line, width))

    formatted = "\n".join(output)
    return formatted + "\n" if had_final_newline else formatted


def _paths(root: Path, arguments: Sequence[str]) -> Iterable[Path]:
    if not arguments:
        return repository_markdown(root)
    paths = []
    for argument in arguments:
        path = Path(argument)
        paths.append(path if path.is_absolute() else root / path)
    return paths


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Markdown files; defaults to repository Markdown")
    parser.add_argument("--check", action="store_true", help="report files requiring formatting")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    args = parser.parse_args(argv)
    if args.width < 40:
        parser.error("--width must be at least 40")

    root = Path(__file__).resolve().parents[1]
    changed = []
    for path in _paths(root, args.paths):
        original = path.read_text(encoding="utf-8")
        formatted = format_markdown(original, args.width)
        if formatted == original:
            continue
        changed.append(path)
        if not args.check:
            path.write_text(formatted, encoding="utf-8")

    if changed:
        action = "needs formatting" if args.check else "formatted"
        for path in changed:
            print(f"{action}: {path.relative_to(root)}")
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
