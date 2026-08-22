# Taskbox

Taskbox is a small JSON-backed task list with no external dependencies.

```bash
python3 -m taskbox --store tasks.json add "Write report"
python3 -m taskbox --store tasks.json list --json
```

Run the tests with:

```bash
python3 -m unittest discover -s tests
```
