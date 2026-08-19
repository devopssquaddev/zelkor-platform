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

## Verify

```bash
kubectl --context kind-zelkor get pods -A
helm --kube-context kind-zelkor list
```

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
