"""Parse deterministic requirement-group outcomes emitted by hidden evaluators."""

import json
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from .errors import InfrastructureError


RESULT_PREFIX = "AGENT_BENCH_RESULT: "


@dataclass(frozen=True)
class EvaluatorReport:
    """Validated named outcomes from one evaluator invocation."""

    group_results: Dict[str, bool]
    candidate_error: bool = False


def parse_evaluator_report(
    stdout: str, expected_groups: Iterable[str]
) -> Optional[EvaluatorReport]:
    """Require one exact JSON report when a task declares requirement groups."""

    expected = list(expected_groups)
    if not expected:
        return None
    markers = [line[len(RESULT_PREFIX) :] for line in stdout.splitlines() if line.startswith(RESULT_PREFIX)]
    if len(markers) != 1:
        raise InfrastructureError(
            f"evaluator must emit exactly one {RESULT_PREFIX.strip()!r} line; got {len(markers)}"
        )
    try:
        payload = json.loads(markers[0])
    except json.JSONDecodeError as exc:
        raise InfrastructureError(f"evaluator result is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) - {"version", "groups", "candidate_error"}:
        raise InfrastructureError("evaluator result must contain only version, groups, and candidate_error")
    if payload.get("version") != 1:
        raise InfrastructureError("evaluator result version must be 1")
    groups = payload.get("groups")
    if not isinstance(groups, dict):
        raise InfrastructureError("evaluator result groups must be a mapping")
    if set(groups) != set(expected):
        missing = sorted(set(expected) - set(groups))
        extra = sorted(set(groups) - set(expected))
        raise InfrastructureError(f"evaluator result groups mismatch; missing={missing}, extra={extra}")
    if any(type(value) is not bool for value in groups.values()):
        raise InfrastructureError("every evaluator group result must be true or false")
    candidate_error = payload.get("candidate_error", False)
    if type(candidate_error) is not bool:
        raise InfrastructureError("candidate_error must be true or false")
    return EvaluatorReport(
        group_results={group: groups[group] for group in expected},
        candidate_error=candidate_error,
    )


def validate_evaluator_exit(returncode: int, report: Optional[EvaluatorReport]) -> None:
    """Keep strict pass/fail consistent with the reported requirement groups."""

    if returncode not in (0, 1):
        raise InfrastructureError(
            f"evaluator exited {returncode}; evaluator contract permits only 0 or 1"
        )
    if report is None:
        return
    all_passed = all(report.group_results.values())
    if returncode == 0 and (not all_passed or report.candidate_error):
        raise InfrastructureError("evaluator exit 0 conflicts with its requirement-group report")
    if returncode == 1 and all_passed and not report.candidate_error:
        raise InfrastructureError("evaluator exit 1 conflicts with its requirement-group report")
