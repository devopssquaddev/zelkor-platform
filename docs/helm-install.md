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

Evaluate Zelkor Community Edition on an existing Kubernetes cluster. This guide installs the evaluation shape (`in-cluster-basic`), which runs stateful components as simple StatefulSets without operators. The workload is a normal Helm release.

**Zelkor sandboxes the agent you already wrote.** It wraps the agent in a comprehensive security and operational perimeter without a rewrite. The agent can't break out, reach unauthorized data or networks, its prompts are verified, budget is controlled, and it is under observation.

* **Community Edition** is the self-hosted runtime.
* **Pro** adds SSO, team controls (budgets and approvals), and production HA / GitOps.
* **Enterprise** adds isolation and compliance on Pro (hardware sandbox, mTLS, retained audit, BAA).

## Prerequisites
- Kubernetes v1.28+ cluster.
- `kubectl` and `helm` v3.10+ installed.
- One LLM API key (e.g., OpenAI, Anthropic).

## Install using the quickstart script

The `install-quickstart.sh` script deploys Envoy Gateway, AI Gateway, and the Zelkor platform.

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform

# Replace with your actual LLM provider key
# Replace with your actual LLM provider key
OPENAI_API_KEY=sk-... ./scripts/install-quickstart.sh \
  --set gateway.hosts.agents=agents.example.com \
  --set gateway.hosts.langfuse=langfuse.example.com
```

## Next steps

- To deploy a highly available shape with Kubernetes operators, see the [Production Install](./production.md).
- To understand how Envoy Gateway integrates with your cluster, see [Gateway Topologies](./topologies.md).