# Reasoning effort in Copilot CLI treatments

First apply the shared [reasoning-effort treatment policy](../../treatments/reasoning-effort.md).
This
reference owns only the native Copilot CLI controls.

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

Recent Copilot CLI versions expose `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, and
`max`; the installed version and selected model determine actual support. `max` is Copilot's
highest-depth
Anthropic tier, not a generic synonym for `xhigh`. Prefer the long `--reasoning-effort` spelling in
benchmark manifests so the treatment is self-explanatory.

Check the installed CLI's help because accepted levels can change:

```bash
copilot --help
```
