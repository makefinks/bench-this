# Solver Turn Metrics Specification

## Problem Statement

Benchmark results compare correctness, tokens, cost, and runtime, but they do not show how many
model cycles a harness's main solver session needs to complete a task. Harnesses expose different
event formats and use terms such as steps and turns differently, so their native event counts are
not directly comparable.

## Solution

Add one normalized `turns` metric to each run and benchmark summary. A turn is one completed model
request/response cycle in the harness's main solver session. Each harness adapter derives this count
from its native telemetry and returns the same field to the runner.

Only solver activity is measured. Preflight, evaluation, auxiliary calls, and delegated agent
activity are excluded. Raw results retain turns from unsuccessful runs, while summary averages use
successful runs so early failures do not appear artificially efficient.

## User Stories

1. As a benchmark operator, I want to compare average turns between configurations, so that I can
   assess main-session efficiency independently of token usage and runtime.
2. As a benchmark operator, I want every harness to expose the same turn field, so that I do not
   need to understand harness-specific event formats.
3. As a benchmark operator, I want turns to count model cycles rather than user-visible prompt
   exchanges, so that single-shot solver runs produce a meaningful measurement.
4. As a benchmark operator, I want only the main solver session counted, so that the metric has one
   simple meaning across harnesses.
5. As a benchmark operator, I want only completed model cycles counted, so that failed requests are
   not mixed with completed work.
6. As a benchmark operator, I want preflight activity excluded, so that benchmark infrastructure
   does not inflate solver measurements.
7. As a benchmark operator, I want turn counts retained for failed and timed-out runs, so that I can
   diagnose work completed before failure.
8. As a benchmark operator, I want summary averages based on successful runs, so that early failures
   do not lower a configuration's apparent turn cost.
9. As a benchmark operator, I want per-configuration and per-task averages, so that I can compare
   treatments and identify tasks with longer agent loops.
10. As a benchmark operator, I want unavailable values rendered clearly, so that missing telemetry
    is distinguishable from zero turns.
11. As a benchmark operator, I want historical result files to remain readable, so that this schema
    addition does not invalidate prior experiments.
12. As a harness integrator, I want turn extraction owned by the harness telemetry boundary, so that
    protocol-specific behavior does not leak into reporting.
13. As a maintainer, I want replayed transcript events deduplicated, so that one model cycle is not
    counted multiple times.
14. As a maintainer, I want synthetic protocol fixtures to cover normalization, so that harness
    updates cannot silently change metric semantics.

## Implementation Decisions

- Extend normalized usage telemetry and persisted run results with one nullable integer field named
  `turns`.
- Define `turns` as completed model request/response cycles in the main solver session.
- Count completed cycles only. Provider errors and requests interrupted before a completed response
  do not increment the field.
- Scope extraction to solver output and solver telemetry. Identity preflight and evaluator phases do
  not contribute turns.
- Keep harness-specific event interpretation in telemetry parsers selected by harness adapters. The
  runner only copies normalized usage into run results.
- OpenCode derives turns from completed step events in the main JSON stream.
- Pi-family harnesses derive turns from unique completed assistant generations, using the final
  transcript when available and the existing replay-safe fallback otherwise. Tool-result usage may
  still contribute token telemetry but does not contribute turns.
- Copilot derives turns from OpenTelemetry model request data. Aggregated request counts and
  individual spans must not be counted together.
- Return `null`, not zero, when telemetry cannot establish a count. Zero is reserved for an
  authoritative observation of no completed turns.
- Persist turns for every run outcome when telemetry is available, including incorrect, failed, and
  timed-out solver runs.
- Add average turns to configuration and task summaries.
- Summary averages include successful runs only. An aggregate is unavailable when any successful
  run in that aggregate lacks an authoritative count.
- Render unavailable values as an em dash and authoritative zero values as zero.
- Historical JSONL rows that omit `turns` deserialize with a `null` default.
- Keep the canonical runner as the source of truth and regenerate its vendored distribution copy.

## Testing Decisions

- Prefer the existing harness adapter telemetry seam. Feed synthetic native events through each
  adapter's public usage parser and assert normalized turns rather than private helpers.
- Cover OpenCode completed steps, Copilot aggregated requests and spans, and Pi-family transcript
  events.
- Verify replay safety when message-end, turn-end, and agent-end events repeat one generation.
- Verify that Copilot aggregate and span representations cannot double-count the same cycles.
- Verify that incomplete and errored requests do not count.
- Verify that tool-result usage contributes tokens without increasing main-session turns.
- Exercise the runner lifecycle seam to confirm turns reach successful and unsuccessful run rows.
- Exercise report generation with successful, failed, historical, unavailable, and zero-valued
  rows.
- Assert successful-run averages, unavailable-value propagation, task/configuration grouping, and
  em-dash rendering.
- Run the complete repository test suite, synchronize the vendored runner, and verify exact source
  agreement.

## Out of Scope

- Classifying or counting subagent, delegated, nested, auxiliary, compaction, title, or summary
  model calls.
- Counting failed or incomplete model requests.
- Including preflight or evaluator activity.
- Reconstructing turns for historical result rows.
- Adding a per-turn timeline or report.

## Further Notes

The name `turns` is user-facing even when a harness calls the corresponding native event a step or
request. The normalized main-session definition controls the metric.
