"""Persist append-only normalized results and human-readable experiment summaries."""

import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Sequence

from .models import RunResult


def append_result(path: Path, result: RunResult) -> None:
    """Append one complete run atomically at the line level."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(result), sort_keys=True) + "\n")


def read_results(path: Path) -> List[RunResult]:
    """Load prior JSONL rows for summary regeneration."""

    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(RunResult(**json.loads(line)))
    return rows


def write_viewer_data(path: Path, rows: Iterable[RunResult]) -> None:
    """Expose results as local JavaScript because browsers cannot fetch sibling files over file://."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps([asdict(row) for row in rows], sort_keys=True)
    path.write_text(f"globalThis.BENCHMARK_RESULTS = {payload};\n", encoding="utf-8")


def _money(value: float) -> str:
    """Use enough precision for inexpensive single-task model runs."""

    return f"${value:.4f}"


def _score(values: Iterable[RunResult], attribute: str) -> tuple[int, int, str]:
    """Aggregate one named boolean-result mapping across measured runs."""

    results = [getattr(row, attribute) for row in values]
    passed = sum(sum(result.values()) for result in results)
    total = sum(len(result) for result in results)
    rendered = f"{passed}/{total} ({passed / total:.1%})" if total else "—"
    return passed, total, rendered


def _average_turns(values: Iterable[RunResult]) -> str:
    """Average successful runs only when every included count is authoritative."""

    successful = [row for row in values if row.passed]
    counts = [row.turns for row in successful]
    if not counts or any(count is None for count in counts):
        return "—"
    return f"{mean(counts):.1f}"


def _token_metrics(values: Iterable[RunResult]) -> Dict[str, object]:
    """Sum reported token buckets and derive cache-hit rate when cache reads exist."""

    rows = list(values)
    input_tokens = sum(row.input_tokens for row in rows)
    cached_input_tokens = sum(row.cache_read_tokens for row in rows)
    cache_write_tokens = sum(row.cache_write_tokens for row in rows)
    output_tokens = sum(row.output_tokens for row in rows)
    reasoning_values = [
        row.reasoning_tokens for row in rows if row.reasoning_tokens is not None
    ]
    reasoning_tokens = sum(reasoning_values) if reasoning_values else None
    total_tokens = (
        input_tokens
        + cached_input_tokens
        + cache_write_tokens
        + output_tokens
        + (reasoning_tokens or 0)
    )
    input_total = input_tokens + cached_input_tokens
    cache_hit_rate = (
        f"{cached_input_tokens / input_total:.1%}" if cached_input_tokens else "—"
    )
    return {
        "total": total_tokens,
        "input": input_tokens,
        "cached_input": cached_input_tokens,
        "cache_write": cache_write_tokens,
        "output": output_tokens,
        "reasoning": reasoning_tokens if reasoning_tokens is not None else "—",
        "cache_hit_rate": cache_hit_rate,
    }


def _render_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[str]],
    alignments: Sequence[str],
) -> List[str]:
    """Render a padded Markdown table while preserving its column alignments."""

    header_cells = list(headers)
    body = [list(row) for row in rows]
    if len(header_cells) != len(alignments):
        raise ValueError("table headers and alignments must have the same length")
    if any(len(row) != len(header_cells) for row in body):
        raise ValueError("table rows must have the same length as the headers")

    table_rows = [header_cells, *body]
    widths = []
    for column, alignment in enumerate(alignments):
        minimum = 5 if alignment == "center" else 4 if alignment in {"left", "right"} else 3
        widths.append(max(minimum, *(len(row[column]) for row in table_rows)))

    def render(cells: Sequence[str]) -> str:
        """Pad cells so the generated source is readable before Markdown rendering."""

        return "| " + " | ".join(cell.ljust(width) for cell, width in zip(cells, widths)) + " |"

    separator = []
    for width, alignment in zip(widths, alignments):
        if alignment == "left":
            separator.append(":" + "-" * (width - 1))
        elif alignment == "right":
            separator.append("-" * (width - 1) + ":")
        elif alignment == "center":
            separator.append(":" + "-" * (width - 2) + ":")
        else:
            separator.append("-" * width)
    return [render(header_cells), render(separator), *(render(row) for row in body)]


