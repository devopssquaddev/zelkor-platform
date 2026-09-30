---
title: Upgrade the Platform
description: Safely upgrade the Zelkor platform Helm chart to a new version.
type: how-to
sidebar_group: Install
sidebar_order: 80
audience: human
edition: all
---

# Upgrade the Platform

This guide explains how to safely upgrade the Zelkor platform Helm chart to a new version. 

## Best Practices

* **Pin your version:** Always upgrade to a specific chart version. Do not rely on `latest`.
* **Reuse values:** Use `--reuse-values` so you don't lose your existing configuration (like `workspace.tools.extraBackends` or `gateway.hosts`).
* **Check the release notes:** Look for any breaking changes or required CRD updates before upgrading.

## Upgrade Procedure

1. **Update your local Helm repository or git clone:**
   Ensure you have the latest chart version available locally.

   ```bash
   git pull origin main
   ```

2. **Run the upgrade command:**

   ```bash
   helm upgrade zelkor-platform charts/zelkor-platform \
     --namespace zelkor \
     --reuse-values \
     --wait
   ```

   If you maintain your own custom overlay files, pass them again:

   ```bash
   helm upgrade zelkor-platform charts/zelkor-platform \
     --namespace zelkor \
     -f my-platform-overlay.yaml \
     --wait
   ```

## Rolling Back

If an upgrade fails or introduces instability, you can easily roll back to the previous Helm release revision:

```bash
# View deployment history
helm history zelkor-platform --namespace zelkor

# Rollback to the previous revision
helm rollback zelkor-platform --namespace zelkor
```
