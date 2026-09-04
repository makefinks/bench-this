# Amazon Bedrock through OpenCode

Read this reference together with the [OpenCode harness reference](../index.md) when the selected
provider is `amazon-bedrock`.

Amazon Bedrock requires an AWS region. Keep the region in the treatment's OpenCode configuration
and the bearer API key in the external authentication profile.

## Resolve a missing model or region

Treat Bedrock model availability as live data. Never recommend a model ID, inference-profile ID, or
region from memory or from this skill's examples. When the user omits any of them, use WebFetch or
the harness's equivalent web-retrieval tool to consult:

- [OpenCode providers](https://opencode.ai/docs/providers) for its current Bedrock integration and
  authentication behavior.
- [Amazon Bedrock models at a
  glance](https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html) to choose a coding-
  and tool-use-capable model and open its detail page.

Open the chosen model's detail page from the live AWS model catalog. Verify the exact base-model or
inference-profile ID and that the proposed source region supports that ID. Prefer a current balanced
coding model unless the user states a different capability, latency, cost, provider, or
data-residency preference. Explain cross-region routing when the proposed ID uses it.

Offer the verified model, source region, and a simple profile label as one recommendation, citing
the official pages used. The user may approve it with a short response or change any value. If live
official documentation is unavailable or does not establish an exact compatible combination, ask
the user for the missing values; do not fall back to remembered model names.

## Generate the treatment

Pin both the model ID and AWS region:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness opencode \
  --provider amazon-bedrock \
  --bedrock-region eu-central-1 \
  --model <pinned-bedrock-model-id> \
  --auth-profile bedrock
```

The generator writes only the non-secret region into `harness/opencode.json`. The API key is not a
treatment input and must never appear under `benchmarks/`.

## Authentication

Amazon Bedrock uses one provider profile shared by every harness. When it is missing, offer to run
the command after the user supplies the key, or show the same command for the user to run. Replace
the example value with the literal key:

```bash
./benchmarks/run.py auth set-key --provider amazon-bedrock \
  --profile bedrock --api-key 'YOUR_API_KEY'
```

If the user chooses agent setup, ask for the key only after that choice and execute the command
without repeating the key. Literal arguments may remain in command history, process listings, and
tool logs. `auth login` is not supported for Bedrock.

The runner injects the stored key as `AWS_BEARER_TOKEN_BEDROCK` without copying its credential file
into the disposable OpenCode home. After setup, verify the matching profile and harness:

```bash
./benchmarks/run.py auth verify --harness opencode --profile bedrock
```
