# Pi

Pi (`pi`) runs as a non-interactive JSON harness. Pin the complete provider/model selector and keep
provider credentials in the runner-owned authentication profile. Read a provider-specific reference
too when the routing table identifies one.

Supported providers are `openai-codex` and `amazon-bedrock`.

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
PI_CODING_AGENT_DIR="$HOME/.agent-bench/auth/codex/pi/.pi/agent" pi
```
The user must then run `/login openai-codex` inside Pi and complete the browser flow. The resulting
`auth.json` stays inside the benchmark-owned profile. Interactive login also creates settings, model
catalogs, and session files; the runner ignores them and stages only `auth.json`. Do not launch Pi
or the OAuth flow for the user.

After login, verify only the matching Pi profile:

```bash
./benchmarks/run.py auth verify --harness pi --profile codex
```
