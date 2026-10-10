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

If you need to skip operator installation (operators already present on the cluster), pass `--skip-operators`.

Set storage and sandbox to the cluster you have. Leave `databases.postgresql.storage.storageClass`, `databases.clickhouse.storage.storageClass`, and `seaweedfs.persistence.storageClass` empty only when the default StorageClass can provision a volume. If you set one, set all three. Postgres stays at 3 instances unless the installer tells you to pass `--set databases.postgresql.instances=N`. 

Sandbox workers need gVisor. If RuntimeClass `gvisor` already works, the installer leaves nodes alone. Otherwise pass one of:

- `--install-gvisor` plus `--set security.sandbox.nodes.selector.<key>=<value>`. This writes `runsc` and restarts the container runtime on the selected nodes. On a multi-node cluster an empty selector is refused. A one-node cluster may omit the selector; the log names that node.
- `--skip-gvisor`. Sets `security.sandbox.enabled=false`. Generated code is not kernel-isolated.

Passing neither flag, when no runtime is present, exits before Helm. OpenShift and CRI-O cannot take the installer. A tainted sandbox pool also needs `security.sandbox.nodes.tolerations`. Helm-only installs stay off the node installer until `security.sandbox.provisioning.mode` is `daemonset`.

The installer prints the Envoy dataplane Service. `--topology layered` also prints an Ingress for namespace `envoy-gateway-system` (preserve Host) and the health URLs `https://<agents-host>/health` and `https://<langfuse-host>/api/public/health`. Apply that Ingress yourself. Do not put another ClusterIP in Endpoints.

Later Helm upgrades that set `workspace.models` must pass the provider key again (`--set-file`) or omit `apiKey` so an empty overlay does not wipe it.

> **Note on JWT Issuers:** Production installs strictly require a JWT issuer. If you are deploying an isolated system without an external IdP (like Okta or Entra ID), you can deploy a lightweight internal OIDC provider (like Keycloak) to your cluster, or use a Helm override to enable Zelkor's native `localSigning` fallback (see [Tenant Reference](reference/tenants.md) for details). `--jwt-issuer` must match token `iss`. Prefer `--jwks-file` over an in-cluster JWKS URL. See [JWT rejected (401)](kb/jwt-rejected.md).

## Uninstall

To remove the Zelkor platform Helm release from the cluster:

```bash
./scripts/uninstall.sh --namespace zelkor
```

This removes the platform release but leaves Envoy Gateway and operators intact. `--purge-gateway` and `--purge-operators` remove those components only when Zelkor recorded them in the cluster ownership ConfigMap (it skips a gateway another team installed).

```bash
./scripts/uninstall.sh --namespace zelkor --purge-gateway --purge-operators
```

To also delete the namespace after uninstalling, append `--delete-namespace`.

## Next Steps

- Deploy a customer agent onto the platform using the [Agent Deploy Guide](agent-deploy.md).