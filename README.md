# Bench-this: Benchmark coding agents on your codebase

Keeping up with coding agents is a part-time job nobody asked for. Every week brings a new model,
new reasoning efforts, a new harness, and another skill to configure. By the time you have a clean
comparison, your setup is already outdated.

`bench-this` makes the comparison easy. It turns real changes from a repository's history into
behavior-focused tasks. Compare complete setups, including the model, reasoning settings, harness,
skills, MCP servers, and workspace instructions, against the same task, so you know which setup
works for your codebase.

Each run records whether the task was completed, along with token usage, duration, and costs when
available.

> For an implementation-level explanation, see the
> [technical guide](docs/implementation-guide.html). It covers the skill helpers,
> task-authoring guards, runner modules, validation model, Docker boundaries, and measured lifecycle
> in detail.

## Installation

```bash
npx skills add makefinks/bench-this
```

## Supported setups

The following harness and provider combinations are currently supported.

| Harness            | Provider or account               |
| ------------------ | --------------------------------- |
| Native Copilot CLI | GitHub Copilot                    |
| OpenCode           | OpenAI (`openai`)                 |
| OpenCode           | GitHub Copilot (`github-copilot`) |
| OpenCode           | OpenCode Zen (`opencode`)         |
| OpenCode           | OpenCode Go (`opencode-go`)       |
| OpenCode           | Amazon Bedrock (`amazon-bedrock`) |

See [configuration.md](skills/bench-this/references/configuration.md) for setup commands and
reproducibility rules.

## The idea in one minute

Suppose a project added duplicate-email detection six months ago. That change gives us two useful
points in history:

```text
base commit                         reference commit
feature does not exist              feature works
       │                                  │
       └──── choose and verify behavior ──┘
                         │
                         ▼
       author public prompt, public tests,
                    and hidden tests
                         │
                         ▼
              give an agent the task
                         │
                         ▼
          run public and hidden evaluators
```

Before comparing agents, the benchmark proves that the evaluator fails on the base commit and
passes on the reference commit. The reference is a calibration point, not a patch shown to the
agent. During a measured run, the agent sees only the base source, the public prompt, and any
deliberately public task files.

That gives the experiment a useful question:

> Starting from the same historical state, which agent configurations can recreate the requested
> behavior?

## A typical journey

Before starting, make sure the target checkout has its full Git history, Docker is running, and the
skill is available to your coding agent. Measured runs also need an account for the selected agent
harness and provider.

In normal use, **you make the decisions and the agent operates the machinery**. You choose which
candidates to approve and which treatments to compare. The agent scaffolds the benchmark, delegates
task authoring, builds the image, and proves the tasks are valid. It defers shared Dockerfile and
setup changes until all task bundles are accepted. The runner commands below remain available for
inspection, diagnosis, and automation; they are not a checklist you must perform by hand.

### 1. Choose candidates with the skill

Run the skill from the repository you want to benchmark. A good opening request is:

```text
Use the bench-this skill to find 3 benchmark task candidates in this repository.
Stop for approval after presenting them.
```

If you do not specify a count, the skill recommends five candidates; requests for more than ten
require confirmation.

The skill deeply explores older, middle, and recent repository history. It checks the worktree and
keeps discovery read-only, resolves candidate and base hashes, verifies their diff, and reads
promising tests and surrounding code rather than choosing from commit titles alone. It checks
history depth and reports shallow or otherwise limited coverage instead of implying a full-history
review. It also sketches a behavioral evaluator and probes each proposed requirement group at both
commits before recommending a candidate.

Treatment configuration is a separate choice. The skill makes it easy to generate valid
configurations just by talking to the agent and handing it references to skills or mcp servers
that you want to compare.

### 2. The agent creates a self-contained benchmark

The target repository receives a self-contained benchmark:

