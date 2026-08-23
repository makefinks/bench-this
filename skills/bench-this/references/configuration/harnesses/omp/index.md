# Oh My Pi

Oh My Pi (`omp`) runs as a non-interactive JSON harness. Select the complete provider/model pair and
keep provider credentials in the runner-owned authentication profile. Read a provider-specific
reference too when the routing table identifies one.

Supported providers are `github-copilot`, `openai-codex`, and `amazon-bedrock`.
GitHub Copilot may use `auto`; OpenAI Codex and Amazon Bedrock require pinned models.

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness omp \
  --provider openai-codex \
  --model <pinned-model-id> \
  --auth-profile codex
```

OpenAI Codex and GitHub Copilot use OMP's native interactive OAuth login:

Give the user the following command to run in their own terminal. The user must then run
`/login openai-codex` (or `/login github-copilot`) inside OMP and complete the browser/device flow:

```bash
PI_CODING_AGENT_DIR="$HOME/.agent-bench/auth/codex/omp/.omp/agent" \
omp
```

The resulting OMP OAuth database is stored in the benchmark-owned profile. Do not launch OMP or the
OAuth flow for the user; the runner's `auth login` command intentionally does not launch this flow
inside Docker.

After login, verify only the matching OMP profile:

```bash
./benchmarks/run.py auth verify --harness omp --profile codex
```

## Optional native integrations

For an MCP treatment, apply the shared [MCP treatment policy](../../treatments/mcp.md) and then the
[Oh My Pi MCP configuration](mcp.md).
