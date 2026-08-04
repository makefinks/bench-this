# Task quality and difficulty

Read this file during candidate selection and again when reviewing authored tasks. A task is not
strong merely because base validation fails and the reference passes.

## Candidate gate

Choose a coherent medium or large behavior change that makes the solver understand and modify the
repository. Deterministic evaluation does not imply a unit-sized task. Prefer changes that combine
multiple public behaviors, lifecycle stages, or integration surfaces with meaningful state, error,
compatibility, or migration behavior.

Before recommending a candidate, divide its public contract into substantive requirement groups. A
group is substantive only when it can fail independently and requires implementation reasoning not
already implied by another group. Ten inputs for one formatter, one API call split across headers
and payload fields, or several assertions around one exception branch are one group, not ten.

Groups describe observable product outcomes, not implementation steps. An internal helper,
decorator, constant, registry, constructor choice, or parameter forwarding at several call sites
does not become a separate group. Repeating the same behavior across several adapters or model
classes is one integration group unless those public surfaces have meaningfully different contracts.
Do not expose the historical patch's internal mechanism in the candidate presentation to make the
group list appear concrete.

A candidate should normally have at least four substantive requirement groups, with no single
localized edit plausibly satisfying nearly all of them. A smaller number needs clear evidence of
comparable repository-wide reasoning and independently observable behavior. Treat product diff size
as diagnostic evidence, not a numeric gate: a very small localized reference patch is strong
evidence against the candidate even when its historical tests contain many assertions.

Apply a counterexample test to every proposed group: describe the smallest plausible partial
implementation that passes all other groups but fails this one. The failure must be observable at a
public boundary. If the counterexample differs only by an internal algorithm, registry, decorator,
constructor keyword, import, generated-code assembly step, error wording, or another branch of the
same localized operation, merge it with the related group. A table of hypothetically independent
failures is not evidence without these concrete counterexamples.

Keep the groups part of one coherent user outcome. Do not combine unrelated fixes, require arbitrary
files to change, or count setup, compilation, repository integrity, or evaluator operation as
product requirements. If repository history does not contain enough deterministically observable
behavior for a suitably large task, report that limitation instead of accepting a small task.

Explore first-parent history deeply across older, middle, and recent parts of the repository's
lifespan. Do not choose candidates from commit titles alone. Inspect representative diffs and tests,
follow promising changes through surrounding code and related commits, and compare plausible
alternatives before recommending a task. Do not report a recent-page search as a full-history audit.
When remote pull-request metadata is also used, either paginate it completely or describe its
limited coverage.

Reject or replace a candidate when most of these are true:

- the base failure is only a missing module, export, constant, or allowlist;
- the prompt can enumerate the complete implementation in a few bullets;
- a standalone pure formatter or mapper solves the task without reading surrounding code;
- the change primarily appends fixed guidance, reminder, warning, or policy text to an enumerated
  set
  of existing outputs;
- the evaluator checks only examples already printed in the prompt;
- no existing behavior can regress;
- the historical change's interesting work lies outside the proposed task slice.
- after fairly stating the complete public contract, the prompt identifies the files,
  control flow, and edits closely enough that implementation is transcription;
- most requirements reduce to edge cases of one localized implementation point;
- the apparent scale comes from test count rather than independently failing behavior groups;

Reject a candidate outright when its only practical deterministic evaluator must reconstruct a
broad internal application/provider context, mock framework hooks or module loading, or call private
component props instead of driving a stable public boundary. Small focused fakes behind a public
entry point are acceptable; a synthetic replica of application state is not. Assess this evaluator
feasibility before recommending the candidate, not after task authoring has begun.

Make that feasibility check concrete. Before approval, sketch the evaluator call path and list every
dependency that would be replaced. Product-source or AST inspection, `sys.modules` injection,
synthetic package trees, or enough nested mocks to reproduce an SDK or framework are rejection
signals. Mocking one network client or clock reached through a real public entry point can be a
focused fake; rebuilding the environment needed to import or drive the implementation is not.

