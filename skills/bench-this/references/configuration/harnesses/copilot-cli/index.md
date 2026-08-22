# Native Copilot CLI treatment configuration

Read this reference after the general [treatment configuration](../../../configuration.md) reference
when the selected harness is native GitHub Copilot CLI. Treat native GitHub Copilot CLI as
`harness: copilot`; it is neither OpenCode with provider `github-copilot` nor the `gh` CLI.

## Generate the baseline

Omit the provider and select the Copilot harness explicitly:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness copilot \
  --model gpt-5.4-mini \
  --auth-profile copilot
```

The generator creates native Copilot manifests without a provider or OpenCode configuration file.
Local skills work with all supported harnesses. Copilot CLI configurations do not use a provider;
OpenCode, Oh My Pi, and Pi configurations require one. The command refuses to overwrite an existing
configuration.

## Authentication

Native Copilot CLI uses its `/login` device flow. For manual setup, give the user the runner command
without a provider argument:

```bash
./benchmarks/run.py auth login --harness copilot --profile copilot
```

In an agent-assisted flow, start the runner command, relay any device URL and one-time code, and
wait
for the user to finish authorization. Never ask for or handle a password. If the flow requests an
API key rather than device authorization, have the user execute the command directly.

After a newly completed login, verify only the matching profile and harness:

```bash
./benchmarks/run.py auth verify --harness copilot --profile copilot
```

Reject an authentication or subscription combination that cannot select the configured model.
Native Copilot CLI accepts either a pinned model ID or the explicit `auto` selection.

## Optional native integrations

For an MCP treatment, apply the shared [MCP treatment policy](../../treatments/mcp.md) and then the
[Copilot CLI MCP configuration](mcp.md).
