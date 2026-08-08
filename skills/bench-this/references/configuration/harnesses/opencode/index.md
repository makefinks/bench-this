# OpenCode treatment configuration

Read this reference after the general [treatment configuration](../../../configuration.md) reference
when the selected harness is OpenCode. Read a provider-specific reference too when the routing table
identifies one.

## Generate the baseline

The generator defaults to OpenCode for backwards compatibility. Use an explicit provider, pinned
model, and benchmark-owned authentication profile:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness opencode \
  --provider openai \
  --model gpt-5.4-mini \
  --auth-profile openai
```

For OpenCode, the generated configuration pins the provider-qualified model, pins `small_model` to
the same model, disables sharing, and leaves the treatment workspace empty. The command refuses to
overwrite an existing configuration.

The scaffold includes a ready-to-copy OpenCode Go example using `opencode-go/glm-5.2`. Generate it
as an active configuration with:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness opencode \
  --provider opencode-go \
  --model glm-5.2 \
  --auth-profile opencode-go
```

The suggested profile label is `opencode-go`. Profile labels are user-chosen names and are separate
from the provider and model.

## Authentication

OpenCode providers other than Amazon Bedrock use the provider's normal OpenCode login. For manual
setup, give the user the runner command with the exact provider and profile:

```bash
./benchmarks/run.py auth login --harness opencode --provider openai \
  --profile openai
```

In an agent-assisted OAuth flow, start the runner command, relay any device URL and one-time code,
and wait for the user to finish authorization. Never ask for or handle a password. If the provider
flow requests an API key rather than browser or device authorization, have the user execute the
command directly.

After a newly completed login, verify only the matching profile and harness:

```bash
./benchmarks/run.py auth verify --harness opencode --profile openai
```

Reject an authentication or subscription combination that cannot explicitly select the configured
pinned model. Do not replace the model with `auto`; a provider-selected model would make the
treatment non-reproducible.

## Optional native integrations

For an MCP treatment, apply the shared [MCP treatment policy](../../treatments/mcp.md) and then the
[OpenCode MCP configuration](mcp.md).

When running the OpenCode Go example, use `--provider opencode-go` and `--profile opencode-go`.
