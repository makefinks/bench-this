# Viewer dev fixture

Synthetic sample data for developing the standalone results browser
(`src/agent_bench/template/benchmarks/viewer.html`) without a real project
run. Values are hand-picked to look realistic and to exercise every widget
(frontier steps, token bars, ledger, failure states) — not measured anywhere.

Contents:

- `sample-runs.jsonl` — 32 rows (8 configurations × 4 generic coding tasks,
  one experiment `dev-fixture`, 16 passes). Configurations cover all four
  supported harnesses (`pi`, `opencode`, `copilot`, `omp`) × two models.
- `viewer-data.js` — the same rows wrapped as `globalThis.BENCHMARK_RESULTS`,
  byte-identical in form to what `report.write_viewer_data()` emits.

Model IDs use the requested names verbatim where possible: config IDs are
slugified (`fable-5-1`, `gpt-5-6-sol`) because real configuration IDs must
match `config._id` (lowercase letters, digits, hyphens).

## Use

Run `./open-viewer.sh` (from this directory) to stage the viewer with
this fixture in a temp dir and open it in your browser. Manual equivalent:

```bash
stage=$(mktemp -d) && mkdir -p "$stage/results" && \
  cp src/agent_bench/template/benchmarks/viewer.html "$stage/" && \
  cp dev-fixtures/viewer/viewer-data.js "$stage/results/" && \
  echo "file://$stage/viewer.html"
```

Open the printed URL. The file picker still overrides the bundled rows.

## Maintenance

Static snapshot by design: if `models.RunResult` gains fields, extend a few
rows here by hand and re-emit `viewer-data.js` via `write_viewer_data()` so
both files stay in sync. Nothing under `dev-fixtures/` is scaffolded into
user projects.
