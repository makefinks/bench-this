# Solver-visible evidence

Use this policy when authoring, verifying, or accepting a task. Correctness follows from the user's
issue and evidence available in the solver's starting workspace, not from reproducing a historical
patch.

## Issue-first prompts

Write the issue a repository user could have reported: the problem, desired outcome, and product
decisions the repository cannot supply. Leave locating code, understanding existing interfaces,
tracing consumers, and choosing an implementation to the solver. Keep group IDs and the detailed
coverage map in the manifest and authoring report; the prompt may use natural prose and headings.

Disclose genuinely new decisions when correctness depends on them: a new external API name or
schema, a new ordering rule, or an exact product literal with no existing source. Include only the
minimum new interface needed for interoperability. Prefer evaluating through an existing public
boundary over prescribing new helper exports merely to make testing convenient.

## Assertion evidence

For every scored expectation, record its approved group and one of these sources in the private
assertion ledger:

1. **Issue:** a specific prompt statement establishes the requested outcome or new product decision.
2. **Repository:** an exact path and symbol or section in the base workspace establishes an existing
   interface, documented behavior, native test expectation, or unambiguous convention relevant to
   the
   requested change. Record the supported fact and why it applies, not just a file name.
3. **Derived case:** an input, combination, or boundary exercising an issue or repository
   expectation;
   cite the parent ledger entry and explain the inference.

Repository evidence must exist in the actual solver export before any edits. Git history, reference
files, hidden tests, and current-HEAD-only documentation are not available evidence. New public
tests
provide executable examples of the issue, but cannot by themselves justify arbitrary product
decisions absent from the issue and base repository. Existing native tests are repository evidence.

A convention supports an exact expectation only when its applicability is clear and alternatives
are ruled out. A nearby implementation is not automatically a mandate to copy its representation.
Existing private implementation details may help the solver investigate; they do not authorize
scoring internal structure. The issue defines scope: repository evidence cannot add unrelated work.

For fixture and support calls, cite the existing interface they use or make them verdict-neutral.
An existing persistence schema need not be restated in the issue just because a fixture uses it.
Test isolation must still be evaluator-controlled and cleanup must not affect the verdict.

## Ambiguity and repairs

Ask whether two implementations could satisfy the issue and applicable base evidence while differing
on the asserted detail. If so, accept both at the observable boundary or remove the assertion. Add
a concise product decision to the issue only when that decision is necessary to the approved outcome
and cannot be discovered. Do not expand the issue into a test specification to preserve an arbitrary
historical representation.

For example, an issue asking to add cancellation to an existing job command can leave its request
format, job-ID convention, and existing error envelope in the repository. A verifier checks the
cited base interfaces instead of requesting that they be copied into the prompt. A new cancellation
status literal found only in the reference is different: evaluate cancellation semantically, or
disclose that literal if external interoperability genuinely requires it.

## Verification boundary

The verifier reads the bundle, assertion ledger, and only cited files in a read-only base workspace.
Verify each repository citation and its applicability. Missing, contradictory, reference-only, or
overinterpreted evidence is blocking; omission from prompt prose alone is not. Report the
unsupported
inference and prefer an evaluator correction over prompt expansion when several solutions are fair.

Keep evidence and the ledger private. The solver receives the issue and starting repository, not an
investigation guide or a list of the files it must discover.
