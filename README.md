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

`bench-this` supports these harness and provider combinations:

| Harness            | GitHub Copilot (`github-copilot`) | OpenAI Codex (`openai-codex`) | OpenCode Zen (`opencode`) | OpenCode Go (`opencode-go`) | Amazon Bedrock (`amazon-bedrock`) |
| ------------------ | --------------------------------- | ----------------------------- | ------------------------- | --------------------------- | --------------------------------- |
| Native Copilot CLI | ✓                                 |                               |                           |                             | ✓                                 |
| OpenCode           | ✓                                 | ✓                             | ✓                         | ✓                           | ✓                                 |
| Oh My Pi           | ✓                                 | ✓                             |                           |                             | ✓                                 |
| Pi                 | ✓                                 | ✓                             |                           |                             | ✓                                 |

Native Copilot CLI uses your GitHub Copilot account when the provider is omitted. Its Amazon Bedrock
integration uses Copilot BYOK with the regional Bedrock Mantle Chat Completions endpoint.

See [configuration.md](skills/bench-this/references/configuration.md) for setup commands and
reproducibility rules. Contributions that add another harness or provider are greatly appreciated.

## The idea in one minute

Suppose a project added duplicate-email detection six months ago. That change gives us two useful
points in history:

```text
base commit                         reference commit
feature does not exist              feature works
       │                                  │
       └── find: probe behavior at both ──┘
           ends, shortlist candidates,
           and stop for your approval
                          │
                          ▼
     approve: you choose which candidates become
     tasks; one coordinator agent runs the rest
                          │
                          ▼
     prepare: the coordinator builds a separate scratch
     workspace for each approved task
                          │
                          ▼
     task agents × N work in parallel; each authors a
     prompt plus public and hidden test suites, organized
     into independently evaluated requirement groups
                          │
                          ▼
     verifier agents × N work in parallel; each checks
     one bundle without editing it
                          │
                          ▼
     review: the coordinator reads every bundle,
     fixes what it can, and accepts each task once
                          │
                          ▼
     build: the coordinator combines shared setup needs
     and proves the benchmark's Docker image builds
                          │
                          ▼
     validate: each task's public and hidden tests run
     against both commits; both suites must fail on the
     base for the requested behavior and pass on reference
                          │
                          ▼
     configure: define benchmark treatments or tell the agent
     which setups you want to test and compare
                          │
                          ▼
     run: evaluate each configured task/treatment pair in
     an isolated container. The solver receives the public
     prompt, public tests, and a writable base-commit workspace.
     Git history, authenticated host CLIs, and hidden tests
     remain inaccessible
                          │
                          ▼
     compare: inspect results by configuration and task,
     including pass rate, token usage, cost, runtime,
     and failure reasons

```

The reference commit calibrates the evaluator; solver agents never see its patch.

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

The skill explores older, middle, and recent repository history. It checks the worktree and
keeps discovery read-only, resolves candidate and base hashes, verifies their diff, and reads
promising tests and surrounding code rather than choosing from commit titles alone. It checks
history depth and reports shallow or otherwise limited coverage instead of implying a full-history
review. It also sketches a behavioral evaluator and probes each proposed requirement group at both
commits before recommending a candidate.

Treatment configuration is a separate choice. The skill makes it easy to generate valid
configurations just by talking to the agent and handing it references to skills or MCP servers
that you want to compare.

### 2. The agent creates a self-contained benchmark

The target repository receives a self-contained benchmark:

```text
benchmarks/
├── run.py                 # The command-line entry point
├── benchmark.yaml         # Shared image, setup, timeouts, and defaults
├── Dockerfile             # Project toolchain plus selected agent harnesses
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

`run.py build` renders the Dockerfile's harness-install block from the configured treatments. Only
the selected harness CLIs are installed; task validation itself does not require an agent CLI.

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
valid base failure. The base must reach a genuine behavioral assertion. Every attempt keeps full
phase logs and an atomic receipt, so an interrupted or flaky validation shows up instead of
quietly counting as success.

When diagnosis is necessary, the agent can retry one task with live logs:

```bash
./benchmarks/run.py validate-task <task-id> --verbose
```

### 4. Choose treatments

A treatment is the complete agent configuration being compared: harness, provider when applicable,
selected model, harness settings, workspace overlay, and authentication profile.

You provide the comparison you care about, or you approve a concrete recommendation after task
validation. The equivalent command for an OpenCode
treatment is:

```bash
python <skill-directory>/scripts/configure.py <target-repository> \
  --harness opencode \
  --provider <provider> \
  --model <pinned-model> \
  --auth-profile <profile>
```

For native Copilot CLI with a GitHub Copilot account, the agent omits the provider:

```bash
python <skill-directory>/scripts/configure.py <target-repository> \
  --harness copilot \
  --model <pinned-model> \
  --auth-profile <profile>
