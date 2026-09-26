# Extra MCP backends (BYO tools)

Customer and demo MCP servers register through `workspace.tools.extraBackends` on the platform chart (v2: `platform.tools` in umbrella overlays). The MCP gateway proxies `tools/list` and `tools/call` under each backend **name** prefix.

## In-cluster ClusterIP (default)

```yaml
workspace:
  tools:
    extraBackends:
      - name: acme
        url: http://acme-mcp.zelkor.svc.cluster.local:8080
```

The gateway forwards the caller's Zelkor Bearer and `X-Tenant-ID` unless you disable forwarding (see below).

## SaaS bearer token (no Zelkor JWT upstream)

```yaml
workspace:
  tools:
    extraBackends:
      - name: acme
        url: https://mcp.acme.com
        auth:
          type: bearer
          secretRef:
            name: acme-mcp-credentials
            key: token
        egress:
          cidrs:
            - 203.0.113.0/24
          ports:
            - 443
```

When `auth` sets `Authorization`, `forwardAuthorization` is forced off. With `security.networkPolicies.enabled`, external URLs require `egress.cidrs` (and optional `ports`).

## API key header

```yaml
      - name: acme
        url: https://mcp.acme.com
        auth:
          type: header
          headerName: X-Api-Key
          secretRef:
            name: acme-mcp-credentials
            key: apiKey
```

## HTTP basic

```yaml
      - name: acme
        url: https://mcp.acme.com
        auth:
          type: basic
          usernameSecretRef:
            name: acme-mcp-credentials
            key: username
          passwordSecretRef:
            name: acme-mcp-credentials
            key: password
```

## Private CA

```yaml
      - name: acme
        url: https://mcp.internal.example
        tls:
          caSecretRef:
            name: acme-ca
            key: ca.crt
```

## Optional knobs

| Field | Default | Purpose |
| --- | --- | --- |
| `path` | `/mcp` | JSON-RPC path on the backend |
| `timeoutSeconds` | `30` | Outbound RPC timeout |
| `forwardTenantHeader` | `true` | Send `X-Tenant-ID` |
| `injectTenantArg` | `true` | Set `args.tenant_id` on `tools/call` when absent |
| `headers` | — | Static non-secret headers |
| `headersFrom` | — | Secret-backed headers (`header` + `secretRef`) |

Secret values are mounted as environment variables on the gateway (and Langfuse bootstrap job for tool seeding); they never appear in `MCP_EXTRA_BACKENDS` JSON.

Agents still use a single `MCP_URL` pointing at the gateway; register extra backends only on the platform chart.

See also [agent-deploy.md](agent-deploy.md) and [quickstart.md](quickstart.md).
