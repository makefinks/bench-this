# Task-agent contract

If you loaded the `bench-this` skill, you are the coordinator: copy the handoff
template below verbatim for every task agent. If the coordinator sent you the handoff, you are a
task agent: follow the role, responsibilities, ownership, and return instructions in this file.

In either role, read this file, `task-quality.md`, and `setup.md` before starting your work.
Consult `formats.md` only when changing the generated manifest or its test command.

## Your role as task agent

You are the leaf task author, not a benchmark coordinator. Do not invoke or load the
`bench-this` skill or spawn another task agent. Do not run `scaffold.py` or call
`task_workspace.py prepare`, `accept`, or `discard`. The coordinator already prepared the private
authoring repository, commit-specific validation repositories, and assigned output path in the
handoff. Author the bundle directly at that path. After authoring and direct behavioral checks, run
`python <skill-directory>/scripts/task_workspace.py check <scratch-root>` and correct the assigned
bundle until it passes. This repeatable, read-only check does not accept the bundle. If assigned
paths are missing or invalid, stop and report the problem instead of starting another workflow.

## Author the task

Complete only the assigned `benchmarks/tasks/<id>/` skeleton: behavior-focused prompt, optional
public files, required public tests, and required hidden evaluator. The workspace helper already
generated
the standard manifest and required paths. Inspect both historical commits and test observable
behavior without exposing Git history, commit identifiers, reference code, or hidden evaluator
details to the solver.

The handoff's approved observable behavior is the complete task scope. Explore the repository and
historical state as deeply as needed for correctness, but use that evidence to understand and
validate the approved slice; exclude adjacent changes from the same commit even when they are easy
to test.

Preserve every approved substantive requirement group. If the assignment collapses into edge cases
around one localized implementation point, if a group cannot be observed deterministically through
a stable public boundary, or if the groups do not form one coherent user outcome, stop and report
the conflict instead of authoring a smaller or artificially combined task.

Keep the approved group list exact. Do not rename, split, or add groups after inspecting the
historical patch. A helper, constant, stored attribute, algorithm, or adjacent change is not an
approved contract merely because it exists in the reference or can be described as public. Omit it
from the prompt and evaluator unless it maps to an approved observable outcome.

Treat the approved behavior and evaluator boundary as constraints to review, not permission to
expose historical implementation details. If the handoff names underscore-prefixed helpers,
prescribes private algorithms or data structures, enumerates the hidden evaluator's edge cases, or
makes import failure the primary base signal, stop and report the conflict instead of encoding it
into the task.

Prefer the application's real public entry point: command, documented function, HTTP surface,
generated artifact, persisted state, or other user-visible result. A newly added symbol is a public
interface only when repository documentation, exports, or established conventions support that
conclusion. Do not make a private helper public merely by mentioning it in `prompt.md`.

Use focused fakes only at dependencies reached through that public entry point. Do not inspect
product source or its AST, mutate `sys.modules`, construct synthetic package/module trees, or
rebuild
an SDK or framework from nested mocks. If the evaluator cannot import and exercise the public entry
point with real historical dependencies plus small dependency-boundary fakes, stop and report the
candidate as unsuitable.

Write the minimum prompt that lets a repository user understand the feature. State inputs, outcomes,
errors, side effects, and compatibility constraints, but leave implementation choices open. Do not
copy the evaluator matrix into the prompt or forbid internal edits solely because they differ from
the historical patch.

Organize the public contract into one Markdown section per substantive requirement group, using the
exact group ID as the heading. Put every normative statement under exactly one of those sections,
including compatibility, error, timing, and preservation requirements. Introductory prose may give
context but must not introduce additional obligations. Do not turn private examples into a long
checklist, and do not split one behavior into many bullets merely to make the task look larger.
Internal helpers, data structures, constructor choices, and repeated forwarding or call-site edits
are not requirement groups.

Keep private cases separate from the public contract. The evaluator may hide inputs, combinations,
and edge conditions, but the prompt must disclose every required observable shape: property names
and nesting, markup tags and placement, ordering, signatures, serialization, and exact wording when
the evaluator enforces them. If the prompt intentionally leaves a representation flexible, the
evaluator must not require the historical representation.

