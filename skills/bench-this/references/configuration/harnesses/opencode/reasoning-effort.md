# Reasoning effort in OpenCode treatments

First apply the shared [reasoning-effort treatment policy](../../treatments/reasoning-effort.md).
This
reference owns only the native OpenCode controls.

Use OpenCode's full `provider/model#variant` selector through `arguments`. Keep the manifest's
`model`
as the base model ID so pricing and identity checks retain the same pin:

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
  - --model=openai/gpt-5.4-mini#high
```

OpenCode variants are provider- and model-specific. Common names include `none`, `minimal`, `low`,
`medium`, `high`, and `xhigh` for OpenAI models; Anthropic and Google models expose different sets.
Never infer variant support from another provider or model. In particular, do not assume an
OpenCode Go model accepts the variants used by an OpenAI model.

When a built-in variant does not express the intended settings, define a named custom variant in
`harness/opencode.json` and select `openai/gpt-5.4-mini#benchmark-high` through `arguments`. Merge
the following provider
entry into the generated file, preserving its provider policies, title model, and permissions:

```json
{
  "providers": {
    "openai": {
      "models": {
        "gpt-5.4-mini": {
          "variants": [
            {
              "id": "benchmark-high",
              "settings": {"reasoningEffort": "high"}
            }
          ]
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
opencode models --standalone
opencode api --standalone get /api/model
```

The API form exposes structured model definitions, including variants. Inspect the selected
provider and model.
