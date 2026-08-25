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

OpenCode Go is also supported. Generate an active configuration with:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness opencode \
  --provider opencode-go \
  --model glm-5.2 \
  --auth-profile opencode-go
```

The suggested profile label is `opencode-go`. Profile labels are user-chosen names and are separate
from the provider and model.

## OpenCode Zen

Use provider `opencode` for OpenCode Zen. The suggested `opencode-zen` profile label is separate
from the provider and model:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness opencode \
  --provider opencode \
  --model <pinned-model> \
  --auth-profile opencode-zen
```

Authenticate and verify the matching provider and profile:

```bash
./benchmarks/run.py auth login --harness opencode \
  --provider opencode --profile opencode-zen
./benchmarks/run.py auth verify --harness opencode --profile opencode-zen
```

## Authentication

OpenCode providers other than Amazon Bedrock use the provider's normal OpenCode login. For manual
setup, give the user the runner command with the exact provider and profile:

```bash
./benchmarks/run.py auth login --harness opencode --provider openai \
  --profile openai
```

Tell the user to run this interactive command in a real terminal and choose the headless or
device-code option. A device-code URL may be opened in the host browser, but callback-based browser
login cannot return to the isolated container. The pinned OpenCode executable runs in the benchmark
image. You should not drive its TTY or handle passwords, device codes, or provider responses.

After a newly completed login, verify only the matching profile and harness:

```bash
./benchmarks/run.py auth verify --harness opencode --profile openai
```

Reject an authentication or subscription combination that cannot select the configured model.
Every OpenCode provider requires a pinned model.

## Optional native integrations

For an MCP treatment, apply the shared [MCP treatment policy](../../treatments/mcp.md) and then the
[OpenCode MCP configuration](mcp.md).

For OpenCode Go, use `--provider opencode-go` and `--profile opencode-go`.
