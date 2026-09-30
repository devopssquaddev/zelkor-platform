# Zelkor Platform — AI Agent Instructions

This is the **public open-source repository** for the Zelkor platform. Product code, Helm charts, and public documentation live here.

Zelkor's core advantage: **bring the agent you already wrote; it is sandboxed — it can't break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation.**

## Repository Layout

- `charts/zelkor-platform/`: Unified Helm chart for the platform. Production defaults only (no dev passwords or `*.localhost`).
- `charts/zelkor-agent/`: Helm chart for deploying customer agents as ClusterIP workers.
- `profiles/`: Local overlays (e.g., `values-local.yaml`) for kind/dev environments.
- `images/`: Dockerfiles for first-party images (Aegra runtime, MCP, guardrails, sandbox).
- `agents/`: Platform auth handlers for tenant isolation.
- `mcp/`: Native MCP servers (thin Postgres, Qdrant library wrap).
- `examples/`: Demo applications (e.g., FinServe) with standalone Helm charts.
- `scripts/`: Install and uninstall scripts (`install-production.sh`, `install-quickstart.sh`, `uninstall.sh`).
- `cli/`: The `zelkor` CLI source code.
- `docs/`: Public product documentation (published to the website).
- `tests/`: Env-agnostic platform integration tests.

## Engineering Rules for Agents

1. **Gateway API Standard:** Never use `ingress-nginx`. All ingress and routing must use Kubernetes Gateway API (`gateway.networking.k8s.io/v1`) with Envoy Gateway.
2. **No Dev Defaults in Platform:** Do not bake `*.localhost`, `dev-key`, or local passwords into `charts/zelkor-platform/values.yaml` or templates. Use `profiles/values-local.yaml` for dev overrides.
3. **Platform vs Demo Boundary:** Demos (`examples/`) are separate Helm charts. Do not put demo-shaped defaults or fixture tenants into the platform chart. Platform tests must pass with `INSTALL_EXAMPLES=false`.
4. **Agent Deployment (Drop-In Contract):** Customer agents are deployed as separate ClusterIP Deployments (`charts/zelkor-agent`), not merged into the platform's `aegra.graphs`. Envoy routes traffic by `X-Graph-ID` or `?graph_id=`.
5. **LLM Routing:** All LLM calls route through the Envoy AI Gateway `/v1` endpoint. Do not connect agents directly to providers. Add providers via Helm overlays.
6. **No Inline Python in Helm:** Do not paste application Python into ConfigMaps. App modules live in container images; config files live in `files/`.
7. **Component Versions:** Pin to exact stable semver tags for third-party components. Re-baseline related pins together.
8. **Platform Logging:** All processes must log to stdout in JSON format at the Helm-controlled level (`ZELKOR_LOG_LEVEL`). Do not log secrets or health probes at INFO.
9. **Git Workflow:** Commit to feature branches (`feat/`, `fix/`, `chore/`) and open a PR. Never commit directly to `main`. Use Conventional Commits.
10. **Documentation:** Write user-friendly, progressive-disclosure documentation in `docs/`. No internal jargon. Provide complete, copy-pasteable commands.

## Installing and Deploying

- **Platform Install:** See `docs/agent-install.md` for instructions on running `install-production.sh` or `install-quickstart.sh`.
- **Agent Deploy:** See `docs/agent-deploy.md` for instructions on deploying agents via `charts/zelkor-agent` or the `zelkor` CLI.