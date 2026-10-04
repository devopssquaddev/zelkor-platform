---
title: Register Extra MCP Backends
description: Register ClusterIP or hosted MCP servers on the unified gateway so agents see prefixed tools on MCP_URL.
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
- GitOps access to upgrade the **platform** Helm release (not the agent release).
- Either a ClusterIP MCP Service in the cluster, or a hosted MCP hostname you want Envoy to dial.

## Deploy your MCP server

For an **in-cluster** server: run your vendor or custom MCP image as a normal Kubernetes workload. Store SaaS credentials in a Secret on that Deployment. Example Service name `acme-itsm-mcp` on port `8080`.

Zelkor does not ship ServiceNow, Jira, Salesforce, or Tavily MCP images.

For a **hosted** MCP (Tavily, a partner URL): skip a wrapper Deployment. Create a Secret whose data key is **`apiKey`** (the gateway reads that key name), then register the FQDN below.

```bash
kubectl create secret generic tavily-mcp-key \
  --namespace zelkor \
  --from-literal=apiKey='tvly-YOUR_KEY'
```

Do not put the key in the hostname URL. The agent never receives this Secret.

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

**External hostname** (no wrapper Deployment; Envoy dials this FQDN). Public HTTPS uses the cluster’s system CAs unless you set `tls.caSecretRef`.

```yaml
      - name: tavily
        fqdn:
          hostname: mcp.tavily.com
          port: 443
        path: /mcp
        apiKey:
          secretRef:
            name: tavily-mcp-key
```

`tools/list` then includes `tavily__tavily_search` (and the vendor’s other tools) next to `postgres__query`. The worker calls `MCP_URL` with a Zelkor JWT; Envoy adds `Authorization: Bearer` from `tavily-mcp-key`.

### Naming rules

| Rule | Detail |
| :--- | :--- |
| `name` | DNS-label safe; used as the tool prefix |
| Reserved | Do not use `postgres`, `qdrant`, `sandbox`, `egress`, `nemo`, `aegra`, or `langfuse` |
| `__` | Must not appear in `name` |
| Target | Set exactly one of `service` or `fqdn` |

Gateway `tools/list` returns **`{name}__{tool}`** (for example `acme__create_incident`). `tools/call` strips the prefix and forwards JSON-RPC to your backend.

Optional fields: `toolSelector`, `forwardHeaders` (not `Authorization` — use `apiKey` instead), `tls.caSecretRef` (private CA). Without `caSecretRef`, an FQDN extra uses system CAs (same as LLM provider backends). `egress.cidrs` / `ports` are optional GitOps notes for your own CNI; Community Edition does not apply them to Envoy. Isolation is the agent NetworkPolicy plus the registered FQDN on MCPRoute. See [External and Third-Party MCP](architecture-external-mcp.md).

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
curl -sS "http://zelkor-platform-mcp:80/mcp" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Expect tool names including your prefix alongside `postgres__query`, `sandbox__execute_python`, etc.

## Identity and isolation

Zelkor forwards tenant headers you configure. It does **not** enforce row-level security inside a community SaaS MCP — your server must honor tenant context or you run one MCP per tenant. Native Postgres and Qdrant wrappers are the servers Zelkor guarantees to filter.

## See also

- [Helm values reference](reference/helm-values.md) — full `extraBackends` schema
- [Use the zelkor CLI](cli.md) — `deploy`, `doctor`, env targets
