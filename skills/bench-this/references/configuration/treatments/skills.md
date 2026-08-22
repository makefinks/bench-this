# Skills as separate treatments

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

The generator copies each skill into `workspace/.agents/skills/<name>`, which supported harnesses
discover natively. For OpenCode it also permits the native skill tool. This is only the first
configuration step: every skill treatment must apply the named skill to every solver task.
Pin or preserve the exact reviewed skill version outside the benchmark before copying it.

Inspect upstream harness-specific activation instructions before completing the variant. Stage the
minimal reviewed `AGENTS.md`, rules, plugin, hooks, or harness configuration under only that
treatment's `workspace/` or `harness/`. When upstream documents only native skill discovery, add a
treatment-local instruction that explicitly requires the solver to invoke the named skill for every
task. A `--skill` variant is not complete merely because the skill directory can be discovered.

Do not run an upstream installer, modify the target repository outside the treatment directory, or
change user-level or host-global configuration. Review executable plugins and hooks before copying
them. Preserve the baseline unchanged, pin all staged artifacts to the reviewed integration
revision, and inspect the treatment diff before validation. If required activation cannot be
represented safely by treatment-local files, stop and ask the user.

Run `validate`, `build`, and `doctor` after staging the complete treatment. After execution, inspect
solver logs for activation evidence: either a native skill invocation or the expected always-on
rule/plugin injection. A run without activation evidence is an invalid treatment execution: report
it as diagnostic and do not attribute or rank its result as an integration effect.

