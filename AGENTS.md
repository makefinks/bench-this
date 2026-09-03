# Comments
Use concise, high-information comments to explain a function’s purpose, non-obvious decisions,
assumptions, and edge cases.
Avoid comments that merely restate the code; optimize for helping a developer quickly understand and
safely modify the function.

## Generality

Treat individual target repositories and E2E runs as diagnostic evidence, not specifications. Every
change to the skill, runner, scaffold, prompts, evaluators, or tests must address a
repository-agnostic class of cases. Never special-case a repository name, path, commit, dependency,
framework, generated task, or observed run. Keep target-specific setup only in that target's
generated benchmark files. Cover general changes with unit tests or synthetic fixtures that do not
encode one repository's behavior.

## Markdown formatting

Wrap Markdown prose at 100 columns. Write Markdown normally, then run the repository
formatter before handing work back:

```bash
python3 scripts/format_markdown.py
python3 scripts/format_markdown.py --check
```

The formatter intentionally preserves YAML frontmatter, fenced and indented code,
tables, headings, HTML, and link-reference definitions when wrapping them could change
their meaning.

## Tests

Test behavior and stable interfaces, not incidental user-facing prose. Assert rendered text only
when its exact wording or format is a documented contract.

## Repository validation

Run the repository tests with:

```bash
PYTHONPATH=src:. uv run --extra test pytest
```

The repository root must be on `PYTHONPATH` because tests import formatter helpers from `scripts/`.

## Skill E2E verification

When asked to run or diagnose the internal full-flow test or E2E verification of `bench-this` in
another repository, read and follow
[the E2E verification skill](.agents/skills/bench-this-e2e/SKILL.md).

## Integration changes

When adding or changing a harness, provider, authentication method or policy, installer, adapter, or
native configuration writer, follow [the integration guide](docs/adding-integrations.md).

## Runner source and vendored copy

`src/agent_bench/` is the canonical development source for the benchmark runner. The copy
under `skills/bench-this/assets/benchmarks/_vendor/agent_bench/` is the
vendored distribution copy used by generated target repositories.

When changing runner behavior, modify and test `src/agent_bench/` first. Then run
`scripts/sync_vendored_runner.py` to update the distribution copy; never edit both copies
independently. Run the script's check mode before E2E verification. The pre-commit hook enforces
byte-for-byte agreement. Skill-only changes, such as `SKILL.md`, references, or scaffold assets, do
not require changes to `src/agent_bench/`.

Generated repositories execute their own `benchmarks/_vendor/agent_bench/` copy and do
not use this repository's `src/` directory.

## Agent skills

### Issue tracker

Issues are tracked as local markdown under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Domain docs

Domain documentation uses a single-context layout. See `docs/agents/domain.md`.
