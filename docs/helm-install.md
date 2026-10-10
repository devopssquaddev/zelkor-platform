---
title: Install on an Existing Cluster
description: Evaluate Zelkor Community Edition on any Kubernetes cluster.
type: how-to
sidebar_group: Install
sidebar_order: 20
audience: human
edition: ce
---

# Install on an Existing Cluster

Evaluate Zelkor Community Edition on an existing Kubernetes cluster. This guide installs the evaluation shape (`databases.mode: in-cluster-basic`), which runs stateful components as simple StatefulSets without operators. The workload is a normal Helm release.

**Zelkor sandboxes the agent you already wrote.** It wraps the agent in a comprehensive security and operational perimeter without a rewrite. The agent can't break out, reach unauthorized data or networks, its prompts are verified, budget is controlled, and it is under observation.

* **Community Edition** is the self-hosted runtime. This page installs the evaluation shape. The [production install](production.md) is the highly available operator shape, still Community Edition.
* **Pro** adds SSO, team controls (budgets and approvals), and team GitOps on top of that shape.
* **Enterprise** adds isolation and compliance on Pro (hardware sandbox, mTLS, retained audit, BAA).

Published north-south hosts are `gateway.hosts.agents` and `gateway.hosts.langfuse` (Agent Protocol and Langfuse UI). Agent workers, MCP, NeMo, and datastores stay ClusterIP. See [Gateway Topologies](topologies.md).

## Prerequisites
- Kubernetes v1.28+ cluster.
- `kubectl` and `helm` v3.10+ installed.
- One LLM API key (e.g., OpenAI, Anthropic).

## Install using the quickstart script

The `install-quickstart.sh` script deploys Envoy Gateway, AI Gateway, and the Zelkor platform. It maps `OPENAI_API_KEY` to `workspace.models.providers.openai.apiKey` and `--hosts-*` to `gateway.hosts.*` (chart defaults for those hosts are empty).

Replace `sk-...` with your provider key:

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform

OPENAI_API_KEY=sk-... ./scripts/install-quickstart.sh \
  --namespace zelkor \
  --hosts-agents agents.example.com \
  --hosts-langfuse langfuse.example.com
```

Omit `--hosts-*` to use `agents.<namespace>.zelkor.local` and `langfuse.<namespace>.zelkor.local`. The script prints commands to read generated Langfuse and datastore passwords from Secrets.

## Install using Helm directly

If you prefer Helm by hand, first install Gateway API and Envoy Gateway (see [Gateway Topologies](topologies.md)):

```bash
./scripts/bootstrap-gateway.sh
```

Then install the platform with the quickstart profile. Chart defaults leave `workspace.models.providers.openai.apiKey` and `gateway.hosts.*` empty — set them on the command (or an overlay). Do **not** set `aiGateway.providers.*`; that V1 root fails render.

```bash
kubectl create namespace zelkor
helm upgrade --install zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  -f profiles/values-quickstart.yaml \
  -f profiles/values-gateway-greenfield.yaml \
  --set workspace.models.providers.openai.apiKey="sk-..." \
  --set gateway.hosts.agents=agents.example.com \
  --set gateway.hosts.langfuse=langfuse.example.com
```

You must also supply Langfuse install secrets (`platform.telemetry.langfuse.nextauthSecret`, `salt`, `encryptionKey`) unless you generate them another way. The quickstart script does that for you.

## Next steps

- To deploy a highly available shape with Kubernetes operators, see the [Production Install](production.md).
- To understand how Envoy Gateway integrates with your cluster, see [Gateway Topologies](topologies.md).
- Uninstall: [Uninstall](uninstall.md).