```text
benchmarks/
├── run.py                 # The command-line entry point
├── benchmark.yaml         # Shared image, setup, timeouts, and defaults
├── Dockerfile             # Project toolchain plus agent harnesses
├── setup.sh               # Installs dependencies in an exported workspace
├── tasks/
│   └── <task-id>/
│       ├── task.yaml
│       ├── prompt.md
│       ├── public/        # Optional solver-visible files
│       ├── public-tests/  # Required solver-visible scored checks
│       └── hidden-tests/  # Required evaluator; never shown to the solver
├── configurations/        # Model and harness treatments
├── results/               # Created by validation and measured runs
└── _vendor/               # Runner and Python dependencies
```

The runner is vendored on purpose. A generated benchmark should work without installing
runner-specific dependencies. The agent invokes it directly, and you can do the same when inspecting
or diagnosing a benchmark.

### 3. The agent proves the task is real

Before spending model tokens, the agent runs these deterministic checks:

```bash
./benchmarks/run.py validate
./benchmarks/run.py build
./benchmarks/run.py validate-tasks --jobs <n>
```

These commands answer three different questions:

1. **Is the benchmark well formed?** `validate` checks manifests, IDs, paths, and supported
   configuration values.
2. **Can the environment be reproduced?** `build` creates the shared Docker image.
3. **Does the evaluator distinguish history correctly?** `validate-tasks` prepares both historical
   revisions and requires these exact results:

   ```text
   base commit      → hidden evaluator exit 1
   reference commit → hidden evaluator exit 0
   ```

   The required public suite runs separately and must independently produce the same
   base-fail/reference-pass pair.

An import failure, missing dependency, evaluator crash, timeout, or half-written receipt is not a
valid base failure. The base must reach a genuine behavioral assertion. Full phase logs and an
atomic receipt are kept for each attempt, which makes an interrupted or flaky validation visible
instead of accidentally treating it as success.

When diagnosis is necessary, the agent can retry one task with live logs:

```bash
./benchmarks/run.py validate-task <task-id> --verbose
```

### 4. Choose treatments

A treatment is the complete agent configuration being compared: harness, provider when applicable,
pinned model, harness settings, workspace overlay, and authentication profile.

You provide the comparison you care about—or approve a concrete recommendation after task
validation—and the agent uses the bundled generator to avoid hand-written configuration mistakes.
The equivalent command for an OpenCode treatment is:

```bash
python <skill-directory>/scripts/configure.py <target-repository> \
  --harness opencode \
  --provider <provider> \
  --model <pinned-model> \
  --auth-profile <profile>
```

For native Copilot CLI, the agent omits the provider:

```bash
python <skill-directory>/scripts/configure.py <target-repository> \
  --harness copilot \
  --model <pinned-model> \
  --auth-profile <profile>
```

Amazon Bedrock treatments require `--provider amazon-bedrock` and an explicit
`--bedrock-region`. Their API key uses a runner-managed profile rather than OpenCode's interactive
login:

```bash
python <skill-directory>/scripts/configure.py <target-repository> \
  --harness opencode \
  --provider amazon-bedrock \
  --bedrock-region <aws-region> \
  --model <pinned-bedrock-model-id> \
  --auth-profile <profile>
```

Copilot Business accounts used through OpenCode require the dedicated
`--github-copilot-business` flag. The generator then writes the fixed Business API endpoint into the
treatment's OpenCode configuration; it does not accept an arbitrary base URL. A profile name such
as `copilot-auth` alone does not select native Copilot CLI, the OpenCode provider, or the Business
subscription.

Skills, MCP servers, reasoning settings, and workspace instructions belong in separate treatment
variants. Keeping the baseline plain makes any change in correctness, cost, or runtime attributable
to the thing being tested.

See [configuration.md](skills/bench-this/references/configuration.md) for supported
harnesses, providers, overlays, and reproducibility rules.

### 5. Authenticate, then ask the agent to run

