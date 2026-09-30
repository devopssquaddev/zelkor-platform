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
      issuer: "https://your-idp.example.com"
      audience: "zelkor-platform"
      jwksUrl: "https://your-idp.example.com/.well-known/jwks.json"
      # Claim to use for the tenant ID (default: "org_id")
      tenantClaim: "org_id"
    # Optional mapping from IDP org names to internal tenant IDs
    orgMappings:
      "idp-org-uuid-1": "tenant-a"
      "idp-org-uuid-2": "tenant-b"
```

## IDM Integration Options

Zelkor uses standard JWKS (JSON Web Key Set) validation. It integrates with any Identity Management (IDM) system that issues signed JWTs:

- **Okta / Auth0:** Set `jwksUrl` to your authorization server's `.well-known/jwks.json`. Use a custom claim (e.g., `org_id`) for `tenantClaim`.
- **Microsoft Entra ID (Azure AD):** Use the v2.0 endpoint for `issuer` and `jwksUrl`. The `tenantClaim` is typically `tid` (tenant ID) or a mapped app role.
- **Keycloak:** Point `jwksUrl` to the realm's certs endpoint (`/realms/<realm>/protocol/openid-connect/certs`).
- **Custom IDP:** Serve a static JWKS endpoint. If your IDP issues opaque UUIDs but your agent expects readable names, use `orgMappings` to translate them (e.g., `b2f4...: Bank_Alpha`).

## Tool Filtering vs. Forwarding

The platform enforces tenant isolation differently depending on the tool backend.

### Native MCP Servers

Native servers apply strict filters based on the tenant ID. The agent cannot bypass these.

- **Postgres:** The MCP server injects `tenant_id = :tenant` into queries or relies on Postgres Row-Level Security (RLS) configured for the connection role.
- **Qdrant:** The MCP server wraps vector operations with a strict payload filter: `must: [{key: "tenant_id", match: {value: "the-tenant"}}]`.

### Extra MCP Backends

For backends registered via `workspace.tools`, Zelkor **forwards** the tenant identity but does not natively filter the data (as it does not control the external SaaS).

The identity is forwarded as an HTTP header (e.g., `X-Tenant-ID`) to the extra backend. The external backend is responsible for enforcing its own isolation.

## `zelkor token mint`

For local development and testing, you can mint valid JWTs using the CLI. These tokens are signed by the platform's dev key (enabled by default in `profiles/values-local.yaml`).

```bash
# Mint a token for a specific tenant
zelkor token mint --tenant "Bank_Alpha"

# Mint a token with an expiration (default 1h)
zelkor token mint --tenant "Squad_Alpha" --expires "24h"
```

The resulting token can be passed in the `Authorization: Bearer <token>` header to the AI Gateway or agent endpoints.
