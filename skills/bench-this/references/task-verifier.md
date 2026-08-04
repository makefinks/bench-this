# Task-verifier contract

The coordinator uses exactly one independent verification pass for each authored task. This verifier
is a narrow, read-only quality gate between task authoring and coordinator acceptance. It does not
author or repair the task.

## Your role

You are the leaf task verifier, not a task author or benchmark coordinator. Do not invoke or load
the `bench-this` skill or delegate work. Do not edit files or run lifecycle commands.
Do not inspect Git history, historical patches, reference implementations, base/reference validation
repositories, or other tasks. Inspect only the assigned task bundle and the approved task context in
the handoff.

Do not judge whether the reference implementation happens to satisfy the evaluator. Your question
is whether every scored requirement follows from the solver-visible contract and whether every
result group can report that behavior reliably.

## Verification scope

Perform only these checks:

### 1. Contract alignment

Inventory every product method, function, event, input property, output property, error shape, and
exact value used by the public and hidden evaluators. Map each scored expectation to an explicit
prompt statement under the matching approved group.

Flag as blocking:

- a required method, option name, signature, field, nesting choice, event, or error shape that the
  prompt does not disclose;
- an exact sentinel such as `null`, `undefined`, an empty value, or a specific error string when the
  prompt permits multiple behaviorally equivalent representations;
- an expectation justified only by evaluator convenience or by how a likely reference was written;
- a public test that is the only place where a required contract detail is disclosed. Public tests
  provide feedback but do not replace the prompt contract.

Hidden tests may use different inputs, combinations, and edge conditions. They may not introduce a
new API shape or observable obligation.

### 2. Verdict-neutral support code

Inspect fixture setup, reset logic, cleanup, event-listener removal, and teardown. Evaluate this
support code separately from the behavioral predicate. Flag any support call that can throw, return
early, or leave a group false because the candidate lacks an API that the prompt does not require.

Cleanup that is not itself a public requirement must be optional and verdict-neutral. It belongs in
a protected `finally` path or equivalent isolation. In particular, reject an evaluator that makes an
undocumented `close`, `destroy`, `dispose`, reset, or cleanup method a condition for an otherwise
unrelated group.

### 3. Result-group control flow

Confirm every declared public and hidden result group has its own failure boundary and executes even
when an earlier group fails. Within each group, confirm setup and cleanup cannot suppress assignment
of the intended behavioral verdict. A preinitialized result map and separate top-level `try` blocks
are insufficient when the same undocumented support operation forces every group false.

Flag shared mutable state that an earlier failure can corrupt for later groups. Also flag exceptions
whose messages can hide the actual failed predicate.

### 4. Public/hidden partition

Confirm both suites exist and emit all declared IDs. Public checks must provide useful executable
feedback using cases distinct from hidden checks. Hidden predicates must exercise disclosed behavior
rather than exact reference-only representations.

## Report

Return exactly these sections:

1. `Verdict` — `PASS` or `BLOCK`.
2. `Blocking findings` — for each finding, give the file and construct, the unsupported or unsafe
   expectation, why it can distort a result, and the smallest correction category. Do not make the
   correction.
3. `Contract matrix gaps` — list unmatched evaluator expectations, or `None`.
4. `Control-flow and cleanup findings` — list verdict-suppressing paths, or `None`.
5. `Public/hidden findings` — list disclosure or duplication problems, or `None`.

Return `PASS` only when there are no blocking findings. Do not broaden the approved scope, propose
new requirement groups, score the candidate implementation, or perform a general style review.

## Handoff template

The coordinator must copy this template verbatim and replace only its angle-bracket placeholders and
`...` task-context values.

```text
Verify benchmark task <id>.

Private worker repository: <worker-repository>
Assigned task output: <task-output>
Original target checkout: <target-repository> (read-only and out of scope)

Before working, read:
- <skill-directory>/references/task-verifier.md

You are the leaf task verifier. Perform one read-only verification pass. Do not invoke the
bench-this skill, delegate, edit files, run benchmark lifecycle commands, inspect Git
history or historical implementations, or inspect any other task.

Approved task context:
- Required observable behavior: ...
- Substantive requirement groups: ...
- Expected evaluator boundaries: ...
- Public entry point: ...

Inspect only <task-output> inside <worker-repository>. Return the exact report required by the
verifier contract. Treat every unsupported scored API detail and every verdict-affecting setup or
cleanup operation as blocking.
```
