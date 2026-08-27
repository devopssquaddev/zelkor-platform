# Zelkor Platform — Contributor Guide

This is the **public open-source repository**. Product code lives here.

## Repository Layout

```
zelkor-platform/
├── install.sh                  # Local bootstrap (kind + Helm)
├── scripts/build-images.sh     # Build/push/kind-load first-party images
├── images/                     # Dockerfiles for Aegra, MCP, guardrails, sandbox, FinServe
├── profiles/
│   └── values-local.yaml       # Kind overlay — secrets/hosts; not in the production chart
├── charts/zelkor-platform/     # Unified Helm chart (platform only)
│   └── values.yaml             # Production defaults — no passwords, localhost, or demo knobs
├── examples/                   # Demo apps — separate Helm charts (not in the platform chart)
│   └── finserve/               # FinServe demo (see internal/requirements/demo/)
│       ├── chart/              # Standalone Helm release
│       └── tests/
├── agents/                     # Platform auth handlers (tenant isolation)
├── mcp/                        # Native MCP servers (copied into zelkor-mcp image)
├── tests/                      # Platform integration tests (env-agnostic)
├── docs/quickstart.md          # Getting started
└── .cursor/rules/              # AI engineering role rules
```

## Examples (demo applications)

Demo workloads validate the platform but are **not** bundled into the production chart.

- Each demo lives under `examples/<name>/` with its own chart at `examples/<name>/chart/`.
- Platform chart + `tests/` must work with `INSTALL_EXAMPLES=false` then `pytest tests/`.
- No demo-shaped defaults in `charts/zelkor-platform/values.yaml`. Local kind secrets/hosts live in `profiles/values-local.yaml`. Demos overlay from `examples/<name>/chart/`.
- Do not reference `examples/` from `charts/zelkor-platform/`.
- Production deploys: platform chart only. Local/test: `install.sh` runs platform + example charts (two Helm releases).
- Combined platform+demo tasks: implement platform first and stop; then overlay the demo. See `.cursor/rules/platform-demo-boundary.mdc`.
- Full layout: documented in `internal/requirements/dev/examples_and_demos.md` (read from multi-root workspace).

## Local Development

```bash
./install.sh
```

Prerequisites: Docker, `kind`, `helm`, `kubectl`.

## Engineering Rules

- All LLM calls route through **Envoy AI Gateway** — never connect agents directly to providers
- **Gateway API Standard (No Ingress-NGINX):** Never use `ingress-nginx` (retired in 2026). Ingress and external routing must use **Kubernetes Gateway API (`gateway.networking.k8s.io/v1`)** with **Envoy Gateway**
- **Requirements & Living Spec Synchronization:** Any functional, architectural, configuration, or test change must be synchronized with governing requirements in `internal/plan/` or `internal/requirements/` with an updated `## Revision History`.
- **Deprecation & Lifecycle Policy:** Always verify all third-party components, base images, and libraries are actively maintained and not deprecated or EOL
- **Component Version Policy:** Pin latest **stable** releases at each Zelkor semver release; hold pins until the next release. Choose Postgres/ClickHouse/Valkey/etc. from **Langfuse + Aegra compatibility**; pin operators to the latest stable release that supports those datastore versions. See `.cursor/rules/component-versions.mdc` and `internal/plan/component_compatibility_matrix.md`.
- **Langfuse** tracing must be enabled on all agent executions
- Untrusted workloads use **gVisor** (`RuntimeClass: gvisor`)
- Tenant isolation via Aegra `@auth.authenticate` handlers
- No `kubectl apply` — all deployments are Helm/GitOps declarative
- **No inline Python in ConfigMaps:** App modules live in container images (`images/`, `ghcr.io/devopssquaddev/zelkor-*`). Helm `files/` is for config (SQL, Colang, `aegra.json`), not application source. See `.cursor/rules/helm-python-packaging.mdc`.
- **Git Commit & Tagging Standard:** Commit major milestones with Conventional Commits; create annotated tags (`git tag -a`) for release points and major architectural milestones.

## Branching

Trunk-based development: `main` is the always-mergeable trunk. Use short-lived feature branches — no long-lived `develop`, `release`, or `phase/*` branches.

| Layer | Strategy |
|-------|----------|
| **`zelkor-platform` (this repo)** | Feature branches → PR → squash merge to `main`; tag semver CE releases |
| **`internal` (private)** | Local-only planning; commit to local `main`; never pushed |
| **`zelkor-platform-enterprise` (Phase 2+)** | Separate private repo; overlay tags pinned to CE semver |

**Branch naming:** `feat/<scope>-<description>`, `fix/<scope>-<description>`, `chore/<scope>-<description>`

Scopes: `install`, `helm`, `agents`, `finserve`, `ci`

**Phases** (1–4 in `internal/plan/`) are planning milestones and semver tags — not git branches.

**CE release tags on `main`:** `v0.1.0-alpha` (local kind install), `v0.2.0-alpha` (production chart), `v0.3.0` (tenant isolation + FinServe), `v1.0.0-ce` (Phase 1 complete).

## Pull Requests

1. Branch from `main`
2. Complete the **Minimal PR checklist** (multi-root workspace: `internal/requirements/dev/agent_code_review.md`):
   - [ ] Bugbot on branch changes — no open Critical/High findings
   - [ ] Security Review if Helm, Terraform, auth, or security paths changed
   - [ ] Phase requirements checked when the change maps to a roadmap phase
   - [ ] Tests added/updated for behavior changes
   - [ ] CI green (adversarial eval when `gateway/`, `agents/`, or `guardrails/` changed)
   - [ ] Test-server validation via `internal/dev/` after merge
3. Squash merge after CI passes and review
4. Keep PRs focused — one feature or fix per PR

## License

Apache 2.0 — see [LICENSE](LICENSE).
