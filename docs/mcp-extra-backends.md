---
title: Register Extra MCP Backends
description: Attach your ClusterIP MCP server to the unified MCP gateway so agents see prefixed tools on MCP_URL.
type: how-to
sidebar_group: Agents
sidebar_order: 30
audience: both
edition: ce
---

# Register Extra MCP Backends

Zelkor ships **infrastructure** MCP servers (Postgres, Qdrant, sandbox, AI Gateway `/v1`). Customer SaaS or internal tools run as **your** ClusterIP Deployment; you **register** them on the unified MCP gateway. Agents keep a single `MCP_URL` — they do not call your MCP Service directly.

Bring the agent you already wrote: tool secrets stay on the MCP pod or gateway, not in the agent. With NetworkPolicies enabled, agent egress to tools goes only through the MCP gateway.

## Prerequisites

- Platform release running with `workspace.tools.enabled: true`.
- Your MCP server reachable inside the cluster (Deployment + ClusterIP Service).
- GitOps access to upgrade the **platform** Helm release (not the agent release).

## Deploy your MCP server

Run your vendor or custom MCP image as a normal Kubernetes workload in your namespace. Store SaaS credentials in a Secret on that Deployment. Example Service name `acme-itsm-mcp` on port `8080`.

Zelkor does not ship ServiceNow, Jira, or Salesforce MCP images.

## Register on the platform release

Add an entry to `workspace.tools.extraBackends` on the **zelkor-platform** release. Chart default is an empty list.

```yaml
workspace:
  tools:
    extraBackends:
      - name: acme
        service:
          name: acme-itsm-mcp
          port: 8080
        path: /mcp
        apiKey:
          secretRef:
            name: acme-mcp-gateway-key
        forwardHeaders:
          - name: X-Tenant-ID
```

Apply with your overlay file:

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  -f my-platform-overlay.yaml
```

**External hostname** (gateway egress allowed when NetworkPolicies are on):

```yaml
      - name: partner
        fqdn:
          hostname: mcp.partner.example.com
          port: 443
        path: /mcp
        tls:
          caSecretRef: partner-mcp-ca
        egress:
          cidrs:
            - 203.0.113.0/24
          ports:
            - 443
        apiKey:
          secretRef:
            name: partner-mcp-key
```

### Naming rules

| Rule | Detail |
| :--- | :--- |
| `name` | DNS-label safe; used as the tool prefix |
| Reserved | Do not use `postgres`, `qdrant`, `sandbox`, `egress`, `nemo`, `aegra`, or `langfuse` |
| `__` | Must not appear in `name` |
| Target | Set exactly one of `service` or `fqdn` |

Gateway `tools/list` returns **`{name}__{tool}`** (for example `acme__create_incident`). `tools/call` strips the prefix and forwards JSON-RPC to your backend.

Optional fields: `toolSelector`, `forwardHeaders` (not `Authorization` — use `apiKey` instead), `tls.caSecretRef`, `egress.cidrs` / `ports` when `security.networkPolicies.enabled` and the URL is external.

## Match agent `tools.json` before deploy

If your project lists MCP servers in `tools.json`, **`zelkor deploy` compares names** with `workspace.tools.extraBackends` on the platform release. On mismatch it exits non-zero and prints a GitOps snippet — it does **not** patch the platform chart for you.

Register extras on the platform first, then deploy the agent:

```bash
helm upgrade zelkor-platform ... -f overlay-with-extraBackends.yaml
cd my-agent && zelkor deploy --env staging
```

## Mode A vs Mode B

| Mode | What you do |
| :--- | :--- |
| **A** | Agent reads `MCP_URL` and calls `tools/list` / `tools/call` itself |
| **B** | Enable MCP inject on the agent chart so the runtime binds listed tools at graph load |

Both modes see native and extra tools on the same gateway. Details: [Drop-In Agent Contract](architecture-agent-contract.md).

## Verify

From a pod that may reach the MCP gateway (or via port-forward to the gateway Service):

```bash
curl -sS "http://zelkor-platform-mcp-gateway:8080/mcp" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Expect tool names including your prefix alongside `postgres__query`, `sandbox__execute_code`, etc.

## Identity and isolation

Zelkor forwards tenant headers you configure. It does **not** enforce row-level security inside a community SaaS MCP — your server must honor tenant context or you run one MCP per tenant. Native Postgres and Qdrant wrappers are the servers Zelkor guarantees to filter.

## See also

- [Helm values reference](reference/helm-values.md) — full `extraBackends` schema
- [Use the zelkor CLI](cli.md) — `deploy`, `doctor`, env targets