Assess feasibility against the actual base and reference dependency manifests and lockfiles, not the
current checkout. Every proposed evaluator runtime, test helper, package export path, and public
entry
point must exist or be installable at both commits. A helper available only at current HEAD is not a
valid historical evaluator seam.

Run a focused reference probe through the proposed public boundary before recommendation whenever
the behavior is measurable directly. Record the command, elapsed time when relevant, and observable
result. Historical test names or assertions are insufficient evidence when they do not measure the
claimed outcome, especially for timing, cancellation, concurrency, persistence, or cleanup.
The probe must instantiate or invoke the user-facing entry point and observe a return value,
exception, emitted event, file, or state transition. Import success, `hasattr`, signatures,
dataclass fields, and direct calls to newly added helpers may supplement that observation but cannot
replace it. A reference that merely exposes the expected structures has not proved the feature.

Write one evidence row per proposed group before counting it. Each row must name the public
invocation, concrete base observation, concrete reference observation, and deterministic evaluator
oracle. An observation such as "parameter absent," "class exists," "field populated after direct
construction," or "helper returns the expected value" is structural evidence, not a qualifying
row. Collapse rows that reach the same product outcome through the same operation.

A new public API can still be valid, but it needs enough interaction, compatibility, or edge
behavior to distinguish a thoughtful repository-level solution from a stub.

The expected absence of a new product API at the base is a functional failure, not evaluator
infrastructure failure. Catch a base `AttributeError` or `TypeError` per check and report the
requirement as failed while continuing the remaining checks. Do not import reference-only product
symbols at evaluator module load time. Use a stable enclosing API, dynamic attribute access, or
result duck typing so the same evaluator starts successfully at both commits. Reject the task only
when the evaluator itself cannot import, install dependencies, create fixtures, or reach any public
boundary.

Do not treat repetition across several call sites as integration difficulty when each edit is the
same additive literal. Fairly disclosing the affected outputs and required text makes that task
transcription; withholding either creates a hidden contract.

## Difficulty evidence

Before recommending a candidate, state:

1. what repository context the solver must discover;
2. which existing public behavior must remain compatible;
3. why a plausible shortcut or partial implementation will fail;
4. how the evaluator reaches behavior beyond import success;
5. the substantive requirement groups and why each can fail independently; and
6. why the task cannot be completed through one localized edit.

If those answers are weak, choose another candidate instead of compensating with obscure hidden
cases.

Apply a **full-disclosure test** before approval: imagine the solver has read every
public requirement needed for a fair task. If that makes the correct edit obvious
without tracing existing state, consumers, or compatibility behavior, reject the
candidate. Do not rescue it by making the prompt vague or hiding required behavior.

Full disclosure means disclosing the definition of correctness, not the evaluator's private cases.
Hidden tests may surprise the solver with inputs, combinations, and edge conditions, but never with
an output shape, field location, markup tag, ordering rule, literal, or compatibility obligation
that the evaluator requires. If disclosing those requirements makes the task mechanical, reject the
candidate instead of using the hidden evaluator to manufacture difficulty.

## Evaluator discrimination

The evaluator must cover the public success path, important failure or boundary behavior, and at
least one compatibility or integration assertion when the feature has one. Do not mirror the
historical unit tests mechanically.

Create deterministic coverage for every substantive requirement group. The exact evaluator inputs,
fixtures, and combinations remain hidden, while every behavior they judge remains public in the
prompt. Use the repository's most stable observable boundary for each group; checks may be unit or
integration tests, CLI calls, generated-artifact comparisons, persisted-state inspection, or other
exact observations. More checks within one group improve coverage but do not make the task larger.

