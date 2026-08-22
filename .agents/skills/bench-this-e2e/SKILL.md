---
name: bench-this-e2e
description: Run or diagnose end-to-end verification of the bench-this skill in its internal full-flow fixture or a user-provided repository with OpenCode or Copilot CLI.
---

# Bench-this E2E verification

Use this developer-only workflow to exercise the skill repeatedly. It is separate from benchmark
policy, treatment configuration, and supported solver setup.

## Boundaries

E2E verification is orchestrated. The orchestrator owns candidate discovery, task and artifact
creation, validation, configuration, and authorized treatment execution. Prepare the repository,
launch or resume the orchestrator, and send the first three prompts as separate turns in one
session:

1. `Use the bench-this skill to recommend 1 benchmark candidate.`
2. `I accept the recommended candidates.`
3. `Create a benchmark configuration for this treatment: <treatment-request>.`

Send the second prompt only after the orchestrator presents a candidate. Send the third only after
it
reports task creation and validation. Replace `<treatment-request>` with the selection defined
below.
These three completed stages are the authoring orchestration criterion.

For the internal full-flow branch, or an external request that explicitly authorizes treatment
execution, send this fourth prompt only after the orchestrator reports treatment configuration:

4. `Verify authentication and run each requested treatment once against one validated task. Inspect
   the normalized result and telemetry, then report the evidence. Do not create or replace
   credentials.`

The fourth completed stage is the treatment-execution criterion. Do not send it for an external
configuration-only E2E request.

An explicit full-flow request with named treatments authorizes source-free auth verification and one
run per treatment. It does not authorize creating or replacing credentials. Orchestrator credentials
do not supply treatment credentials. Each treatment uses its explicitly named benchmark-owned
profile under `~/.agent-bench/auth/<profile>/<harness>/`. If a requested profile is missing, the
orchestrator reports the exact setup command and leaves that treatment unverified.

Choose the target preparation branch from the user's request:

- For the internal full-flow test repository, follow **Prepare the internal target** below. This
  branch requires at least one explicit treatment.
- For a user-provided repository, use the directory the user placed in scope. Work there, not in a
  clone or synthetic fixture.
- If neither branch is clear, ask which target to use. Do not infer it from the current directory.

Keep the orchestrator prompt short: the skill name plus the user's high-level goal. The installed
`bench-this` skill owns discovery and validation details. Target-specific setup belongs only in the
target's generated benchmark files.

Keep the orchestrator model, subscription assumptions, and diagnostic logs in this developer
workflow.
Benchmark prompts, evaluators, and Dockerfiles derive their settings independently. Treatment
configuration comes only from the selection below.

## Select the treatment

Use every treatment setting in the user's E2E request, including the harness, provider, model,
reasoning variant, authentication profile, repetitions, skills, MCP servers, and other requested
configuration. If the user names multiple treatments, preserve each combination. Carry the complete
selection into `<treatment-request>` without deriving values from the orchestrator.

For an external target only, when the user supplies no treatment settings, use this default:

```text
harness: opencode
provider: openai
model: gpt-5.6-luna
reasoning variant: medium
authentication profile: openai
```

For a partially specified treatment, default the model to `gpt-5.6-luna` and the reasoning variant
to `medium` when the selected harness and provider support them. If either default is incompatible,
resolve the missing value with the user before launching the orchestrator. Include optional
treatments and
settings only when the user requests them.

Treatment selection is complete when the final prompt contains every user-supplied setting, all
compatible defaults, and no unresolved required values.

For the internal target, treatment selection is complete only when the user has named at least one
treatment with every required setting resolved. Ask for one instead of applying the external
default.

## Select the orchestrator session

The orchestrator is the interactive OpenCode or Copilot session that drives the `bench-this`
workflow. It creates benchmark artifacts and configuration, then executes requested treatments when
the request authorizes a fourth turn. The default orchestrator is:

```text
harness: opencode
provider: openai
model: gpt-5.6-luna
qualified model: openai/gpt-5.6-luna
reasoning variant: high
authentication: Codex OAuth
```

