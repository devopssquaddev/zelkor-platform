# FinServe AI: Demo Reference Application

FinServe AI is a reference wealth management agent designed to validate multi-tenant isolation, stateful memory persistence, and untrusted Python code execution on the Zelkor Platform.

## Architecture

- **Agent:** Python application with read-only portfolio database querying and dynamic code execution tools.
- **Tenant Isolation:** Enforced via Aegra authentication handlers and database scoping (`Bank_Alpha` vs `Bank_Beta`).
- **Untrusted Code Execution:** Sandboxed via `RuntimeClass: gvisor` on the `finserve-code-executor` workload.
- **Stateful Memory:** Managed via Aegra checkpointing.

## Deployment

FinServe is deployed as a standalone Helm release on local development or test environments:

```bash
helm upgrade --install finserve examples/finserve/chart \
  -f examples/finserve/chart/values-local.yaml \
  --wait --timeout 10m
```
