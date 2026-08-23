# Zelkor Platform — Contributor Guide

This is the **public open-source repository**. Product code lives here.

## Repository Layout

```
zelkor-platform/
├── install.sh                  # Local bootstrap (kind + Helm)
├── charts/zelkor-platform/     # Unified Helm chart (platform only)
│   ├── values.yaml             # Base Tier defaults — no demo toggles
│   └── values-local.yaml       # Local kind overrides — platform only
├── examples/                   # Demo apps — separate Helm charts (not in platform chart)
│   └── finserve/               # FinServe demo (see internal/requirements/demo/)
│       ├── chart/              # Standalone Helm release
│       ├── finserve_agent.py
│       └── tests/
├── agents/                     # Platform auth handlers (tenant isolation)
├── tests/                      # Platform integration tests (env-agnostic)
├── docs/quickstart.md          # Getting started
└── .cursor/rules/              # AI engineering role rules
```

## Examples (demo applications)

Demo workloads validate the platform but are **not** bundled into the production chart.

- Each demo lives under `examples/<name>/` with its own chart at `examples/<name>/chart/`.
- **Do not** add `finserve.enabled` or other demo toggles to `charts/zelkor-platform/values.yaml`.
- Production deploys: platform chart only. Local/test: `install.sh` runs platform + example charts (two Helm releases).
- Full layout: documented in `internal/requirements/dev/examples_and_demos.md` (read from multi-root workspace).

## Local Development

```bash
./install.sh
```

Prerequisites: Docker, `kind`, `helm`, `kubectl`.

## Engineering Rules

- All LLM calls route through **Envoy AI Gateway** — never connect agents directly to providers
- **Langfuse** tracing must be enabled on all agent executions
- Untrusted workloads use **gVisor** (`RuntimeClass: gvisor`)
- Tenant isolation via Aegra `@auth.authenticate` handlers
- No `kubectl apply` — all deployments are Helm/GitOps declarative

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
