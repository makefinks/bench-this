# Setup contract

Use this checklist after scaffolding and before validating tasks. The benchmark image serves two
independent purposes: it provides the target project's build/test environment and the selected
coding-agent harness. Preserve both.

## Docker image

- Extend the scaffold Dockerfile with the project's runtimes, native libraries, and build tools. Do
  not replace the base image without carrying forward the selected harness CLI and its pinned
  version.
- Install harnesses and project setup tools in system paths such as `/usr/local/bin`. The runner
  uses the host user's numeric UID/GID and a temporary `HOME`; executables must not resolve through
  `/root`, a login shell profile, or another user's home directory.
- Prefer real system-wide installations over symlinks into a root-owned installer directory. If an
  installer writes into a home directory, copy the executable into a world-executable system path
  and verify the final resolved target.
- Pin runtime and harness versions. Respect the historical project's runtime constraints rather than
  whichever interpreter a host-side environment manager happens to select.
- Keep credentials and provider configuration out of the image.

## Project setup

`setup.sh` receives a workspace as `$1`. It runs inside the image with network access, as a non-root
user with a temporary home. Validation runs it once for each historical workspace. A measured cell
runs it once before solving, then copies the candidate into a separate evaluator workspace and runs
it there again. The second setup prevents solver changes to `.venv`, `node_modules`, or similar
dependency environments from affecting evaluation.

- Make setup non-interactive and deterministic from the checked-out lockfiles or manifests.
- Install only project dependencies and generated build artifacts. Do not add credentials, hidden
  tests, benchmark metadata, or host-specific paths.
- Use commands available inside the image. Do not rely on host aliases, shell startup files, or
  host-managed virtual environments.
- Ensure setup works at every task's base and reference commit; dependency metadata can differ
  across history.
- Prepare enough of the real project environment for a solver to run the repository's normal
  task-relevant checks. A setup that supports only the hidden evaluator is incomplete. Verify the
  project package manager, focused tests, typechecker, or build command named in the task-agent
  report actually resolves inside a staged solver workspace at both commits.

Set `defaults.setup_timeout_seconds` independently from `evaluator_timeout_seconds`. Both must be
positive integers. An older v1 manifest without a setup timeout falls back to its evaluator timeout.
Keep `solver_timeout_seconds: null` unless the user explicitly requests a finite experimental
budget. Do not shrink task scope or reject a candidate merely to fit an arbitrary solver deadline.

Install evaluator runtime dependencies here, not from `hidden-tests/run.sh`. Public and hidden
evaluators reuse the separately prepared evaluator workspace without network access.

Hidden evaluator files are mounted read-only at `/evaluator`. Never copy them into the exported
workspace, even temporarily. Run files from that path, but direct caches, temporary files, and
generated output elsewhere (or disable them). If imports require a project-relative layout, recreate
it under an evaluator-private temporary directory and link or reference only the needed product
files from the workspace.

The required canonical public tests are mounted read-only at `/public-tests` during evaluation. The
solver receives a writable copy at `.agent-bench-public-tests/` so it can inspect and run the
tests, but evaluation never trusts that copy. The runner reports final modifications or deletions of
supplied public test files as integrity telemetry without changing the score. Public evaluators have
the same no-network, no-credential, bounded-runtime constraints as hidden evaluators.

## Verification order

Run the self-contained CLI directly from the target repository:

```bash
./benchmarks/run.py validate
./benchmarks/run.py build
./benchmarks/run.py validate-tasks --jobs <n>
```

Do not prefix these commands with `uv run`, Poetry, npm, or another project environment manager.
Those wrappers can silently select a different host runtime even though the runner vendors its
Python dependencies.

As coordinator, you own task validation as part of benchmark creation; do not hand it off to the
user. Task agents report setup requirements but do not run these commands. Before starting
validation, inspect host and Docker CPU and memory when possible. A validation worker may run two
substantial setup environments, so consider disk, network, and memory pressure rather than host CPU
count alone. Use the CLI default of three jobs when inspection is unavailable or capacity is
uncertain. Pass a higher bounded value only when Docker can sustain that many concurrent setups; use
`--jobs 1` when reproducing contention or timeout failures. The runner caps workers at the task
count, preserves base-before-reference ordering within each task, and keeps task logs and receipts
isolated.

Do not parallelize separate `validate-task` shell calls. `validate-tasks` owns bounded concurrency
and prints task and phase progress while suppressing interleaved raw output. Complete per-phase logs
remain available for diagnosis. Use `validate-task <task-id> --verbose` for focused diagnosis and
task-local retries.

Set the shell-tool timeout to exactly `14400000` milliseconds (four hours) for every
`validate-tasks` or `validate-task` command. The runner's phase-level timeouts remain authoritative;
task count, concurrency, expected duration, and observed progress do not shorten this outer timeout.

When setup fails, fix benchmark-owned `Dockerfile`, `setup.sh`, task files, or evaluators. Rebuild
after Dockerfile changes. Changes to the shared image or setup invalidate the common validation
environment, so rerun `validate-tasks` for every task. After task-local prompt, manifest, public, or
evaluator changes, run `validate-task <task-id>` sequentially for each affected task and never rerun
unaffected tasks. Never patch product source to make validation pass.

Only an exit-zero command plus a terminal `validated` receipt and inspected phase logs proves task
validation. Timeouts, partial or running receipts, and worker-local checks do not. Confirm the base
evaluator reached a behavioral assertion; missing files, imports, commands, dependencies, compile
errors, or uncaught initialization exceptions are infrastructure failures even if the test framework
returns 1. Full phase logs remain in the unique attempt directory; pass `--verbose` only when live
raw output is useful.

Only after every task validates should treatment setup begin. Provider, model, and auth profile are
user choices; do not derive them from existing credential folders, example configurations, or a
provider's error suggestions.
