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

> **Warning:** Purging operators will affect any other workloads on the cluster that depend on them. Do not use `--purge-operators` if you have non-Zelkor Postgres or ClickHouse clusters managed by these operators.

## Delete the Namespace

To delete the entire namespace after uninstalling, append the `--delete-namespace` flag. This will remove any remaining ConfigMaps, Secrets, or PVCs.

```bash
./scripts/uninstall.sh --namespace zelkor --delete-namespace
```
