# MCP servers in Pi treatments

First apply the shared [MCP treatment policy](../../treatments/mcp.md). This reference owns only the
Pi representation.

Pi has a built-in MCP client configured through `mcp.json`.

After the user approves a named server and its command, network, and data-access behavior, create
`harness/mcp.json`:

```json
{
  "mcpServers": {
    "compact": {
      "command": "compact-mcp",
      "args": [],
      "exposure": "direct"
    }
  }
}
```

For Streamable HTTP, use `"url"` instead of `command` and `args`. Keep credentials out of this file.
Pi defaults to `"exposure": "codemode"`; the example selects direct tool exposure explicitly. Record
the chosen exposure in the treatment because it changes the model's tool surface. Servers start
with the session.

The runner stages the file into `/home/bench/.pi/agent/mcp.json` in the disposable home. Preserve
unrelated Pi settings when adding MCP configuration.
