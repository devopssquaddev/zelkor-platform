# MCP extra backends (Envoy MCPRoute)

Register customer SaaS MCP servers on the same `/mcp` path as native Zelkor tools.

## Values

Set `workspace.tools.extraBackends` on your platform Helm overlay:

```yaml
workspace:
  tools:
    extraBackends:
      - name: crm
        service:
          name: crm-mcp
          port: 8080
        path: /mcp
        apiKey:
          secretRef:
            name: crm-mcp-key
        toolSelector:
          include: []
```

- `name` becomes the tool prefix (`crm__*`).
- Upstream auth uses `apiKey` (Secret data key must be `apiKey`). Client `Authorization` is never forwarded to extras.
- Claim headers (`X-Tenant-ID`, `X-Zelkor-Claim-*`) are always sent to extras on the shared route.

## Agent URL

Point agents at `http://<platform-release>-mcp/mcp` with a tenant JWT (`zelkor token mint` on kind/quickstart).
