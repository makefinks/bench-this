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

The non-interactive helper accepts a Bedrock API key through its process environment:

```bash
python <skill-directory>/scripts/provision_auth.py <repository> \
  --harness pi --provider amazon-bedrock --profile bedrock
```

Supply `AGENT_BENCH_BEDROCK_API_KEY` through the execution API. Never put it in the shell command,
command arguments, logs, or repository files. The helper fails immediately when the environment
entry is absent.

The runner injects the key as `AWS_BEARER_TOKEN_BEDROCK` and sets `AWS_REGION` inside Pi's
disposable
container.

After provisioning, verify only the matching Pi profile:

```bash
./benchmarks/run.py auth verify --harness pi --profile bedrock
```
