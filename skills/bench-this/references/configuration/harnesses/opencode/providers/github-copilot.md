# GitHub Copilot through OpenCode

Read this reference together with the [OpenCode harness reference](../index.md) when the selected
provider is `github-copilot`. This integration is distinct from the
[native Copilot CLI harness](../../copilot-cli/index.md).

An auth-profile name such as `copilot-auth`, `copilot`, or `work` does not identify the harness,
provider, or subscription. If the user has not already specified them, confirm whether Copilot means
native Copilot CLI or OpenCode with provider `github-copilot`. For OpenCode, also ask whether the
account uses Copilot Business. Do not infer Business from the profile name or choose a custom API
endpoint.

For Copilot Business through OpenCode, use the dedicated flag:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness opencode \
  --provider github-copilot \
  --github-copilot-business \
  --model gpt-5.4-mini \
  --auth-profile copilot-auth
```

The flag writes the fixed Business API endpoint into the provider options in
`harness/opencode.json`. It is valid only with the OpenCode `github-copilot` provider; the generator
does not accept an agent-selected base URL.

Follow the normal OpenCode authentication flow in the harness reference. Reject an authentication
or subscription combination that cannot select the configured model. This provider accepts either a
pinned model ID or the explicit `auto` selection.
