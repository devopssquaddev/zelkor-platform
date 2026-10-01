---
title: Uninstall the Platform
description: Remove the Zelkor platform, gateways, and operators from your cluster.
type: how-to
sidebar_group: Install
sidebar_order: 90
audience: human
edition: all
---

# Uninstall the Platform

This guide explains how to uninstall the Zelkor platform from a shared or production cluster. 

## Remove the Platform Release

To remove the core platform components (gateways, tools, interceptors) without deleting databases or operators, use the `uninstall.sh` script.

```bash
./scripts/uninstall.sh --namespace zelkor
```

If you prefer to run Helm directly:

```bash
helm uninstall zelkor-platform --namespace zelkor
```

## Remove Gateways and Operators

If Zelkor originally installed Envoy Gateway, CloudNativePG, or the ClickHouse Operator during the production install, you can instruct the uninstall script to remove them as well:

```bash
./scripts/uninstall.sh --namespace zelkor --purge-gateway --purge-operators
```

> **Warning:** `--purge-gateway` removes Envoy Gateway and AI Gateway only if Zelkor recorded them as its own. It skips a gateway another workload installed. `--purge-operators` affects any other Postgres or ClickHouse on those operators. Do not pass those flags unless you intend to remove that shared infrastructure.

## Delete the Namespace

To delete the entire namespace after uninstalling, append the `--delete-namespace` flag. This will remove any remaining ConfigMaps, Secrets, or PVCs.

```bash
./scripts/uninstall.sh --namespace zelkor --delete-namespace
```
