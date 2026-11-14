# Third-Party Notices — Zelkor Community Edition

Zelkor CE orchestrates third-party open-source components. This file lists the
pinned components, their SPDX license, and how each is distributed. It is
maintained per **CE-18** (third-party license & distribution compliance) and is
updated whenever component pins change (see
`internal/plan/component_compatibility_matrix.md` for the authoritative pin
inventory; the CE-8a image scan SBOM is the exhaustive transitive list).

**As of CE `2.4.4`** (2026-11-11).

## Distribution paths

- **Runtime pull** — pulled into the customer's cluster at install (Helm
  subchart, upstream manifest, or image reference). Not redistributed inside any
  Zelkor artifact.
- **Embedded** — installed via pip/npm into first-party `ghcr.io/devopssquaddev/zelkor-*`
  images published to GHCR.
- **Customer pull** — pulled in the customer VPC (e.g. on first boot); never
  pre-baked into a redistributed Zelkor image or appliance.

## Bootstrap & gateway

| Component | Version | SPDX | Distribution |
| :--- | :--- | :--- | :--- |
| Envoy Gateway | v1.10.0 | Apache-2.0 | Runtime pull (`install.yaml` + images) |
| Gateway API CRDs | v1.6.2 | Apache-2.0 | Runtime pull (bundled with Envoy Gateway) |
| Envoy AI Gateway / **Agent Router** | v1.2.1 | Apache-2.0 | Runtime pull (OCI Helm + controller/extproc images) |
| Envoy ratelimit | `5ae0682e` | Apache-2.0 | Runtime pull (image) |
| gVisor (`runsc`) | 20261019 | Apache-2.0 | Runtime pull (node installer) |
| Docker Registry | 2.8.3 | Apache-2.0 | Runtime pull (local pull-through cache) |

## Datastores

| Component | Version | SPDX | Distribution |
| :--- | :--- | :--- | :--- |
| PostgreSQL | 18.6 | PostgreSQL | Runtime pull (image) |
| Valkey | 9.1.2 | BSD-3-Clause | Runtime pull (image) |
| ClickHouse | 26.9.25.15 | Apache-2.0 | Runtime pull (image) |
| Qdrant | v1.20.0 | Apache-2.0 | Runtime pull (image) |
| SeaweedFS | 4.51 | Apache-2.0 | Runtime pull (image) |

## Operators (Gate B)

| Component | Version | SPDX | Distribution |
| :--- | :--- | :--- | :--- |
| CloudNativePG | 1.30.1 (chart 0.29.1) | Apache-2.0 | Runtime pull |
| Barman Cloud plugin | 0.15.1 | GPL-3.0-only | Runtime pull — unmodified upstream CLI inside the CNPG image; no Barman source vendored into Zelkor images |
| Altinity ClickHouse Operator | 0.27.4 | Apache-2.0 | Runtime pull |
| cert-manager | v1.21.3 | Apache-2.0 | Runtime pull |

## Observability

| Component | Version | SPDX | Distribution |
| :--- | :--- | :--- | :--- |
| Langfuse (web + worker) | 4.76.0 | MIT | **Customer pull** — `langfuse/langfuse*` pulled from Docker Hub at runtime. CE uses MIT-licensed features only; the `/ee` commercial edition is not shipped and is **not** pre-baked into any Zelkor image or appliance. |

## Embedded in first-party images (pip / npm)

| Component | Version | SPDX | Distribution |
| :--- | :--- | :--- | :--- |
| Aegra (`aegra-api`, `aegra-cli`) | 0.11.0 | Apache-2.0 | Embedded |
| LangChain (`langchain`, `-core`, `-openai`, `-mcp-adapters`) | 1.4.7 / 1.7.0 / 1.7.2 / 0.3.2 | MIT | Embedded |
| NeMo Guardrails | 0.24.1 | Apache-2.0 | Embedded |
| deepagents | 0.7.32 | MIT | Embedded (deep image) |
| mcp-server-qdrant | 0.8.1 | Apache-2.0 | Embedded |
| boto3 | 1.43.118 | Apache-2.0 | Embedded |
| OpenTelemetry (SDK / instrumentation) | 1.45.1 / 0.66b1 | Apache-2.0 | Embedded |
| a2a-sdk | 1.3.0 | Apache-2.0 | Embedded (sidecar) |
| Pydantic AI (`pydantic-ai-slim`) | 2.62.0 | MIT | Embedded (runtime) |
| fasta2a | 2.1.1 | MIT | Embedded (runtime) |
| CrewAI | 1.15.30 | MIT | Embedded (runtime) |
| OpenCode (`opencode-ai`) | 1.19.4 | MIT | Embedded (npm platform binary; the `opencode-linux-*` package omits the LICENSE, so the upstream MIT LICENSE is vendored to `/opt/opencode/LICENSE` per CE-18d) |

## Base images (embedded)

| Component | Version | SPDX | Distribution |
| :--- | :--- | :--- | :--- |
| Python (`slim-trixie`) | 3.14.9 / 3.13.17 | Python-2.0 | Embedded (first-party image base) |
| Alpine | 3.24.3 | MIT (base; individual apk packages vary) | Embedded (installer/init base) |
| busybox | 1.38.0 | GPL-2.0-only | Embedded (init container; unmodified upstream image) |

## Revision History

| Date | Change |
| :--- | :--- |
| 2026-11-11 | Initial `THIRD_PARTY_NOTICES` for CE `2.4.4`: Agent Router v1.2.1, Envoy Gateway v1.10.0 (Gateway API 1.6.2), Langfuse 4.76.0; OpenCode LICENSE vendored (CE-18d). |