The internal full-flow branch always uses an OpenCode orchestrator. OpenCode Go and OpenCode with
GitHub Copilot authentication remain valid explicit alternatives, but native Copilot CLI is an
external-target orchestrator only. Use this default unless the user requests one of those compatible
alternatives. Use the exact requested model in an alternative mode. Orchestrator and treatment
settings remain independent.

For the default, confirm `opencode auth list` reports an OpenAI OAuth credential. Launch OpenCode
with `OPENAI_API_KEY` unset so it cannot select API-key authentication.

For OpenCode with GitHub Copilot, confirm `opencode auth list` reports a GitHub Copilot OAuth
credential and use `github-copilot/<requested-model>`. Confirm Copilot Business status before using
a Business endpoint; an auth-profile name is not evidence of the subscription.

For native Copilot CLI, confirm `copilot --version` succeeds and run `copilot login` when needed.
Use the requested model rather than `auto`.

Orchestrator selection is complete when the executable, exact model, supported reasoning variant,
and required OAuth credential are all known.

## Prepare the internal target

Resolve `bench_this_dir` to the current `bench-this` checkout. Create the external log directory
used
by later stages, then verify that the runner source and shipped copy agree before creating a target:

```bash
log_dir=$(mktemp -d "${TMPDIR:-/tmp}/benchmark-skill-e2e-logs.XXXXXX")
python3 "$bench_this_dir/scripts/sync_vendored_runner.py" --check
```

If the check reports drift after canonical validation, run the synchronization command and repeat
check mode. Create the retained target only after check mode passes:

```bash
python3 "$bench_this_dir/scripts/create_full_flow_fixture.py"
```

Read `repository` from the command's JSON result and use it as `repository_dir`. Record the result,
including every commit ID and the installed skill path, in the phase report. The prepared repository
contains the current skill but no remote, benchmark artifacts, or treatment configuration. The
helper
installs the skill after creating history and excludes `.agents/` through `.git/info/exclude`.

Internal target preparation is complete when the sync check passes and the helper returns a unique
repository path containing `.agents/skills/bench-this/SKILL.md`.

## Prepare the run

For the internal branch, keep the `repository_dir` and `log_dir` produced above and continue to the
OpenCode orchestrator. For an external target, set paths from the current checkout and the
user-provided repository, keeping logs outside the target:

```bash
repository_dir="/absolute/path/to/the/user-provided/repository"
skill_dir="/absolute/path/to/bench-this/skills/bench-this"
log_dir=$(mktemp -d "${TMPDIR:-/tmp}/benchmark-skill-e2e-logs.XXXXXX")
```

Preparation is complete when the target contains the current `bench-this` skill at the location for
the selected orchestrator and `log_dir` exists outside the target.

## OpenCode orchestrator

For an external target, install the skill. The internal bootstrap has already completed this step:

```bash
(
  cd "$repository_dir"
  mkdir -p ./.agents/skills/bench-this
  cp -R "$skill_dir"/. ./.agents/skills/bench-this/
)
```

Run every command from `repository_dir`. `--auto` authorizes local file and shell tools, so the
user-provided repository must already be in scope. Capture JSON events and diagnostic logs
separately.

### Background checkpoint loop

When the execution environment supports background tasks, submit each `opencode run` command below
as one background task with a pseudo-terminal. OpenCode may remain at `init` without a terminal even
when stdout and stderr are redirected. Keep the returned task handle and leave the OpenCode process
attached to that task. Use a foreground terminal only when background execution is unavailable.

After launching the task, run this wait as a separate Bash call. The interval depends on the target:
`sleep 30` for the internal full-flow fixture, `sleep 120` for an external target:

```bash
sleep 30 # internal full-flow fixture; use sleep 120 for an external target
```

When the wait returns, inspect the background task, its JSON and diagnostic logs, relevant OpenCode
parent and child sessions, and target-repository changes. Report both:

- **Current:** the active stage, process or task state, and the operation now in progress.
- **Since last check:** completed steps, new tool activity, files changed, and any new errors or
  blockers.

