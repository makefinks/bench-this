# MCP servers in Pi treatments

First apply the shared [MCP treatment policy](../../treatments/mcp.md). This reference owns only the
Pi representation.

Pi deliberately has no built-in MCP client. Its official integration surface is a Pi extension or
package. Use `pi-mcp-adapter`, which is listed in Pi's package catalog, for MCP servers. Before
using
`pi-mcp-adapter`, check the server's upstream documentation for a native Pi integration. If one
exists, tell the user that it would make the Pi treatment native rather than MCP and ask whether to
switch; continue with `pi-mcp-adapter` unless the user approves the native treatment.

The runner installs a compatible pinned version at
`/opt/pi-mcp-adapter/node_modules/pi-mcp-adapter`. Pi disables package downloads at startup, so
activate that image-local package rather than declaring an npm source that would need installation
during a measured run.

After the user approves a named server and its command, network, and data-access behavior, create
`harness/settings.json`:

```json
{
  "packages": [
    {
      "source": "/opt/pi-mcp-adapter/node_modules/pi-mcp-adapter",
      "skills": []
    }
  ]
}
```

The empty `skills` filter activates the adapter extension without also adding its optional MCP
scripting skill to the treatment. This keeps the comparison scoped to MCP support.

Create `harness/mcp.json` using the adapter's `mcpServers` schema:

```json
{
  "mcpServers": {
    "compact": {
      "command": "compact-mcp",
      "args": [],
      "lifecycle": "lazy"
    }
  }
}
```

For Streamable HTTP, use `"url"` instead of `command` and `args`. Keep credentials out of this file.
The adapter exposes a compact proxy tool by default and discovers server tools on demand; that tool
surface is part of the Pi treatment and differs from harnesses that expose every MCP tool directly.

The runner stages both files into the disposable Pi agent directory. Preserve any other approved Pi
settings when adding the package entry.
