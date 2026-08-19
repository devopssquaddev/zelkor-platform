# Zelkor Platform — Contributor Guide

This is the **public open-source repository**. Product code lives here.

## Repository Layout

```
zelkor-platform/
├── install.sh                  # Local bootstrap (kind + Helm)
├── charts/zelkor-platform/     # Unified Helm chart
│   ├── values.yaml             # Base Tier defaults
│   └── values-local.yaml       # Local kind overrides
├── docs/quickstart.md          # Getting started
└── .cursor/rules/              # AI engineering role rules
```

## Local Development

```bash
./install.sh
```

Prerequisites: Docker, `kind`, `helm`, `kubectl`.

## Engineering Rules

- All LLM calls route through **LiteLLM** — never connect agents directly to providers
- **Langfuse** tracing must be enabled on all agent executions
- Untrusted workloads use **gVisor** (`RuntimeClass: gvisor`)
- Tenant isolation via Aegra `@auth.authenticate` handlers
- No `kubectl apply` — all deployments are Helm/GitOps declarative

## Pull Requests

1. Branch from `main`
2. CI runs adversarial evals on changes to `gateway/`, `agents/`, `guardrails/`
3. Keep PRs focused — one feature or fix per PR

## License

Apache 2.0 — see [LICENSE](LICENSE).
