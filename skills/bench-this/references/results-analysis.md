# Analyze treatment results

Analyze completed treatments in the conversation and create no report or other artifact. Use the
experiment run in the current session; otherwise, ask which experiment is in scope when the results
contain more than one possible experiment.

## Establish the comparison

Inspect the in-scope section of `summary.md` and rows in `runs.jsonl`, then inspect the task
prompts,
manifests, public and hidden evaluators, treatment configurations, and every skill, MCP server, or
instruction file they activate. Use an explicit baseline when the experiment establishes one;
otherwise, compare the treatment differences without inventing a control. Describe each distinct
skill, MCP server, or instruction set in no more than three sentences, focused on its purpose and
relevance to the comparison.

## Compare the results

Start with correctness, then failure kinds and observed solver behavior, and finally tokens, cost,
and runtime. Use the summary for aggregate and task-level orientation and the JSONL rows for
digests, repetitions, requirement-group results, public results, failures, mutations, and phase
metrics. Make comparative or causal statements only as strongly as the experiment and its
repetitions support them.

## Investigate every run

Inspect every available log file for every in-scope run, including setup, solver, evaluator, stderr,
and telemetry logs. Account for every failure and look for repeated strategies, surprising
behavior, treatment-specific differences, recovery, and unusually effective work. Report only
meaningful observations; a successful run needs no individual commentary when it adds no insight.

Keep findings traceable by naming the relevant task, configuration, repetition, and run ID, plus a
log path when it helps verify a non-obvious claim. Give a concise comparative synthesis with the
important task-level exceptions, failures, behavioral findings, caveats, and supported conclusions.
These are coverage requirements, not required report sections.
