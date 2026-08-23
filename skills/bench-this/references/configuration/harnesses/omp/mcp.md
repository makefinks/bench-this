# MCP servers in Oh My Pi treatments

First apply the shared [MCP treatment policy](../../treatments/mcp.md). This reference owns only the
Oh My Pi-native representation.

Oh My Pi has first-party MCP support. After the user approves a named server and its command,
network, and data-access behavior, create `harness/mcp.json` using OMP's native `mcpServers`
schema:

```json
{
  "mcpServers": {
    "compact": {
      "type": "stdio",
      "command": "compact-mcp",
      "args": []
    }
  }
}
```

For Streamable HTTP, use `"type": "http"` and `"url"` instead of `command` and `args`. Keep
credentials out of this file.

The runner stages `harness/` into the disposable OMP agent directory, so this becomes
`~/.omp/agent/mcp.json`. OMP discovers it directly; no extension or compatibility adapter is
required.
