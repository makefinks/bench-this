---
name: harness-upgrade
description: Investigate harness upgrades across supported harnesses by comparing pinned
  versus latest versions, verifying output and telemetry parsing, and checking harness
  config docs freshness.
---

# Harness upgrade check

Evaluate one harness or all for a safe version bump. Change no pinned versions
without explicit approval.

Resolve targets yourself (step 1) and write the verdict yourself (step 5).
Dispatch one subagent per target for steps 2-4. Launch all subagents before
waiting; hold the verdict until every report is in.

## 1. Resolve targets

Read pinned packages from `src/agent_bench/catalog.py`. Map each target to its
docs under `skills/bench-this/references/configuration/harnesses/` (`copilot`
lives under `copilot-cli/`).

Complete when every target has a pinned version and docs path.

## 2. Subagent: latest and delta

Resolve the latest upstream release and summarize breaking changes.

Complete when the harness has a pinned-to-latest delta and a candidate verdict.

## 3. Subagent: parsing

Stage the candidate in scratch, drive it through its adapter in
`src/agent_bench/harnesses.py`, and run the captures through the adapter's own
parse and verify methods. Compare against the pinned baseline and run the test
suite.

Complete when the harness has a parsing verdict backed by captured output, or
a named blocking cause.

## 4. Subagent: docs and report

Check every doc claim against the candidate's observed behavior. Report
versions and delta, parsing verdict with evidence, and confirmed-versus-outdated
docs. Propose edits; change nothing.

Complete when the report is returned.

## 5. Verdict

Synthesize the subagent reports into a per-harness summary. Give each harness
one verdict — safe to upgrade, needs follow-up work, or hold — plus a one-line
reason and a pointer to its supporting evidence.

Complete when every target has a verdict, reason, and evidence pointer.
