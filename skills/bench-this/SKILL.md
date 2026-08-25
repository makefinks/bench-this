---
name: bench-this
description: >-
  Create fair project-specific coding-agent benchmark tasks from historical pull requests and
  validate them with the bundled v1 runner. Use when selecting substantial deterministic changes,
  authoring behavior-focused prompts and hidden evaluators, scaffolding benchmark files, or
  validating base-fail/reference-pass tasks for Copilot CLI, OpenCode, Oh My Pi, and Pi comparisons
  using GitHub Copilot, OpenAI, OpenAI Codex, OpenCode Zen, OpenCode Go, or Amazon Bedrock
  authentication.
---

# Create a project benchmark

You are responsible for creating fair, project-specific benchmark tasks for the repository the user
placed in scope. First discover and verify candidate tasks, then stop for approval. After approval,
create each task with the bundled scaffold and workspace tools and validate that it fails
behaviorally at the base commit and passes at the reference commit.

Use judgment for candidate selection, prompt design, and evaluator design. Keep scaffolding,
isolation, integration, and validation deterministic by using the bundled tools.

## Workflow

Act as the coordinator throughout this workflow. You own discovery, approval, scaffolding, shared
setup, integration, validation, and treatment configuration. Delegate the authoring of each
independent approved task to its own task agent.

### 1. Discover candidates

1. Use the positive candidate count requested by the user; otherwise recommend 5 candidates. If the
   user requests more than 10, confirm the unusually large scope before continuing.
2. Inspect `git status` and record existing changes. Keep the worktree read-only during discovery:
   never stash, reset, clean, checkout, or modify files. Export a commit with `git archive` when a
   clean historical tree is necessary.
3. Read [references/task-quality.md](references/task-quality.md). Confirm Docker and the project's
   normal test tool are available. Perform a deep exploration of local first-parent history across
   the repository's lifespan, including older, middle, and recent changes, before narrowing the
   list. A commit-title scan is not sufficient: inspect representative diffs and changed tests in
   each part of history, then follow promising changes into their surrounding code and related
   commits. Compare multiple plausible changes before choosing the recommendations. Check whether
   the repository is shallow and do not claim full-history coverage when history is incomplete.
   Inspect merged pull requests with local Git plus `gh` or a connected GitHub tool.
   Paginate remote results when they supplement local Git; a default or numeric page limit is not
   full-history coverage. If the repository has no merged pull requests, use self-contained commits
   with their parent as `base_commit`. Before
   presenting any commit candidate, resolve its full
   reference and base hashes with `git rev-parse <reference> <reference>^`, then inspect
   `git diff --stat <base> <reference>`. Do not infer ancestry from log order, nearby releases, or
   memory; reject a candidate whose resolved diff is not the behavior being described. Inspect the
   relevant public path at both commits and separate behavior introduced by the change from behavior
   that already existed at the base. Candidate scope may require preserving existing behavior, but
   must not describe that behavior as newly added. Verify proposed evaluator runtimes, test helpers,
   package export paths, and public entry points against the dependency manifests or trees at both
   commits; availability at the current `HEAD` does not prove that a historical evaluator can run.
   Map each candidate into substantive public requirement groups as defined by the quality
   reference. Reject candidates whose apparent scale is only many tests or edge cases around one
   localized edit. Count observable outcomes rather than helpers, constants, registries, constructor
   choices, parameter-forwarding steps, or repeated edits across equivalent call sites. Sketch the
   evaluator seam before recommending the candidate: name the public entry point, the real
   dependencies available at both commits, and each focused fake required. For each proposed
   requirement group, state a plausible partial implementation that passes the other groups while
   failing this one. Collapse groups when that counterexample changes only an internal mechanism,
   constructor activation, error wording, or a branch of the same localized operation. Reject the
   candidate if the sketch needs product-source or AST inspection, `sys.modules` injection,
   synthetic package trees, or broad SDK/application reconstruction.
   Do not reject a documented new public API merely because the base raises `AttributeError` or
   `TypeError`. That is a valid functional base failure when the evaluator catches it and records a
   failed behavior check. An infrastructure failure means the evaluator itself cannot import, set
   up, or run. Keep evaluator module imports base-compatible; access reference-only product symbols
   dynamically or through an enclosing public entry point.
   A reference probe must call the proposed public entry point and observe its return value,
   exception, emitted events, or persisted state. Import success, `hasattr`, signature inspection,
   dataclass-field inspection, or direct calls to a new helper are structural evidence only and
   cannot establish a requirement group without an end-to-end behavioral observation. Record a
   probe evidence row for every proposed group with the public invocation, concrete base
   observation, concrete reference observation, and whether the evaluator can distinguish them.
   Reject or collapse any row whose observation is only that a symbol, parameter, field, constant,
   or helper exists.
