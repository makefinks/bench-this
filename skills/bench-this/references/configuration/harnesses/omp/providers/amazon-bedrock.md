# Amazon Bedrock through Oh My Pi

Read this reference together with the [Oh My Pi harness reference](../index.md) when the selected
provider is `amazon-bedrock`.

Amazon Bedrock requires an AWS region. Keep the region in the treatment configuration and the bearer
API key in the external authentication profile.

## Resolve a missing model or region

Treat Bedrock model availability as live data. Never recommend a model ID, inference-profile ID, or
region from memory or from this skill's examples. When the user omits any of them, consult:

- [Oh My Pi providers](https://omp.sh/docs/providers) for its current Bedrock integration and model
  selection behavior.
- [Amazon Bedrock models at a
  glance](https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html) to choose a coding-
  and tool-use-capable model and open its detail page.

Verify the exact base-model or inference-profile ID and that the proposed source region supports
that ID. If live official documentation is unavailable or does not establish an exact compatible
combination, ask the user for the missing values rather than guessing.

## Generate the treatment

Pin both the model ID and AWS region:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness omp \
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

The runner injects the key as `AWS_BEARER_TOKEN_BEDROCK` without staging its credential file. After
setup, verify only the matching OMP profile:

```bash
./benchmarks/run.py auth verify --harness omp --profile bedrock
```

Bedrock uses the native Converse API path, not Mantle.
