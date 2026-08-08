#!/usr/bin/env python3
"""Wrap Markdown prose at 100 columns and align tables without constraining their width."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


DEFAULT_WIDTH = 100
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
LIST_RE = re.compile(r"^(\s*(?:[-+*]|\d+[.)])\s+)(.*)$")
STRUCTURAL_RE = re.compile(
    r"^(?:\s{4}|\s*#|\s*\||\s*<|\s*\[.+\]:|\s*<!--|\s*[-*_]{3,}\s*$)"
)
TABLE_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")


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


def _split_table_row(line: str) -> Optional[Tuple[str, List[str]]]:
    """Return a table row's indentation and cells without splitting escaped pipes."""

    indentation = line[: len(line) - len(line.lstrip(" "))]
    stripped = line[len(indentation) :]
    if len(indentation) >= 4 or not stripped.startswith("|") or not stripped.endswith("|"):
        return None

    cells: List[str] = []
    current: List[str] = []
    backslashes = 0
    for character in stripped[1:-1]:
        if character == "|" and backslashes % 2 == 0:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
        backslashes = backslashes + 1 if character == "\\" else 0
    cells.append("".join(current).strip())
    return indentation, cells


def _separator_alignment(cell: str) -> Optional[str]:
    """Return a valid separator cell's alignment, or None when it is not a separator."""

    if not TABLE_SEPARATOR_RE.fullmatch(cell):
        return None
    if cell.startswith(":") and cell.endswith(":"):
        return "center"
    if cell.startswith(":"):
        return "left"
    if cell.endswith(":"):
        return "right"
    return "default"


def _format_table(lines: Sequence[str], start: int) -> Optional[Tuple[List[str], int]]:
    """Format one complete pipe table and return its output plus the next input index."""

    if start + 1 >= len(lines):
        return None
    header = _split_table_row(lines[start])
    separator = _split_table_row(lines[start + 1])
    if header is None or separator is None:
        return None

    indentation, header_cells = header
    separator_indentation, separator_cells = separator
    if separator_indentation != indentation or len(separator_cells) != len(header_cells):
        return None
    alignments = [_separator_alignment(cell) for cell in separator_cells]
    if any(alignment is None for alignment in alignments):
        return None

    rows = [header_cells, separator_cells]
    next_index = start + 2
    while next_index < len(lines):
        row = _split_table_row(lines[next_index])
        if row is None or row[0] != indentation or len(row[1]) != len(header_cells):
            break
        rows.append(row[1])
        next_index += 1

    widths: List[int] = []
    for column, alignment in enumerate(alignments):
        minimum = 5 if alignment == "center" else 4 if alignment in {"left", "right"} else 3
        widths.append(max(minimum, *(len(row[column]) for row in rows if row is not separator_cells)))

    formatted: List[str] = []
    for row_index, row in enumerate(rows):
        if row_index == 1:
            rendered_cells = []
            for width, alignment in zip(widths, alignments):
                if alignment == "left":
                    rendered_cells.append(":" + "-" * (width - 1))
                elif alignment == "right":
                    rendered_cells.append("-" * (width - 1) + ":")
                elif alignment == "center":
                    rendered_cells.append(":" + "-" * (width - 2) + ":")
                else:
                    rendered_cells.append("-" * width)
        else:
            rendered_cells = [cell.ljust(width) for cell, width in zip(row, widths)]
        formatted.append(f"{indentation}| " + " | ".join(rendered_cells) + " |")
    return formatted, next_index


def format_markdown(text: str, width: int = DEFAULT_WIDTH) -> str:
    """Wrap prose and align pipe tables while preserving other Markdown structure."""

    had_final_newline = text.endswith("\n")
    lines = text.splitlines()
    output: List[str] = []
    in_frontmatter = bool(lines and lines[0].strip() == "---")
    in_fence = False
    fence_marker = ""
    index = 0

    while index < len(lines):
        line = lines[index]
        if in_frontmatter:
            output.append(line)
            if index > 0 and line.strip() == "---":
                in_frontmatter = False
            index += 1
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
            index += 1
            continue

        if in_fence:
            output.append(line)
            index += 1
            continue

        table = _format_table(lines, index)
        if table is not None:
            formatted_table, index = table
            output.extend(formatted_table)
            continue

        output.extend(_wrap_line(line, width))
        index += 1

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