4. Present exactly the requested number of recommended candidates. For each, give its PR or commit
   identifier and title, verified base identifier, observable behavior, approximate scope,
   substantive requirement groups, evaluator boundaries, setup needs, and difficulty evidence from
   the quality reference. Explain why the groups can fail independently, include the partial
   implementation counterexamples, and explain why one localized edit cannot satisfy nearly all of
   them. Briefly describe the history ranges and sources inspected. Never claim broader coverage
   than this evidence supports. Mention
   which surrounding behaviors are compatibility constraints rather than new requirements. Mention
   alternates only when a recommended candidate has a meaningful tradeoff.
5. Stop and wait for explicit approval. Do not scaffold or create benchmark files before approval.

### 2. Create the approved benchmark

1. After the user approves the candidates, do not repeat discovery, shrink the approved requirement
   groups into a smaller task, or expand the task with unrelated historical changes. Treat the
   approved observable behavior, requirement groups, and evaluator boundaries as the complete task
   scope. Preserve their names and meaning verbatim through the worker handoff and pre-accept
   decision. A helper, constant, stored attribute, algorithm, or adjacent behavior found in the
   historical patch is not a new requirement group and cannot be promoted by calling it public.
   The reference commit is evidence, not a requirement to benchmark every change it contains. If
   `benchmarks/` is absent, immediately run
   `python <skill-directory>/scripts/scaffold.py
   <repository>` using the base directory reported by the skill loader. Confirm the generated runner
   and templates exist; do not recreate or hand-copy scaffold internals.
2. Remove only scaffold-owned examples whose IDs and contents match the scaffold. Treat every other
   existing task, configuration, or result as user data: preserve it unless the user explicitly
   approves replacement. Read [references/setup.md](references/setup.md) and keep the scaffold
   Dockerfile as a provisional base containing the harnesses and generally useful runtimes. Do not
   try to predict every task's dependency needs before delegation.
3. Read [references/task-agent.md](references/task-agent.md),
   [references/task-quality.md](references/task-quality.md), and
   [references/formats.md](references/formats.md). Resolve only the approved task ID and exact base
   and reference commits, then immediately run
   `python <skill-directory>/scripts/task_workspace.py prepare <repository> <task-id> <base>
   <reference>`
   using the skill loader's absolute base directory. Do not create a private repository or scratch
   directory with `git archive`, `git clone`, `mkdir`, `cp`, or another substitute; the helper owns
   workspace isolation and prints the only authoring repository, base/reference validation
   repositories, output, and scratch paths allowed in the handoff. It also creates the assigned
   task's mechanical manifest, empty prompt, `public/`, `public-tests/run.sh`, and
   `hidden-tests/run.sh` skeletons. Both test suites are mandatory for every task authored by this
   skill. The
   authoring repository contains helper-owned untracked infrastructure and must never be switched,
   stashed, or cleaned; task agents use only the prepared validation repositories for historical
   checks. The helper verifies that reference descends from base and rejects reversed or unrelated
   commits before creating scratch state. If preparation fails, diagnose the
   supplied identities; never swap arguments speculatively or fall back to parallel writes in the
   target. Complete each `prepare` command before starting the next; never issue multiple `prepare`
   tool calls in one assistant step or run them concurrently.
