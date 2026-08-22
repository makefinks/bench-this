# Full-flow Taskbox fixture

This fixture supplies reviewable source history for the internal `bench-this` E2E workflow. The
generated repository contains only Taskbox product source, tests, documentation, and six commits. It
contains no benchmark tasks, treatment configuration, or Git remote. After creating the history, the
bootstrap installs the current skill under `.agents/skills/bench-this/` and excludes `.agents/` from
Git status without committing it.

`initial/` is the first commit's complete tree. Each entry after the first in `commits.json` names
an
ordinary patch under `patches/`. `scripts/create_full_flow_fixture.py` replays those inputs with the
fixed author and dates from the manifest.

Keep each historical change self-contained and preserve a public CLI that can be evaluated at every
commit. Regenerate a patch from the parent and child trees when changing history; do not hand-edit
generated patch line numbers without applying the complete fixture test afterward.