Create a compact public suite that gives the solver executable feedback on representative public
behavior without turning the task into transcription. Put it under `public-tests/`, retain all three
`public_test_*` manifest fields generated from `formats.md`, and use the same structured result
protocol as the hidden evaluator. Public checks must be representative rather than exhaustive. Give
every hidden check a different concrete input, combination, boundary, or compatibility condition;
do not duplicate or mechanically translate a public check into the hidden suite. Repository-native
tests may supplement but never replace the required public suite. If no fair public check can give
useful feedback without revealing the implementation recipe, report the candidate as unsuitable
instead of authoring a hidden-only task. Make the public entrypoint resolve its helpers relative to
its own file location, not a hard-coded `/public-tests` path, so the solver-visible copy is actually
runnable.

Review the boolean predicate behind every check, not only its human-readable label. Error-message
checks must accept every clear wording allowed by the prompt. Every asserted event or result type,
including supplemental stream events and nonzero event counts, must be explicitly required by the
prompt or removed from the evaluator.

Treat the root Dockerfile and `setup.sh` as provisional shared infrastructure. Do not edit them.
Determine what the assigned task needs and report:

- runtime versions and system packages;
- a deterministic, non-interactive dependency setup command that works at both commits;
- differences between the base and reference dependency metadata;
- whether the shared image can support the task or a distinct image is genuinely necessary.

The v1 benchmark format has one project image and setup command. If the task truly requires an
incompatible image, report it as a blocker instead of adding an unsupported task-local override.

Do not invoke `benchmarks/run.py`; its build, validation, doctor, and execution commands belong to
the coordinator. When the private environment already supports it, run both required evaluators
directly against the prepared base and reference validation repositories. In
particular, run the hidden evaluator directly rather than relying on a repository-native proxy, and
run safe repository-native checks there as additional evidence. Do not create another clone or
worktree. Do not build, modify, or diagnose shared infrastructure. Clearly distinguish successful
checks, checks not run, functional failures, and infrastructure failures. The coordinator owns the
integrated build and authoritative validation receipts.

When running the hidden evaluator directly, use the interpreter and invocation declared by the
generated manifest's `test_command`, substituting only the private hidden-test and workspace paths
for their container mount paths. Executing `run.sh` through its shebang or invoking the test
framework separately is insufficient because it can hide shell and path-resolution failures.

Apply the same rule to `public_test_command`, substituting the task-owned public-test and workspace
paths for `/public-tests` and `/workspace`. The runner exposes a writable copy to the solver at
`.agent-bench-public-tests/`, but measured evaluation always runs the unchanged task-owned suite.

Report the project's normal task-relevant validation commands and whether the prepared environment
lets a solver run them. An environment that supports only the hidden evaluator is insufficient. List
missing package managers, compilers, typecheckers, or test tools as setup requirements rather than
accepting an unverifiable solver workspace.

Design the evaluator so its primary base-commit failure reaches the public behavior and observes a
wrong result. Missing imports for benchmark-prescribed helpers are insufficient unless adding that
importable public interface is the task's actual user-facing requirement.

List every approved group as a stable lowercase ID in `task.yaml` under `requirement_groups`. Make
the evaluator emit exactly one `AGENT_BENCH_RESULT:` JSON line mapping every declared ID to a
boolean. Return `0` only when all groups pass and `1` when any group fails. When a submitted product
workspace cannot import or compile, return `1` with `"candidate_error":true`; reserve `2` or higher
for evaluator code, dependency, setup, or fixture failures. If the test framework conflates
assertions and crashes, add wrapper logic that distinguishes candidate product failures from broken
evaluation infrastructure. The base must emit ordinary failed groups without `candidate_error`; the
reference must emit all true groups and exit `0`. Inspect both logs; a base exit `1` caused before
the public entry point is exercised is invalid.