4. Spawn a task agent after preparing its workspace. Do not author the initial prompt, public
   content, public tests, or evaluator yourself; the workspace helper owns only the mechanical
   skeleton. If you
   cannot delegate tasks, stop and report that task authoring cannot continue. Do not silently
   switch to direct authoring. For every task-agent spawn, copy the handoff template from
   [references/task-agent.md](references/task-agent.md) verbatim. Replace only its angle-bracket
   placeholders and `...` task-context values. Do not summarize, paraphrase, or omit any part of the
   template, and do not assume the task agent inherited this skill's context. Use the skill loader's
   absolute base directory in every reference path. The handoff's leaf-role restriction is
   mandatory: each task agent must not load this skill, delegate again, scaffold, or run the
   workspace's mutating `prepare`, `accept`, or `discard` commands. The repeatable, read-only
   `check`
   command is the only workspace helper it may run. After all task workspaces are prepared, launch
   one task agent for each approved task concurrently. Start every task agent before waiting for any
   task agent to finish. Then wait for all task agents and collect their reports, but do not modify
   or accept any bundle yet.
5. Run exactly one independent, read-only verification pass for every authored task before doing the
   coordinator review. Read [references/task-verifier.md](references/task-verifier.md), then spawn
   one verifier agent per task using its handoff template verbatim and replacing only the named
   placeholders and task-context values. The verifier has a narrow role: detect unsupported scored
   API details, verdict-affecting setup or cleanup, result-group control-flow suppression, and
   public/hidden disclosure problems. It must not edit files, inspect history or the reference
   implementation, run lifecycle commands, or delegate. Start every task verifier before waiting
   for any verifier to finish. Do not spawn separate specialist verifiers or a routine follow-up
   verification pass. The coordinator owns all corrections after this single pass.

   Before accepting a bundle, read every file in it, the task agent's report, and its verifier
   report. Treat every verifier `BLOCK` finding as mandatory: either make a contained correction in
   the assigned scratch bundle and record how the finding was resolved, or reject the task when the
   correction requires fundamental re-scoping. A verifier `PASS` does not replace the coordinator's
   own review. Write a concise pre-accept decision containing an exact approved-scope diff, the
   public entry point, the
   disposition of every requirement group, the focused fakes used, and the result of a
   forbidden-technique scan across all evaluator files. Copy the approved groups without renaming,
   splitting, or adding to them, then map every prompt requirement and evaluator section back to
   exactly one approved group. Require a Markdown section headed by the exact group ID for every
   group, and ensure contextual prose outside those sections introduces no normative requirement.
   Remove any unmatched item before acceptance. The scan must explicitly
   cover product-source inspection, AST assertions about product
   implementation, `sys.modules` mutation, synthetic module/package trees, private call structure,
   and broad provider or framework mocks. Any finding rejects the bundle; a worker report or passing
   base/reference result cannot waive it. Apply the quality reference's full-disclosure test, recipe
   audit, and assertion-ledger audit. Require every
   observable evaluator assertion to derive from an explicit prompt requirement, preserved public
   behavior, or a private case exercising one of those requirements. Reject tasks that are
   mechanically solvable from the prompt, depend mainly on a missing import, or omit important
   success, boundary, or compatibility behavior. Reject a prompt that reads like an implementation
   recipe or a copy of the evaluator matrix. Reject exact hidden requirements for response nesting,
   field placement, markup tags, ordering, punctuation, casing, or wording unless the prompt or an
   explicit compatibility requirement makes them public. Reject an evaluator that copies hidden
   source into the workspace. If fair disclosure itself makes the task mechanical, return to
   discovery instead of making the prompt vague. Review the completed tasks together for accidental
   duplication or an overly narrow set as part of this same review. Verify that each approved
   requirement group remains independently represented in the prompt, evaluator, and assertion
   ledger. Confirm `task.yaml` declares the exact approved group IDs and the evaluator emits one
   structured boolean result for each without weighting groups by assertion count. Inspect the
   public and hidden evaluator control flow, not just the final result maps. Require every declared
   result group to have its own `try`/`catch`, test case, or equivalent failure boundary, and reject
   any shared block where one assertion failure, exception, or early return can prevent later groups
   from executing. Confirm each group has independent fixture setup or that shared state remains
   valid after any earlier group fails. A task-agent report and a preinitialized map containing all
   group IDs do not prove this isolation.
   Require the public suite to emit its own declared result IDs, sample representative behavior,
   and use concrete cases distinct from every hidden case. Reject copied or mechanically translated
   public/hidden checks. Reject any task that omits either suite. If no fair public test can provide
   useful feedback without revealing the implementation recipe, reject the candidate instead of
   creating a hidden-only task.
   Make contained prompt, evaluator, or manifest corrections directly in the assigned scratch bundle
   instead of depending on task-agent continuation. Reject and replace a task when correcting it
   would require fundamental re-scoping. After a task passes review, run
   `python <skill-directory>/scripts/task_workspace.py check <scratch>` and correct the bundle until
   this repeatable, read-only check passes. Run it again after every correction. Do not modify the
   bundle after its final successful check. Then run
   `python <skill-directory>/scripts/task_workspace.py accept <scratch>` one task at a time. This is
   the one and only accept attempt for that prepared workspace. Preserve failed workspaces for
   diagnosis. From `prepare` until the matching `accept` succeeds, do not edit shared benchmark
   infrastructure or any other protected target path; defer Dockerfile, setup, and configuration
   changes until all task bundles are accepted. If `accept` fails, stop integration and diagnose the
   protected-state or infrastructure mismatch. Do not edit the scratch infrastructure or target to
   make its snapshot match and do not rerun `accept`; a later attempt requires a newly prepared
   workspace. Never copy, recreate, or materialize the task-agent bundle manually in the target,
   and never treat direct copying as a fallback for the guard.
   Consolidate requirements shared by the accepted tasks into the root Dockerfile and `setup.sh`;
   keep the scaffold's harness installation unless the user selected a different harness explicitly.
   Require a task agent to report a task-specific image requirement instead of introducing one. The
   v1 project format has one image and one setup command.
