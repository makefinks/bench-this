#!/usr/bin/env python3
"""Provision a benchmark-owned authentication profile without interactive input."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


TOKEN_VARIABLES = {
    "amazon-bedrock": "AGENT_BENCH_BEDROCK_API_KEY",
}
PROFILE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def main() -> int:
    """Load the target's vendored runner and store one supplied provider secret."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--harness", required=True, choices=("omp", "opencode"))
    parser.add_argument("--provider", required=True, choices=("amazon-bedrock",))
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()

    repository = args.repository.expanduser().resolve()
    vendor = repository / "benchmarks" / "_vendor"
    if not (vendor / "agent_bench").is_dir():
        parser.error(f"benchmark runner not found under {vendor}")
    if not PROFILE_PATTERN.fullmatch(args.profile):
        parser.error("profile must use lowercase letters, digits, and hyphens")
    token_variable = TOKEN_VARIABLES[args.provider]
    token = os.environ.pop(token_variable, None)
    if token is None:
        parser.error(
            f"{token_variable} must be supplied through the process environment"
        )
    sys.path.insert(0, str(vendor))
    from agent_bench.workspace import store_bedrock_api_key, store_omp_credential

    if args.harness == "omp":
        destination = store_omp_credential(args.profile, args.provider, token)
    elif args.provider == "amazon-bedrock":
        destination = store_bedrock_api_key(args.profile, token)
    else:
        parser.error("OpenCode provisioning supports only amazon-bedrock")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
