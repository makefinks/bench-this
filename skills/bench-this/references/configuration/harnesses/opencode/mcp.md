# MCP servers in OpenCode treatments

First apply the shared [MCP treatment policy](../../treatments/mcp.md). This reference owns only the
OpenCode-native representation.

OpenCode uses Code Mode for MCP tools by default. Set a server's `codemode` to `false` only when
the treatment requires its tools on the provider's native tool list. MCP instructions and tool
catalogs still consume context; select servers for the task rather than adding a general bundle.

After the user approves a named MCP server and its command, network, and data-access behavior, merge
the server into `mcp.servers` in `harness/opencode.json`:

```json
{
  "mcp": {
    "servers": {
      "compact": {
        "type": "local",
        "command": ["compact-mcp"]
      }
    }
  }
}
```

The runner stages `harness/` into the disposable native configuration home. Preserve the generated
OpenCode provider policies, model, and permission settings when adding `mcp.servers`. Servers
connect unless `disabled` is `true`; timeouts are objects with `startup`, `catalog`, and `execution`
values in milliseconds.
