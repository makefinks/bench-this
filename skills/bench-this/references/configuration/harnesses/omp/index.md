# Oh My Pi

Oh My Pi (`omp`) runs as a non-interactive JSON harness. Select the complete provider/model pair and
keep provider credentials in the runner-owned authentication profile. Read a provider-specific
reference too when the routing table identifies one.

Supported providers are `github-copilot`, `openai-codex`, `amazon-bedrock`, and `openrouter`.
Every provider requires a pinned model.

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness omp \
  --provider openai-codex \
  --model <pinned-model-id> \
  --auth-profile codex
```

OpenAI Codex and GitHub Copilot use OMP's native interactive OAuth login. Give the user the runner
command with the exact provider and profile to execute in a real terminal:

```bash
./benchmarks/run.py auth login --harness omp \
  --provider openai-codex --profile codex
```

The pinned OMP executable runs in the benchmark image without project source or host credentials.
For OpenAI Codex, tell the user to run `/login` inside OMP, select **ChatGPT**, and then choose the
**headless** option. For GitHub Copilot, run `/login`, select **GitHub Copilot**, and choose its
headless or device-code option. Use the host browser only for a displayed device-code URL. Only the
selected provider's validated OAuth database is retained.

After login, verify only the matching OMP profile:

```bash
./benchmarks/run.py auth verify --harness omp --profile codex
```

## Optional native integrations

For an MCP treatment, apply the shared [MCP treatment policy](../../treatments/mcp.md) and then the
[Oh My Pi MCP configuration](mcp.md).