Authentication is the one intentionally user-facing setup step because it may require a browser or
device flow, or a provider token. Profiles live outside the target repository under
`~/.agent-bench/auth/`, and login happens without project source mounted:

```bash
./benchmarks/run.py auth login \
  --harness opencode --provider <provider> --profile <profile>

# Or, for native Copilot CLI:
./benchmarks/run.py auth login --harness copilot --profile <profile>

# Manual Amazon Bedrock setup; the user runs this in their own terminal.
./benchmarks/run.py auth login \
  --harness opencode --provider amazon-bedrock --profile <profile>
```

The agent checks for the exact benchmark profile only after an approved treatment identifies the
required harness, provider, and profile. An existing benchmark profile is reused. The runner never
silently imports the user's normal Copilot, OpenCode, GitHub CLI, browser, or home-directory
credentials. If the profile is missing, the agent offers to start the appropriate setup or gives you
the same command to run yourself. You personally complete browser or device authorization. For
agent-assisted Bedrock setup, the agent asks for the token first and uses the bundled
non-interactive
provisioning helper. The `auth login` command above
is the manual alternative. In either path, the runner injects the stored token as
`AWS_BEARER_TOKEN_BEDROCK` and never writes it into treatment files.

After login, you or the agent verify the matching profile and harness before running a treatment:

```bash
./benchmarks/run.py auth verify --harness <harness> --profile <profile>
```

Once authentication is ready, ask the agent to run the selected treatment or matrix. It checks
Docker, the image, profiles, and pinned model identity first:

```bash
./benchmarks/run.py doctor
```

The agent uses the same public CLI shown here. You can also invoke it directly for automation or
hands-on experiments:

```bash
# One task and one treatment
./benchmarks/run.py run \
  --task <task-id> \
  --configuration <configuration-id>

# Every configured task/treatment pair, repeated three times
./benchmarks/run.py run --repetitions 3

# An explicit subset with more parallel workers
./benchmarks/run.py run \
  --task <task-a> --task <task-b> \
  --configuration <configuration-a> --configuration <configuration-b> \
  --jobs 5
```

The default output keeps concurrent cells readable. Add `--verbose` for raw sequential phase output,
or `--json` for normalized JSONL rows suitable for scripts.

## What makes a good task?

A benchmark task should feel like a compact piece of real engineering work, not a trivia question
about a historical diff.

Strong tasks usually have:

- a stable public entry point;
- several substantive behaviors that can fail independently;
- a base commit before the behavior exists and a reference commit where it works;
- deterministic inputs and observable outputs, errors, events, artifacts, or state changes; and
- enough repository context that simply transcribing the prompt is not a plausible solution.

Suitable tasks normally have at least four substantive requirement groups that can fail
independently; many assertions around one helper do not establish task scale.

The historical patch is evidence that the behavior is possible. It is not the specification. A
solver may implement the behavior differently and should still pass.

Prompts therefore describe the public contract, while evaluators exercise that contract through
real public boundaries. They do not inspect product source, demand the historical algorithm, call
new private helpers directly, or hide required output structure that a solver could not infer from
the prompt.

Each task divides its contract into **requirement groups**: meaningful outcomes such as “reject a
duplicate” or “preserve the existing record.” The evaluator reports one boolean per group. A task
still passes only when every group passes, while the grouped result makes partial progress
interpretable without awarding extra credit for a pile of similar assertions.

Every task provides a compact public test suite in addition to its hidden evaluator. The solver can
inspect and run a writable copy, while evaluation executes the unchanged task-owned source from a
separate read-only mount. Public checks sample representative behavior; hidden checks use different
inputs, combinations, and edge conditions. Results report public, hidden, and combined completion
separately, plus a neutral flag when the solver's final workspace changed or deleted supplied public
test files.

Both suites declare their own result IDs and must independently pass the base-fail/reference-pass
check. Review also audits full disclosure, implementation recipes, the assertion ledger, and
independent failure boundaries so one failed group cannot suppress the others. The detailed gates
live in [task-quality.md](skills/bench-this/references/task-quality.md).

