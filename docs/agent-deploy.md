# Agent guide: Deploy customer agents on Zelkor

**Audience:** Coding agents. **Prerequisite:** Platform release installed in the target namespace — see [agent-install.md](agent-install.md) first.

Human docs: [quickstart.md](quickstart.md) (Deploying an Agent), [production.md](production.md) (Deploying Agents).

---

## Mental model (three planes)

| Plane | What it does | Agent code change |
| :--- | :--- | :--- |
| **Intercept** | Envoy AI Gateway on `/v1` — keys, NeMo, OTEL | None if LLM uses OpenAI-compatible client against gateway |
| **Aegra wrap** | Agent Protocol host; threads/checkpoints in **existing** platform Postgres | None for LangGraph/Aegra graphs in your image |
| **MCP** | Tools via in-cluster `MCP_URL` → `{release}-mcp` (Envoy MCPRoute on `/mcp`) | None if the graph already uses MCP; else enable inject (below) or register extra backends |

Register BYO MCP servers on the **platform** chart (`workspace.tools.extraBackends`). See [mcp-extra-backends.md](mcp-extra-backends.md).

Production agents use in-cluster `{release}-ai-gateway` and `http://{release}-mcp` as `MCP_URL` — not raw provider API keys on the pod. Each `tools/call` forwards the run's `Authorization` bearer (tenant JWT); do not pass `tenant_id` in tool arguments.

Off kind, set `ZELKOR_IMAGE_REGISTRY` or `zelkor deploy --registry` so the CLI does not assume `ghcr.io/devopssquaddev`.

**Adding a model or provider** is a **platform overlay** (`workspace.models.providers`, `openaiCompat`, `defaultModel`), not a change to agent chart core or `charts/zelkor-platform` templates. Per-agent default: `platform.defaultLlmModel` on `zelkor-agent`. See [adding-llm-providers-and-models.md](adding-llm-providers-and-models.md).

---

## Platform vs agent release

| Layer | Artifact | Graph registration |
| :--- | :--- | :--- |
| Platform front door | `zelkor-platform` → `{release}-aegra` | **`aegra.graphs` empty** in production chart |
| Your agent | Own image + **`charts/zelkor-agent`** Helm release (or demo chart under `examples/`) | HTTPRoute on `gateway.hosts.agents` via `sharedRoute` |

**Must not:** Add customer graphs to platform Aegra Deployment or platform `graphModules` ConfigMap. **Must not:** Publish a separate public hostname per agent unless explicitly opted in.

Demo apps (e.g. FinServe) use **separate** charts under `examples/` — not part of `install-production.sh`.

---

## Routing topologies (Envoy)

Envoy matches **Host + header/query** — not JSON bodies. Agent Protocol omits `graph_id` on stream/join/cancel; routing must use headers for multi-backend setups.

| Topology | Shape | Client must send |
| :--- | :--- | :--- |
| **1 — catch-all** | One backend; `sharedRoute.asDefault: true` | No `X-Graph-ID` on shared host |
| **2 — one graph per Deployment** | N `zelkor-agent` releases, each `graphId` set | `X-Graph-ID` or `?graph_id=` on **every** call to that backend |
| **3 — mixed** | Multi-graph image on one Service + extra Deployments | Header/query for non-default graphs; unmatched → platform Aegra |

First deployed agent can own catch-all (topology 1). Additional agents need topology 2 or 3.

---

## CLI vs GitOps

| Path | When | Langfuse OTEL |
| :--- | :--- | :--- |
| **`zelkor deploy`** | Laptop or CI that builds from a local agent tree | Copies `LANGFUSE_*` / `OTEL_TARGETS` from platform Aegra |
| **Helm overlay** (`charts/zelkor-agent` + your values) | Image already built and pushed (own Dockerfile, registry, extra MCP) | Set `platform.releaseName`. Chart envFrom `{release}-langfuse-otel` and constructs `http://{release}-langfuse:3000`. Do not paste keys. |

Do not run `zelkor deploy` against a tree that already has a GitOps image pipeline — the CLI rebuilds, pushes `zelkor-agent-<release>`, and writes a generated overlay.

