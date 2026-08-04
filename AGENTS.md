# Comments
Use concise, high-information comments to explain a function’s purpose, non-obvious decisions,
assumptions, and edge cases.
Avoid comments that merely restate the code; optimize for helping a developer quickly understand and
safely modify the function.

## README
Always keep the README up to date when doing larger changes.
Do not add every detail to the README but evaluate if the change needs to be reflected there
yourself before writing there.

## Generality

Treat individual target repositories and E2E runs as diagnostic evidence, not specifications. Every
change to the skill, runner, scaffold, prompts, evaluators, or tests must address a
repository-agnostic class of cases. Never special-case a repository name, path, commit, dependency,
framework, generated task, or observed run. Keep target-specific setup only in that target's
generated benchmark files. Cover general changes with unit tests or synthetic fixtures that do not
encode one repository's behavior.

## Markdown formatting

Wrap Markdown prose at 100 columns. Write Markdown normally, then run the repository
formatter before handing work back:

```bash
python3 scripts/format_markdown.py
python3 scripts/format_markdown.py --check
```

The formatter intentionally preserves YAML frontmatter, fenced and indented code,
tables, headings, HTML, and link-reference definitions when wrapping them could change
their meaning.

## Repository validation

Run the repository tests with:

```bash
PYTHONPATH=src:. uv run --extra test pytest
```

The repository root must be on `PYTHONPATH` because the fixture-generator tests import from
`scripts/`.

## Optional skill E2E verification

This section describes a developer-only verification loop. It is not part of
`bench-this`'s behavior, benchmark policy, treatment configuration, or
supported solver setup.

By default, use this exact provider/model combination for the parent agent that exercises the
skill:

```text
provider: openai
model: gpt-5.6-luna
qualified model: openai/gpt-5.6-luna
reasoning variant: max
```

The default parent OpenCode session must use `openai/gpt-5.6-luna` with reasoning variant `max` and
Codex OAuth authentication. OpenCode Go, OpenCode with GitHub Copilot authentication, and native
GitHub Copilot CLI are also supported when the user explicitly requests them. Use the exact model
the user requests for an alternative mode; do not silently choose a model.

Parent-agent selection and benchmark-treatment selection are separate decisions. Do not infer or
create a treatment from the parent agent's harness, provider, model, or authentication. This
developer workflow normally stops after task creation and behavioral validation without configuring
or running a treatment. If the user separately requests a treatment, use its independently approved
harness, provider where applicable, model, and auth profile. Matching the parent is allowed but is
not required.

For the default, verify that `opencode auth list` reports an OpenAI OAuth credential and run the
parent OpenCode session with `OPENAI_API_KEY` unset so it cannot silently use API-key authentication
instead. For example, run the parent with:

```bash
env -u OPENAI_API_KEY opencode run \
  --model openai/gpt-5.6-luna \
  --variant max \
  --agent build \
  --format json \
  --auto \
  '<prompt>'
```

For OpenCode with GitHub Copilot authentication, verify that `opencode auth list` reports a GitHub
Copilot OAuth credential and use `github-copilot/<requested-model>` for the parent session. Confirm
whether the account uses Copilot Business before relying on a Business endpoint; do not infer the
subscription from an auth-profile name.

For native Copilot CLI, verify that `copilot --version` succeeds and authenticate with
`copilot login` when needed. Use the requested model explicitly rather than `auto`. The commands
below use only CLI options confirmed by `copilot --help` for the installed version.

Parent-session credentials do not supply benchmark treatment credentials. Every treatment must use
its own explicitly named benchmark-owned profile under
`~/.agent-bench/auth/<profile>/<harness>/` and follow the treatment authentication workflow.

Do not substitute another parent provider, model, or reasoning variant without an explicit user
request. The auth-profile name may vary by environment; verify treatment settings independently
before running a benchmark.

Use this workflow only to repeatedly exercise the skill. The normal E2E path targets the actual
repository directory explicitly supplied by the user; do not silently substitute a clone or a
synthetic fixture. Do not copy this model, its subscription assumptions, or its logs into the skill,
benchmark prompts, evaluator, Dockerfile, or treatment configuration.

Invoke the parent orchestrator with only the skill name and the user's high-level goal. Name
`bench-this` so the orchestrator reliably loads it, but do not prescribe task discovery or
validation
steps, restate benchmark policy, or tell it which tools or subagents to use. The installed skill is
responsible for supplying that workflow. Keep follow-up messages equally minimal and communicate
only the user's decision, such as approval or rejection.

### User-provided repository

Set `repository_dir` to the absolute path the user placed in scope. Set `skill_dir` to this
checkout's `skills/bench-this` directory, or use the normal local skill installation if it is
already available to the selected parent harness. Keep logs outside the target repository:

```bash
repository_dir="/absolute/path/to/the/user-provided/repository"
skill_dir="/absolute/path/to/bench-this/skills/bench-this"
log_dir=$(mktemp -d /tmp/benchmark-skill-e2e-logs.XXXXXX)
```

### OpenCode parent session

Install the skill for OpenCode inside the target repository at
`./.opencode/skills/bench-this/`:

```bash
(
  cd "$repository_dir"
  mkdir -p ./.opencode/skills/bench-this
  cp -R "$skill_dir"/. ./.opencode/skills/bench-this/
)
```