6. Run `./benchmarks/run.py validate`, then `./benchmarks/run.py build`. Invoke the self-contained
   runner directly; do not wrap it in the target project's `uv`, Poetry, npm, or other environment
   manager.
7. You own task validation, and the user's approval to create the tasks already authorizes it. Do
   not ask the user to run validation or approve its concurrency. Inspect host and Docker CPU and
   memory when possible, then follow the validation job guidance in `references/setup.md`. Run
   `./benchmarks/run.py validate-tasks --jobs <n>` with the selected bounded concurrency, using its
   default of three when capacity cannot be determined. Do not launch separate parallel shell
   commands; the runner owns concurrency, isolated logs, and receipts. Set the shell-tool timeout to
   exactly `14400000` milliseconds (four hours) for every `validate-tasks` or `validate-task`
   command. Never shorten this outer timeout based on task count, concurrency, expected duration, or
   observed progress; the runner's phase-level timeouts remain authoritative.

   Do not consider the benchmark complete until every durable receipt has terminal status
   `validated`, passed setup for both phases, base evaluator exit 1, and reference evaluator exit 0.
   Require the same base 1/reference 0 pair for the mandatory public suite.
   A timeout, missing or `running` receipt, partial logs, or task-agent report is not authoritative
   evidence.
   Read the base and reference setup/public-evaluator/hidden-evaluator logs before accepting each
   receipt. The base must
   reach a behavioral assertion: missing files or modules, import/compile errors, uncaught
   initialization exceptions, and missing evaluator tools are infrastructure failures even when a
   test framework exits 1. Repair task-local benchmark files and retry an affected task with
   `validate-task <id>`. After changing shared `Dockerfile` or `setup.sh`, rebuild when necessary.
   Rerun `validate-tasks` for every task because the validation environment changed. After changing
   only task-local prompt, manifest, public files, public tests, or evaluator files, run
   `validate-task <id>`
   sequentially for each affected task and never rerun unaffected tasks. Never modify product source
   to make validation pass.

   During measured runs, accept `candidate_error` only with direct evidence that the submitted
   product cannot import or compile. Never derive it from the number or pattern of false groups. At
   historical-base validation, catch the expected absence of a requested API and report an ordinary
   group failure when evaluation can continue.

### 3. Configure or run treatments

Configure treatments only when the user supplies configuration values, asks you to configure or run
treatments, or accepts your configuration offer after task validation. In those cases, read
[references/configuration.md](references/configuration.md). Otherwise, do not load that reference.

