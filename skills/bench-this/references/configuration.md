# Optional treatment configuration

Use this reference only when the user asks you to configure or run a treatment, or when validated
tasks exist and the user accepts your configuration offer. Task creation and deterministic
validation do not require a treatment.

## Minimal decision

Use configuration values the user already supplied: harness, provider where applicable, pinned
model, and auth-profile name. A request such as "configure OpenAI GPT-5.4 mini with profile openai"
remains an OpenCode configuration for backwards compatibility. A request such as "configure Copilot
CLI with model X and profile copilot" creates a native Copilot treatment. When values are missing,
propose one concrete configuration and let the user approve, change, or skip it.

An auth-profile name such as `copilot-auth`, `copilot`, or `work` does not identify the harness,
provider, or subscription. If the user has not already specified them, confirm whether Copilot means
native Copilot CLI or OpenCode with provider `github-copilot`. For OpenCode, also ask whether the
account uses Copilot Business. Do not infer Business from the profile name or choose a custom API
endpoint. Treat native GitHub Copilot CLI as `harness: copilot`; it is not the `gh` CLI.

Amazon Bedrock also requires an AWS region. Keep the region in the treatment's OpenCode
configuration and the bearer API key in the external authentication profile.

Never derive authorization from credential files. A profile name identifies credentials outside the
repository; it does not grant permission to run a treatment. Do not create a configuration merely
because `doctor` suggests a model or an auth directory exists.

### Resolve a missing Bedrock model or region

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

## Resolve authentication after configuration

Wait until the approved configurations exist so their exact harness, provider, and profile
requirements are known. Deduplicate configurations that use the same benchmark profile, then check
for `~/.agent-bench/auth/<profile>/<harness>/`. Reuse that profile when it exists. Do not copy or
translate credentials from the user's ordinary `~/.copilot`, OpenCode, GitHub CLI, browser, or
keychain state. Do not copy a complete home directory. The benchmark profile is deliberately
separate so the runner can stage only the selected credentials into a disposable home.

For each missing profile, identify the configurations that need it and ask whether the user wants
agent-assisted authentication or the exact command to run themselves. Configuration approval alone
does not authorize starting authentication.

OpenCode providers other than Amazon Bedrock use the provider's normal OpenCode login. Native
Copilot CLI uses its `/login` device flow. In either assisted flow, start the runner command, relay
any device URL and one-time code, and wait for the user to finish authorization. Never ask for or
handle a password. If one of these provider flows requests an API key rather than browser or device
authorization, have the user execute the command directly.

Amazon Bedrock is different: OpenCode consumes `AWS_BEARER_TOKEN_BEDROCK` and does not own this
runner setup. Agent-assisted and manual setup use separate paths.

For agent-assisted setup, first ask the user to supply the API key after they authorize creating or
replacing the named profile. Do not start `auth login`; its hidden terminal prompt can block an
orchestrator forever. Run the non-interactive skill helper instead:

```bash
python <skill-directory>/scripts/provision_auth.py <repository> \
  --harness opencode --provider amazon-bedrock --profile bedrock
```

Supply the token through the helper process's `AGENT_BENCH_BEDROCK_API_KEY` environment entry using
the execution API. Never put it in the shell command, an argument, or a repository file. The helper
fails immediately rather than prompting when the environment entry is absent.

For manual setup, give the user the runner command below. The user executes it in their own
terminal,
where the runner can safely wait for hidden input.

```bash
# OpenCode uses an explicit provider.
./benchmarks/run.py auth login --harness opencode --provider openai \
  --profile openai

# Native Copilot CLI has no provider argument.
./benchmarks/run.py auth login --harness copilot --profile copilot

# Manual Bedrock setup; do not launch this from an agent-assisted flow.
./benchmarks/run.py auth login --harness opencode \
  --provider amazon-bedrock --profile bedrock
```

After a newly completed login, verify only the matching profile and harness:

