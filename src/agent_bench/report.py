"""Persist append-only normalized results and human-readable experiment summaries."""

import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List

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


def write_summary(path: Path, experiment_id: str, rows: Iterable[RunResult]) -> None:
    """Append one treatment summary without discarding earlier experiments."""

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
        "| Configuration | Passed | Pass rate | Public | Hidden | Overall | Public tests modified | Total tokens | Input tokens | Cached input tokens | Cache write tokens | Output tokens | Reasoning tokens | Cache hit rate | Native cost | Estimated cost | Cost / success | Avg solver time | Avg runtime | Failures |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
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
        lines.append(
            "| {config} | {passed}/{total} | {rate:.1%} | {public} | {hidden} | {overall} | "
            "{mutations} | {total_tokens:,} | {input_tokens:,} | {cached_input_tokens:,} | "
            "{cache_write_tokens:,} | {output_tokens:,} | {reasoning_tokens} | "
            "{cache_hit_rate} | {native} | "
            "{estimated} | {per_success} | {solver_runtime} | {runtime:.1f}s | {failures} |".format(
                config=(
                    f"{config_id}@{config_digest[:12]}"
                    if config_digest
                    else config_id
                ),
                passed=passed,
                total=len(values),
                rate=passed / len(values),
                public=public_score,
                hidden=hidden_score,
                overall=overall_score,
                mutations=mutation_score,
                total_tokens=metrics["total"],
                input_tokens=metrics["input"],
                cached_input_tokens=metrics["cached_input"],
                cache_write_tokens=metrics["cache_write"],
                output_tokens=metrics["output"],
                reasoning_tokens=metrics["reasoning"],
                cache_hit_rate=metrics["cache_hit_rate"],
                native=_money(native) if native else "—",
                estimated=_money(estimated) if estimated else "—",
                per_success=_money(known_cost / passed) if passed and known_cost else "—",
                solver_runtime=solver_runtime,
                runtime=mean(row.duration_seconds for row in values),
                failures=failures,
            )
        )

    lines.extend(
        [
            "",
            "### Task results",
            "",
            "| Configuration | Task | Passed | Public | Hidden | Overall | Total tokens | Input tokens | Cached input tokens | Cache write tokens | Output tokens | Reasoning tokens | Cache hit rate | Cost | Avg solver time | Avg runtime | Failures |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
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
        lines.append(
            "| {config} | {task} | {passed}/{total} | {public} | {hidden} | {overall} | "
            "{total_tokens:,} | {input_tokens:,} | {cached_input_tokens:,} | "
            "{cache_write_tokens:,} | {output_tokens:,} | {reasoning_tokens} | "
            "{cache_hit_rate} | {cost} | {solver_runtime} | "
            "{runtime:.1f}s | {failures} |".format(
                config=(
                    f"{config_id}@{config_digest[:12]}"
                    if config_digest
                    else config_id
                ),
                task=task_id,
                passed=sum(row.passed for row in values),
                total=len(values),
                public=public_score,
                hidden=hidden_score,
                overall=overall_score,
                total_tokens=metrics["total"],
                input_tokens=metrics["input"],
                cached_input_tokens=metrics["cached_input"],
                cache_write_tokens=metrics["cache_write"],
                output_tokens=metrics["output"],
                reasoning_tokens=metrics["reasoning"],
                cache_hit_rate=metrics["cache_hit_rate"],
                cost=cost,
                solver_runtime=(
                    f"{mean(solver_durations):.1f}s" if solver_durations else "—"
                ),
                runtime=mean(row.duration_seconds for row in values),
                failures=", ".join(
                    f"{name}: {count}" for name, count in sorted(failures.items())
                )
                or "—",
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