Add a small public test suite that gives the solver useful executable feedback without turning the
task into transcription. Public checks should cover representative success or integration behavior.
Hidden checks must use different concrete inputs, combinations, boundaries, or compatibility
conditions; never copy a public check into the hidden suite. Public and hidden checks may exercise
the same disclosed requirement, but their case predicates must be meaningfully distinct.
Repository-native tests may supplement but never replace the required public suite. Reject the
candidate when no fair public check can give useful feedback without revealing the implementation
recipe; do not create a hidden-only task.

Give every declared group its own prompt section headed by the exact group ID. Every normative
sentence, including introductory compatibility or preservation language, must map to one declared
group. Context outside those sections must not create another obligation. This makes group scoring
traceable to the instructions instead of turning the group list into evaluator-only metadata.

For time limits, cancellation, interruption, or early-return behavior, observing an eventual error
is insufficient. Use a finite workload whose natural duration exceeds the limit, measure elapsed
time at the public boundary, and require completion within the stated limit plus explicit bounded
slack. Ensure another operation cap, retry limit, or natural completion cannot produce the same
result after the deadline. Reject the candidate when the reference implementation does not satisfy
the claimed timing behavior.

Do not use elapsed wall time when the contract only requires invoking a delay or scheduler. Record
or replace the clock, sleep, or scheduler boundary and verify the requested duration and call order
deterministically. Reserve elapsed-time thresholds for contracts whose observable outcome is itself
a deadline, and use bounded slack only there.

Consider likely partial implementations while deciding which public success, boundary,
compatibility, and integration behavior to cover. Do not create or execute artificial solution
variants during authoring.

Declare those groups in `task.yaml` and emit the standard structured result line. Group completion
is equal-weighted by public outcome, not by assertion count: combine every success, boundary,
failure, and compatibility check for one group into one boolean. A candidate product import or
compile failure is a scored candidate failure; evaluator dependency, fixture, or protocol failure is
infrastructure and must not produce a partial score.

Isolate every declared public and hidden result group in its own failure boundary. A shared
`try`/`catch`, test case, callback, or setup path must not allow one group's assertion failure,
exception, or early return to skip later groups and leave their default booleans looking like real
failures. Prefer independent fixtures for each group; otherwise preserve shared state while catching
and recording each group's outcome separately. Review evaluator control flow explicitly rather than
assuming that a complete result map proves every group executed.

Declare the required public suite's stable result IDs under `public_test_groups` and make it emit
the
same structured protocol. Validate public and hidden suites independently on both commits:
each suite must fail behaviorally on the base and pass on the reference. Treat public completion,
hidden requirement-group completion, and their combined total as separate result dimensions; do not
change hidden coverage merely to produce a preferred ratio.

`candidate_error` requires direct evidence that the submitted product cannot import or compile and
therefore cannot be behaviorally evaluated. Never derive it from a failure count or group pattern.
The historical base's expected absence of a requested public API is an ordinary false group when the
evaluator can catch it and continue.

Do not inflate difficulty with long prompts, arbitrary file-count requirements, brittle
implementation assertions, time pressure, or unrelated scope. Difficulty should come from repository
reasoning and behavioral completeness.

Do not reject, split, or shrink a coherent task to fit a solver wall-clock budget. Measured solver
time is unlimited by default; deterministic setup and evaluator phases remain bounded separately.

## Assertion ledger

Before validation, list every evaluator assertion about observable behavior and justify it as one
of:

1. an explicit requirement in the public prompt;
2. pre-existing observable behavior that the prompt requires the solver to preserve; or
3. a hidden input, combination, or edge case exercising requirements from categories 1 or 2.

An assertion justified only by the reference patch, historical test literals, or evaluator
convenience is an undisclosed contract requirement and is forbidden. Rewrite the prompt, relax the
assertion, or reject the task. Do not use broad prompt language such as "appropriate," "style," or
"include a reminder" to justify one exact representation among several reasonable choices.

Treat the following as contract details when the evaluator enforces them:

