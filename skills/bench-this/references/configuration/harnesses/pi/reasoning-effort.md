# Pi reasoning effort

Pi accepts `--thinking <level>` for a pinned model. Check the installed CLI and selected model
before
creating the treatment:

```bash
pi --help
pi --list-models <model-id>
```

Add the exact supported level to `arguments`:

```yaml
arguments:
  - --thinking
  - high
```

Use a distinct configuration ID for each level. Do not rely on Pi's interactive setting or a model
suffix because the benchmark runner creates a fresh home for every run.
