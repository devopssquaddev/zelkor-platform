# Agent guide: Deploy customer agents on Zelkor

**Audience:** Coding agents. **Prerequisite:** Platform release installed in the target namespace — see [agent-install.md](agent-install.md) first.

Human docs: [quickstart.md](quickstart.md) (Deploying an Agent), [production.md](production.md) (Deploying Agents).

---

## Mental model (three planes)

| Plane | What it does | Agent code change |
| :--- | :--- | :--- |
| **Intercept** | Envoy AI Gateway on `/v1` — keys, NeMo, OTEL | None if LLM uses OpenAI-compatible client against gateway |
| **Aegra wrap** | Agent Protocol host, threads, tenant auth | None for LangGraph/Aegra graphs in your image |
| **MCP** | Tools via `MCP_URL` / gateway | None if graph already uses MCP; else platform injects or you register backends |

Production agents use in-cluster `*-ai-gateway` and optional `MCP_URL` — not raw provider API keys on the pod.

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

- `ZELKOR_SKIP_BUILD=1` — image already in registry (CI / remote build).
- `deploy` picks LangGraph (`aegra.json` / `langgraph.json`) vs Deep Agents (`agent.json` + `AGENTS.md` → `zelkor-aegra-deep` base).
- `deploy` copies platform `imagePullSecrets`, Langfuse OTEL, Postgres/Valkey URLs from the namespace.
- `undeploy` — `helm uninstall` **this agent release only**; platform stays.

---

## Manual / GitOps (`charts/zelkor-agent`)

Required values (see `charts/zelkor-agent/values.yaml`):

| Value | Purpose |
| :--- | :--- |
| `graphId` or `graphIds[]` | Routing key(s) |
| `image.repository` / tag / digest | `FROM zelkor-aegra` or `zelkor-aegra-deep` |
| `platform.databaseUrl`, `platform.valkeyUrl`, MCP / AI gateway URLs | Same namespace as platform |
| `sharedRoute.host`, `gatewayName`, `gatewayNamespace`, `asDefault` | Register on shared agents host |
| `redis.channelPrefix`, `redis.queueKey` | **Isolate** Valkey keys per Deployment |

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
  --set sharedRoute.host=agents.example.com \
  --set sharedRoute.gatewayName=zelkor-platform-gateway \
  --set sharedRoute.gatewayNamespace=zelkor \
  --set image.repository=ghcr.io/org/my-agent \
  --set platform.databaseUrl=postgresql://... \
  ...
```

---

## Verify

```bash
kubectl -n <ns> get deploy,svc,httproute -l app.kubernetes.io/instance=<release>
# Topology 2+: every client call includes graph id
curl -sS -H "Host: <gateway.hosts.agents>" -H "X-Graph-ID: <graphId>" https://<agents-host>/...
```

Agent pods should emit Langfuse OTEL when CLI deploy copied keys from platform.

---

## Agent must-not (deploy)

- Patch `charts/zelkor-platform` to register your graph.
- Set `OPENAI_API_KEY` to a public provider — use in-cluster AI gateway.
- Reuse the same Redis queue key across multiple agent Deployments.
- Add Routes that bypass Envoy graph routing on the shared agents host.

---

## See also

- [agent-install.md](agent-install.md) · [quickstart.md](quickstart.md) · [production.md](production.md)
