# Reasoning-effort treatments

Read this file only when the user asks to set, pin, or compare reasoning effort. Treat effort as an
experimental input: keep the model, harness, provider, prompt, workspace, and repetition policy
fixed while changing it.

Create a separate configuration ID for every effort level, including the level in the ID. Do not
silently add an effort setting to an existing baseline or overwrite an existing configuration. The
same label does not promise equivalent compute, latency, or behavior across models, providers, or
harnesses.

Read the selected harness's native reasoning-effort reference before creating the treatment:

- [OpenCode reasoning effort](../harnesses/opencode/reasoning-effort.md)
- [Copilot CLI reasoning effort](../harnesses/copilot-cli/reasoning-effort.md)

## Verify before measuring

Check the installed CLI's help and model inventory using the command in the selected harness
reference because accepted levels can change.

Run `./benchmarks/run.py doctor` after creating each treatment. The runner applies `arguments` to
the source-free identity preflight as well as the solver command, so an unsupported flag or variant
should fail before source is mounted. Then run one task and one repetition before expanding the
matrix.

For an effort comparison, report pass rate and failure kind before reasoning tokens, total tokens,
cost, and duration. Do not interpret a lower-effort failure or early exit as an efficiency gain.
