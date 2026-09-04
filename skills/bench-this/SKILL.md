---
name: bench-this
description: >-
  Create or validate project-specific coding-agent benchmarks from repository history, or configure
  and run benchmark treatment comparisons.
---

# Create a project benchmark

Act as the coordinator. Own discovery, approval, scaffolding, shared setup, integration,
validation, and optional treatment configuration. Delegate each approved task's authorship to its
own task agent.

Use judgment for task and evaluator design. Use the bundled tools for deterministic scaffolding,
workspace isolation, integration, and validation.

## 1. Discover candidates

1. Use the positive candidate count requested by the user; otherwise recommend five. Confirm before
   proceeding when the requested count exceeds ten.
2. Inspect `git status` and record existing changes. Keep the worktree read-only throughout
   discovery. Use `git archive` when inspecting a clean historical tree requires an export.
3. Read [task quality](references/task-quality.md). Confirm Docker and the project's normal test
   tool are available, then apply its candidate gate across older, middle, and recent first-parent
   history. Supplement local Git with paginated merged-PR metadata when available. State any limits
   caused by shallow history or incomplete remote coverage.
4. Before presenting a candidate, resolve its full reference and parent hashes with
   `git rev-parse <reference> <reference>^` and inspect `git diff --stat <base> <reference>`. When
   merged pull requests are unavailable, a self-contained commit may use its parent as the base.
5. Complete every candidate artifact required by the quality reference, including substantive
   requirement groups, independent-failure counterexamples, evaluator boundaries, and one
   behavioral probe evidence row per group.
6. Present exactly the requested number of recommendations. Include the PR or commit identifier and
   title, verified base identifier, observable behavior, approximate scope, requirement groups,
   evaluator boundary, setup needs, difficulty evidence, compatibility constraints, and inspected
   history coverage. Mention an alternate only when it exposes a meaningful tradeoff.
7. Stop for explicit approval. Discovery is complete only when the requested candidate set has the
   required evidence; create no benchmark files before approval.

## 2. Create approved tasks

### Lock scope and scaffold

1. Treat the approved observable behavior, requirement groups, and evaluator boundaries as the
   complete scope. Preserve every group's name and meaning. The reference commit is evidence, not a
   requirement to benchmark every historical edit.
2. If `benchmarks/` is absent, immediately run:

   ```bash
   python <skill-directory>/scripts/scaffold.py <repository>
   ```

   Use the absolute skill base directory reported by the loader. Confirm the generated runner and
   templates exist. Then remove the complete scaffold example with:

   ```bash
   python <skill-directory>/scripts/scaffold.py --remove-example <repository>
   ```

   The helper removes the example only when its full file tree still matches the scaffold. Preserve
   a modified or partial example and all other tasks, configurations, and results as user data.
3. Read [setup](references/setup.md). Keep the generated Dockerfile provisional until task agents
   report their requirements.

### Prepare and delegate

1. Read [the task-agent contract](references/task-agent.md). Read
   [formats](references/formats.md) only when changing a generated manifest or test command.
2. Prepare every approved task sequentially, completing one command before starting the next:

   ```bash
   python <skill-directory>/scripts/task_workspace.py prepare \
     <repository> <task-id> <base> <reference>
   ```

   The helper exclusively owns workspace isolation and the generated task skeleton. Diagnose a
   failed preparation using the supplied identities; preserve its scratch state.
3. After all preparations succeed, launch one task agent per task concurrently. Start every agent
   before waiting for any result. Copy the contract's handoff template verbatim, replacing only its
   documented placeholders and task-context values. If delegation is unavailable, stop: direct
   initial authorship is outside the coordinator role.
4. Collect all task-agent reports before modifying or accepting any bundle. This stage is complete
   only when every agent leaves a bundle in its assigned scratch output and reports its workspace
   check result.

### Verify and review

1. Read [the task-verifier contract](references/task-verifier.md). Launch exactly one independent,
   read-only verifier per task, concurrently, using its handoff template verbatim. Start every
   verifier before waiting for reports.
2. Review each bundle, task-agent report, and verifier report against
   [task quality](references/task-quality.md). Resolve every verifier `BLOCK` with a contained
   scratch-bundle correction or reject the task when correction requires fundamental re-scoping.
3. Record the pre-accept decision required by the quality reference. Review the tasks together for
   duplication and breadth. Coordinator review is complete only when every approved group maps
   exactly across prompt, manifest, public tests, hidden evaluator, and assertion ledger; every
   result group has an independent failure boundary; both suites are complementary; and the
   forbidden-technique scan is clean.

### Check and accept

1. Make contained prompt, evaluator, or manifest corrections directly in the assigned scratch
   bundle. Run the repeatable check after every correction:

   ```bash
   python <skill-directory>/scripts/task_workspace.py check <scratch>
   ```

   Freeze the bundle after its final successful check.
2. Accept checked bundles one at a time:

   ```bash
   python <skill-directory>/scripts/task_workspace.py accept <scratch>
   ```

   Each prepared workspace permits one accept attempt. From preparation until acceptance, preserve
   protected target paths and shared benchmark infrastructure. If acceptance fails, stop integration
   and diagnose the protected-state mismatch; a retry requires a newly prepared workspace.
3. After every bundle is accepted, consolidate shared runtime requirements into the root Dockerfile
   and `setup.sh`. Preserve the selected harness installation. The v1 format has one image and one
   setup command.

### Validate

1. Follow [setup](references/setup.md) for the authoritative build, validation, concurrency, retry,
   and receipt procedure. Invoke the self-contained runner directly.
2. The user's approval to create tasks authorizes deterministic task validation. Treatment execution
   remains separately authorized.
3. Validation is complete only when every durable receipt is terminal and `validated`, setup passes
   in both phases, and both public and hidden suites exit `1` behaviorally at the base and `0` at
   the
   reference. Inspect every phase log; a missing tool, import or compile error, or evaluator setup
   failure is infrastructure failure rather than behavioral evidence.

## 3. Configure or run treatments

This branch is optional. Read and follow
[treatment configuration](references/configuration.md) only when the user:

- supplies treatment configuration values;
- asks to configure, authenticate, verify, or run treatments; or
- accepts the configuration offer after deterministic task validation.

Configuration approval does not authorize authentication or execution. The configuration reference
owns provider selection, `auth set-key` and native login flows, secret handling, treatment-specific
references, execution scope, and reporting.
