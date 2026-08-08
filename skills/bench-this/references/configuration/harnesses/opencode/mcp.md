# MCP servers in OpenCode treatments

First apply the shared [MCP treatment policy](../../treatments/mcp.md). This reference owns only the
OpenCode-native representation.

OpenCode exposes every enabled MCP tool to the model and warns that large tool sets can add
substantial context. Do not recommend a general MCP bundle as a token-saving default.

After the user approves a named MCP server and its command, network, and data-access behavior, merge
the server into the `mcp` mapping in `harness/opencode.json`:

```json
{
  "mcp": {
    "compact": {
      "type": "local",
      "command": ["compact-mcp"]
    }
  }
}
```

The runner stages `harness/` into the disposable native configuration home. Preserve the generated
OpenCode provider, model, sharing, and permission settings when adding its `mcp` mapping.
