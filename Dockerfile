# Minimal image for Glama/MCP-directory introspection.
# Builds the vigil-agent package with the MCP extra and starts the
# Vigil MCP server over stdio (default transport for `vigil serve`).
FROM python:3.12-slim

WORKDIR /app
COPY . /app

# Install the package plus the `mcp` extra that the stdio server needs
# (vigil.mcp_server imports mcp.server.fastmcp.FastMCP).
RUN pip install --no-cache-dir ".[mcp]"

# Glama connects over stdio and issues an introspection (tools/list) request.
ENTRYPOINT ["vigil", "serve"]
