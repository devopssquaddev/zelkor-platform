# Quick Start

Deploy a production-like Zelkor Platform instance locally in under 5 minutes using Kubernetes IN Docker (`kind`).

## Prerequisites

- macOS (Docker Desktop / OrbStack), Linux, or Windows (WSL2)
- [Docker](https://docs.docker.com/get-docker/)
- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [Helm](https://helm.sh/docs/intro/install/) 3.x
- [kubectl](https://kubernetes.io/docs/tasks/tools/)

## Install

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform
./install.sh
```

The script will:

1. Verify `docker`, `kind`, `helm`, and `kubectl` are available
2. Create a `kind` cluster named `zelkor` (if it doesn't exist)
3. Deploy the unified Helm chart with `values-local.yaml`

## Verify & Access

```bash
kubectl --context kind-zelkor get pods -A
helm --kube-context kind-zelkor list
```

All services and Web UIs are accessible via Kubernetes Gateway API on port `8088`:

| Component | URL | Dev Credentials |
| :--- | :--- | :--- |
| **Langfuse Observability** | [http://langfuse.localhost:8088](http://langfuse.localhost:8088) | `admin@zelkor.local` / `zelkor-dev-password` (Project: `FinServe AI`) |
| **Envoy AI Gateway** | [http://ai-gateway.localhost:8088](http://ai-gateway.localhost:8088) | `Authorization: Bearer dev-key`, `X-Tenant-ID: Bank_Alpha` |
| **Aegra Agent Runtime** | [http://aegra.localhost:8088/docs](http://aegra.localhost:8088/docs) | `Authorization: Bearer dev-key` |
| **FinServe Demo Agent** | [http://finserve.localhost:8088/docs](http://finserve.localhost:8088/docs) | `Authorization: Bearer dev:Bank_Alpha` |

### Instant Observability
The local development environment pre-seeds a Langfuse user, organization, and API keys. Requests sent through the Envoy AI Gateway or the FinServe demo agent automatically appear as live traces in the Langfuse dashboard under the `finserve` project.

## Configuration

Local defaults live in `charts/zelkor-platform/values-local.yaml`. Override at install time:

```bash
VALUES_FILE=charts/zelkor-platform/values-local.yaml ./install.sh
```

## Uninstall

```bash
helm --kube-context kind-zelkor uninstall zelkor-platform
kind delete cluster --name zelkor
```

## Next Steps

- Deploy to a standard Kubernetes cluster using `charts/zelkor-platform/values.yaml`
- Configure tenant isolation via Aegra auth handlers
- See the root [README.md](../README.md) for Enterprise features