## CE CLI (happy path)

```bash
pip install -e ./cli
zelkor env add <name> --kube-context <ctx> --namespace <ns>
zelkor init my-agent && cd my-agent
zelkor deploy
zelkor run --input "hello"
zelkor logs --no-follow --tail 50
zelkor undeploy
```

**Agent notes:**

- `ZELKOR_SKIP_BUILD=1` — image already in registry (CI / remote build). Still prefer a Helm overlay when CI owns the image tag.
- `deploy` picks LangGraph (`aegra.json` / `langgraph.json`) vs Deep Agents (`agent.json` + `AGENTS.md` → `zelkor-aegra-deep` base).
- `deploy` copies platform `imagePullSecrets`, Langfuse OTEL, and the **existing** Postgres/Valkey URLs from the namespace. It does not create a database.
- `undeploy` — `helm uninstall` **this agent release only**; platform stays.

---

## Persistence (do not provision a database)

Aegra stores threads, checkpoints, and runs in Postgres. That is why the chart requires `platform.databaseUrl` — not because each agent needs its own cluster.

**Happy path:** reuse the platform datastores already in the namespace.

| Value | Point at | Do not |
| :--- | :--- | :--- |
| `platform.databaseUrl` | Existing platform Aegra DB (typically `{release}-postgresql:5432/aegra`) | Create a CloudNativePG `Database`, a new cluster, or a per-agent schema |
| `platform.valkeyUrl` | Existing platform Valkey Service | Deploy another Valkey |
| `redis.prefix` | Unique key namespace (`aegra:<release>` if empty) | Share default `aegra:jobs` / `aegra:run:` across Deployments |

`charts/zelkor-agent` has no CNPG resources. Demo charts (FinServe) may create a CNPG `Database` for **application / MCP** data — that is not the Aegra checkpointer and is not part of this chart.

A dedicated checkpointer DSN is an optional overlay when you need `runs` isolated from other agents. It is not required to deploy.

---

## Manual / GitOps (`charts/zelkor-agent`)

Required values (see `charts/zelkor-agent/values.yaml`):

| Value | Purpose |
| :--- | :--- |
| `graphId` or `graphIds[]` | Routing key(s) |
| `image.repository` / tag / digest | `FROM zelkor-aegra` or `zelkor-aegra-deep` |
| `platform.databaseUrl`, `platform.valkeyUrl` | Existing platform Aegra DSN + Valkey (see Persistence) |
| `platform.releaseName` or MCP / AI gateway / Langfuse URLs | `{release}-mcp` / `{release}-ai-gateway` / `{release}-langfuse` + envFrom `{release}-langfuse-otel`, or copy from platform Aegra env |
| `sharedRoute.host`, `gatewayName`, `gatewayNamespace`, `asDefault` | Register on shared agents host. Empty `gatewayName` + `releaseName` → `{release}-gateway`. |
| `redis.prefix` | Isolate Valkey keys per Deployment (sets channel + job queue) |

Chart can emit HTTPRoute when `sharedRoute` is set; otherwise add routes via GitOps.

### Kubernetes probes (in-cluster)

Zelkor runtime images (`zelkor-aegra`, `zelkor-aegra-deep`) serve health on port **8000**. The chart configures kubelet probes against the pod **ClusterIP** Service (not the public agents host):

| Path | Probe | Purpose |
| :--- | :--- | :--- |
| `/health` | startup | Process is up |
| `/live` | liveness | Keep pod running |
| `/ready` | readiness | Accept traffic (503 if Mode B MCP inject is not ready) |

Tune `startupProbe` / `livenessProbe` / `readinessProbe` in `values.yaml`; do not change paths unless you use a non-Aegra base image.

Example:

```bash
helm upgrade --install my-agent charts/zelkor-agent \
  --namespace zelkor \
  --set graphId=my-agent \
  --set platform.releaseName=<platform-release> \
  --set sharedRoute.host=agents.example.com \
  --set sharedRoute.gatewayNamespace=zelkor \
  --set image.repository=ghcr.io/org/my-agent \
  --set platform.databaseUrl='postgresql://USER:PASS@<platform-release>-postgresql:5432/aegra' \
  --set platform.valkeyUrl='redis://:PASS@<platform-release>-valkey:6379/0' \
  --set redis.prefix=aegra:my-agent \
  ...
```

`platform.releaseName` fills `openaiBaseUrl`, `mcpUrl` (`http://{release}-mcp`), `langfuseBaseUrl`, and `sharedRoute.gatewayName` as `{release}-ai-gateway` / `{release}-langfuse` / `{release}-gateway`. The runtime appends `/mcp` when calling the dataplane. Workers inject `{release}-langfuse-otel` (optional Secret the platform chart writes from `platform.telemetry.langfuse.init`). Override those fields when Service names differ. Copy `databaseUrl` / `valkeyUrl` from the live platform Aegra Deployment (or `zelkor deploy`). Do not put Langfuse keys in the customer overlay.

### MCP tool inject (Mode B)

When `platform.mcpInject: true` (chart default), the worker sets `MCP_INJECT_ENABLED` and lists tools from `MCP_URL` on each run. Bind named tools in the graph module with `MCP_INJECT_TOOLS = ("postgres__query",)` (or set `platform.mcpInjectToolPrefixes` when modules omit prefixes). For startup `tools/list` before inbound traffic, mount a tenant JWT via `platform.mcpAuthTokenSecret` (platform chart can write one when `localSigning` is enabled). Readiness stays 503 until inject succeeds.

### Auth (tenant JWT)

Configure **`platform.tenants.jwt`** on the platform release: `issuer`, `audiences`, and JWKS (`jwks`, `jwksConfigMap`, or `remoteJwksUri`). Production installs pass `--jwt-issuer`, `--jwks-file`, and `--jwt-audience` to `install-production.sh`. Kind lab only: `platform.tenants.jwt.localSigning.enabled: true` in `profiles/values-local.yaml` (not chart defaults).

Clients and agent runs send `Authorization: Bearer <RS256 JWT>` with a `tenant_id` claim (also `org_id` / `sub` when mapped). The wrap handler forwards that bearer to MCP; MCP verifies JWT and derives tenant context — not a bare `X-Tenant-ID` header from clients.

Mint lab tokens after install:

```bash
export AUTH_JWT_ISSUER=https://local.zelkor.invalid   # match platform.tenants.jwt.issuer in your overlay
zelkor token mint --release <platform-release> --tenant <tenant_id> --namespace <ns>
```

On `charts/zelkor-agent`, set `auth.issuer` / `auth.audiences` or rely on `{release}-tenant-jwks` when `platform.releaseName` is set. Blueprint: `examples/finserve/chart/values-tenants.yaml` + `values-platform-overlay-tenants.yaml`.

---

## Verify

```bash
kubectl -n <ns> get deploy,svc,httproute -l app.kubernetes.io/instance=<release>
# Topology 2+: every client call includes graph id
curl -sS -H "Host: <gateway.hosts.agents>" -H "X-Graph-ID: <graphId>" https://<agents-host>/...
```

Agent pods should emit Langfuse OTEL when `platform.releaseName` is set (GitOps inherit) or when `zelkor deploy` copied keys from platform.

---

## Agent must-not (deploy)

- Patch `charts/zelkor-platform` to register your graph.
- Set `OPENAI_API_KEY` to a public provider — use in-cluster AI gateway.
- Provision a new Postgres cluster or CNPG `Database` for the agent checkpointer.
- Copy FinServe `cnpgClusterName` / CNPG templates onto `zelkor-agent`.
- Reuse the same Redis queue key across multiple agent Deployments.
- Add Routes that bypass Envoy graph routing on the shared agents host.
- Rely on unsigned tokens, `dev:` prefixes, or header-only tenant identity on production clusters (removed from the platform contract).

---

## See also

- [agent-install.md](agent-install.md) · [quickstart.md](quickstart.md) · [production.md](production.md)
