# MCP servers as separate treatments

Do not add an MCP server to the baseline configuration. Add one only when it replaces a
demonstrably more expensive workflow and the user approves its network, command, and data-access
behavior.

After the user approves a named MCP server and its command, network, and data-access behavior, write
the server directly into the selected harness's native configuration. The user does not need to
provide a configuration file. Follow the selected harness's native instructions:

- [OpenCode MCP configuration](../harnesses/opencode/mcp.md)
- [Copilot CLI MCP configuration](../harnesses/copilot-cli/mcp.md)
- [Oh My Pi MCP configuration](../harnesses/omp/mcp.md)
- [Pi MCP configuration](../harnesses/pi/mcp.md)

Never put credentials in benchmark files. Do not configure a credentialed MCP server unless the
runner has an explicit, benchmark-safe mechanism for supplying those credentials. Keep the baseline
MCP-free, use a distinct configuration ID, run `doctor`, and compare correctness plus input, output,
cache, duration, and cost telemetry.
