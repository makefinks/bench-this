import json

import pytest

from agent_bench.errors import InfrastructureError
from agent_bench.evaluator import RESULT_PREFIX, parse_evaluator_report, validate_evaluator_exit
from agent_bench.models import RunResult
from agent_bench.report import write_summary


def report(groups, candidate_error=False):
    payload = {"version": 1, "groups": groups, "candidate_error": candidate_error}
    return RESULT_PREFIX + json.dumps(payload) + "\n"


def test_group_report_preserves_manifest_order_and_candidate_error() -> None:
    parsed = parse_evaluator_report(
        "diagnostic\n" + report({"second": False, "first": True}, True),
        ["first", "second"],
    )

    assert list(parsed.group_results) == ["first", "second"]
    assert parsed.group_results == {"first": True, "second": False}
    assert parsed.candidate_error
    validate_evaluator_exit(1, parsed)


@pytest.mark.parametrize(
    "stdout,match",
    [
        ("", "exactly one"),
        (report({"one": True}) * 2, "exactly one"),
        (RESULT_PREFIX + "not-json\n", "valid JSON"),
        (report({"other": True}), "groups mismatch"),
        (report({"one": 1}), "true or false"),
    ],
)
def test_group_report_rejects_missing_or_malformed_protocol(stdout, match) -> None:
    with pytest.raises(InfrastructureError, match=match):
        parse_evaluator_report(stdout, ["one"])


def test_group_report_exit_must_match_strict_result() -> None:
    passed = parse_evaluator_report(report({"one": True}), ["one"])
    failed = parse_evaluator_report(report({"one": False}), ["one"])

    with pytest.raises(InfrastructureError, match="exit 1 conflicts"):
        validate_evaluator_exit(1, passed)
    with pytest.raises(InfrastructureError, match="exit 0 conflicts"):
        validate_evaluator_exit(0, failed)


def test_summary_reports_deterministic_group_completion(tmp_path) -> None:
    rows = [
        RunResult(
            "one",
            "model",
            1,
            False,
            1.0,
            group_results={"a": True, "b": False},
            public_test_results={"smoke": True},
            public_test_mutation_detected=True,
            solver_duration_seconds=2.0,
            estimated_cost_usd=0.1,
        ),
        RunResult(
            "two",
            "model",
            1,
            True,
            1.0,
            group_results={"c": True},
            public_test_results={"smoke": True},
            public_test_mutation_detected=False,
            estimated_cost_usd=0.2,
        ),
    ]

    path = tmp_path / "summary.md"
    write_summary(path, "experiment-one", rows)
    write_summary(path, "experiment-two", rows)

    summary = path.read_text()
    assert summary.count("# Benchmark summary") == 1
    assert summary.count("## Experiment `experiment-") == 2
    assert summary.index("`experiment-one`") < summary.index("`experiment-two`")
    assert "| Public | Hidden | Overall | Public tests modified |" in summary
    assert "| Avg solver time | Avg runtime |" in summary
    assert "2.0s" in summary
    assert summary.count("### Configuration summary") == 2
    assert summary.count("### Task results") == 2
    assert summary.count("| model | one | 0/1 |") == 2
    assert summary.count("| model | two | 1/1 |") == 2
    assert summary.count("$0.1000 estimated") == 2
    assert summary.count("$0.2000 estimated") == 2
    aggregate = (
        "| model | 1/2 | 50.0% | 2/2 (100.0%) | 2/3 (66.7%) | "
        "4/5 (80.0%) | 1/2 |"
    )
    assert summary.count(aggregate) == 2
