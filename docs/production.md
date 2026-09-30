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

- Kubernetes v1.28+ with at least 3 worker nodes.
- Default StorageClass with dynamic provisioning.
- `metrics-server` installed (required for HPA).
- A JWT Identity Provider (IdP) for tenant authentication, with a downloaded JWKS JSON file (or an internal OIDC issuer like Keycloak for isolated environments).

NetworkPolicies are **disabled by default**. Set `security.networkPolicies.enabled: true` in your values to enforce [Network Boundaries](architecture-network.md) and isolate pod traffic.

## Sandbox Runtime (gVisor)

Community Edition uses gVisor to sandbox generated code. On production clusters, you must install the `runsc` binary on your worker nodes and configure a Kubernetes `RuntimeClass` named `gvisor`. (Managed Kubernetes services like GKE and AKS often provide this as a built-in node pool option). If the `RuntimeClass` is missing, sandbox worker pods will fail to schedule.

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
> 2. Pass a custom override file containing `platform.tenants.jwt.localSigning.enabled: true` to bypass the issuer requirement and use Zelkor's native dev signing (not recommended for true production).

Store the generated passwords (such as `POSTGRES_PASSWORD`) securely. The script will configure Envoy Gateway using a standard LoadBalancer by default. If you have an existing Ingress controller, you can use the `--topology layered` option.

## Optional configurations

- **TLS**: Use `--tls --cluster-issuer letsencrypt-prod` to attach a cert-manager ClusterIssuer to the Gateway.
- **ServiceMonitor**: Use `--service-monitor` to enable Prometheus metrics scraping.

## Next steps

- Read about [Gateway Topologies](./topologies.md) to integrate with existing Traefik, NGINX, or ALB setups.