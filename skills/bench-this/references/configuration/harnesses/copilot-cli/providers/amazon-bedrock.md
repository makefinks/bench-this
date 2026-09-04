# Amazon Bedrock through Copilot CLI

Read this reference with the [Copilot CLI harness reference](../index.md) when the selected provider
is `amazon-bedrock`.

This integration uses Copilot CLI BYOK with Amazon Bedrock Mantle's OpenAI-compatible APIs.
It supports pinned model IDs exposed through the regional `/v1` Mantle path and routes
the harness through either the Chat Completions or Responses wire API.

## Resolve a missing model or region

Treat Bedrock model and region availability as live data. Consult the official
[Amazon Bedrock Chat Completions
API](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-chat-completions-mantle.html)
and the selected model's AWS model card. Verify the exact model ID, that the source region exposes
it through Mantle's `/v1` path, and that it supports streaming and tool calling.

Mantle hosts both the Chat Completions and Responses APIs on the same `/v1` host, but not every
model supports both. Use the probe helper to determine the correct wire API without hand-writing
a request:

```bash
./benchmarks/run.py auth probe --profile bedrock --harness copilot \
  --model <pinned-mantle-model-id> --region <aws-region>
```

The probe reports `completions`, `responses`, and a recommended `wire_api`. Prefer the probed
value over provider docs when they disagree. If the probe is inconclusive or the model is
not accessible, ask the user to confirm the wire API.

## Generate the treatment

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness copilot \
  --provider amazon-bedrock \
  --bedrock-region <aws-region> \
  [--bedrock-wire-api completions|responses] \
  --model <pinned-mantle-model-id> \
  --auth-profile bedrock
```

The runner derives `https://bedrock-mantle.<aws-region>.api.aws/v1` and sets
`COPILOT_PROVIDER_WIRE_API` to the configured `wire_api` (defaults to `completions`).
Keep the API key outside the treatment files.

If you ran `auth probe` first, pass its `wire_api` via `--bedrock-wire-api`.

## Authentication

Use one Bedrock provider profile shared by every harness. Copilot BYOK does not use GitHub login for
this treatment, and the runner does not inherit the host AWS credential chain. When the profile is
missing, offer to run the command after the user supplies the key, or show the same command for the
user to run. Replace the example value with the literal key:

```bash
./benchmarks/run.py auth set-key --provider amazon-bedrock \
  --profile bedrock --api-key 'YOUR_API_KEY'
```

If the user chooses agent setup, ask for the key only after that choice and execute the command
without repeating the key. Literal arguments may remain in command history, process listings, and
tool logs. `auth login` is not supported for Bedrock.

The runner injects the key as `COPILOT_PROVIDER_API_KEY` without staging its credential file. After
setup, verify the matching profile and harness:

```bash
./benchmarks/run.py auth verify --harness copilot --profile bedrock
```