## Why the deterministic checks are so strict

Coding-agent runs are already variable. The benchmark should not add avoidable uncertainty of its
own.

### History provides the control

The same evaluator runs against the base and reference commits. Requiring base-fail/reference-pass
catches tasks that were already solved, reference revisions that no longer work, and evaluators that
test the wrong thing.

### Behavior matters; code shape does not

The hidden evaluator observes returned values, exceptions, emitted events, generated artifacts, or
persisted state. This leaves room for a novel correct solution while rejecting patches that only add
the expected symbol or mimic an internal implementation detail.

### Task acceptance is guarded

Task agents author in isolated scratch workspaces. A repeatable, read-only workspace check catches
incomplete manifests, evaluator protocol mistakes, forbidden techniques, and integrity drift before
integration. The task agent runs it before handoff and the coordinator reruns it after review
corrections. Shared Dockerfile and setup changes wait until all bundles pass this review. Only then
does the coordinator make the one-shot acceptance attempt that atomically copies the reviewed task
into the benchmark.

## Docker without the mystery

The Docker image is the benchmark's portable laboratory. It has two jobs:

1. provide the historical project's runtimes, native libraries, package managers, and test tools;
2. provide the pinned coding-agent harness used by measured treatments.

The scaffold starts with a Debian-based image containing common tooling and pinned harness CLIs.
Benchmark authors extend it for the target project instead of replacing one half of the laboratory.
There is one shared image and one `setup.sh` for a v1 benchmark, so every task is measured in the
same environment.

`setup.sh` receives the exported project at `/workspace`. It installs dependencies with network
access before validation and before the solver in measured runs, and it must work at every task's
base and reference commit. After solving, the runner copies the candidate into a separate evaluator
workspace and runs `setup.sh` there again. Evaluation then runs without network access.

The generated image name includes a digest of the target checkout's absolute path. Two clones with
the same repository name therefore do not quietly overwrite each other's benchmark image.

For the full setup checklist, see
[setup.md](skills/bench-this/references/setup.md).

## What can see what?

Isolation is part of the experiment, not just a security bonus.

| Resource               | Solver        | Evaluator          | Reason                                              |
| ---------------------- | ------------- | ------------------ | --------------------------------------------------- |
| Project workspace      | Read/write    | Separate copy      | The evaluator setup cannot be changed by the solver |
| `.git` history         | No            | No                 | Prevents recovery of the historical solution        |
| Benchmark manifests    | No            | No                 | Keeps task metadata out of the workspace            |
| Public task files      | Yes           | Through workspace  | Supplies intentional fixtures or instructions       |
| Public tests           | Writable copy | Read-only original | Supports iteration without trusting edited tests    |
| Hidden evaluator       | No            | Read-only          | Prevents test-aware patching                        |
| Temporary auth profile | Yes           | No                 | Lets the harness call its provider                  |
| Network                | Yes           | No                 | The solver needs its provider; evaluation does not  |

Before source is mounted, the runner also performs a source-free identity preflight in an empty
workspace. Authentication must succeed and the harness must report the configured model (and, for
OpenCode, provider). A silent fallback fails before the model sees the project.

During solver execution, the container receives an explicit environment allowlist, no Docker
socket, dropped Linux capabilities, and a disposable home. Evaluation is a separate container
invocation with hidden tests mounted read-only, no credentials, and `--network none`.

## Reading the results

Runs are stored under `benchmarks/results/`:

```text
results/
├── runs.jsonl                         # Append-only normalized rows
├── summary.md                         # Append-only human-readable experiment summaries
├── raw/<experiment-id>/<run-id>/      # Measured-run phase logs
├── validation/<task-id>/<attempt-id>/ # Validation receipt and phase logs
└── auth/<configuration-id>/           # Explicit identity-check logs
```

