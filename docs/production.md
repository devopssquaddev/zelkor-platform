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

* **Community Edition** is the self-hosted runtime.
* **Pro** adds SSO, team controls (budgets and approvals), and production HA / GitOps.
* **Enterprise** adds isolation and compliance on Pro (hardware sandbox, mTLS, retained audit, BAA).

## Prerequisites

- Kubernetes v1.28+ with at least 3 worker nodes.
- Default StorageClass with dynamic provisioning.
- `metrics-server` installed (required for HPA).
- A JWT Identity Provider (IdP) for tenant authentication, with a downloaded JWKS JSON file.

## Deploy with the production script

The `install-production.sh` script bootstraps the required operators, installs Envoy Gateway, and deploys the platform using the `values-production.yaml` profile.

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform

# Replace placeholders with your actual hosts, keys, and JWT settings
OPENAI_API_KEY=sk-... ./scripts/install-production.sh \
  --namespace zelkor \
  --hosts-agents agents.example.com \
  --hosts-langfuse langfuse.example.com \
  --jwt-issuer "https://your-idp.example.com" \
  --jwt-audience "zelkor" \
  --jwks-file "./path/to/jwks.json" \
  --generate-passwords
```

Store the generated passwords (such as `POSTGRES_PASSWORD`) securely. The script will configure Envoy Gateway using a standard LoadBalancer by default. If you have an existing Ingress controller, you can use the `--topology layered` option.

## Optional configurations

- **TLS**: Use `--tls --cluster-issuer letsencrypt-prod` to attach a cert-manager ClusterIssuer to the Gateway.
- **ServiceMonitor**: Use `--service-monitor` to enable Prometheus metrics scraping.

## Next steps

- Read about [Gateway Topologies](./topologies.md) to integrate with existing Traefik, NGINX, or ALB setups.