# Pi

Pi (`pi`) runs as a non-interactive JSON harness. Pin the complete provider/model selector and keep
provider credentials in the runner-owned authentication profile. Read a provider-specific reference
too when the routing table identifies one.

Supported providers are `github-copilot`, `openai-codex`, `amazon-bedrock`, and `openrouter`.

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness pi \
  --provider openai-codex \
  --model <pinned-model-id> \
  --auth-profile codex
```

OpenAI Codex uses Pi's native interactive OAuth login. Give the user this command to run in their
own terminal:

```bash
./benchmarks/run.py auth login --harness pi \
  --provider openai-codex --profile codex
```

The pinned Pi executable runs in the benchmark image without project source or host credentials.
Tell the user to run `/login openai-codex` inside Pi and choose its headless or device-code option.
Use the host browser only for a displayed device-code URL; browser callbacks cannot return to the
isolated container. The runner retains only the selected provider's OAuth entry from `auth.json`;
settings, model catalogs, and sessions are discarded.

For a GitHub Copilot profile, use `/login github-copilot` instead. Pi derives the account-specific
endpoint from the OAuth credential; do not configure a custom endpoint.

After login, verify only the matching Pi profile:

```bash
./benchmarks/run.py auth verify --harness pi --profile codex
```

## Optional package integrations

For an MCP treatment, apply the shared [MCP treatment policy](../../treatments/mcp.md) and then the
[Pi MCP package configuration](mcp.md).