Each completed experiment section contains both a configuration-level comparison and a per-task
breakdown with scores, token usage, cost, solver time, runtime, and failure reason.

Failures are kept distinct so an agent is not blamed for a broken laboratory:

- **incorrect**: the solver finished normally, but at least one requirement group failed;
- **candidate**: the submitted workspace no longer imports or compiles;
- **solver**: the solver process itself exited unsuccessfully;
- **infrastructure and phase failures**: setup, authentication, model identity, Docker, evaluator
  errors, timeouts, and quota failures remain identifiable rather than becoming wrong answers.

The summary reports pass rate, public and hidden completion, their combined total, public-test
mutation telemetry, total/input/cached-input/output/reasoning tokens, cache hit rate when cached
input is present, solver and total runtime, costs when known, and failure counts. Provider-reported cost remains
separate from locally estimated cost. The runner uses benchmark-defined `prices` first, then falls
back to the live [Models.dev](https://models.dev/) provider catalog. Native Copilot CLI runs export
content-free OpenTelemetry so cache and reasoning token buckets can contribute to this
API-equivalent
estimate; Copilot AI credits are not mislabeled as USD. A catalog outage or missing price leaves the
estimate blank rather than failing a run. Hidden completion remains the primary correctness signal;
the public/hidden split shows whether a solver generalized beyond visible examples. Per-phase
durations in run rows and base/reference validation receipts support debugging setup, solver, and
evaluator performance.

## Where the detailed contracts live

- [SKILL.md](skills/bench-this/SKILL.md) — the complete authoring workflow and policy
- [task-quality.md](skills/bench-this/references/task-quality.md) — candidate,
  prompt, and evaluator quality gates
- [setup.md](skills/bench-this/references/setup.md) — Docker and project setup
- [formats.md](skills/bench-this/references/formats.md) — YAML formats, evaluator
  protocol, and command reference
- [configuration.md](skills/bench-this/references/configuration.md) — treatments,
  authentication, and overlays
- [reasoning-effort.md](skills/bench-this/references/reasoning-effort.md) —
  harness-specific reasoning controls
- [task-agent.md](skills/bench-this/references/task-agent.md) — worker isolation and
  task-authoring handoff contract
- [task-verifier.md](skills/bench-this/references/task-verifier.md) — narrow read-only
  contract and evaluator verification pass

## Developing this repository

`src/agent_bench/` is the canonical runner source. The skill ships synchronized runner and scaffold
assets under `skills/bench-this/assets/benchmarks/` so generated repositories do not depend on this
checkout. After changing runner behavior, update the canonical source first; the synchronization
script refreshes both the vendored runner and scaffold assets.

The rest of the repository is intentionally small:

```text
.
├── src/agent_bench/                  # Runner package
├── tests/                            # Unit and Docker integration tests
├── scripts/
│   ├── create_synthetic_fixture.py   # Two-commit smoke-test project
│   ├── format_markdown.py            # Repository Markdown formatter
│   └── sync_vendored_runner.py       # Refreshes runner and scaffold assets
└── skills/bench-this/               # Skill, references, helpers, and scaffold
```

Run the test suite from the repository root:

```bash
PYTHONPATH=src:. uv run --extra test pytest
```

Format and verify Markdown before handing back changes:

```bash
python3 scripts/format_markdown.py
python3 scripts/format_markdown.py --check
```

After changing runner behavior, synchronize and verify the vendored runner and scaffold assets:

```bash
python3 scripts/sync_vendored_runner.py
python3 scripts/sync_vendored_runner.py --check
```

For a disposable end-to-end smoke-test repository:

```bash
python3 scripts/create_synthetic_fixture.py --help
```

Most tests use fake Docker implementations to cover ordering, mounts, isolation, reporting, and
failure classification quickly. Docker integration tests cover the smaller set of behavior that
needs a real daemon and image.
