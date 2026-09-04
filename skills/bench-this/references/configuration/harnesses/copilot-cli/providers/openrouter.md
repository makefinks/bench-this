# OpenRouter through Copilot CLI

Read this reference with the [Copilot CLI harness reference](../index.md) when the selected provider
is `openrouter`.

This integration uses Copilot CLI BYOK with OpenRouter's OpenAI-compatible API. It accepts any
non-empty pinned model ID, including provider/model IDs containing `/`, and passes the plain model
ID to Copilot.

## Generate the treatment

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness copilot \
  --provider openrouter \
  --model anthropic/claude-sonnet-4.6 \
  --auth-profile openrouter
```

The runner sets `https://openrouter.ai/api/v1` with provider type `openai` and offline mode. Keep
the API key outside the treatment files.

## Authentication

Use one OpenRouter provider profile shared by every supported harness. Copilot BYOK does not use
GitHub login for this treatment. When the profile is missing, offer to run the command after the
user supplies the key, or show the same command for the user to run. Replace the example value with
the literal key:

```bash
./benchmarks/run.py auth set-key --provider openrouter \
  --profile openrouter --api-key 'YOUR_API_KEY'
```

If the user chooses agent setup, ask for the key only after that choice and execute the command
without repeating the key. Literal arguments may remain in command history, process listings, and
tool logs. `auth login` is not used for OpenRouter.

The runner injects the stored key as `COPILOT_PROVIDER_API_KEY` without staging its credential
file. After setup, verify the matching profile and harness:

```bash
./benchmarks/run.py auth verify --harness copilot --profile openrouter
```

## Routing interpretation

OpenRouter default routing may select different upstream deployments or fallbacks between runs.
Treat results as default-routing results. This treatment adds no routing controls, provider pinning,
custom endpoint, or model allowlist.
