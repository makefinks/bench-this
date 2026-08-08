# Reasoning effort in OpenCode treatments

First apply the shared [reasoning-effort treatment policy](../../treatments/reasoning-effort.md).
This
reference owns only the native OpenCode controls.

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

Check the installed CLI's model inventory because accepted variants can change:

```bash
opencode models <provider> --verbose
```
