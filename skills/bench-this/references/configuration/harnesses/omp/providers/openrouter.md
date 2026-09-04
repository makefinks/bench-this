# OpenRouter through Oh My Pi

Read this reference together with the [Oh My Pi harness reference](../index.md) when the selected
provider is `openrouter`.

## Generate the treatment

OpenRouter accepts any non-empty pinned model ID, including provider/model IDs containing `/`:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness omp \
  --provider openrouter \
  --model anthropic/claude-sonnet-4.6 \
  --auth-profile openrouter
```

The runner passes the provider-qualified model `openrouter/anthropic/claude-sonnet-4.6` to OMP.
It relies on OMP's built-in OpenRouter integration and generates no native model configuration.

## Authentication

OpenRouter uses one provider profile shared by every supported harness. When it is missing, offer to
run the command after the user supplies the key, or show the same command for the user to run.
Replace the example value with the literal key:

```bash
./benchmarks/run.py auth set-key --provider openrouter \
  --profile openrouter --api-key 'YOUR_API_KEY'
```

If the user chooses agent setup, ask for the key only after that choice and execute the command
without repeating the key. Literal arguments may remain in command history, process listings, and
tool logs. `auth login` is not used for OpenRouter.

The runner injects the stored key as `OPENROUTER_API_KEY` without copying its credential file into
the disposable OMP home. After setup, verify the matching profile and harness:

```bash
./benchmarks/run.py auth verify --harness omp --profile openrouter
```

## Routing interpretation

OpenRouter default routing may select different upstream deployments or fallbacks between runs.
Treat results as default-routing results. This treatment adds no routing controls, provider pinning,
custom endpoint, or model allowlist.
