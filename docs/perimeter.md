---
title: Perimeter Profile
description: A zero-database AI and MCP egress boundary — a gateway plus a stateless sidecar that wraps your agent.
type: explanation
sidebar_group: Install
sidebar_order: 15
audience: human
edition: ce
---

# Perimeter Profile

*What it is: the Zelkor armor around an agent's outbound calls, with none of the persistence — no datastores, no Aegra runtime, no trace store.*

`profile=perimeter` installs a **zero-database egress boundary** for your agents' LLM and MCP traffic. It has two parts:

1. **The gateway** — a shared Envoy AI Gateway (`/v1`) and MCP gateway (`/mcp`) that inject provider keys, rate-limit, deny mutating tools, and log audit metadata. Installs in under 90 seconds and under 500 MB of RAM (without the optional guardrails and code sandbox).
2. **A stateless sidecar** — the same `zelkor-sidecar` the full runtime uses, minus its database. You wrap an agent with `zelkor deploy`, and the sidecar forces that agent's LLM and MCP calls through the gateway, attaches its tenant identity and keys, and meters it — with nothing stateful behind it.

Use it when your agents run on Kubernetes and you want to **armor their outbound calls** without adopting the full runtime (no Postgres, ClickHouse, Valkey, Qdrant, SeaweedFS, Langfuse, or Aegra agent host). Your wrapped agents are still published on the same agents host as in the full profile. NeMo guardrails and the gVisor code sandbox are off by default; add either one when you need it ([Optional guardrails and code sandbox](#optional-guardrails-and-code-sandbox)).

## Why a gateway alone is not enough

A gateway only controls traffic that is routed to it, and a Kubernetes NetworkPolicy only governs pods in its own namespace. The perimeter gateway cannot, by itself, stop an agent in another namespace from calling an LLM provider directly. Enforcement has to live **where the agent runs**. The perimeter does that by wrapping the agent with a stateless sidecar in the same pod and locking that pod's egress to the gateway.

## How it works

```mermaid
---
config:
  theme: neutral
---
flowchart LR
  subgraph wrapped["Your agent, wrapped (zelkor deploy)"]
    agent["Your agent container<br/>base_url = 127.0.0.1:8001"]
    sc["zelkor-sidecar (egress-only, no DB)<br/>tenant JWT + key injection, budget"]
    agent -->|loopback, intra-pod| sc
  end
  subgraph per["Perimeter (profile=perimeter) — zero-DB"]
    gw["Envoy AI Gateway /v1 and MCP /mcp<br/>provider keys, global RPM, tool-deny, audit"]
  end
  prov["LLM providers / BYO MCP"]
  bad["Direct internet"]
  sc -->|allowed by pod egress policy| gw
  gw --> prov
  agent -. DENIED by pod egress policy .-> bad
```

The sidecar runs in the agent's pod. The agent talks to `127.0.0.1:8001`; the sidecar is the only thing allowed to leave the pod, and only to the gateway. A hardcoded `api.openai.com` call is dropped by the pod's egress NetworkPolicy. The agent never holds provider keys and cannot assume another tenant — the sidecar stamps both.

## What it deploys versus the full profile

```mermaid
---
config:
  theme: neutral
---
flowchart TB
  subgraph keep["Kept in perimeter (the boundary)"]
    k1["Envoy Gateway + EnvoyProxy dataplane"]
    k2["Envoy AI Gateway: key injection, global RPM"]
    k3["MCP gateway: deny / RPM / audit"]
    k4["aigateway MCP backend"]
    k5["stateless sidecar (per wrapped agent, no DB)"]
    k6["per-pod egress NetworkPolicy"]
  end
  subgraph opt["Off by default, opt-in (no datastore needed)"]
    o1["NeMo guardrails"]
    o2["gVisor sandbox MCP + workers"]
  end
  subgraph drop["Disabled in perimeter (the runtime)"]
    d1["Aegra agent host + thread/run persistence"]
    d2["Postgres, ClickHouse, Valkey, Qdrant, SeaweedFS"]
    d3["Langfuse web + worker"]
    d6["postgres / qdrant / object MCP"]
  end
  note["Default result: under 90s install, under 500 MB RAM, no datastores"]
  keep --- note
  opt --- note
  drop --- note
```

The sidecar's footprint lives in your agent's pod, not in the perimeter install — so the gateway stays under 500 MB and zero-DB no matter how many agents you wrap.

## What happens to a request

```mermaid
---
config:
  theme: neutral
---
sequenceDiagram
  autonumber
  participant A as Your agent
  participant S as Sidecar (127.0.0.1:8001)
  participant G as Gateway /v1 and /mcp
  participant P as Provider / MCP
  participant L as Access log (stdout)
  A->>S: /v1 or /mcp call (localhost)
  S->>S: attach tenant JWT and provider key
  S->>S: per-run budget / RPM check
  S->>G: forward (only egress the pod allows)
  G->>G: global RPM, tool-deny, key injection
  G->>P: forwarded request
  P-->>A: response
  G->>L: audit metadata (tenant, tool, bytes, status — no bodies)
```

## Install

Laptop `kind`:

```bash
OPENAI_API_KEY=sk-... ./install.sh --profile=perimeter
```

On kind the installer skips the datastore, Langfuse, Aegra, and demo phases and does not install gVisor, so a perimeter install is a fraction of a full install. Add `--with-guardrails` or `--with-sandbox` for the optional planes ([below](#optional-guardrails-and-code-sandbox)).

On any other cluster, use the same production installer as the full profile with `--profile perimeter`. Supply at least one provider credential, the agents hostname, and your identity provider's tenant-JWT contract (the gateway and the sidecar verify every caller's token). It skips the datastore operators, Langfuse, and gVisor (unless you add `--with-sandbox`):

```bash
OPENAI_API_KEY=sk-... ./scripts/install-production.sh --profile perimeter \
  --hosts-agents agents.example.com \
  --jwt-issuer https://idp.example.com --jwt-audience zelkor --jwks-file ./jwks.json
```

With Helm or GitOps directly, layer the one-line perimeter overlay on the production overlay. Give the JWKS either as a file (`--jwks-file` above) or as your IdP's URL (`remoteJwksUri` here, plus the CIDR of that endpoint, because egress is default-deny):

```bash
helm upgrade --install zelkor-platform charts/zelkor-platform \
  -f profiles/values-production.yaml -f profiles/values-perimeter.yaml \
  --set workspace.models.providers.openai.apiKey=sk-... \
  --set gateway.hosts.agents=agents.example.com \
  --set platform.tenants.jwt.issuer=https://idp.example.com \
  --set "platform.tenants.jwt.audiences={zelkor}" \
  --set platform.tenants.jwt.remoteJwksUri=https://idp.example.com/.well-known/jwks.json \
  --set "platform.tenants.jwt.jwksEgressCIDRs={<idp-cidr>}"
```

## Deploy and call an agent

Deploy from your agent's project directory exactly as in the full profile. `zelkor deploy` reads the platform's profile and, on a perimeter, runs the agent behind the stateless (no-database) sidecar and locks the pod's egress to the gateway. A deploy-first project (`agent.json` + `AGENTS.md`) needs nothing more; your own Dockerfile serving A2A must read `OPENAI_BASE_URL` and `MCP_URL`, which `zelkor deploy` points at the sidecar. Name the MCP tool prefixes the agent may use — the extra backends you registered under `workspace.tools` ([Register extra MCP backends](mcp-extra-backends.md)), since the built-in Postgres and Qdrant tools are off unless you point them at your own databases ([below](#use-your-existing-databases)), and the `sandbox` tool exists only with the sandbox opt-in — or pass `--all-tools`:

```bash
zelkor deploy --tools crm
```

LangGraph projects run on the Aegra runtime, which only the full profile has; `zelkor deploy` stops with that message before changing anything.

Call the agent through the agents host, the same front door as the full profile (with a `zelkor env` for this cluster and a tenant token; see [CLI](cli.md)):

```bash
zelkor run --input "Summarize tenant usage"
```

Run history lives in the sidecar's memory: it survives neither a pod restart nor a second replica. Keep one replica per agent.

## Agents you do not wrap

If an agent is not wrapped by `zelkor deploy` — for example a black-box workload, or an agent in another cluster — the gateway becomes an **opt-in proxy**: it enforces key injection, rate limits, tool-deny, and audit on traffic sent to it, but nothing compels that agent to use it. To make egress mandatory for such workloads, apply a default-deny-egress NetworkPolicy to their namespace (allow egress only to the gateway Service and DNS), or use a cluster egress firewall. See [Network Isolation](architecture-network.md).

## Observability

The database is off, so there is no Langfuse trace UI — but the gateway still reports **per-request token usage** to stdout as structured JSON. Every `/v1` call emits an `llm_access` log line with the tenant, model, input / output / total token counts, response code, and timing — never prompt or completion bodies. Scrape it from pod logs or your existing log pipeline to track usage and cost without a datastore.

**Send traces to your own backend (optional).** Set `platform.telemetry.otlp.endpoint` to an OTLP collector and the AI gateway exports every `/v1` LLM call as a standard OpenTelemetry GenAI span — view it in Tempo, Jaeger, Datadog, Honeycomb, or Phoenix, no bundled datastore required. Agents you wrap with `zelkor deploy` export the full **run → LLM → tool** trace to the same collector, so one waterfall spans the agent and the gateway. They send it **through the gateway**, not to the collector directly: the agent's network policy still allows only the gateway and DNS, and the collector's address and credentials never reach the agent pod. Message content is off by default (`platform.telemetry.otlp.captureContent: false`). Community Edition uses **one** trace sink at a time: bundled Langfuse (the full profile) or a single OTLP endpoint (perimeter); setting both is rejected at install.

## What it does not include

Because the perimeter is zero-database, these are off by design:

- **No trace UI.** Langfuse is off, so there is no waterfall view. The gateway still emits the `llm_access` token log and MCP audit metadata to stdout (see [Observability](#observability)).
- **No Aegra agent host and no persistence.** Wrapped agents are published on the agents host, but the stateless sidecar keeps threads and runs in memory only, and LangGraph projects need the Aegra host. For durable run history, LangGraph agents, and the trace UI, use the full profile.
- **No code sandbox and no guardrails by default.** gVisor and NeMo are off to hold the memory budget; both are opt-ins ([next section](#optional-guardrails-and-code-sandbox)).

When you need durable runs, LangGraph agents, or the trace UI, install the full profile (the default) — it is the same gateway and sidecar with the persistence and trace planes turned on, and guardrails and the sandbox on by default. See [Helm Install](helm-install.md) and [Local Quickstart](quickstart.md).

## Optional guardrails and code sandbox

Neither plane needs a datastore, so a perimeter can add them and stay zero-database:

| Opt-in | What you get | Kind | Production | Helm |
| :--- | :--- | :--- | :--- | :--- |
| Guardrails | [NeMo guardrails](nemo-guardrails.md) check every `/v1` prompt and reply against a safety policy and block unsafe ones | `--with-guardrails` | `--with-guardrails` | `perimeter.guardrails=true` |
| Code sandbox | the `sandbox` MCP tool, which runs generated code in a [gVisor sandbox](architecture-sandbox.md) | `--with-sandbox` (installs gVisor on the kind node) | `--with-sandbox`; the installer uses gVisor already on your nodes, or installs it with `--install-gvisor`, and otherwise stops before changing anything | `perimeter.sandbox=true` (nodes need the gVisor RuntimeClass) |

```bash
OPENAI_API_KEY=sk-... ./install.sh --profile=perimeter --with-guardrails --with-sandbox
```

What each opt-in costs:

- **Memory.** The under-500 MB figure is for the default perimeter. NeMo requests about 256 MB, and the sandbox adds an orchestrator plus three warm workers of about 128 MB each.
- **Model calls.** Guardrails judge each request and reply with your default model, so every agent call costs extra model calls.

Deploy an agent that may run code with `zelkor deploy --tools sandbox` (add your other prefixes, for example `--tools sandbox,crm`). With an OTLP endpoint set, NeMo's rail spans join the agent's trace in your collector, sent through the gateway like the agents' spans.

## Use your existing databases

Zelkor's Postgres and Qdrant tools can work on databases you already run, so tenants stay isolated over your data while the perimeter still installs no database. The tools receive each caller's verified token and scope every call to that tenant: Postgres queries run read-only with the tenant set for row-level security, and Qdrant searches only return documents whose `tenant_id` matches.

```yaml
perimeter:
  dataTools:
    postgres: true
    qdrant: true
workspace:
  tools:
    postgresMCP:
      databaseUrlSecretRef: {name: crm-db, key: url}   # Secret with postgresql://user:pass@host:5432/db
      egressTo: [{namespace: crm-data, port: 5432}]   # where the tool may connect
    qdrantMCP:
      url: http://qdrant.crm-data.svc.cluster.local:6333
      collection: policies                             # your collection (default: documents)
      egressTo: [{namespace: crm-data, port: 6333}]
```

Create the Secret in the platform's namespace first, then add the values to your platform overlay (`-f` with `install-production.sh` or `helm upgrade`):

```bash
kubectl -n zelkor create secret generic crm-db \
  --from-literal=url='postgresql://crm_mcp:<password>@postgres.crm-data.svc.cluster.local:5432/crm'
```

Give an agent the tools with `zelkor deploy --tools postgres,qdrant` (plus your other prefixes).

Your database has to do its part. Postgres isolation holds only if:

- each table the agent may read has a row-level security policy on the session tenant, for example `USING (tenant_id = current_setting('app.current_tenant', true))`, with `FORCE ROW LEVEL SECURITY`;
- the login in the Secret is a plain role: not a superuser, not `BYPASSRLS`, and granted only `SELECT` on those tables.

A role that bypasses row-level security returns every tenant's rows. Qdrant documents need a `tenant_id` payload field.

Without the opt-in, or for any other tool, register your own MCP server instead ([Register extra MCP backends](mcp-extra-backends.md)). The gateway then sends it the caller's tenant as a header it sets itself, never the token, and isolation inside that server is the server's job.