Treat the launch as the baseline for the first report. Record enough checkpoint state, such as log
positions and observed file changes, to make later reports deltas rather than repeated summaries.
If the task is still running, immediately issue another separate wait Bash call with the same
target interval and repeat the inspection and report. Continue this checkpoint loop until the task
completes, fails, or needs user input. Never infer a stall from one quiet interval.

After a stage completes, verify its completion criterion before launching the next prompt as a new
background task and restarting the same checkpoint loop. All prompts remain separate turns in one
OpenCode session.


For the default orchestrator:

```bash
orchestrator_model="openai/gpt-5.6-luna"

(
  cd "$repository_dir"
  env -u OPENAI_API_KEY opencode run \
    --model "$orchestrator_model" \
    --variant high \
    --agent build \
    --format json \
    --print-logs \
    --log-level INFO \
    --auto \
    'Use the bench-this skill to recommend 1 benchmark candidate.' \
    >"$log_dir/orchestrator.jsonl" 2>"$log_dir/opencode.log"
)
```

Record the orchestrator `sessionID` from the JSON stream. After it presents candidates, resume the
same session:

```bash
(
  cd "$repository_dir"
  env -u OPENAI_API_KEY opencode run \
    --session <orchestrator-session-id> \
    --model "$orchestrator_model" \
    --variant high \
    --agent build \
    --format json \
    --print-logs \
    --log-level INFO \
    --auto \
    'I accept the recommended candidates.' \
    >"$log_dir/creation.jsonl" 2>>"$log_dir/opencode.log"
)
```

After the orchestrator reports task creation and validation, resume once more:

```bash
(
  cd "$repository_dir"
  env -u OPENAI_API_KEY opencode run \
    --session <orchestrator-session-id> \
    --model "$orchestrator_model" \
    --variant high \
    --agent build \
    --format json \
    --print-logs \
    --log-level INFO \
    --auto \
    'Create a benchmark configuration for this treatment: <treatment-request>.' \
    >"$log_dir/configuration.jsonl" 2>>"$log_dir/opencode.log"
)
```

When treatment execution is authorized, resume the same session after configuration:

```bash
(
  cd "$repository_dir"
  env -u OPENAI_API_KEY opencode run \
    --session <orchestrator-session-id> \
    --model "$orchestrator_model" \
    --variant high \
    --agent build \
    --format json \
    --print-logs \
    --log-level INFO \
    --auto \
    'Verify authentication and run each requested treatment once against one validated task. Inspect the normalized result and telemetry, then report the evidence. Do not create or replace credentials.' \
    >"$log_dir/execution.jsonl" 2>>"$log_dir/opencode.log"
)
```

For an explicitly requested non-OpenAI orchestrator, replace `orchestrator_model` and omit
`env -u OPENAI_API_KEY`. Remove `--variant high` unless the selected mode supports and requests that
variant. Use `opencode-go/glm-5.2` for an explicitly requested OpenCode Go orchestrator.

The OpenCode run is complete when all required prompts finish in the same recorded session and all
JSON and diagnostic logs are preserved. The internal full-flow branch always requires all four.

## Native Copilot CLI orchestrator

Install the skill in the target:

```bash
(
  cd "$repository_dir"
  mkdir -p ./.agents/skills/bench-this
  cp -R "$skill_dir"/. ./.agents/skills/bench-this/
)
```

Run Copilot from `repository_dir`. The autonomous flags authorize local file and shell tools, so the
user-provided repository must already be in scope. Disable the GitHub tool and remote access because
this workflow uses only the local repository:

```bash
orchestrator_model="<requested-model>"

(
  cd "$repository_dir"
  copilot \
    --model "$orchestrator_model" \
    --output-format json \
    --allow-all-tools \
    --allow-all-paths \
    --deny-tool=github \
    --no-remote \
    --no-auto-update \
    --prompt \
    'Use the bench-this skill to recommend 1 benchmark candidate.' \
    >"$log_dir/orchestrator.jsonl" 2>"$log_dir/copilot.log"
)
```