def write_summary(path: Path, experiment_id: str, rows: Iterable[RunResult]) -> None:
    """Append one padded treatment summary without discarding earlier experiments."""

    groups: Dict[tuple, List[RunResult]] = defaultdict(list)
    task_groups: Dict[tuple, List[RunResult]] = defaultdict(list)
    for row in rows:
        configuration = (row.configuration, row.configuration_digest)
        groups[configuration].append(row)
        task_groups[(*configuration, row.task)].append(row)

    lines = [
        f"## Experiment `{experiment_id}`",
        "",
        "### Configuration summary",
        "",
    ]
    configuration_rows: List[List[str]] = []
    for (config_id, config_digest), values in sorted(
        groups.items(), key=lambda item: (item[0][0], item[0][1] or "")
    ):
        passed = sum(row.passed for row in values)
        metrics = _token_metrics(values)
        native = sum(row.native_cost_usd or 0 for row in values)
        estimated = sum(row.estimated_cost_usd or 0 for row in values)
        # Rows may now carry both costs; the derived cost-per-success uses the
        # authoritative per-row figure (native when reported, else estimated).
        known_cost = sum(
            row.native_cost_usd
            if row.native_cost_usd is not None
            else (row.estimated_cost_usd or 0)
            for row in values
        )
        failure_counts = Counter(
            row.failure_kind or "incorrect" for row in values if not row.passed
        )
        failures = ", ".join(
            f"{name}: {count}" for name, count in sorted(failure_counts.items())
        ) or "—"
        public_passed, public_total, public_score = _score(values, "public_test_results")
        hidden_passed, hidden_total, hidden_score = _score(values, "group_results")
        overall_passed = public_passed + hidden_passed
        overall_total = public_total + hidden_total
        overall_score = (
            f"{overall_passed}/{overall_total} ({overall_passed / overall_total:.1%})"
            if overall_total
            else "—"
        )
        mutation_values = [
            row.public_test_mutation_detected
            for row in values
            if row.public_test_mutation_detected is not None
        ]
        mutation_score = (
            f"{sum(mutation_values)}/{len(mutation_values)}" if mutation_values else "—"
        )
        solver_durations = [
            row.solver_duration_seconds
            for row in values
            if row.solver_duration_seconds is not None
        ]
        solver_runtime = f"{mean(solver_durations):.1f}s" if solver_durations else "—"
        configuration_rows.append(
            [
                f"{config_id}@{config_digest[:12]}" if config_digest else config_id,
                f"{passed}/{len(values)}",
                f"{passed / len(values):.1%}",
                public_score,
                hidden_score,
                overall_score,
                mutation_score,
                _average_turns(values),
                f"{metrics['total']:,}",
                f"{metrics['input']:,}",
                f"{metrics['cached_input']:,}",
                f"{metrics['cache_write']:,}",
                f"{metrics['output']:,}",
                str(metrics["reasoning"]),
                str(metrics["cache_hit_rate"]),
                _money(native) if native else "—",
                _money(estimated) if estimated else "—",
                _money(known_cost / passed) if passed and known_cost else "—",
                solver_runtime,
                f"{mean(row.duration_seconds for row in values):.1f}s",
                failures,
            ]
        )

    lines.extend(
        _render_table(
            [
                "Configuration",
                "Passed",
                "Pass rate",
                "Public",
                "Hidden",
                "Overall",
                "Public tests modified",
                "Avg turns",
                "Total tokens",
                "Input tokens",
                "Cached input tokens",
                "Cache write tokens",
                "Output tokens",
                "Reasoning tokens",
                "Cache hit rate",
                "Native cost",
                "Estimated cost",
                "Cost / success",
                "Avg solver time",
                "Avg runtime",
                "Failures",
            ],
            configuration_rows,
            ["default"] + ["right"] * 19 + ["default"],
        )
    )
    lines.extend(["", "### Task results", ""])
    task_rows: List[List[str]] = []
    for (config_id, config_digest, task_id), values in sorted(
        task_groups.items(), key=lambda item: (item[0][0], item[0][1] or "", item[0][2])
    ):
        metrics = _token_metrics(values)
        public_passed, public_total, public_score = _score(values, "public_test_results")
        hidden_passed, hidden_total, hidden_score = _score(values, "group_results")
        overall_passed = public_passed + hidden_passed
        overall_total = public_total + hidden_total
        overall_score = (
            f"{overall_passed}/{overall_total} ({overall_passed / overall_total:.1%})"
            if overall_total
            else "—"
        )
        native = sum(row.native_cost_usd or 0 for row in values)
        estimated = sum(row.estimated_cost_usd or 0 for row in values)
        if native and estimated:
            cost = f"{_money(native)} native + {_money(estimated)} estimated"
        elif native:
            cost = f"{_money(native)} native"
        elif estimated:
            cost = f"{_money(estimated)} estimated"
        else:
            cost = "—"
        solver_durations = [
            row.solver_duration_seconds
            for row in values
            if row.solver_duration_seconds is not None
        ]
        failures = Counter(
            row.failure_kind or "incorrect" for row in values if not row.passed
        )
        task_rows.append(
            [
                f"{config_id}@{config_digest[:12]}" if config_digest else config_id,
                task_id,
                f"{sum(row.passed for row in values)}/{len(values)}",
                public_score,
                hidden_score,
                overall_score,
                _average_turns(values),
                f"{metrics['total']:,}",
                f"{metrics['input']:,}",
                f"{metrics['cached_input']:,}",
                f"{metrics['cache_write']:,}",
                f"{metrics['output']:,}",
                str(metrics["reasoning"]),
                str(metrics["cache_hit_rate"]),
                cost,
                f"{mean(solver_durations):.1f}s" if solver_durations else "—",
                f"{mean(row.duration_seconds for row in values):.1f}s",
                ", ".join(
                    f"{name}: {count}" for name, count in sorted(failures.items())
                )
                or "—",
            ]
        )

    lines.extend(
        _render_table(
            [
                "Configuration",
                "Task",
                "Passed",
                "Public",
                "Hidden",
                "Overall",
                "Avg turns",
                "Total tokens",
                "Input tokens",
                "Cached input tokens",
                "Cache write tokens",
                "Output tokens",
                "Reasoning tokens",
                "Cache hit rate",
                "Cost",
                "Avg solver time",
                "Avg runtime",
                "Failures",
            ],
            task_rows,
            ["default", "default"] + ["right"] * 15 + ["default"],
        )
    )
    if not groups:
        lines.extend(["", "No runs recorded."])
    path.parent.mkdir(parents=True, exist_ok=True)
    has_prior_summaries = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8") as handle:
        if has_prior_summaries:
            handle.write("\n")
        else:
            handle.write("# Benchmark summary\n\n")
        handle.write("\n".join(lines) + "\n")

