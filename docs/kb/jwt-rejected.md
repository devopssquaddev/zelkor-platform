---
title: JWT rejected (401)
description: Agent or MCP returns 401 for a token that looks valid.
type: kb
sidebar_group: KB
sidebar_order: 20
audience: both
edition: ce
---

# JWT rejected (401)

## Symptom

- Agent Protocol or MCP returns **401**.
- The Bearer token decodes (header and payload look fine).
- Unsigned requests are also rejected (expected).

## Cause

The platform checks `iss`, `aud`, and the JWKS signature.

Common mismatches:

- Helm `platform.tenants.jwt.issuer` is not the token `iss` (for example an in-cluster Service URL while tokens still carry the public IdP URL).
- `remoteJwksUri` is an in-cluster HTTP URL that 404s without the public `Host` header.
- NetworkPolicies are on and Aegra/MCP cannot reach HTTPS JWKS (missing `jwksEgressCIDRs`).

## Confirm

```bash
# Token iss vs Helm issuer
helm get values zelkor-platform -n zelkor -o yaml | grep -A20 'jwt:'
```

Decode the token payload (do not paste secrets into tickets). `iss` must equal `platform.tenants.jwt.issuer`. `aud` must include one of `audiences`.

```bash
kubectl -n zelkor get networkpolicy -l app.kubernetes.io/instance=zelkor-platform
```

With NetworkPolicies on and `remoteJwksUri` set, the Aegra and MCP egress policies must include an `ipBlock` on TCP **443**.

## Fix

1. Set `issuer` to the public `iss` string the IdP puts in tokens.
2. Prefer `--jwks-file` / `jwksConfigMap` when the IdP JWKS is not reachable as HTTPS without a special Host.
3. For a public HTTPS JWKS with NetworkPolicies, set `platform.tenants.jwt.jwksEgressCIDRs` to the IdP CIDRs and upgrade.

## See also

- [Tenant Isolation Reference](../reference/tenants.md)
