---
title: Production Install
description: Deploy the highly available production shape of Zelkor Community Edition.
type: how-to
sidebar_group: Install
sidebar_order: 30
audience: human
edition: ce
---

# Production Install

Deploy the production shape of Zelkor Community Edition. This runs databases via Kubernetes operators (CloudNativePG, ClickHouse Operator) and enables High Availability (HA) and NetworkPolicies. The workload is a normal Helm release.

**Zelkor sandboxes the agent you already wrote.** It wraps the agent in a comprehensive security and operational perimeter without a rewrite. The agent can't break out, reach unauthorized data or networks, its prompts are verified, budget is controlled, and it is under observation.

* **Community Edition** is the self-hosted runtime. It can run this highly available operator shape out of the box.
* **Pro** adds SSO, team controls (budgets and approvals), and team GitOps on top of this shape.
* **Enterprise** adds isolation and compliance on Pro (hardware sandbox, mTLS, retained audit, BAA).

## Prerequisites

- Kubernetes v1.28+. The production profile runs 3 Postgres instances. The installer stops when the Postgres StorageClass is not on that many Ready nodes and tells you the `--set` to pass.
- A default StorageClass that can provision a volume, or all three class keys: `databases.postgresql.storage.storageClass`, `databases.clickhouse.storage.storageClass`, `seaweedfs.persistence.storageClass`.
- `metrics-server` installed (required for HPA).
- A JWT Identity Provider (IdP) for tenant authentication, with a downloaded JWKS JSON file (or an internal OIDC issuer like Keycloak for isolated environments).

NetworkPolicies are **disabled by default**. Set `security.networkPolicies.enabled: true` in your values to enforce [Network Boundaries](architecture-network.md) and isolate pod traffic.

## Sandbox Runtime (gVisor)

Zelkor Community Edition isolates generated code with gVisor. Sandbox workers use RuntimeClass `gvisor` and do not fall back to the normal container runtime.

Installing gVisor writes `runsc` onto nodes and restarts their container runtime. Workloads on those nodes are rescheduled. The production installer does not do that unless you ask.

Pick one:

1. The cluster already has a working RuntimeClass `gvisor` (GKE Sandbox, Talos, or a node image you prepared). The installer detects it and leaves the nodes alone.
2. Install onto a sandbox pool. This restarts the container runtime on the selected nodes:

```bash
--install-gvisor \
  --set "security.sandbox.nodes.selector.kubernetes\.io/hostname=sandbox-node-1"
```

3. Skip kernel isolation. The platform still installs. Generated code is not sandboxed:

```bash
--skip-gvisor
```

If you pass neither flag and the cluster has no working gVisor runtime, the installer stops before Helm and prints those two commands.

A one-node cluster may use `--install-gvisor` without a selector. The installer names that node and says its runtime will restart. On more than one node, an empty selector is refused so the control plane is not restarted with the workers.

After a successful install, the node is labeled `zelkor.io/gvisor-ready=true`. Sandbox workers run only on labeled nodes. A node where install fails is not labeled.

### Prerequisites and limitations

- **Containerd.** k3s, RKE2, kubeadm, EKS, and AKS. OpenShift and CRI-O are unsupported.
- **GKE Sandbox** (node label `sandbox.gke.io/runtime=gvisor`) and **Talos** (`siderolabs/gvisor`) are detected. Zelkor does not install `runsc` there.
- **SELinux Enforcing** often accepts the `runsc` files and still refuses to start a gVisor pod. Point the selector at nodes that can run it.
- **Air-gap.** The installer downloads from `storage.googleapis.com` unless you set `security.sandbox.provisioning.baseUrl` to a mirror.
- **Helm without the script.** Chart default `security.sandbox.provisioning.mode` is `auto`, which does not install `runsc`. Set `mode: daemonset` and a node selector when GitOps should do the node install.
- **Taints.** The installer does not tolerate every taint. A tainted sandbox pool needs `security.sandbox.nodes.tolerations`.

## Deploy with the production script

The `install-production.sh` script bootstraps the required operators, installs Envoy Gateway, and deploys the platform using the `values-production.yaml` profile.

# Replace placeholders with your actual hosts, keys, and JWT settings

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform

OPENAI_API_KEY=sk-... ./scripts/install-production.sh \
  --namespace zelkor \
  --hosts-agents agents.example.com \
  --hosts-langfuse langfuse.example.com \
  --jwt-issuer "https://your-idp.example.com" \
  --jwt-audience "zelkor" \
  --jwks-file "./path/to/jwks.json" \
  --generate-passwords
```

This script maps the JWT flags to the underlying Helm keys (`platform.tenants.jwt.issuer`, `audiences[0]`, and `jwksConfigMap`). 

> **Note on JWT Issuers:** Production installs strictly enforce identity verification. If you do not have an external IdP (like Auth0 or Entra ID) and are deploying to an isolated or air-gapped environment, you have two alternatives: 
> 1. Run a lightweight internal OIDC provider (like Keycloak or Zitadel) in your cluster and point `--jwt-issuer` to it.
> 2. Use Zelkor's native dev signing (not recommended for true production). To bypass the issuer requirement, pass the `localSigning` override instead of the `--jwt-*` flags:
> ```bash
> OPENAI_API_KEY=sk-... ./scripts/install-production.sh \
>   --hosts-agents agents.example.com \
>   --hosts-langfuse langfuse.example.com \
>   --set "platform.tenants.jwt.localSigning.enabled=true" \
>   --generate-passwords
> ```

Store the generated passwords (such as `POSTGRES_PASSWORD`) securely. The script will configure Envoy Gateway using a standard LoadBalancer by default. If you have an existing Ingress controller, you can use the `--topology layered` option.

## Optional configurations

- **TLS**: Use `--tls --cluster-issuer letsencrypt-prod` to attach a cert-manager ClusterIssuer to the Gateway.
- **ServiceMonitor**: Use `--service-monitor` to enable Prometheus metrics scraping.
- **Existing operators**: Pass `--skip-operators` when CloudNativePG, ClickHouse Operator, or cert-manager are already on the cluster.
- **Storage**: Leave the three volume classes empty only when the default StorageClass can provision. If you set one of `databases.postgresql.storage.storageClass`, `databases.clickhouse.storage.storageClass`, or `seaweedfs.persistence.storageClass`, set all three. Postgres stays at 3 instances unless the installer prints `--set databases.postgresql.instances=N`.
- **gVisor**: Pass `--install-gvisor` with a node selector, or `--skip-gvisor`. See [Sandbox Runtime (gVisor)](#sandbox-runtime-gvisor).
- **Layered edge**: `--topology layered` prints the Envoy dataplane Service and an Ingress example (namespace `envoy-gateway-system`, preserve Host). The script does not apply it. Health checks are `https://<agents-host>/health` and `https://<langfuse-host>/api/public/health`. Do not wrap the dataplane in another ClusterIP Endpoints list.
- **LLM keys on upgrade**: keep passing `--set-file` for `workspace.models.providers.*.apiKey`, or omit the key. An overlay with `apiKey: ""` deletes the AI Gateway route ([route not found](./kb/ai-gateway-route-not-found.md)).

`--jwt-issuer` must match the token `iss`. Prefer `--jwks-file`. Remote JWKS needs HTTPS plus `jwksEgressCIDRs` when NetworkPolicies are on ([JWT rejected](./kb/jwt-rejected.md)).

## Next steps

- Read about [Gateway Topologies](./topologies.md) to integrate with existing Traefik, NGINX, or ALB setups.