Run each OpenCode command from the target repository with `cd "$repository_dir"`; do not pass the
repository through `--dir`. `--auto` permits local file and shell tools, so use it only after the
user has explicitly placed that repository in scope. Set `parent_model` to the selected qualified
model: `openai/gpt-5.6-luna` by default, `opencode-go/glm-5.2` when explicitly requested, or
`github-copilot/<requested-model>` for GitHub Copilot. Capture JSON events and diagnostic logs
separately:

```bash
parent_model="openai/gpt-5.6-luna"

(
  cd "$repository_dir"
  env -u OPENAI_API_KEY opencode run \
    --model "$parent_model" \
    --variant max \
    --agent build \
    --format json \
    --print-logs \
    --log-level INFO \
    --auto \
    'Use the bench-this skill to create one benchmark task for this repository.' \
    >"$log_dir/parent.jsonl" 2>"$log_dir/opencode.log"
)
```

Record the parent `sessionID` from the JSON stream and continue that same session after
explicitly approving the candidate:

```bash
(
  cd "$repository_dir"
  env -u OPENAI_API_KEY opencode run \
    --session <parent-session-id> \
    --model "$parent_model" \
    --variant max \
    --agent build \
    --format json \
    --print-logs \
    --log-level INFO \
    --auto \
    'Approved. Continue.' \
    >"$log_dir/creation.jsonl" 2>>"$log_dir/opencode.log"
)
```

For an explicitly requested non-OpenAI parent, replace `parent_model` and omit the `env` prefix.
Remove `--variant max` unless that mode has its own requested and supported variant.

### Native Copilot CLI parent session

Install the skill in a Copilot-supported project location:

```bash
(
  cd "$repository_dir"
  mkdir -p ./.github/skills/bench-this
  cp -R "$skill_dir"/. ./.github/skills/bench-this/
)
```

Run Copilot from the target repository. The autonomous flags permit local file and shell tools, so
use them only after the user has explicitly placed that repository in scope. Disable the GitHub tool
and remote access because this workflow requires only the local repository:

```bash
parent_model="<requested-model>"

(
  cd "$repository_dir"
  copilot \
    --model "$parent_model" \
    --output-format json \
    --allow-all-tools \
    --allow-all-paths \
    --deny-tool=github \
    --no-remote \
    --no-auto-update \
    --prompt \
    'Use the bench-this skill to create one benchmark task for this repository.' \
    >"$log_dir/parent.jsonl" 2>"$log_dir/copilot.log"
)
```

Record the session ID reported in the JSON stream and resume that session after explicitly approving
the candidate:

```bash
(
  cd "$repository_dir"
  copilot \
    --resume=<parent-session-id> \
    --model "$parent_model" \
    --output-format json \
    --allow-all-tools \
    --allow-all-paths \
    --deny-tool=github \
    --no-remote \
    --no-auto-update \
    --prompt \
    'Approved. Continue.' \
    >"$log_dir/creation.jsonl" 2>>"$log_dir/copilot.log"
)
```

### OpenCode child-session observability

Do not classify a worker as stuck merely because the parent JSON stream is quiet. The
Task tool creates a child session with a `parentID`; the global OpenCode log records the
child session ID and its subsequent steps. Find the log directory with:

```bash
opencode debug paths
```

Inspect a parent or child transcript with:

```bash
opencode export <session-id> --sanitize
opencode session list --format json
```

Wait while the child log shows new steps, tool calls, or file changes. Allow a generous
task-level wall-clock budget; exploration and dependency analysis can take several
minutes. Treat it as a genuine integration failure only when the child has stopped
making progress for the chosen no-progress timeout and the parent Task part remains
running. Preserve the JSON stream, OpenCode log, parent session ID, child session ID,
and exported transcripts for diagnosis. The interactive TUI can also enter child
sessions and open logs when a visual check is useful.

### Copilot CLI observability

Preserve the JSON streams, stderr log, and parent session ID.
A quiet JSON stream alone does not mean Copilot is stuck.
Inspect `copilot.log` and repository changes for ongoing progress.
Allow the same generous task-level wall-clock budget used for OpenCode. Treat the run as an
integration failure only after the chosen no-progress timeout.
Native Copilot does not use OpenCode's parent/child session log model.
Do not apply `opencode export` or `parentID` checks to it.

### Completion checks

After the worker reports back, inspect the generated prompt, evaluator, and setup
requirements. Then run the benchmark-owned checks directly from the user-provided
repository:

```bash
./benchmarks/run.py validate
./benchmarks/run.py build
./benchmarks/run.py validate-task <task-id>
```

A successful E2E verification requires behavioral base-fail/reference-pass validation;
passing CLI commands alone is not sufficient. Keep diagnostic logs in `log_dir`, outside
the user-provided repository. A disposable fixture is reserved for smoke tests that
intentionally exercise destructive or auto-approved behavior in isolation; it is not
the normal E2E target.

### Runner source and vendored copy

`src/agent_bench/` is the canonical development source for the benchmark runner. The copy
under `skills/bench-this/assets/benchmarks/_vendor/agent_bench/` is the
vendored distribution copy used by generated target repositories.

When changing runner behavior, modify and test `src/agent_bench/` first, then synchronize
the vendored copy after the source change is complete. Do not independently edit both
copies. Skill-only changes, such as `SKILL.md`, references, or scaffold assets, do not
require changes to `src/agent_bench/`.

Generated repositories execute their own `benchmarks/_vendor/agent_bench/` copy and do
not use this repository's `src/` directory.
