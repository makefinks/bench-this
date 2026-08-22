# Adding harness and provider integrations

Use this guide when adding or changing a harness, provider, authentication method or policy,
installer, adapter, or native configuration writer.

## Goal

Extend the supported integration matrix with the smallest new behavior surface. The catalog declares
which existing capabilities a harness/provider selection uses. Focused registries implement behavior
only when an existing capability cannot satisfy the new integration's contract.

Do not create a new strategy merely because the harness or provider is new. Reuse an existing
adapter, authentication policy, writer, model-reference form, and installer structure whenever
their complete behavioral contracts match.

## Start with reuse

Classify the integration before editing code:

1. Identify the harness protocol: command construction, environment, identity verification,
   telemetry,
   and harness-level error detection.
2. Identify the complete authentication lifecycle: login or provisioning, validation, narrowing,
   staging, and secret injection.
3. Identify the native configuration files and settings that must be generated.
4. Identify model reference syntax, supported treatment fields, pricing identity, and installation
   commands.
5. Compare each requirement with the existing catalog values and registered implementations.

Add a catalog entry that selects existing capabilities when all contracts match. Add a new enum
value
and registry implementation only for a genuine behavioral difference that cannot be represented by
an existing capability without adding harness/provider-specific branches to generic code.

Similar credentials alone do not make authentication policies interchangeable. An authentication
policy is reusable only when its entire lifecycle matches. Similarly, similar command-line syntax
does not make adapters interchangeable when identity or telemetry semantics differ.

## Change matrix

| Change                                               | Primary work                                                                                                                                                                         |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Add a provider using existing behavior               | Add a `ProviderSpec` under the harness in `catalog.py`; add catalog and configuration contract coverage.                                                                             |
| Add a provider requiring new authentication behavior | Implement and register one complete strategy in `auth.py`, add its `AuthPolicy`, then select it from the provider specification.                                                     |
| Add provider-specific native configuration           | Reuse and extend the harness writer in `writers.py`; add provider metadata or fields only as needed. Add a `WriterKind` only for a new harness-native format.                        |
| Add a harness using an existing protocol             | Add a `HarnessSpec` that selects the existing adapter and other reusable capabilities.                                                                                               |
| Add a harness with a new protocol                    | Implement and register an adapter in `harnesses.py`, add its `AdapterKind`, then select it from the harness specification.                                                           |
| Add harness installation commands                    | Add them to the harness `InstallerSpec`. Provider selections reuse the harness installation. Change `installers.py` only if the harness-wide installer model itself is insufficient. |
| Add treatment fields or model rules                  | Extend typed catalog metadata and canonical configuration validation rather than adding consumer-specific exceptions.                                                                |

A single integration may combine these rows. Implement only the rows whose existing capability
cannot
be reused.

## Ownership boundaries

`src/agent_bench/catalog.py` is the source of truth for supported harness/provider combinations and
capability selection. Keep executable behavior in focused modules:

- `harnesses.py`: commands, environment, preflight, identity, telemetry, and harness errors.
- `auth.py`: login, provisioning, validation, credential narrowing, staging, and secret injection.
- `writers.py`: harness-selected native configuration, including provider-specific settings.
- `installers.py`: generic rendering of harness-wide installation metadata.
- `config.py`: generic catalog-driven treatment validation.

A provider does not select a separate writer or installer. Reuse and extend the harness capability
when provider-specific settings are necessary. Add a new writer or installer model only when the
harness-level contract cannot represent the required behavior.

Generic consumers must resolve behavior from catalog metadata. Do not recreate harness/provider
allowlists or add name-based dispatch outside the owning strategy. Unsupported or incompletely
registered combinations must fail during configuration loading or registry resolution, before a
benchmark container starts.

## Implementation workflow

1. Write down the new integration's contracts for protocol, authentication, native configuration,
   model syntax, fields, pricing, and installation.
2. Map every contract to an existing catalog value or registry implementation.
3. Implement the smallest missing capability, if any, in its owning module and register it
   fail-closed.
4. Add or update the `HarnessSpec` or `ProviderSpec` in `catalog.py`.
5. Add focused tests only for new behavior and catalog-driven contract tests for the supported
   combination.
6. Update user-facing configuration and authentication documentation.
7. Run the relevant targeted tests, then the repository test suite.
8. Run `python3 scripts/sync_vendored_runner.py`, followed by
   `python3 scripts/sync_vendored_runner.py --check`.

Edit `src/agent_bench/` first. Never edit the vendored runner independently.

## Completion criteria

The integration is complete when:

- CLI choices, configuration validation, authentication, installation, native configuration, and
  execution derive from the same catalog selection.
- Every new behavior has one owning implementation and no equivalent existing implementation could
  have been reused.
- Generic modules contain no new harness/provider-specific dispatch.
- Invalid and partially registered combinations fail before execution.
- Canonical and vendored runner copies match.
- Relevant tests and documentation cover the observable contract.
