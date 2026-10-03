---
title: Use the zelkor CLI
description: Install the CLI, target a cluster env, deploy an agent, run a graph, and inspect platform endpoints.
type: how-to
sidebar_group: Agents
sidebar_order: 20
audience: both
edition: ce
---

# Use the zelkor CLI

The `zelkor` CLI packages LangGraph, Aegra, and Deep Agents projects into a **`zelkor-agent` Helm release**. It discovers the live platform (database URL, AI Gateway `/v1`, `MCP_URL`, agents Host) from Kubernetes — it does **not** install the platform chart.

Your agent keeps running on Zelkor’s sandbox: calls go through the AI Gateway and MCP gateway; the CLI copies platform auth and trace settings onto the worker Deployment.

## Prerequisites

- Python 3.10+ and `pip`.
- `kubectl` and `helm` on your PATH.
- A running Zelkor platform in a namespace you can reach.
- For `zelkor run`: `langgraph-sdk` installed in the same environment as the CLI.

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform
pip install -e ./cli
zelkor version
```

## Point at a cluster

Named **envs** store only kube context and namespace — no hosts, tokens, or DSNs.

```bash
zelkor env add staging \
  --kube-context my-eks \
  --namespace zelkor

zelkor env use staging
zelkor env list
```

Override for one command: `zelkor status --env staging`.  
Store file: `~/.zelkor/envs.yaml` or project `.zelkor/env` (override with `ZELKOR_ENV_FILE`).

`zelkor dev` prefers an env named `local` when present (kind overlay); otherwise it uses the current env.

## Scaffold a project

```bash
mkdir my-agent && cd my-agent
zelkor init
```

Creates `agent.json` and `AGENTS.md`. Add your graph source and optional `tools.json` for MCP server names.

## Deploy and run

From the project directory (parent of `charts/zelkor-agent` on your machine or set `ZELKOR_AGENT_CHART` / `--chart`):

```bash
zelkor deploy --env staging --registry ghcr.io/myorg
```

- **Non-kind clusters:** `--registry` or `ZELKOR_IMAGE_REGISTRY` is required.
- **Kind:** registry defaults to `ghcr.io/devopssquaddev`; image loads with `kind load` when not pushing.
- **Skip local build:** `ZELKOR_SKIP_BUILD=1 zelkor deploy` when the image is already in the registry.
- **Prepared values overlay:** `zelkor deploy -f path/to/values.yaml` builds a sibling `Dockerfile` (context: repo root), then Helm-installs. Kind load on kind; `--registry` / `ZELKOR_IMAGE_REGISTRY` required off kind. `ZELKOR_SKIP_BUILD=1` skips docker. Docker/kind output streams to stderr. After Helm, wait prints replica status and a tail of current-hash pod logs every ~10s. Empty `platform.*` and `sharedRoute.host` are filled from the live cluster. Repeat `-f` (Helm-style). `image.tag` stays the values file (lab `ZELKOR_IMAGE_TAG` does not override). Catalog overlays: `examples/armored-agents/`.
- **Platform MCP extras:** if `tools.json` names servers not registered in `workspace.tools.extraBackends`, deploy fails with a GitOps snippet — fix the platform overlay first ([Register extra MCP backends](mcp-extra-backends.md)).

Optional workload intent (compiled to Helm values):

```bash
zelkor deploy --timeout 120s --max-tokens 4096
```

`--approval-threshold` exits non-zero on Community Edition (Human-in-the-loop is Pro).

Run one Agent Protocol stream against the discovered agents host:

```bash
export ZELKOR_AUTH_TOKEN="Bearer <tenant-jwt>"
zelkor run --input "Summarize tenant usage"
```

Optional: `--url`, `--auth`, `--graph-id`. Non-default graphs need `X-Graph-ID`; the CLI sets it when your release is not the catch-all route.

## Inspect and undeploy

```bash
zelkor status --env staging
zelkor doctor --env staging
zelkor logs --tail 100 --no-follow
zelkor undeploy
```

`doctor` checks discovered `DATABASE_URL`, `OPENAI_BASE_URL`, `MCP_URL`, and agents Host on the platform Aegra Deployment.

## Global flags

| Flag | Purpose |
| :--- | :--- |
| `--env` | Named env (kube context + namespace) |
| `--chart` | Path to `charts/zelkor-agent` |
| `--platform-chart` | Path to `charts/zelkor-platform` (undeploy default-route restore) |

Environment variables: `ZELKOR_AGENT_CHART`, `ZELKOR_PLATFORM_CHART`, `ZELKOR_IMAGE_TAG`, `ZELKOR_DEEP_IMAGE`, `ZELKOR_AGENTS_URL`, `ZELKOR_AUTH_TOKEN`.

## Command reference

Commands registered by the `zelkor` binary:

| Command | CE | Description |
| :--- | :---: | :--- |
| `init [dir]` | ● | Write `agent.json` + `AGENTS.md` |
| `dev [dir]` | ● | Build and `helm upgrade` without registry push |
| `deploy [dir]` | ● | Build, push (or kind load), `helm upgrade` agent release |
| `deploy -f FILE` | ● | Build sibling Dockerfile unless `ZELKOR_SKIP_BUILD=1`; Helm-install overlay |
| `undeploy [dir]` | ● | `helm uninstall` agent; restore platform default route if needed |
| `run [dir]` | ● | Create thread + stream run (`langgraph-sdk`) |
| `logs [dir]` | ● | `kubectl logs` on agent Deployment (`-f` default) |
| `status` | ● | List platform and agent Helm releases and HTTPRoutes |
| `doctor` | ● | Probe discovered platform endpoints |
| `version` | ● | CLI version; platform chart when env resolves |
| `env add\|list\|use\|remove` | ● | Manage kube targets |
| `token mint` | ● | Mint RS256 JWT from cluster signing key (ops/testing) |
| `token jwks` | ● | Write public JWKS from cluster ConfigMap |
| `login` | | Pro/Enterprise — exits with upgrade message on CE |
| `license` | | Pro/Enterprise |
| `whoami` | | Pro/Enterprise |
| `team` | | Pro/Enterprise — `AITeam` CRUD |
| `budget` | | Pro/Enterprise — `AITeam.spec.budget` |
| `audit` | | Enterprise — audit export |

Paid commands print: `This command requires Zelkor Pro or Enterprise. Community Edition does not apply it.` and exit code `2`.

### `token mint` flags

`--release`, `--tenant` (required), `--namespace`, `--kubeconfig`, `--context`, `--issuer`, `--audience`, `--ttl`, `--out`.

### `token jwks` flags

`--release`, `--out` (required), `--env-file`, `--namespace`, `--kubeconfig`, `--context`.

## See also

- [Register extra MCP backends](mcp-extra-backends.md)
- [Drop-In Agent Contract](architecture-agent-contract.md)
- [Helm values reference](reference/helm-values.md)
