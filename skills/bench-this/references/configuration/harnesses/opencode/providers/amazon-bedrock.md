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

Amazon Bedrock is different from the normal OpenCode login flow: OpenCode consumes
`AWS_BEARER_TOKEN_BEDROCK` and does not own this runner setup. Agent-assisted and manual setup use
separate paths.

For agent-assisted setup, first ask the user to supply the API key after they authorize creating or
replacing the named profile. Do not start `auth login`; its hidden terminal prompt can block an
orchestrator forever. Run the non-interactive skill helper instead:

```bash
python <skill-directory>/scripts/provision_auth.py <repository> \
  --harness opencode --provider amazon-bedrock --profile bedrock
```

Supply the token through the helper process's `AGENT_BENCH_BEDROCK_API_KEY` environment entry using
the execution API. Never put it in the shell command, an argument, or a repository file. The helper
fails immediately rather than prompting when the environment entry is absent. Never repeat or log
the token. The runner later injects the stored token as `AWS_BEARER_TOKEN_BEDROCK`.

For manual setup, give the user this runner command. The user executes it in their own terminal,
where the runner can safely wait for hidden input. Do not launch it from an agent-assisted flow:

```bash
./benchmarks/run.py auth login --harness opencode \
  --provider amazon-bedrock --profile bedrock
```

After a newly completed login, verify only the matching profile and harness:

```bash
./benchmarks/run.py auth verify --harness opencode --profile bedrock
```
