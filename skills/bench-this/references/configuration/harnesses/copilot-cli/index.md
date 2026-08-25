# Native Copilot CLI treatment configuration

Read this reference after the general [treatment configuration](../../../configuration.md) reference
when the selected harness is native GitHub Copilot CLI. Treat native GitHub Copilot CLI as
`harness: copilot`; it is neither OpenCode with provider `github-copilot` nor the `gh` CLI.

## Choose the provider path

Omit the provider to use a GitHub Copilot account:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness copilot \
  --model gpt-5.4-mini \
  --auth-profile copilot
```

Use a pinned model for this providerless path.

For Amazon Bedrock BYOK, also read the
[Copilot Amazon Bedrock reference](providers/amazon-bedrock.md). This path requires provider
`amazon-bedrock`, a pinned model, and a region.

Local skills work with both paths. The command refuses to overwrite an existing configuration.

## GitHub Copilot authentication

The providerless path uses Copilot CLI's `/login` device flow. For manual setup, give the user the
runner command without a provider argument:

```bash
./benchmarks/run.py auth login --harness copilot --profile copilot
```

Tell the user to run this interactive command in a real terminal and choose the headless or
device-code option. A device-code URL may be opened in the host browser, but callback-based browser
login cannot return to the isolated container. The pinned Copilot executable runs in the benchmark
image. You should not drive its TTY or handle passwords, device codes, or provider responses.

After a newly completed login, verify only the matching profile and harness:

```bash
./benchmarks/run.py auth verify --harness copilot --profile copilot
```

Reject an authentication or subscription combination that cannot select the configured model.

## Optional native integrations

For an MCP treatment, apply the shared [MCP treatment policy](../../treatments/mcp.md) and then the
[Copilot CLI MCP configuration](mcp.md).
