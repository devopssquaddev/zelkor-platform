---
title: Tenant Isolation Reference
description: Claims, org map, what is filtered vs forwarded, and zelkor token mint fields.
type: reference
sidebar_group: Reference
sidebar_order: 60
audience: human
edition: all
---

# Tenant Isolation Reference

This page documents how tenant identity is configured, mapped, and enforced across Zelkor.

## JWT Configuration

Identity comes from a verified JWT. The platform validates the token and maps it to a tenant ID. **There is no default tenant** — if the claim is missing or validation fails, the request is rejected immediately.

Configuration in `values.yaml`:

```yaml
platform:
  tenants:
    jwt:
      audiences:
        - "zelkor-platform"
      remoteJwksUri: "https://your-idp.example.com/.well-known/jwks.json"
      # Claims to use for the tenant ID (default: ["tenant_id", "org_id", "sub"])
      tenantClaims:
        - "tenant_id"
        - "org_id"
        - "sub"
    # Optional mapping from IDP org names to internal tenant IDs
    orgMappings:
      "idp-org-uuid-1": "tenant-a"
      "idp-org-uuid-2": "tenant-b"
```

## IDM Integration Options

Zelkor uses standard JWKS (JSON Web Key Set) validation. It integrates with any Identity Management (IDM) system that issues signed JWTs:

- **Okta / Auth0:** Set `issuer` and `remoteJwksUri` to your authorization server's endpoints (e.g. `.well-known/jwks.json`). Use a custom claim (e.g., `org_id`) in `tenantClaims`.
- **Microsoft Entra ID (Azure AD):** Use the v2.0 endpoint for `issuer` and `remoteJwksUri`. The `tenantClaims` is typically `tid` (tenant ID) or a mapped app role.
- **Keycloak:** Point `remoteJwksUri` to the realm's certs endpoint (`/realms/<realm>/protocol/openid-connect/certs`).
- **Custom IDP:** Serve a static JWKS endpoint. If your IDP issues opaque UUIDs but your agent expects readable names, use `orgMappings` to translate them (e.g., `b2f4...: tenant-a`).

## Tool Filtering vs. Forwarding

The platform enforces tenant isolation differently depending on the tool backend.

### Native MCP Servers

Native servers apply strict filters based on the tenant ID. The agent cannot bypass these.

- **Postgres:** The MCP server injects `tenant_id = :tenant` into queries or relies on Postgres Row-Level Security (RLS) configured for the connection role.
- **Qdrant:** The MCP server wraps vector operations with a strict payload filter: `must: [{key: "tenant_id", match: {value: "the-tenant"}}]`.

### Extra MCP Backends

For backends registered via `workspace.tools`, Zelkor **forwards** the tenant identity but does not natively filter the data (as it does not control the external SaaS).

The identity is forwarded as an HTTP header (e.g., `X-Tenant-ID`) to the extra backend. The external backend is responsible for enforcing its own isolation.

## `zelkor token mint` & `localSigning`

For local development, testing, or fully air-gapped deployments without an IdP, you can enable Zelkor's native `localSigning` fallback feature. This allows the platform to act as its own signer. 

Configuration in `values.yaml` for a single-tenant isolated environment:

```yaml
platform:
  tenants:
    jwt:
      localSigning:
        enabled: true
        # Automatically generate a long-lived token for this tenant at install
        seedTenant: "tenant-a"
        seedTokenTTL: "24h"
```

When enabled (which is the default in `profiles/values-local.yaml` used by the quickstart script), you can also mint valid JWTs using the CLI:

```bash
# Mint a token for a specific tenant
zelkor token mint --release zelkor-platform --tenant "tenant-a"

# Mint a token with a specific time-to-live (default 1h)
zelkor token mint --release zelkor-platform --tenant "tenant-b" --ttl "24h"
```

The resulting token can be passed in the `Authorization: Bearer <token>` header to the AI Gateway or agent endpoints.
