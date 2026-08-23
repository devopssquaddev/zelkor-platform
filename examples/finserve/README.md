# FinServe AI: Demo Reference Application

FinServe AI is a reference wealth management agent designed to validate multi-tenant isolation, stateful memory persistence, untrusted Python code execution, and Envoy AI Gateway routing on the Zelkor Platform.

## Architecture

- **Agent:** Python FastAPI application with read-only portfolio database querying and dynamic code execution tools.
- **AI Gateway & Routing:** Routes LLM requests through **Envoy AI Gateway** (`http://zelkor-platform-ai-gateway:8080/v1`) using team consumer keys and wildcard provider mappings.
- **Tenant Isolation:** Enforced via Aegra authentication handlers and database query scoping (`Bank_Alpha` vs `Bank_Beta`). Supports `Bearer dev:<tenant_id>` and `X-Tenant-ID` headers.
- **Untrusted Code Execution:** Sandboxed via `RuntimeClass: gvisor` on the `finserve-code-executor` workload to isolate execution in user-space.
- **Stateful Memory:** Managed via Aegra checkpointing backed by PostgreSQL and Valkey.
- **Instant Observability:** Pre-instrumented with Langfuse tracing (`http://langfuse.localhost:8088`). Captures PostgreSQL queries, Qdrant semantic vector search spans, and sandboxed code execution events under the pre-seeded `finserve` project.

## Deployment

FinServe is deployed as a standalone Helm release on local development or test environments:

```bash
helm upgrade --install finserve examples/finserve/chart \
  -f examples/finserve/chart/values-local.yaml \
  --wait --timeout 10m
```

## Testing

Run the integration test suite (BASE-01 to BASE-04):

```bash
pytest examples/finserve/tests/ -v
```