```

Copilot CLI also accepts `--provider amazon-bedrock` with the Bedrock fields below.

For Pi, the agent sets the explicit provider:

```bash
python <skill-directory>/scripts/configure.py <target-repository> \
  --harness pi \
  --provider openai-codex \
  --model <pinned-model> \
  --auth-profile <profile>
```

Amazon Bedrock treatments require `--provider amazon-bedrock` and an explicit
`--bedrock-region`. OpenCode, Oh My Pi, and Pi use runner-managed bearer-token profiles:

```bash
python <skill-directory>/scripts/configure.py <target-repository> \
  --harness opencode \
  --provider amazon-bedrock \
  --bedrock-region <aws-region> \
  --model <pinned-bedrock-model-id> \
  --auth-profile <profile>
```

Use `--harness copilot`, `--harness omp`, or `--harness pi` with the same provider, region, model,
and profile fields for those Bedrock treatments. Copilot CLI routes models that support streaming,
tool calling, and Mantle Chat Completions through the regional `/v1` endpoint.

Copilot Business accounts used through OpenCode require the dedicated
`--github-copilot-business` flag. The generator then writes the fixed Business API endpoint into the
treatment's OpenCode configuration; it does not accept an arbitrary base URL. A profile name such
as `copilot-auth` alone does not select native Copilot CLI, the OpenCode provider, or the Business
subscription.

Every treatment requires a pinned model.

Skills, MCP servers, reasoning settings, and workspace instructions belong in separate treatment
variants. Keeping the baseline plain makes any change in correctness, cost, or runtime attributable
to the thing being tested. OMP uses its first-party MCP client. Pi has no built-in MCP, so its MCP
treatments use a compatible pinned adapter through Pi's package system.

See [configuration.md](skills/bench-this/references/configuration.md) for supported
harnesses, providers, overlays, and reproducibility rules.

### 5. Authenticate, then ask the agent to run

Authentication is the one intentionally user-facing setup step because it may require a browser or
device flow, a provider token, or AWS credentials. Profiles live outside the target repository under
`~/.agent-bench/auth/`, and login happens without project source mounted:

```bash
./benchmarks/run.py auth login \
  --harness opencode --provider <provider> --profile <profile>

# Or, for native Copilot CLI:
./benchmarks/run.py auth login --harness copilot --profile <profile>

# Pi and Oh My Pi use the same containerized CLI boundary.
./benchmarks/run.py auth login \
  --harness pi --provider openai-codex --profile <profile>

# Manual Amazon Bedrock setup; the user runs this in their own terminal.
./benchmarks/run.py auth login \
  --harness copilot --provider amazon-bedrock --profile <profile>
