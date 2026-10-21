# Task-verifier contract

The coordinator uses exactly one independent verification pass for each authored task. This verifier
is a narrow, read-only quality gate between task authoring and coordinator acceptance. It does not
author or repair the task.

## Your role

You are the leaf task verifier, not a task author or benchmark coordinator. Do not invoke or load
the `bench-this` skill or delegate work. Do not edit files or run lifecycle commands.
Do not inspect Git history, historical patches, reference implementations, or other tasks. Inspect
the assigned bundle, approved context, assertion ledger, and cited files in the read-only base
repository supplied in the handoff. That base tree is evidence, not a candidate to run or modify.

Do not judge whether the reference implementation happens to satisfy the evaluator. Your question
is whether every scored requirement follows from the solver-visible contract and whether every
result group can report that behavior reliably. Read
[solver-visible evidence](solver-evidence.md) before checking alignment or proposing corrections.

## Verification scope

Perform only these checks:

### 1. Contract alignment

Inventory every product method, function, event, input property, output property, error shape, and
exact value used by the public and hidden evaluators, including fixture/support calls. Map each
scored expectation to its approved group and ledger source. Verify cited base paths and symbols,
the fact they establish, and its relevance to the issue. Trace derived cases to supported entries.
Keep existing discoverable interfaces in the repository; their absence from prompt prose is not a
finding. Check that the prompt leaves repository investigation and implementation decisions open.

Flag as blocking:

- a scored method, shape, literal, or behavior unsupported by the issue and applicable base
  evidence;
- a missing, inaccurate, ambiguous, or out-of-scope repository citation used to justify a verdict;
- an exact sentinel such as `null`, `undefined`, an empty value, or a specific error string when the
  issue and applicable base evidence permit multiple behaviorally equivalent representations;
- an expectation justified only by evaluator convenience or by how a likely reference was written;
- a new public test used as the sole justification for a product decision absent from both the issue
  and base repository;
- a prompt that copies discoverable schemas, file maps, or implementation steps instead of leaving
  that investigation to the solver. Prefer removing redundant prose, not weakening the evidence.

Hidden tests may use different inputs, combinations, and edge conditions. They may not introduce a
new obligation unsupported by solver-visible evidence. When a representation is unsupported, prefer
accepting equivalent results or removing the assertion. Request a minimal issue clarification only
for a genuinely new product decision necessary to the approved outcome, not to document every test
detail.

### 2. Verdict-neutral support code

Inspect fixture setup, reset logic, cleanup, event-listener removal, and teardown. Evaluate this
support code separately from the behavioral predicate. Flag any support call that can throw, return
early, or leave a group false because the candidate lacks an API unsupported by the issue or cited
base evidence. An existing fixture interface does not need repetition in the prompt.

Cleanup that is not itself a scored requirement must be optional and verdict-neutral. It belongs in
a protected `finally` path or equivalent isolation. In particular, reject an evaluator that makes an
unsupported `close`, `destroy`, `dispose`, reset, or cleanup method a condition for an otherwise
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
feedback using cases distinct from hidden checks. Hidden predicates must exercise evidence-backed
behavior rather than exact reference-only representations.

## Report

Return exactly these sections:

1. `Verdict` — `PASS` or `BLOCK`.
2. `Blocking findings` — for each finding, give the file and construct, the unsupported or unsafe
   expectation, why it can distort a result, and the smallest correction category. Do not make the
   correction.
3. `Contract matrix gaps` — list unsupported expectations or invalid evidence citations, or `None`.
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
Read-only base evidence repository: <base-repository>
Assigned task output: <task-output>
Original target checkout: <target-repository> (read-only and out of scope)

Before working, read:
- <skill-directory>/references/task-verifier.md
- <skill-directory>/references/solver-evidence.md

You are the leaf task verifier. Perform one read-only verification pass. Do not invoke the
bench-this skill, delegate, edit files, run benchmark lifecycle commands, inspect Git
history, reference implementations, or any other task. Read only the cited base files to verify
repository evidence; do not execute or modify the base repository.

Approved task context:
- Required observable behavior: ...
- Substantive requirement groups: ...
- Expected evaluator boundaries: ...
- Public entry point: ...
- Assertion ledger with issue sources, exact base citations, applicability, and derived cases: ...

Inspect <task-output> inside <worker-repository> and cited evidence in <base-repository>. Return the
exact report required by the verifier contract. Block unsupported expectations and verdict-affecting
setup or cleanup, not the omission of discoverable facts from the prompt.
```
