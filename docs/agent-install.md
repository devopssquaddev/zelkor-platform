---
title: Install the Platform (Agent Guide)
description: How to install and uninstall Zelkor Community Edition on a Kubernetes cluster.
type: tutorial
sidebar_group: Agents
sidebar_order: 1
audience: agent
edition: ce
---

# Install the Platform (Agent Guide)

This guide is for coding agents. It explains how to install and uninstall the Zelkor Community Edition platform on an existing Kubernetes cluster.

Zelkor's core advantage: **bring the agent you already wrote; it is sandboxed — it can't break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation.**

## Prerequisites

- `kubectl` configured and pointing to the target cluster.
- `helm` installed.
- A valid LLM provider API key (e.g., `OPENAI_API_KEY`).
- Target hostnames for the agent protocol and Langfuse UI.

## Install (Evaluation)

To install the platform for evaluation (in-cluster-basic topology, no operators), use the quickstart script. This is suitable for testing and development.

```bash
OPENAI_API_KEY=sk-... ./scripts/install-quickstart.sh \
  --namespace zelkor
```

The script has built-in localhost defaults (like `agents.<namespace>.zelkor.local`) for local evaluation. If you want to use real domains, provide `--hosts-agents` and `--hosts-langfuse`. The script will generate passwords and output the Envoy dataplane services.

## Install (Production)

To install the platform in a production shape (operator-cr, HA, NetworkPolicies), use the production script. This requires real DNS names (not `*.localhost`).

```bash
OPENAI_API_KEY=sk-... ./scripts/install-production.sh \
  --hosts-agents agents.example.com \
  --hosts-langfuse langfuse.example.com \
  --jwt-issuer "https://your-idp.example.com" \
  --jwt-audience "zelkor-platform" \
  --jwks-file "./path/to/jwks.json" \
  --namespace zelkor
```

If you need to skip operator installation (e.g., in a brownfield environment where operators are already present), pass `--skip-operators`.

> **Note on JWT Issuers:** Production installs strictly require a JWT issuer. If you are deploying an isolated system without an external IdP (like Okta or Entra ID), you can deploy a lightweight internal OIDC provider (like Keycloak) to your cluster, or use a Helm override to enable Zelkor's native `localSigning` fallback (see [Tenant Reference](reference/tenants.md) for details).

## Uninstall

To remove the Zelkor platform Helm release from the cluster:

```bash
./scripts/uninstall.sh --namespace zelkor
```

This removes the platform release but leaves Envoy Gateway and operators intact. To purge them (if Zelkor installed them), append `--purge-gateway` and `--purge-operators`.

```bash
./scripts/uninstall.sh --namespace zelkor --purge-gateway --purge-operators
```

To also delete the namespace after uninstalling, append `--delete-namespace`.

## Next Steps

- Deploy a customer agent onto the platform using the [Agent Deploy Guide](agent-deploy.md).