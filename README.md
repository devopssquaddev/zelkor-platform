# Zelkor Platform

Self-hosted infrastructure to deploy, test, govern, and run AI agents in production.

Zelkor wraps battle-tested open-source components — **Aegra**, **Envoy AI Gateway**, **Langfuse**, **NeMo Guardrails**, and **Qdrant** — into a unified Kubernetes deployment. It is an open-source alternative to LangGraph Platform and LangSmith for teams that need to run agents on their own infrastructure.

## Quick Start

**Prerequisites:** Docker, `kind`, `helm`, `kubectl` (macOS, Linux, or Windows via WSL2).

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform
./install.sh
```

See [docs/quickstart.md](docs/quickstart.md) for details.

## What's Included (Base Tier)

| Component | Role |
|-----------|------|
| **Aegra** | Stateful agent orchestrator (LangGraph alternative) |
| **Envoy AI Gateway** | LLM API gateway, MCP router, and OTel GenAI telemetry |
| **NeMo Guardrails** | CPU-native conversational boundaries and dialog rails |
| **Langfuse** | Observability, tracing, and evaluations |
| **Qdrant** | Semantic memory and vector search |
| **PostgreSQL / Valkey / ClickHouse** | Databases for state, cache, and analytics |

Baseline sandboxing via **gVisor** (`runsc`) for untrusted code execution workloads.

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Kubernetes Cluster                  │
│  ┌─────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │  Aegra  │  │   Envoy     │  │   Langfuse   │ │
│  │(runtime)│  │ AI Gateway  │  │(observability│ │
│  └────┬────┘  └──────┬──────┘  └───────┬──────┘ │
│       │              │                 │        │
│  ┌────┴──────────────┴─────────────────┴──────┐ │
│  │  PostgreSQL │ Valkey │ ClickHouse │ Qdrant │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

## For Enterprise

Need SSO/SAML, hardware sandboxing (Kata Containers), mTLS, audit logging, or HIPAA/PCI DSS compliance packs?

Contact us for **Zelkor Enterprise** — self-hosted Helm charts with operational SLAs.

<!-- auth.sso.enabled: true  — requires Enterprise license -->

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## Contributing

See [AGENTS.md](AGENTS.md) and [docs/quickstart.md](docs/quickstart.md).
