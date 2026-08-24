# Optional treatment configuration

Use this reference only when the user asks you to configure or run a treatment, or when validated
tasks exist and the user accepts your configuration offer. Task creation and deterministic
validation do not require a treatment.

This file owns the rules shared by every harness. The bundled runner catalog is the executable
support matrix; this routing table only points to the per-harness references. Read only the
additional references required by the approved treatment.

## Harness and provider references

Read the row for the approved harness and provider. A provider-specific page extends the harness
page for that combination:

| Harness     | Provider                     | Additional reference                                                                                                                     |
| ----------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| OpenCode    | openai, opencode-go          | [OpenCode](configuration/harnesses/opencode/index.md)                                                                                    |
| OpenCode    | opencode (Zen)               | [OpenCode Zen](configuration/harnesses/opencode/index.md#opencode-zen)                                                                   |
| OpenCode    | amazon-bedrock               | [OpenCode](configuration/harnesses/opencode/index.md) and [Amazon Bedrock](configuration/harnesses/opencode/providers/amazon-bedrock.md) |
| OpenCode    | github-copilot               | [OpenCode](configuration/harnesses/opencode/index.md) and [GitHub Copilot](configuration/harnesses/opencode/providers/github-copilot.md) |
| Copilot CLI | none                         | [Copilot CLI](configuration/harnesses/copilot-cli/index.md)                                                                              |
| Oh My Pi    | github-copilot, openai-codex | [Oh My Pi](configuration/harnesses/omp/index.md)                                                                                         |
| Oh My Pi    | amazon-bedrock               | [Oh My Pi](configuration/harnesses/omp/index.md) and [Amazon Bedrock](configuration/harnesses/omp/providers/amazon-bedrock.md)           |
| Pi          | github-copilot, openai-codex | [Pi](configuration/harnesses/pi/index.md)                                                                                                |
| Pi          | amazon-bedrock               | [Pi](configuration/harnesses/pi/index.md) and [Amazon Bedrock](configuration/harnesses/pi/providers/amazon-bedrock.md)                   |

## Treatment and execution references

| Situation                        | Additional reference                                                                   |
| -------------------------------- | -------------------------------------------------------------------------------------- |
| Skill treatment                  | [Skills](configuration/treatments/skills.md)                                           |
| MCP treatment                    | [MCP policy](configuration/treatments/mcp.md) and the selected harness's MCP reference |
| Reasoning-effort treatment       | [Reasoning effort](configuration/treatments/reasoning-effort.md)                       |
| Treatment execution or reporting | [Execution and reporting](configuration/execution.md)                                  |

## Minimal decision

Use configuration values the user already supplied: harness, provider where applicable, selected
model, and auth-profile name. The generator defaults to OpenCode when the harness is omitted. A
request such as "configure Copilot CLI with model X and profile copilot" creates a native Copilot
treatment. When values are missing, propose one concrete configuration and let the user approve,
change, or skip it.

An auth-profile name such as `copilot-auth`, `copilot`, or `work` does not identify the harness,
provider, or subscription. If the user has not already specified them, confirm the exact harness and
provider. For OpenCode with provider `github-copilot`, also ask whether the account uses Copilot
Business. Do not infer Business from the profile name or choose a custom API endpoint. Treat native
GitHub Copilot CLI as `harness: copilot`; it is not the `gh` CLI.

Never derive authorization from credential files. A profile name identifies credentials outside the
repository; it does not grant permission to run a treatment. Do not create a configuration merely
because `doctor` suggests a model or an auth directory exists.

Provider behavior is scoped to its harness. Follow the reference for the exact harness/provider
combination; do not transfer authentication, model, endpoint, or configuration assumptions from one
harness to another.

## Generate the approved configuration

Use the bundled catalog-driven generator instead of hand-writing configuration files. Read the
selected harness reference for the exact command and any provider-specific additions. The generator
refuses to overwrite an existing configuration.

Do not add skills or MCP servers to a baseline. They change the treatment and require distinct
configuration IDs; follow their treatment references after the baseline is defined.

## Resolve authentication after configuration

Wait until the approved configurations exist so their exact harness, provider, and profile
requirements are known. Deduplicate configurations that use the same benchmark profile, then check
for `~/.agent-bench/auth/<profile>/<harness>/`. Reuse that profile when it exists. Do not copy or
translate credentials from the user's ordinary `~/.copilot`, OpenCode, GitHub CLI, browser, or
keychain state. Do not copy a complete home directory. The benchmark profile is deliberately
separate so the runner can stage only the selected credentials into a disposable home.

For each missing profile, identify the configurations that need it and follow the selected harness
and provider references to offer only their supported setup options. Ask whether the user wants an
agent-assisted flow when one is supported or the exact command to run themselves. Configuration
approval alone does not authorize starting authentication.

Read the selected harness reference for its normal authentication and verification commands. Also
read the harness/provider reference when one exists: provider integrations can replace the normal
flow. In an assisted browser or device flow, relay any device URL and one-time code and wait for the
user to finish authorization. Never ask for or handle a password. If a provider flow requests an API
key rather than browser or device authorization, have the user execute the command directly unless
the harness/provider reference defines an explicit non-interactive, benchmark-safe route.

After a newly completed login, verify only the matching profile and harness. If the profile already
existed and the user only asked for configuration, report that it will be verified before execution
and do not make a provider call. Offer `auth verify` when standalone verification is useful. A
request to execute the treatment authorizes its required source-free identity preflight, but it does
not authorize replacing a missing profile through a new login.

Reject an authentication or subscription combination that cannot select the configured model.
Native Copilot CLI, OpenCode with GitHub Copilot, and OMP with GitHub Copilot may use `auto`; every
other catalog selection requires a pinned model.

## Continue to execution

Once the required profiles are ready, do not execute a treatment unless the user explicitly asks.
When execution is authorized, follow [execution and reporting](configuration/execution.md) for
validation, requested scope, parallel-job selection, timeouts, and reporting.
