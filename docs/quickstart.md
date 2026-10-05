---
title: Local Quickstart
description: Install Zelkor Community Edition on kind, call a model, and open a run trace.
type: tutorial
sidebar_group: Get started
sidebar_order: 10
audience: human
edition: ce
---

# Local Quickstart

You get Community Edition on your own laptop cluster. Bring the agent you already wrote; it is sandboxed — it can't break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation; tenants stay isolated ([see the tenant hop](architecture-tenants.md)). This tutorial installs that runtime on kind, proves a model call, and opens the matching trace — then points you at the CLI for your own agent.

Community Edition is the self-hosted runtime in this repo. Pro adds SSO, team controls (budgets and approvals), and production HA / GitOps. Enterprise adds isolation and compliance on Pro (hardware sandbox, mTLS, retained audit, BAA). You do not need Pro or Enterprise to finish this page.

## Prerequisites

Install and leave running:

- Docker Desktop, Docker Engine, or OrbStack
- [`kind`](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [`helm`](https://helm.sh/docs/intro/install/) v3.10+
- [`kubectl`](https://kubernetes.io/docs/tasks/tools/) v1.28+

You also need **one** LLM provider credential (or a local Ollama). The install refuses to start without it. Upstream keys go into the cluster secret; client calls use a local consumer token (`dev-key` on this tutorial).

Pick one:

| Provider | Env when you install | Default model the install picks |
| :--- | :--- | :--- |
| OpenAI | `OPENAI_API_KEY` | `openai/gpt-4o-mini` |
| Ollama Cloud | `OLLAMA_API_KEY` | `gpt-oss:20b` |
| Ollama on the host | `OLLAMA_LOCAL_HOST=http://host.docker.internal:11434` | `ollama/llama3.2` |
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic/claude-3-5-sonnet` |
| Gemini | `GEMINI_API_KEY` | `gemini/gemini-2.0-flash` |
| vLLM | `VLLM_BACKEND_URL` | `vllm/default` |

You can set more than one provider; the first match in the table above wins for `DEFAULT_LLM_MODEL` unless you override it.

## Install Community Edition

From a clone of this repository:

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform
OPENAI_API_KEY=sk-... ./install.sh
```

Other providers use the same script — substitute the env var from the table. Example with Ollama Cloud:

```bash
OLLAMA_API_KEY=... ./install.sh
```

What `./install.sh` does (you do not run these by hand):

1. Checks Docker, kind, helm, and kubectl
2. Creates kind cluster `zelkor` with host port `8088`
3. Installs the gVisor runtime on the kind node for sandboxed code
4. Deploys Envoy Gateway, Envoy AI Gateway, and the Zelkor platform Helm chart (`appVersion` / image tag `2.2.1`)
5. Deploys the optional FinServe example agents by default
6. Prints service URLs and a ready curl when everything is healthy

First create is typically under five minutes when Docker is already warm and image pulls are not bandwidth-bound. Re-runs skip work that is already ready.

**Success:** the script ends with `Done. Zelkor Platform deployed on kind cluster: zelkor` and a footer of localhost URLs on port `8088`, plus the `zelkor env add local` commands for this cluster.

## Call a model

Use the consumer token `dev-key`. The `model` must match the provider you configured at install.

OpenAI install:

```bash
curl -X POST http://ai-gateway.localhost:8088/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-key" \
  -d '{
    "model": "openai/gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello from Zelkor"}]
  }'
```

Ollama Cloud install — change the model to `gpt-oss:20b`. Ollama on the host — use `ollama/llama3.2`. Anthropic — `anthropic/claude-3-5-sonnet`. Gemini — `gemini/gemini-2.0-flash`.

**Success:** HTTP 200 and a completion in the JSON body. If you see `no healthy upstream`, the model id does not match the provider you installed with.

## Open a trace

1. Open [http://langfuse.localhost:8088](http://langfuse.localhost:8088)
2. Sign in with the credentials the install footer printed (local defaults: `admin@zelkor.local` / `Zelkor-dev1!`)
3. Open project **Zelkor Platform** → **Traces**
4. Find the gateway call from the curl above

**Success:** a new trace appears for that completion. Later agent runs land in the same project as one waterfall per run.

## Deploy your own agent (next)

You already write LangGraph or Deep Agents graphs. After this install, the platform path is:

```bash
pip install -e cli/
zelkor env add local --kube-context kind-zelkor --namespace default
zelkor env use local
```

Then from your agent project directory: `zelkor init` (if needed), `zelkor deploy` (or `zelkor dev` on kind), `zelkor run`, and refresh Langfuse Traces.

Command reference: [`cli/README.md`](../cli/README.md). Keep provider keys in the platform; your agent talks to the gateway and tools the cluster already exposes.

## Optional: try the FinServe sample

`./install.sh` also deploys a wealth-management sample under [`examples/finserve/`](../examples/finserve/README.md). Use it when you want a ready-made agent — not as the way you learn how to ship your own. The install footer prints sample curl commands and how to mint a tenant token with `zelkor token mint` (that token is the tenant, see [Tenant Isolation](architecture-tenants.md)).

## Tear down

```bash
helm --kube-context kind-zelkor uninstall finserve --ignore-not-found
helm --kube-context kind-zelkor uninstall zelkor-platform --ignore-not-found
kind delete cluster --name zelkor
```

## Where to go next

| Goal | Page |
| :--- | :--- |
| Ship your agent on this cluster | [`cli/README.md`](../cli/README.md) |
| Read the FinServe sample | [`examples/finserve/README.md`](../examples/finserve/README.md) |
| Docs map | [Documentation index](README.md) |
| Vertex `gemini-*` 500 `unknown backend` | [KB](kb/ai-gateway-vertex-unknown-backend.md) |

Read [Install on an Existing Cluster](helm-install.md) and [Production Install](production.md) to move off kind. The objects you set here — model, tool, agent — are the same ones you keep.