When the user names a common external skill or MCP server, also read
[references/common-integrations.md](references/common-integrations.md) to resolve its canonical
source. Treat the link as a discovery pointer only; retain the configuration reference's approval
and reproducibility requirements. For every skill comparison, inspect its upstream harness-specific
activation documentation and stage every required local artifact inside only that treatment. Ensure
the named skill is applied to every solver task; copying `SKILL.md` without an activation mechanism
does not complete the configuration.

When the user asks to set or compare reasoning effort, also read
[references/configuration/treatments/reasoning-effort.md](references/configuration/treatments/reasoning-effort.md).
Reasoning controls are harness-specific experimental inputs, not portable model settings.

If the user already supplied the harness, provider where applicable, selected model, and
auth-profile name, use the bundled catalog-driven configuration generator without asking them to
repeat those values. Otherwise, after deterministic task validation, offer one concrete recommended
configuration plus the option to skip. Do not create it until the user approves; never infer
authorization from credential folders, documentation fragments, or provider error suggestions.

For Amazon Bedrock, never choose a missing model or region from memory. Use the live official AWS
and harness documentation linked from the selected harness's provider reference, then verify the
exact model or inference-profile ID and a supported source region before making a recommendation. If
current documentation cannot be fetched, ask the user for the missing values instead of guessing.

Treat names such as `copilot-auth` as profile labels, not proof of the intended harness or Copilot
subscription. Before configuring an ambiguous Copilot treatment, confirm the exact harness and
provider. For OpenCode with provider `github-copilot`, also confirm whether the account uses
Copilot Business. Pass `--github-copilot-business` only when the user confirms it; never ask for or
accept an arbitrary provider base URL.

After creating the approved configurations, derive the unique harness, provider, and auth-profile
requirements from those configurations. Run `./benchmarks/run.py build` once after all approved
configurations exist so the image contains exactly their configured harness executables. Complete
this build before authentication verification, `doctor`, or treatment execution. Check only for
the exact benchmark-owned profile at
`~/.agent-bench/auth/<profile>/<harness>/`. Reuse it when present, but never import credentials from
the user's normal Copilot, OpenCode, GitHub CLI, browser, or home-directory state. An existing
benchmark profile avoids another login; it still does not authorize a treatment run.

For every missing benchmark profile, tell the user which approved configurations require it and
follow the selected harness and provider references to provide the exact `auth login` command. Tell
the user to run it in a real terminal and choose the CLI's headless or device-code authentication
option. Browser or localhost-callback options cannot return to the isolated container; a device-code
flow may still ask the user to open a URL in their host browser. You should not drive the CLI's TTY
or handle passwords, device codes, or provider responses. Do not start authentication merely because
a configuration was created, and do not authenticate unused harnesses or providers. Receive an API
key only where the harness or provider reference defines a non-interactive benchmark-safe route,
such as the Bedrock helper. Follow the harness and provider references reached from
[references/configuration.md](references/configuration.md)
for the exact interactive CLI or Bedrock helper commands.

After authentication completes, run the matching `auth verify` command. For an existing unverified
profile, offer verification or defer its source-free identity preflight until the user authorizes
treatment execution. Follow the routing table in
[references/configuration.md](references/configuration.md) for exact harness and provider commands
and failure handling.

For OpenCode Go, use provider `opencode-go`; the suggested profile label is `opencode-go`. For
OpenCode Zen, use provider `opencode`; the suggested profile label is `opencode-zen`. Provider IDs
and profile labels are separate.

The generator defaults to OpenCode and reads the exact catalog bundled with this skill. Use
`--harness copilot` for native Copilot CLI, `--harness omp` for Oh My Pi, and `--harness pi` for Pi.
Native Copilot CLI omits the provider. OpenCode, Oh My Pi, and Pi require one of their
harness-scoped catalog providers. Native and provider-backed GitHub Copilot selections may use
`auto`; every other selection requires a pinned model.

