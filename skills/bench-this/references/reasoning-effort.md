# Reasoning-effort treatments

Read this file only when the user asks to set, pin, or compare reasoning effort. Treat effort as an
experimental input: keep the model, harness, provider, prompt, workspace, and repetition policy
fixed while changing it.

Create a separate configuration ID for every effort level, including the level in the ID. Do not
silently add an effort setting to an existing baseline or overwrite an existing configuration. The
same label does not promise equivalent compute, latency, or behavior across models, providers, or
harnesses.

## Copilot CLI

Pass Copilot's native flag through `arguments` in `configuration.yaml`:

```yaml
id: copilot-gpt-5-4-mini-high
harness: copilot
model: gpt-5.4-mini
harness_config: harness
workspace_config: workspace
auth_profile: copilot
arguments:
  - --reasoning-effort=high
```

Recent Copilot CLI versions expose `none`, `low`, `medium`, `high`, `xhigh`, and `max`; the
installed version and selected model determine actual support. `max` is Copilot's highest-depth
Anthropic tier, not a generic synonym for `xhigh`. Prefer the long `--reasoning-effort` spelling in
benchmark manifests so the treatment is self-explanatory.

## OpenCode

Pass OpenCode's native model variant through `arguments`:

```yaml
id: opencode-openai-gpt-5-4-mini-high
harness: opencode
provider: openai
model: gpt-5.4-mini
agent: build
harness_config: harness
workspace_config: workspace
auth_profile: openai
arguments:
  - --variant=high
```

OpenCode variants are provider- and model-specific. Common names include `none`, `minimal`, `low`,
`medium`, `high`, and `xhigh` for OpenAI models; Anthropic and Google models expose different sets.
Never infer variant support from another provider or model. In particular, do not assume an
OpenCode Go model accepts the variants used by an OpenAI model.

When a built-in variant does not express the intended settings, define a named custom variant in
`harness/opencode.json` and select that exact name with `--variant`. Preserve the generated
`enabled_providers`, `small_model`, sharing, and permission settings. For example:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "enabled_providers": ["openai"],
  "small_model": "openai/gpt-5.4-mini",
  "share": "disabled",
  "provider": {
    "openai": {
      "models": {
        "gpt-5.4-mini": {
          "variants": {
            "benchmark-high": {
              "reasoningEffort": "high"
            }
          }
        }
      }
    }
  }
}
```

Provider options such as `reasoningEffort` are not portable. Use only options documented for the
pinned provider and model; otherwise use a supported built-in variant.

## Verify before measuring

Check the installed CLI's help and model inventory because accepted levels can change:

```bash
copilot --help
opencode models <provider> --verbose
```

Run `./benchmarks/run.py doctor` after creating each treatment. The runner applies `arguments` to
the source-free identity preflight as well as the solver command, so an unsupported flag or variant
should fail before source is mounted. Then run one task and one repetition before expanding the
matrix.

For an effort comparison, report pass rate and failure kind before reasoning tokens, total tokens,
cost, and duration. Do not interpret a lower-effort failure or early exit as an efficiency gain.