- property names, nesting, and whether data is top-level or wrapped;
- function paths, signatures, and exported symbols;
- markup element names, attributes, placement, and ordering;
- exact punctuation, casing, wording, prefixes, and suffixes;
- serialization, error, mutation, and compatibility shapes.

Audit predicates as well as assertion labels. If the prompt permits descriptive error text, accept
all clear messages that identify the required problem instead of recognizing only historical words
or phrases. Every event, return-object, or state type whose presence or count is asserted must be
named in the public contract; a related event type does not imply an additional event. Remove
diagnostic assertions that are not required for the public behavior even when the reference emits
them.

State such details publicly when they are genuinely required. Otherwise evaluate the essential
behavior without requiring the reference representation. Preserve the ledger in the task-agent
report for coordinator review; it is authoring evidence and must not be exposed to the solver.

## Prompt calibration

Give the solver the public contract and necessary compatibility expectations, not the evaluator
plan. Representative examples may clarify an interface, but do not enumerate every boundary the
hidden tests exercise. If the prompt reads like pseudocode for the reference implementation,
simplify it before validation.

Audit flexible phrases before saving the prompt. When wording such as "style," "format
appropriately," "preserve the payload," or "include metadata" permits multiple observable results,
either define the required public representation or ensure the evaluator accepts every result
allowed by that wording. Do not silently select the historical representation in hidden tests.

Then run a **recipe audit**: list the implementation decisions a solver must still make
after reading the prompt. There must be meaningful repository-specific decisions left.
If the honest list is empty because the full public contract necessarily describes the
patch step by step, reject the task rather than withholding requirements.

## Review completed tasks

Before acceptance, record a short decision that starts with an exact approved-scope diff. Copy the
approved group list without renaming, splitting, or adding items, then map every prompt requirement
and evaluator section to one of those groups. A constant, helper, stored attribute, algorithm, or
adjacent historical behavior is scope inflation unless it was explicitly approved as an observable
contract. Calling it public after authoring does not approve it. Also name the public entry point,
list focused fakes, and report a scan of every evaluator file for source/AST implementation checks,
module injection, synthetic package trees, private call structure, and broad provider/framework
mocks. Reject on any finding. Do not let a large assertion count, passing reference commit, or
confident worker report override the evaluator source.

Audit the reference against every normative prompt statement, not only against implemented
assertions. Inspect every evaluator's control flow and reject a shared failure boundary that can
short-circuit later result groups; a preinitialized map containing every group does not prove that
every group ran. Base-fail/reference-pass proves only what the evaluator covers. If a disclosed
promise
has no deterministic check, add one; if the approved reference violates the approved promise,
replace the task rather than weakening the contract after approval.

Reject an authored task even after base-fail/reference-pass validation when:

- the failure is only import resolution and the remaining implementation is mechanical;
- the worker did not identify a real public entry point;
- the assertion ledger is missing, incomplete, or relies on the reference patch as specification;
- an exact observable requirement enforced by the evaluator is not disclosed by the prompt or an
  explicit compatibility requirement;
- the base exits 1 because of a missing file/module, import or compile error, uncaught evaluator
  initialization exception, or unavailable tool instead of a reached behavioral assertion;
- the staged solver environment cannot run the project's normal task-relevant validation command;
- the prompt leaks most hidden assertions;
- the full-disclosure or recipe audit shows no meaningful implementation decisions;
- the task is a detached fragment of a more meaningful historical behavior.
- the evaluator reconstructs broad internal application state or framework machinery instead of
  exercising a stable public boundary.
- the evaluator inspects product source or its AST, mutates `sys.modules`, constructs synthetic
  package trees, or asserts private call structure;
- the completed requirement map collapses into one localized implementation point;
- evaluator assertion count disguises a lack of independently failing requirement groups.
- a timeout, cancellation, or interruption check observes only an eventual exception and does not
  verify that the public call returns within the promised deadline plus bounded slack.

When a task is too easy, return to candidate discovery for a replacement. Do not quietly add
unrelated requirements to make it harder.