Record the session ID from the JSON stream. After the orchestrator presents candidates, resume the
same session:

```bash
(
  cd "$repository_dir"
  copilot \
    --resume=<orchestrator-session-id> \
    --model "$orchestrator_model" \
    --output-format json \
    --allow-all-tools \
    --allow-all-paths \
    --deny-tool=github \
    --no-remote \
    --no-auto-update \
    --prompt \
    'I accept the recommended candidates.' \
    >"$log_dir/creation.jsonl" 2>>"$log_dir/copilot.log"
)
```

After the orchestrator reports task creation and validation, resume once more:

```bash
(
  cd "$repository_dir"
  copilot \
    --resume=<orchestrator-session-id> \
    --model "$orchestrator_model" \
    --output-format json \
    --allow-all-tools \
    --allow-all-paths \
    --deny-tool=github \
    --no-remote \
    --no-auto-update \
    --prompt \
    'Create a benchmark configuration for this treatment: <treatment-request>.' \
    >"$log_dir/configuration.jsonl" 2>>"$log_dir/copilot.log"
)
```

When treatment execution is authorized, resume the same session after configuration:

```bash
(
  cd "$repository_dir"
  copilot \
    --resume=<orchestrator-session-id> \
    --model "$orchestrator_model" \
    --output-format json \
    --allow-all-tools \
    --allow-all-paths \
    --deny-tool=github \
    --no-remote \
    --no-auto-update \
    --prompt \
    'Verify authentication and run each requested treatment once against one validated task. Inspect the normalized result and telemetry, then report the evidence. Do not create or replace credentials.' \
    >"$log_dir/execution.jsonl" 2>>"$log_dir/copilot.log"
)
```

The Copilot run is complete when all required prompts finish in the same recorded session and the
JSON streams, stderr log, and session ID are preserved.

## Observe active runs

A quiet JSON stream is not evidence that a worker is stuck. For OpenCode, use the background
checkpoint loop above throughout every active stage. Progress evidence includes logs, tool calls,
session activity, and file changes. Classify an integration failure only when the worker has made no
progress for the chosen timeout and the background task remains running.

Find OpenCode's log directory with:

```bash
opencode debug paths
```

The terms `parent` and `child` below describe OpenCode's internal Task sessions. They do not
describe benchmark treatments.

The Task tool creates a child session with a `parentID`. The global log records the child session ID
and later steps. Inspect either transcript with:

```bash
opencode export <session-id> --sanitize
opencode session list --format json
```

Preserve the parent and child session IDs, background-task handle, JSON stream, OpenCode log, and
sanitized transcripts. The interactive TUI can enter child sessions and show logs for visual
diagnosis.

Native Copilot has no OpenCode parent-child session model. Diagnose it from `copilot.log`, JSON
streams, and repository changes. A quiet stream alone is not a stall; allow several minutes for
exploration and dependency analysis.

## Verify completion

After each orchestrator turn, inspect its tool activity and retained artifacts. The orchestrator
must
run the benchmark-owned checks from the target repository:

```bash
./benchmarks/run.py validate
./benchmarks/run.py build
./benchmarks/run.py validate-task <task-id>
```

Do not repeat a successful check. Run a command directly only when retained evidence is missing or a
failure needs diagnosis. Confirm the applicable evidence from session activity and files:

- validation receipts prove base-fail and reference-pass for every authored task;
- the built image and configuration match the requested treatment identity;
- when execution was authorized, auth preflight logs report the pinned harness, provider where
  applicable, and model;
- when execution was authorized, one normalized run row exists for every requested treatment and its
  evaluator result is recorded;
- when execution was authorized, parsed input and output token telemetry is nonzero, while optional
  reasoning, cache, and native-cost fields are reported when available.

Preserve the prepared repository, external `log_dir`, session IDs, sanitized transcripts, benchmark
receipts, and run logs after success or failure. Finish with a phase report covering target
preparation, discovery, authoring, validation, build, configuration, authentication, execution, and
telemetry. For every phase, cite evidence and explain failures or concrete improvements. Do not turn
missing credentials or skipped work into a pass.