Evaluate every declared public and hidden result group in its own failure boundary, using a separate
`try`/`catch` block or the test framework's equivalent isolation. Never place multiple groups in one
aborting block: a failed assertion, exception, or early return in one group must not prevent any
later group from executing. Give each group its own fixture setup when practical; when setup is
shared, catch group failures separately and keep the shared state valid for every remaining group.
Initialize and update each boolean only for that group's checks. Before handoff, inspect the control
flow and confirm that every group still runs when an earlier group fails.

List the public suite's stable result IDs under `public_test_groups`. The public suite must emit
ordinary false results and exit `1` on the base, then emit all true results and exit `0` on the
reference. Keep its result IDs and case predicates in a public/hidden partition table in your report
so the coordinator can verify that the two required suites are complementary rather than duplicates.

Set `candidate_error` only from a concrete submitted-product import or compile failure that prevents
behavioral evaluation. Never infer it from how many groups are false, from a particular pattern of
failures, or from the expected absence of a newly requested API at the historical base. Catch that
absence inside the affected group and report an ordinary false result while continuing independent
checks.

For a documented new public API, catch its expected absence at the base and record a functional
failure without aborting the remaining checks. A base `AttributeError` or `TypeError` from calling
the missing feature is not infrastructure failure. Do not import reference-only product symbols at
evaluator module load time; use base-compatible imports and dynamic access or duck typing.

Exercise every group through its approved public entry point. Do not treat import success,
`hasattr`, signature or dataclass-field inspection, or a direct call to a newly added helper as the
primary behavior check. Observe the public return value, exception, emitted event, generated file,
or state transition; structural assertions may only supplement that observation.

Use `task-quality.md` to challenge the assignment before writing. Apply its full-disclosure test and
recipe audit, then create the required assertion ledger mapping every observable evaluator assertion
to an explicit prompt requirement, preserved observable behavior, or a hidden case of one of those
requirements. If an assertion is justified only by the reference patch, rewrite or remove it. If the
task is mechanically solvable from a fair prompt or has no meaningful behavior beyond a new import,
report that it is too easy and stop. Consider likely partial implementations while choosing
behavioral coverage, but do not create or execute artificial solution variants.

Create deterministic evaluator coverage for every approved requirement group and identify the group
for each ledger entry. Use multiple checks where they add meaningful success, boundary, failure, or
compatibility coverage. Many assertions for one group do not substitute for missing groups. The
exact inputs and combinations may remain hidden; every behavior they judge must be public.
Aggregate all checks within a group before emitting its boolean result. Do not expose individual
hidden cases as manifest groups or award check-count-weighted credit.

Choose the time oracle from the public promise. When the promise is that a timeout, cancellation,
interruption, or early return happens by a deadline, measure elapsed time at the public boundary
using a finite workload that would naturally run longer. Assert that the call returns within the
promised limit plus explicit bounded slack. An eventual exception after the work finishes or reaches
another operation limit does not verify the behavior. When the promise is only that code waits or
schedules a delay, replace or record the clock or sleep boundary and assert the requested duration;
do not use wall-clock thresholds for a delay-call contract.

After the evaluator is written, audit every normative prompt statement against the reference
behavior, even if no assertion currently covers it. Reference-pass is insufficient when the
evaluator omits a public promise. Add deterministic coverage or remove an unapproved promise; if the
approved reference does not satisfy the approved contract, stop and report the task for replacement
rather than weakening the contract.

Never copy hidden tests, evaluator source, or evaluator-only metadata into the exported workspace,
even temporarily. When imports require the project's directory layout, build an evaluator-private
layout under `/tmp` and link or reference product source from `$workspace`; keep the hidden test
itself outside `$workspace`.

## Respect file ownership

Work only in the assigned private worker repository and leave the bundle at its assigned scratch
output path. The original target checkout is read-only and out of scope. The worker repository is
the authoring clone and contains helper-owned untracked infrastructure: never switch its commit,
stash it, clean it, or use it for base/reference validation. Use only the prepared base and
reference validation repositories for commit-specific checks. Never change or clean outside the
scratch root. Edit only `benchmarks/tasks/<id>/` in the authoring clone and no shared infrastructure
or product source.

## Report your work

Return a concise report with these headings:

1. `Created files`
2. `Runtime and OS requirements`
3. `Deterministic setup command`
4. `Commit compatibility`
5. `Image decision`
6. `Validation results`
7. `Difficulty evidence`
8. `Evaluator assertion ledger`
9. `Requirement coverage map`
10. `Approved-scope diff`
11. `Evaluator technique audit`
12. `Unresolved failures`
13. `Public/hidden partition`
14. `Workspace check`

Also state which public entry point the evaluator exercises and why any exact symbol named in the
prompt is genuinely public. In the assertion ledger, identify the public requirement or preserved
behavior and substantive group supporting each observable assertion and flag any assertion that had
to be removed or relaxed because the prompt permitted multiple representations. In the requirement
coverage map, connect every approved group to its public evaluator boundary and representative check
types without exposing private inputs. In the approved-scope diff, copy the handed-off group list
verbatim and identify any unmatched prompt or evaluator item; the only acceptable result before
handoff is no additions, removals, splits, or renames. In the evaluator technique audit, list every
fake and confirm
that all evaluator files avoid product-source/AST inspection, module injection, synthetic package
trees, private call assertions, and broad provider or framework reconstruction.

In the public/hidden partition, list each public result ID and the disclosed behavior it samples,
then describe the distinct hidden condition families without exposing private literals or fixtures.
Confirm that both required suites are present and that the public suite gives useful solver
feedback.

In the requirement coverage map, also confirm that every normative prompt sentence belongs to one
exact group, that the reference was directly observed satisfying it, and that each result group has
an independent failure boundary that cannot be skipped by an earlier group's failure. State the
time oracle for
every timing-related requirement and the exact conditions that can set `candidate_error`.

Use `None` under a heading when there is nothing to report. Include exact commands and exit statuses
for validations that ran. Under `Workspace check`, include the successful JSON output from the final
`task_workspace.py check` invocation.

## Hand off a task

Copy this template verbatim for every task agent. Replace every angle-bracket placeholder and each
`...` task-context value with the prepared paths and approved task's concrete context. Do not
otherwise change its wording or structure.

```text
Create benchmark task <id>.

Private worker repository: <worker-repository>
Base validation repository: <base-repository>
Reference validation repository: <reference-repository>
Assigned task output: <task-output>
Scratch root: <scratch-root>
Original target checkout: <target-repository> (read-only and out of scope)

Before working, read:
- <skill-directory>/references/task-agent.md
- <skill-directory>/references/task-quality.md
- <skill-directory>/references/setup.md

Read <skill-directory>/references/formats.md only before changing the generated task manifest or its
test command.

You are the leaf task author. Do not invoke the bench-this skill, delegate this task, run
`scaffold.py`, or call `task_workspace.py prepare`, `accept`, or `discard`. Work directly in the
assigned private repository. Before returning, run
`python <skill-directory>/scripts/task_workspace.py check <scratch-root>` and correct the assigned
bundle until this repeatable, read-only check passes.

Task context:
- Base commit: ...
- Reference commit: ...
- Required observable behavior: ...
- Substantive requirement groups: ...
- Expected evaluator boundaries: ...
- Public entry point and evidence that it is public: ...
- Difficulty rationale and repository context required: ...

You own only <task-output> inside <worker-repository>.
Do not switch, stash, or clean <worker-repository>. Use <base-repository> and
<reference-repository> for commit-specific validation. Do not change or clean any path outside
<scratch-root>. Leave the completed task bundle at <task-output>.
Do not edit shared Dockerfile, setup.sh, configurations, or other tasks.

Return:
- created files
- required runtimes and OS packages
- deterministic dependency setup command
- compatibility notes for both commits
- whether a task-specific image is genuinely required
- validation results, difficulty evidence, and unresolved failures
- successful `task_workspace.py check` result
- evaluator assertion ledger mapping observable checks to public requirements or preserved behavior
- requirement coverage map connecting every approved group to a stable public evaluator boundary
- approved-scope diff with the handed-off groups copied verbatim and no unmatched items
- evaluator technique audit listing all fakes and forbidden-technique scan results
```
