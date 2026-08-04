#!/usr/bin/env python3
"""Create a tiny two-commit repository for real harness lifecycle smoke tests."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from agent_bench.scaffold import scaffold


BASE_IMPLEMENTATION = '''"""Email normalization used by the synthetic benchmark fixture."""


def normalize_email(value: str) -> str:
    """Trim surrounding whitespace from an email address."""

    return value.strip()
'''


REFERENCE_IMPLEMENTATION = '''"""Email normalization used by the synthetic benchmark fixture."""


def normalize_email(value: str) -> str:
    """Return a trimmed, lowercase email address."""

    return value.strip().lower()
'''


PUBLIC_EVALUATOR = '''"""Give solvers one representative executable normalization check."""

import importlib
import json
import sys


def main(workspace: str) -> int:
    """Emit the public result protocol for a case distinct from hidden evaluation."""

    sys.path.insert(0, workspace)
    try:
        normalize = importlib.import_module("email_utils").normalize_email
        passed = normalize("  Public.User@Example.TEST  ") == "public.user@example.test"
        print(
            "AGENT_BENCH_RESULT: "
            + json.dumps({"version": 1, "groups": {"normalization-basic": passed}})
        )
        return 0 if passed else 1
    except Exception as exc:
        print(f"candidate import failure: {exc}", file=sys.stderr)
        print(
            "AGENT_BENCH_RESULT: "
            + json.dumps(
                {
                    "version": 1,
                    "groups": {"normalization-basic": False},
                    "candidate_error": True,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
'''

HIDDEN_EVALUATOR = '''"""Emit the hidden structured result for complete normalization behavior."""

import importlib
import json
import sys
import traceback


def main(workspace: str) -> int:
    """Evaluate only the prompt's public contract, independent of implementation."""

    sys.path.insert(0, workspace)
    try:
        module = importlib.import_module("email_utils")
        normalize = module.normalize_email
        passed = (
            normalize("  Alice.Example@Example.COM  ") == "alice.example@example.com"
            and normalize("already@lower.test") == "already@lower.test"
        )
        print(
            "AGENT_BENCH_RESULT: "
            + json.dumps({"version": 1, "groups": {"normalization-complete": passed}})
        )
        return 0 if passed else 1
    except Exception:
        traceback.print_exc()
        print(
            "AGENT_BENCH_RESULT: "
            + json.dumps(
                {
                    "version": 1,
                    "groups": {"normalization-complete": False},
                    "candidate_error": True,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
'''


def _write(path: Path, content: str, executable: bool = False) -> None:
    """Write one fixture file and create its parent directory deterministically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def _git(repository: Path, *arguments: str) -> str:
    """Run Git with captured output so fixture failures identify the exact operation."""

    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def _create_history(destination: Path) -> tuple[str, str]:
    """Create the fixture's base and reference commits."""

    _git(destination, "init", "-q")
    _git(destination, "config", "user.email", "fixture@example.invalid")
    _git(destination, "config", "user.name", "Benchmark Fixture")
    _write(destination / "email_utils.py", BASE_IMPLEMENTATION)
    _write(
        destination / "README.md",
        "# Synthetic email utility\n\nA minimal repository for benchmark lifecycle testing.\n",
    )
    _git(destination, "add", "email_utils.py", "README.md")
    _git(destination, "commit", "-qm", "Add email normalization")
    base_commit = _git(destination, "rev-parse", "HEAD")

    _write(destination / "email_utils.py", REFERENCE_IMPLEMENTATION)
    _git(destination, "add", "email_utils.py")
    _git(destination, "commit", "-qm", "Normalize email case")
    reference_commit = _git(destination, "rev-parse", "HEAD")

    return base_commit, reference_commit


def _write_task(benchmark: Path, base_commit: str, reference_commit: str) -> None:
    """Write the task manifest, prompt, and executable test scripts."""

    task = benchmark / "tasks" / "normalize-email"
    _write(
        task / "task.yaml",
        f"""version: 1
id: normalize-email
base_commit: {base_commit}
reference_commit: {reference_commit}
prompt: prompt.md
public_directory: public
public_tests_directory: public-tests
public_test_command: /bin/sh /public-tests/run.sh /workspace
public_test_groups:
  - normalization-basic
hidden_tests_directory: hidden-tests
test_command: /bin/sh /evaluator/run.sh /workspace
requirement_groups:
  - normalization-complete
solver_timeout_seconds: 300
""",
    )
    _write(
        task / "prompt.md",
        """Update `normalize_email(value: str) -> str` in `email_utils.py`.

The function must remove surrounding whitespace and normalize the complete email
address to lowercase. Preserve the public function name and signature. Do not add
external dependencies.
""",
    )
    (task / "public").mkdir(parents=True, exist_ok=True)
    _write(
        task / "public-tests" / "run.sh",
        "#!/bin/sh\nset -eu\npython3 \"$(dirname \"$0\")/evaluate.py\" \"$1\"\n",
        executable=True,
    )
    _write(task / "public-tests" / "evaluate.py", PUBLIC_EVALUATOR)
    _write(
        task / "hidden-tests" / "run.sh",
        "#!/bin/sh\nset -eu\npython3 /evaluator/evaluate.py \"$1\"\n",
        executable=True,
    )
    _write(task / "hidden-tests" / "evaluate.py", HIDDEN_EVALUATOR)


def _write_benchmark(
    destination: Path,
    image: str,
    base_commit: str,
    reference_commit: str,
) -> Path:
    """Write the benchmark manifest, setup script, and task files."""

    benchmark = destination / "benchmarks"
    _write(
        benchmark / "benchmark.yaml",
        f"""version: 1

image:
  name: {image}
  dockerfile: benchmarks/Dockerfile

setup_command: /bin/sh /benchmark/setup.sh /workspace
compose_file: null

defaults:
  solver_timeout_seconds: 300
  evaluator_timeout_seconds: 60
  repetitions: 1

prices: {{}}
""",
    )
    _write(
        benchmark / "setup.sh",
        "#!/bin/sh\nset -eu\ntest -d \"${1:?workspace path is required}\"\n",
        executable=True,
    )
    _write_task(benchmark, base_commit, reference_commit)
    return benchmark


def _write_configuration(benchmark: Path, model: str) -> None:
    """Write the single OpenCode/OpenAI treatment configuration."""

    config = benchmark / "configurations" / "opencode-openai-gpt-5-4-mini"
    _write(
        config / "configuration.yaml",
        f"""id: opencode-openai-gpt-5-4-mini
harness: opencode
provider: openai
model: {model}
agent: build
harness_config: harness
workspace_config: workspace
auth_profile: openai
arguments: []
""",
    )
    _write(
        config / "harness" / "opencode.json",
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "enabled_providers": ["openai"],
                # OpenCode otherwise calls a provider-selected small model for
                # session titles, which would contaminate a one-model treatment.
                "small_model": f"openai/{model}",
                "share": "disabled",
            },
            indent=2,
        )
        + "\n",
    )
    _write(
        config / "workspace" / "AGENTS.md",
        (
            "# Fixture instructions\n\n"
            "Keep the change minimal and run local checks without network access.\n"
        ),
    )


def _remove_examples(benchmark: Path) -> None:
    """Remove inactive scaffold examples from generated benchmark files."""

    shutil.rmtree(benchmark / "tasks" / "example", ignore_errors=True)
    for example in (
        "copilot-example",
        "opencode-example",
        "opencode-openai-example",
        "opencode-go-example",
    ):
        shutil.rmtree(benchmark / "configurations" / example, ignore_errors=True)


def create_fixture(destination: Path, image: str, model: str) -> dict:
    """Create history, benchmark files, and one OpenCode/OpenAI treatment."""

    destination = destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"refusing to overwrite non-empty {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    base_commit, reference_commit = _create_history(destination)
    scaffold(destination)
    benchmark = _write_benchmark(destination, image, base_commit, reference_commit)
    _write_configuration(benchmark, model)
    _remove_examples(benchmark)

    return {
        "repository": str(destination),
        "base_commit": base_commit,
        "reference_commit": reference_commit,
        "task": "normalize-email",
        "configuration": "opencode-openai-gpt-5-4-mini",
        "model": model,
    }


def main() -> int:
    """Parse command-line arguments and print machine-readable fixture metadata."""

    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--image", default="project-agent-benchmark-smoke")
    parser.add_argument("--model", default="gpt-5.4-mini")
    arguments = parser.parse_args()
    metadata = create_fixture(arguments.destination, arguments.image, arguments.model)
    print(json.dumps(metadata))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
