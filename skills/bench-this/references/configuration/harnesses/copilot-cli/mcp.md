# MCP servers in Copilot CLI treatments

First apply the shared [MCP treatment policy](../../treatments/mcp.md). This reference owns only the
Copilot CLI-native representation.

After the user approves a named MCP server and its command, network, and data-access behavior,
create `harness/mcp-config.json` using the native `mcpServers` schema:

```json
{
  "mcpServers": {
    "compact": {
      "type": "local",
      "command": "compact-mcp",
      "args": [],
      "env": {},
      "tools": ["*"]
    }
  }
}
```

The runner stages `harness/` into the disposable native configuration home.