```bash
./benchmarks/run.py auth verify --harness opencode --profile openai
./benchmarks/run.py auth verify --harness copilot --profile copilot
./benchmarks/run.py auth verify --harness opencode --profile bedrock
```

If the profile already existed and the user only asked for configuration, report that it will be
verified before execution and do not make a provider call. Offer `auth verify` when standalone
verification is useful. A request to execute the treatment authorizes its required source-free
identity preflight, but it does not authorize replacing a missing profile through a new login.

Reject an authentication or subscription combination that cannot explicitly select the configured
pinned model. Do not replace the model with `auto`; a provider-selected model would make the
treatment non-reproducible.

## Generate the baseline

Use the bundled generator instead of hand-writing configuration files:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness opencode \
  --provider openai \
  --model gpt-5.4-mini \
  --auth-profile openai
```

For the native Copilot CLI, omit the provider and select the Copilot harness explicitly:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness copilot \
  --model gpt-5.4-mini \
  --auth-profile copilot
```

For Copilot Business through OpenCode, use the dedicated flag:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness opencode \
  --provider github-copilot \
  --github-copilot-business \
  --model gpt-5.4-mini \
  --auth-profile copilot-auth
```

The flag writes the fixed Business API endpoint into the provider options in
`harness/opencode.json`. It is valid only with the OpenCode `github-copilot` provider; the generator
does not accept an agent-selected base URL.

For Amazon Bedrock, pin both the model ID and AWS region:

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

The scaffold includes a ready-to-copy OpenCode Go example using `opencode-go/glm-5.2`. Generate it
as an active configuration with:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --harness opencode \
  --provider opencode-go \
  --model glm-5.2 \
  --auth-profile opencode-go
```

For OpenCode, the generated configuration pins the provider-qualified model, pins `small_model` to
the same model, disables sharing, and leaves the treatment workspace empty. The command refuses to
overwrite an existing configuration.

The generator creates native Copilot manifests without a provider or OpenCode config file. Local
skills work with both harnesses. Once the required profiles are ready and the user explicitly asks
to execute the treatment, validate the project, verify every active configuration, and run the
requested scope:

```bash
./benchmarks/run.py validate
./benchmarks/run.py doctor
./benchmarks/run.py run --task <task-id> --configuration <configuration-id>
```

Repeat `--configuration` when the approved experiment includes only a subset of configured
treatments. Keep the subset in one invocation so it shares an experiment ID and comparison summary:

```bash
./benchmarks/run.py run --task <task-id> \
  --configuration <configuration-a> --configuration <configuration-b>
```

`--task` is repeatable too. When both selectors are repeated, the runner executes their Cartesian
product with the requested repetitions and records every cell under the same experiment ID.

For the OpenCode Go example, use `--provider opencode-go` and
`--profile opencode-go` instead.

Execute the task, configuration, and repetition scope the user requested. Do not insert a one-cell
pilot before a requested matrix run.

Use `solver_timeout_seconds: null` for measured runs unless the user explicitly requests a finite
time budget. A solver deadline changes the experiment and can censor larger tasks; do not select or
shrink tasks to fit the scaffold's historical 20-minute default. Keep setup and evaluator timeouts
finite because they bound infrastructure, not model capability.

Apply the following job selection only after the user explicitly asks you to execute the expanded
matrix. Configuration approval does not authorize execution. Inspect both host resources
and Docker's effective CPU and memory allocation. Also count configurations that share a provider
and authentication profile, because their concurrent solvers consume the same account-level
capacity. Use the CLI default of three jobs when capacity is uncertain. Pass a higher explicit
`--jobs` value only when Docker memory can sustain that many isolated setup environments, CPU and
disk contention are acceptable, and the shared provider account is unlikely to throttle the
concurrent solvers. Prefer a bounded increase such as four jobs, observe memory pressure, setup
duration, rate-limit failures, and timeouts, then increase again only with evidence. Never infer
safe
capacity from host CPU count alone because Docker may have a smaller allocation. Use `--jobs 1` when
reproducing a suspected contention or timeout failure.

