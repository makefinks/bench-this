#!/usr/bin/env python3
"""Provision a benchmark-owned authentication profile without interactive input."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


BEDROCK_TOKEN_VARIABLE = "AGENT_BENCH_BEDROCK_API_KEY"
SKILL_ROOT = Path(__file__).resolve().parents[1]
VENDOR = SKILL_ROOT / "assets" / "benchmarks" / "_vendor"
sys.path.insert(0, str(VENDOR))

from agent_bench.catalog import AuthPolicy, supported_selections


BEDROCK_SELECTIONS = tuple(
    (harness.id, provider.id)
    for harness, provider in supported_selections()
    if provider.auth_policy is AuthPolicy.BEDROCK_BEARER
)


def main() -> int:
    """Use the skill's bundled runner to store one supplied provider secret."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument(
        "--harness",
        required=True,
        choices=sorted(harness for harness, _ in BEDROCK_SELECTIONS),
    )
    parser.add_argument(
        "--provider",
        required=True,
        choices=sorted({provider for _, provider in BEDROCK_SELECTIONS}),
    )
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    if (args.harness, args.provider) not in BEDROCK_SELECTIONS:
        parser.error(
            f"{args.provider} noninteractive provisioning does not support {args.harness}"
        )

    repository = args.repository.expanduser().resolve()
    benchmark = repository / "benchmarks" / "benchmark.yaml"
    if not benchmark.is_file():
        parser.error(f"benchmark scaffold not found: {benchmark.parent}")

    from agent_bench.auth import PROFILE_PATTERN, store_bedrock_credential

    if not PROFILE_PATTERN.fullmatch(args.profile):
        parser.error("profile must use lowercase letters, digits, and hyphens")
    token = os.environ.pop(BEDROCK_TOKEN_VARIABLE, None)
    if token is None:
        parser.error(
            f"{BEDROCK_TOKEN_VARIABLE} must be supplied through the process environment"
        )

    destination = store_bedrock_credential(
        args.profile,
        args.harness,
        token,
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
