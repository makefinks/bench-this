# V1 formats and commands

## Project file

`benchmarks/benchmark.yaml` contains one image, one setup command, defaults, and optional per-model
prices. Explicit prices override the runner's best-effort Models.dev provider pricing. Keep
`compose_file: null` in v1.

## Task file

```yaml
version: 1
id: duplicate-email
base_commit: 0123456789abcdef0123456789abcdef01234567
reference_commit: fedcba9876543210fedcba9876543210fedcba98
prompt: prompt.md
public_directory: public
public_tests_directory: public-tests
public_test_command: /bin/sh /public-tests/run.sh /workspace
public_test_groups:
  - duplicate-basic
hidden_tests_directory: hidden-tests
test_command: /bin/sh /evaluator/run.sh /workspace
requirement_groups:
  - duplicate-detection
  - persisted-state
solver_timeout_seconds: null
```

Use full commit hashes. Paths must be relative to the task directory.
`task_workspace.py prepare` generates this standard manifest and its required directories. Change
the manifest only when the task needs a nonstandard evaluator command or finite solver timeout. The
generated manifest omits `solver_timeout_seconds` so the project default applies. Set the project or
task value to `null` for unlimited solver time; setup and evaluator timeouts remain finite.

Every task must provide all three `public_test_*` fields and both public and hidden test suites.
`public_test_groups` must contain at least one unique lowercase ID. During solving, the runner
copies
the suite to `.agent-bench-public-tests/` in the writable workspace. During evaluation, it runs the
unchanged task-owned source read-only at `/public-tests`; edits to the visible copy never affect the
score. The public suite uses the same result protocol as the hidden evaluator. Its entrypoint must
resolve helper files relative to its own location rather than hard-coding `/public-tests`, so the
same files run from the solver-visible copy and the canonical mount.

`requirement_groups` must contain at least one stable public-contract group ID. The hidden evaluator
must print exactly one machine-readable line after its diagnostics:

```text
AGENT_BENCH_RESULT: {"version":1,"groups":{"duplicate-detection":true,"persisted-state":false}}
```

Every declared group appears exactly once with a boolean result. Exit `0` requires all groups to be
true; exit `1` requires at least one false group. Set `"candidate_error":true` with exit `1` when
the submitted product workspace cannot import or compile. Reserve exit codes above `1` for failures
in evaluator code, dependencies, setup, or its own fixtures.

For the public suite, `groups` must exactly match `public_test_groups`. For the hidden suite, it
must
exactly match `requirement_groups`. Public and hidden IDs are scored and reported separately; the
overall diagnostic score combines both sets. Strict task success for skill-authored tasks requires
the solver, public suite, and hidden suite all to exit `0`.

## Copilot configuration

```yaml
id: copilot-model-a
harness: copilot
model: model-a
harness_config: harness
workspace_config: workspace
auth_profile: copilot
arguments: []
```

Native Copilot CLI may use `model: auto`. Other providerless values are rejected.

## OpenCode configuration

```yaml
id: opencode-model-a
harness: opencode
provider: github-copilot
model: model-a
agent: build
harness_config: harness
workspace_config: workspace
auth_profile: copilot
arguments: []
```

OpenCode with GitHub Copilot may use `model: auto`. Add
`github_copilot_business: true` only for a confirmed Copilot Business account.

For OpenCode authenticated through its OpenAI OAuth flow, use:

```yaml
id: opencode-openai-model-a
harness: opencode
provider: openai
model: model-a
agent: build
harness_config: harness
workspace_config: workspace
auth_profile: openai
arguments: []
```

For an OpenCode Go subscription, use its provider name separately from the profile label:

```yaml
id: opencode-go-glm-5-2
harness: opencode
provider: opencode-go
model: glm-5.2
agent: build
harness_config: harness
workspace_config: workspace
auth_profile: opencode-go
arguments: []
```

For OpenCode Zen, use its provider ID separately from the local auth-profile label:

```yaml
id: opencode-zen-deepseek-v4-flash
harness: opencode
provider: opencode
model: deepseek-v4-flash
agent: build
harness_config: harness
workspace_config: workspace
auth_profile: opencode-zen
arguments: []
```

The `opencode-zen` profile must be authenticated through OpenCode Zen before the treatment runs.

The `auth_profile` values `openai`, `opencode-go`, and `opencode-zen` are local labels under
`~/.agent-bench/auth/`. They happen to match the provider IDs in these examples, but profile labels
do not select a provider. The `provider` field and matching `auth login --provider` argument do.