Configuring treatments or validating tasks does not authorize their execution. Run treatments only
when the user explicitly asks you to do so, and execute exactly the requested task, configuration,
and repetition scope. Do not insert a one-cell pilot or otherwise narrow the run. Before executing a
multi-cell matrix, inspect host and Docker CPU and memory, then follow the job-selection guidance in
`references/configuration/execution.md`; the CLI defaults to three workers, but you may pass a
higher
`--jobs` value when resources support it. When the user will execute the commands, hand off the
commands without inspecting resources or starting treatments. Diagnose failures through
runner-owned logs and disposable staged homes. Treat optional skills or MCP servers as separate
experimental configurations, never baseline defaults. Accept local skill paths and let the
generator install them portably. For an approved MCP server, author the selected harness's native
configuration directly; do not ask the user to supply an MCP configuration file. Compare
correctness before token or cost savings.

After executing treatments, offer a comparative results analysis without loading
[references/results-analysis.md](references/results-analysis.md). Read that reference only when the
user accepts the offer or asks to analyze completed treatment results.

Keep measured solver time unlimited with `solver_timeout_seconds: null` unless the user explicitly
requests a finite time budget. Setup, identity preflight, and evaluator phases remain bounded. Never
choose smaller tasks merely so a solver fits an arbitrary wall-clock limit.

## Choose candidates

Prefer medium or large coherent behavioral changes with clear inputs, observable outputs,
deterministic evaluation, and reproducible project setup. A suitable task normally contains at least
four independently failing public requirement groups and cannot be completed through one localized
edit. Do not count many assertions around one helper as task scale. Reject broad refactors without a
coherent observable outcome, primarily visual work, flaky behavior, production-only integrations,
and changes testable only through private implementation details.

Reject UI or stateful candidates whose evaluator would need to recreate a broad internal provider or
application context, mock framework hooks/module resolution, or invoke private component props. A
focused fake behind a stable public entry point is acceptable; a synthetic replica of the app is
not. Treat product-source or AST inspection, `sys.modules` injection, and synthetic module/package
trees as rejection signals, not deterministic substitutes for behavior.

Reject tasks that reduce to transcribing a fully enumerated helper, constant table, formatter, or
allowlist without meaningful repository interaction. A task should require repository reasoning and
enough behavioral completeness to distinguish a thoughtful solution from a stub; do not manufacture
difficulty with unrelated scope.

Also reject changes whose main behavior is appending fixed guidance, reminder, warning, or policy
text to an enumerated set of outputs. Repeating one additive literal across call sites is not
integration difficulty, and hiding the exact text or affected outputs would create a hidden
contract.

Reject candidates when the only practical evaluator imports a new underscore-prefixed symbol,
asserts private call structure, or reconstructs the historical patch. A symbol introduced by the
reference change is public only when repository documentation, an exported package interface, or
established project conventions make that contract public; calling it public in the benchmark prompt
does not make it so.

Never expose Git history, PR metadata, commit hashes, the historical patch, reference code, or
hidden tests to the solver.

## Review authored tasks

The task agent owns prompt and evaluator authorship under the contract in
[references/task-agent.md](references/task-agent.md). As coordinator, inspect its completed prompt,
evaluator, and assertion ledger together before accepting the bundle. Apply the acceptance criteria
in [references/task-quality.md](references/task-quality.md); verify that the bundle stays within the
approved scope, fully discloses its observable contract, exercises a genuine public entry point, and
distinguishes behavioral failures from infrastructure failures.

Audit every normative prompt statement against directly observed reference behavior, not only
against the assertions the evaluator currently implements. Reference-pass does not validate an
unchecked promise. Add missing deterministic coverage or replace the task when the approved
reference does not satisfy the approved contract; do not weaken that contract after approval.

Make only the contained corrections allowed by the integration workflow. Reject or return a bundle
when its public contract, evaluator boundary, or difficulty requires fundamental re-scoping.

## Protect secrets

Use only `~/.agent-bench/auth/<profile>/<harness>/`. Never copy a complete home directory, Docker
socket, general GitHub credentials, hidden tests, or benchmark metadata into solver containers.
Never run a diagnostic with that persistent profile mounted as a writable home; let the runner copy
it into a disposable staged home. Pin the model and, for OpenCode, the provider. Treat a missing or
mismatched identity as an infrastructure failure before mounting source.

Read [references/formats.md](references/formats.md) when writing YAML or explaining runner commands.
Load the task-quality and configuration references only at the workflow stages that name them.
