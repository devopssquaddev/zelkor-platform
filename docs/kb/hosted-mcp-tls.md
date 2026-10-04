---
title: Hosted extra MCP tools missing
description: tools/list omits a hosted extra prefix, or Envoy cannot TLS-handshake the FQDN.
type: kb
sidebar_group: KB
sidebar_order: 24
audience: both
edition: ce
---

# Hosted extra MCP tools missing

## Symptom

- `tools/list` on `MCP_URL` has native tools (`postgres__query`, …) but not `{name}__…` for a hosted extra (for example `tavily__tavily_search`).
- `zelkor deploy` fails because `tools.json` names a backend that is not on the platform release.
- Dataplane logs show TLS errors to the extra’s hostname (certificate unknown / handshake failure).

## Cause

An FQDN extra is an Envoy **Backend**. HTTPS needs a CA. Without `tls.caSecretRef`, the chart attaches **BackendTLSPolicy** `wellKnownCACertificates: System` (public CAs, same idea as LLM provider backends). Older chart versions omitted that policy, so Envoy could not complete TLS to hosts such as `mcp.tavily.com`.

A missing `workspace.tools.extraBackends` entry or a wrong `path` / `apiKey.secretRef` produces the same empty prefix with no TLS error.

## Confirm

```bash
kubectl -n zelkor get backend,backendtlspolicy,mcproute
helm get values zelkor-platform -n zelkor -o yaml | grep -A40 extraBackends
```

For hostname `mcp.tavily.com` expect a Backend named `tavily` and, unless you set `tls.caSecretRef`, BackendTLSPolicy `tavily-tls` with system CAs. `extraBackends[].name` must match the prefix you expect.

## Fix

1. Register the extra on the **platform** release ([Register extra MCP backends](../mcp-extra-backends.md)). Secret data key is `apiKey`.
2. Upgrade to a chart that renders System CA BackendTLSPolicy when `tls.caSecretRef` is empty, then `helm upgrade --reuse-values`.
3. Private CAs only: set `tls.caSecretRef` to a Secret Envoy can mount (do not put the SaaS token there).
4. `tools/list` again from a pod that may reach the MCP gateway. Expect `{name}__{tool}`.

The agent never holds the vendor key. If NetworkPolicies are on, the worker must not dial the SaaS hostname itself — only `MCP_URL`.
