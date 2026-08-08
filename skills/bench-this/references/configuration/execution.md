# Treatment execution and reporting

Read this reference only after the required authentication profiles are ready and the user
explicitly
asks to execute one or more treatments. Configuration approval does not authorize execution.

Validate the project, verify every active configuration, and run the requested scope:

```bash
./benchmarks/run.py validate
./benchmarks/run.py doctor
./benchmarks/run.py run --task <task-id> --configuration <configuration-id>
```

Repeat `--configuration` when the approved experiment includes only a subset of configured
treatments. Keep the subset in one invocation so it shares an experiment ID and comparison summary:

```bash
./benchmarks/run.py run --task <task-id> \
  --configuration <configuration-a> --configuration <configuration-b>
```

`--task` is repeatable too. When both selectors are repeated, the runner executes their Cartesian
product with the requested repetitions and records every cell under the same experiment ID.

Execute the task, configuration, and repetition scope the user requested. Do not insert a one-cell
pilot before a requested matrix run.

Use `solver_timeout_seconds: null` for measured runs unless the user explicitly requests a finite
time budget. A solver deadline changes the experiment and can censor larger tasks; do not select or
shrink tasks to fit the scaffold's historical 20-minute default. Keep setup and evaluator timeouts
finite because they bound infrastructure, not model capability.

## Select parallel jobs

Apply this job selection only after the user explicitly asks you to execute the expanded matrix.
Configuration approval does not authorize execution. Inspect both host resources and Docker's
effective CPU and memory allocation. Also count configurations that share a provider and
authentication profile, because their concurrent solvers consume the same account-level capacity.

Use the CLI default of three jobs when capacity is uncertain. Pass a higher explicit `--jobs` value
only when Docker memory can sustain that many isolated setup environments, CPU and disk contention
are acceptable, and the shared provider account is unlikely to throttle the concurrent solvers.
Prefer a bounded increase such as four jobs, observe memory pressure, setup duration, rate-limit
failures, and timeouts, then increase again only with evidence. Never infer safe capacity from host
CPU count alone because Docker may have a smaller allocation. Use `--jobs 1` when reproducing a
suspected contention or timeout failure.

## Reporting

After a run, report correctness before token savings. Compare treatment digests, repetitions,
failure kinds, token fields, native or estimated cost, and duration. Do not call a configuration
more efficient when it saves tokens by failing early, skipping required behavior, or degrading pass
rate.