## Skills as separate treatments

Do not add a skill to the baseline configuration. A skill changes the treatment and needs its own
configuration ID so results remain attributable. After the user approves a local skill directory,
create a variant with one or more `--skill` arguments:

```bash
python <skill-directory>/scripts/configure.py <repository> \
  --id opencode-openai-gpt-5-4-mini-ponytail \
  --provider openai \
  --model gpt-5.4-mini \
  --auth-profile openai \
  --skill /absolute/path/to/ponytail
```

The generator copies each skill into `workspace/.agents/skills/<name>`, which both supported
harnesses discover natively. For OpenCode it also permits the native skill tool. This is only the
first configuration step: every skill treatment must apply the named skill to every solver task.
Pin or preserve the exact reviewed skill version outside the benchmark before copying it.

Inspect upstream harness-specific activation instructions before completing the variant. Stage the
minimal reviewed `AGENTS.md`, rules, plugin, hooks, or harness configuration under only that
treatment's `workspace/` or `harness/`. When upstream documents only native skill discovery, add a
treatment-local instruction that explicitly requires the solver to invoke the named skill for every
task. A `--skill` variant is not complete merely because the skill directory can be
discovered.

Do not run an upstream installer, modify the target repository outside the treatment directory, or
change user-level or host-global configuration. Review executable plugins and hooks before copying
them. Preserve the baseline unchanged, pin all staged artifacts to the reviewed integration
revision, and inspect the treatment diff before validation. If required activation cannot be
represented safely by treatment-local files, stop and ask the user.

Run `validate`, `build`, and `doctor` after staging the complete treatment. After execution, inspect
solver logs for activation evidence: either a native skill invocation or the expected always-on
rule/plugin injection. A run without activation evidence is an invalid treatment execution: report
it as diagnostic and do not attribute or rank its result as an integration effect.

Ponytail is a plausible minimal-implementation treatment because it asks agents to prefer existing
dependencies and smaller diffs. Caveman is a plausible output-compression treatment, but independent
testing has reported materially smaller savings than its headline claim. Present both as
experiments, not guaranteed optimizations. Do not combine them in the first comparison; measure
baseline versus one intervention at a time.

## MCP servers

OpenCode exposes every enabled MCP tool to the model and warns that large tool sets can add
substantial context. Do not recommend a general MCP bundle as a token-saving default. Add an MCP
server only when it replaces a demonstrably more expensive workflow and the user approves its
network, command, and data-access behavior.

After the user approves a named MCP server and its command, network, and data-access behavior, write
the server directly into the selected harness's native configuration. The user does not need to
provide a configuration file.

For OpenCode, merge the server into the `mcp` mapping in `harness/opencode.json`:

```json
{
  "mcp": {
    "compact": {
      "type": "local",
      "command": ["compact-mcp"]
    }
  }
}
```

For Copilot CLI, create `harness/mcp-config.json` using its native `mcpServers` schema:

```json
{
  "mcpServers": {
    "compact": {
      "type": "local",
      "command": "compact-mcp",
      "args": [],
      "env": {},
      "tools": ["*"]
    }
  }
}
```

The runner stages `harness/` into the disposable native configuration home. Preserve the generated
OpenCode provider, model, sharing, and permission settings when adding its `mcp` mapping. Never put
credentials in benchmark files. Do not configure a credentialed MCP server unless the runner has an
explicit, benchmark-safe mechanism for supplying those credentials. Keep the baseline MCP-free, use
a distinct configuration ID, run `doctor`, and compare correctness plus input, output, cache,
duration, and cost telemetry.

## Reporting

After a run, report correctness before token savings. Compare treatment digests, repetitions,
failure kinds, token fields, native or estimated cost, and duration. Do not call a configuration
more efficient when it saves tokens by failing early, skipping required behavior, or degrading pass
rate.
