# Security Policy

## Report a vulnerability

Use GitHub private vulnerability reporting: **Security → Report a vulnerability** on
[devopssquaddev/zelkor-platform](https://github.com/devopssquaddev/zelkor-platform/security/advisories/new).
Do not open a public issue or pull request for an unfixed vulnerability.

Include the affected version (`vX.Y.Z-ce` or image digest), the component, steps to reproduce, and the impact you
observed. We acknowledge reports within 3 business days and keep you updated in the advisory until it is fixed.

## Scope

| In scope | Out of scope |
| :--- | :--- |
| First-party images `ghcr.io/devopssquaddev/zelkor-*` | Upstream images we ship unmodified (Langfuse, Postgres, ClickHouse, Valkey, Qdrant, SeaweedFS): report to their maintainers; we pin and bump them |
| The `zelkor-platform` and `zelkor-agent` Helm charts | Customer agent code and images |
| The `zelkor` CLI | Clusters configured against the docs (for example NetworkPolicies off, unsigned dev tokens on) |
| Bypasses of a documented isolation promise ([threat model](docs/threat-model.md)) | Findings that need cluster-admin on the target |

## Fix targets

| Severity | Target from confirmation to a released fix |
| :--- | :--- |
| Critical in a first-party image | 72 hours |
| High | Next patch release |
| Medium / Low | Scheduled release |

Fixes ship as a new `vX.Y.Z-ce` patch release; published tags are never overwritten. Image scans run weekly in CI.
These are targets for the Community Edition, not contractual SLAs.

## Disclosure

Fixed vulnerabilities are listed with their time to fix in the public [CVE log](docs/security/cve-log.md) and in the
GitHub security advisory. Verify any release with [Verify a Release](docs/security/verify-release.md).