```

The agent checks for the exact benchmark profile only after an approved treatment identifies the
required harness, provider, and profile. An existing benchmark profile is reused. The runner never
silently imports the user's normal Copilot, OpenCode, Pi, GitHub CLI, browser, AWS, or
home-directory
credentials. If the profile is missing, the agent gives you the exact `auth login` command to run
in a real terminal and tells you to choose the CLI's headless or device-code option. Browser or
localhost-callback options cannot return to the isolated container. A device-code URL may still be
opened in your host browser.

The non-interactive Bedrock helper accepts credentials only through its process environment. The
helper reads `AGENT_BENCH_BEDROCK_API_KEY` and stores one harness-scoped profile. OpenCode, OMP,
and Pi inject it as `AWS_BEARER_TOKEN_BEDROCK`; Copilot CLI injects it as
`COPILOT_PROVIDER_API_KEY`. Credentials are never written into treatment files.

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

Each task divides its contract into **requirement groups**: meaningful outcomes such as "reject a
duplicate" or "preserve the existing record." The evaluator reports one boolean per group. A task
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

### Isolated authoring, checked twice

Task agents author in isolated scratch workspaces. A repeatable, read-only workspace check catches
incomplete manifests, evaluator protocol mistakes, forbidden techniques, and integrity drift before
integration. The task agent runs it before handoff and the coordinator reruns it after review
corrections. Shared Dockerfile and setup changes wait until all bundles pass this review. Only then
does the coordinator make the one-shot acceptance attempt that atomically copies the reviewed task
into the benchmark.

## Docker without the mystery

The Docker image has two jobs:

1. provide the historical project's runtimes, native libraries, package managers, and test tools;
2. provide the pinned coding-agent harness used by measured treatments.

The scaffold starts with a Debian-based image containing common tooling and pinned harness CLIs.
Benchmark authors extend it for the target project rather than replacing it.
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

Isolation protects the measurement first and your machine second.

| Resource               | Solver        | Evaluator          | Reason                                             |
| ---------------------- | ------------- | ------------------ | -------------------------------------------------- |
| Project workspace      | Read/write    | Separate copy      | The solver cannot change the evaluator's setup     |
| `.git` history         | No            | No                 | Prevents recovery of the historical solution       |
| Benchmark manifests    | No            | No                 | Keeps task metadata out of the workspace           |
| Public task files      | Yes           | Through workspace  | Supplies intentional fixtures or instructions      |
| Public tests           | Writable copy | Read-only original | Supports iteration without trusting edited tests   |
| Hidden evaluator       | No            | Read-only          | Prevents test-aware patching                       |
| Temporary auth profile | Yes           | No                 | Lets the harness call its provider                 |
| Network                | Yes           | No                 | The solver needs its provider; evaluation does not |

Before source is mounted, the runner also performs a source-free identity preflight in an empty
workspace. Authentication must succeed and the harness must report the configured model (and, for
OpenCode, provider). A silent fallback fails before the model sees the project.

During solver execution, the container receives an explicit environment allowlist, no Docker
socket, dropped Linux capabilities, and a disposable home. Evaluation is a separate container
invocation with hidden tests mounted read-only, no credentials, and `--network none`.

## Reading the results

Results live under `benchmarks/results/`:

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

The runner keeps failure kinds distinct so a broken environment never counts as a wrong answer:

- **incorrect**: the solver finished normally, but at least one requirement group failed;
- **candidate**: the submitted workspace no longer imports or compiles;
- **solver**: the solver process itself exited unsuccessfully;
- **infrastructure and phase failures**: setup, authentication, model identity, Docker, evaluator
  errors, timeouts, and quota failures remain identifiable rather than becoming wrong answers.

The summary reports:

- pass rate and public, hidden, and combined completion;
- public-test mutation telemetry;
- main-session turn averages;
- total, input, cached-input, cache-write, output, and reasoning tokens;
- cache hit rate when cached input is present;
- solver and total runtime;
- native and estimated costs when known;
- failure counts.

Turn metrics have these semantics:

- **Turns** count completed model cycles in the harness's main solver session. Delegated or
  subagent activity is excluded.
- **Averages** use successful runs only. An em dash means the count is unavailable.

Provider-reported cost remains separate from locally estimated cost. The runner uses
benchmark-defined `prices` first, then falls back to the live
[Models.dev](https://models.dev/) provider catalog. Native Copilot CLI runs export content-free
OpenTelemetry so cache and reasoning token buckets can contribute to this API-equivalent estimate;
Copilot AI credits are not mislabeled as USD. A catalog outage or missing price leaves the estimate
blank rather than failing a run. Hidden completion remains the primary correctness signal; the
public/hidden split shows whether a solver generalized beyond visible examples. Per-phase durations
in run rows and base/reference validation receipts support debugging setup, solver, and evaluator
performance.

## Where the detailed contracts live

- [SKILL.md](skills/bench-this/SKILL.md) covers the complete authoring workflow and policy
- [task-quality.md](skills/bench-this/references/task-quality.md) defines candidate,
  prompt, and evaluator quality gates
- [setup.md](skills/bench-this/references/setup.md) explains Docker and project setup
- [formats.md](skills/bench-this/references/formats.md) specifies YAML formats, the
  evaluator protocol, and commands
- [configuration.md](skills/bench-this/references/configuration.md) documents treatments,
  authentication, and overlays
- [reasoning-effort.md](skills/bench-this/references/configuration/treatments/reasoning-effort.md)
  describes reasoning-effort treatment policy and harness-specific controls
- [task-agent.md](skills/bench-this/references/task-agent.md) specifies worker isolation
  and the task-authoring handoff contract
- [task-verifier.md](skills/bench-this/references/task-verifier.md) defines the narrow
  read-only contract and the evaluator verification pass

## Developing this repository

`src/agent_bench/` is the canonical runner source. The skill ships synchronized runner and scaffold
assets under `skills/bench-this/assets/benchmarks/` so generated repositories do not depend on this
checkout. After changing runner behavior, update the canonical source first; the synchronization
script refreshes both the vendored runner and scaffold assets.

The rest of the repository is intentionally small:

```text
.
├── src/agent_bench/                  # Runner package
├── tests/                            # Unit, fixture, and Docker integration tests
│   └── fixtures/full-flow-taskbox/   # Reviewable six-commit E2E project history
├── scripts/
│   ├── create_full_flow_fixture.py   # Ready-to-run internal E2E target
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

Create a disposable target for the agent-driven full-flow E2E workflow:

```bash
python3 scripts/create_full_flow_fixture.py
```

The command prints the retained repository path, six commit IDs, and installed skill path as JSON.
It creates Taskbox source history and installs the current skill without committing it. The E2E
skill
then performs discovery, benchmark authoring, treatment configuration, authentication verification,
execution, and telemetry inspection.

Most tests use fake Docker implementations to cover ordering, mounts, isolation, reporting, and
failure classification. Docker integration tests cover the smaller set of behavior that needs a
real daemon and image.