For Amazon Bedrock with a runner-managed bearer API key, use:

```yaml
id: opencode-bedrock-model-a
harness: opencode
provider: amazon-bedrock
model: model-a
agent: build
region: us-east-1
harness_config: harness
workspace_config: workspace
auth_profile: bedrock
arguments: []
```

The corresponding `harness/opencode.json` must pin the AWS region under
`provider.amazon-bedrock.options.region`. The external profile supplies
`AWS_BEARER_TOKEN_BEDROCK`; never put that token in YAML or `opencode.json`.

Every treatment manifest uses one strict flat schema. The loader rejects unknown fields, fields that
do not apply to the selected catalog entry, missing providers, provider fields on native Copilot,
and automatic models outside the three GitHub Copilot selections.

## Oh My Pi configuration

```yaml
id: omp-codex-model-a
harness: omp
provider: openai-codex
model: model-a
harness_config: harness
workspace_config: workspace
auth_profile: codex
arguments: []
```

OMP with GitHub Copilot may use `model: auto`. OMP Amazon Bedrock configurations use
`provider: amazon-bedrock` and add the required `region`.

## Pi configuration

```yaml
id: pi-codex-model-a
harness: pi
provider: openai-codex
model: model-a
harness_config: harness
workspace_config: workspace
auth_profile: codex
arguments: []
```

Pi Amazon Bedrock configurations use `provider: amazon-bedrock` and add the required `region`.
The external profile holds a Bedrock API key injected as `AWS_BEARER_TOKEN_BEDROCK`.

## Commands

```bash
# Run after candidate approval, using the skill loader's reported base directory.
python <skill-directory>/scripts/scaffold.py .
./benchmarks/run.py validate
./benchmarks/run.py build
./benchmarks/run.py validate-tasks --jobs 3
./benchmarks/run.py validate-task duplicate-email
./benchmarks/run.py auth login --harness copilot --profile copilot
./benchmarks/run.py auth login --harness opencode --provider github-copilot --profile copilot
./benchmarks/run.py auth login --harness opencode --provider openai --profile openai
./benchmarks/run.py auth login --harness opencode --provider opencode-go --profile opencode-go
./benchmarks/run.py auth login --harness opencode --provider opencode --profile opencode-zen
./benchmarks/run.py auth login --harness pi --provider openai-codex --profile codex
./benchmarks/run.py doctor
./benchmarks/run.py run --task duplicate-email --configuration copilot-model-a
./benchmarks/run.py run --task duplicate-email --task another-task \
  --configuration copilot-model-a --configuration opencode-model-b
./benchmarks/run.py run --repetitions 3
./benchmarks/run.py run --verbose --task duplicate-email --configuration copilot-model-a
./benchmarks/run.py run --json --task duplicate-email --configuration copilot-model-a
```

Invoke `benchmarks/run.py` directly. It is executable and vendors its Python dependencies, so
wrapping it in the target project's environment manager is unnecessary and can select the wrong host
interpreter.

Results are written under `benchmarks/results/`. Strict task pass/fail remains the primary result;
the summary also aggregates deterministic public requirement-group completion. Treat evaluator exit
codes above 1 as infrastructure failures, never as model failures.
Every `run` command creates one experiment ID and a unique run ID per attempt. Live phase logs are
retained under `results/raw/<experiment-id>/<run-id>/`, including partial output from timed-out
containers. Default output uses prefixed phase and result lines that remain readable across
concurrent cells and harnesses. Use `--verbose` to stream raw phase output sequentially or `--json`
to emit only normalized result rows for scripts. Repeat `--task` and `--configuration` to run their
exact Cartesian product under one experiment ID; selection fails if any requested ID does not exist.

Project defaults include independent positive integer `setup_timeout_seconds` and
`evaluator_timeout_seconds` values. `solver_timeout_seconds` accepts either a positive integer or
`null`; the scaffold uses `null` so larger tasks are not censored by an arbitrary wall-clock limit.
Older v1 manifests without the setup timeout retain their old effective behavior by using the
evaluator timeout for setup too.

`validate-tasks` validates distinct tasks with bounded concurrency while preserving sequential base
and reference phases within each task. Each task validation writes a unique attempt below
`results/validation/<task-id>/` and atomically refreshes `latest.json`. Only a complete receipt with
status `validated`, passed setup in both phases, base exit 1, and reference exit 0 is success. Use
the single-task command with `--verbose` to stream raw phase output; complete logs are retained
regardless.
