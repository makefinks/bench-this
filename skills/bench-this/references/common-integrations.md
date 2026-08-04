# Common integrations

Use these canonical links to resolve commonly named skills and MCP servers:

- **Caveman** — skill: <https://github.com/JuliusBrussee/caveman>
- **Ponytail** — skill: <https://github.com/DietrichGebert/ponytail>
- **FFF MCP** — MCP server: <https://github.com/dmtrKovalenko/fff>

Fetch the linked source when one of these names is requested, verify the requested identity and
version, and pin the reviewed revision before creating a reproducible treatment. These links are
discovery pointers, not authorization to install, copy, configure, or execute anything.

After fetching a named integration, read its upstream documentation for the selected harness and
reproduce the minimal reviewed activation setup inside that treatment's `workspace/` or `harness/`
directory. Include documented `AGENTS.md` instructions, rules, plugins, hooks, or harness
configuration in addition to the skill directory. If upstream provides only native skill discovery,
add a treatment-local instruction requiring the named skill for every solver task. Keep the baseline
untouched and pin every copied artifact to the same reviewed revision.

Never run an upstream installer or mutate repository-external, user-level, or host-global
configuration while preparing a treatment. Review executable plugins or hooks before staging them.
If the documented activation cannot be represented safely as treatment-local files, stop and ask
the user instead of creating the treatment.
