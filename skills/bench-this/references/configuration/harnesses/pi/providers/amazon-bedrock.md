# Amazon Bedrock through Pi

Read this reference with the [Pi harness reference](../index.md) when the selected provider is
`amazon-bedrock`.

Amazon Bedrock requires an AWS region. Keep the region in the treatment configuration. The external
benchmark profile supplies a Bedrock API key; never put the key in the repository.

## Resolve a missing model or region

Treat Bedrock model availability as live data. Never recommend a model ID, inference-profile ID, or
region from memory or from this skill's examples. When the user omits any of them, consult:

- [Pi provider
  documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/providers.md#amazon-bedrock)
- [Amazon Bedrock models at a
  glance](https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html)

Verify the exact base-model or inference-profile ID and that the proposed source region supports it.
Ask the user for any value the official documentation does not establish.

## Generate the treatment

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness pi \
  --provider amazon-bedrock \
  --bedrock-region <aws-region> \
  --model <pinned-bedrock-model-id> \
  --auth-profile bedrock
```

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

The runner injects the key as `AWS_BEARER_TOKEN_BEDROCK`, sets `AWS_REGION`, and does not stage its
credential file in Pi's disposable home. After setup, verify only the matching Pi profile:

```bash
./benchmarks/run.py auth verify --harness pi --profile bedrock
```
