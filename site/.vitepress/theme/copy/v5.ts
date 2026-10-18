import type { VariantCopy } from './types'

const helm =
  'helm upgrade --install zelkor oci://ghcr.io/zelkor-ai/charts/zelkor-platform --namespace zelkor-system --wait'

export const v5: VariantCopy = {
  id: 5,
  name: 'Emerald Control Plane',
  short: 'Emerald',
  announcement: {
    badge: 'Helm chart v0.4',
    text: 'Deploy the Zelkor control plane on any Kubernetes cluster with gVisor, Cilium, and OpenTelemetry in under 10 minutes.',
    linkLabel: 'Read the Helm Reference →',
    href: '/docs',
  },
  brandSub: 'K8s runtime',
  navCta: { label: 'Request Architecture Review', href: '/contact' },
  productsNav: [
    { slug: 'sandbox', title: 'gVisor Sandbox', blurb: 'Userspace kernel isolation (runsc), rootless read-only containers, ephemeral execution pods.' },
    { slug: 'gateway', title: 'AI Gateway & Guardrails', blurb: 'Upstream credential brokering, per-tenant token budgets, inline prompt/PII inspection.' },
    { slug: 'mcp', title: 'MCP Proxy & Tool Isolation', blurb: 'Authenticated MCP routing, per-agent tool allowlists, schema validation.' },
    { slug: 'tenancy', title: 'Multi-Tenant Data Perimeter', blurb: 'X-Tenant-ID across PostgreSQL RLS, Qdrant, Neo4j, and MinIO.' },
    { slug: 'observability', title: 'Flight Recorder Tracing', blurb: 'Correlated OTel spans across HTTP, LLM turns, MCP calls, and sandbox syscalls.' },
    { slug: 'network', title: 'Network & Cluster Armor', blurb: 'Default-deny Cilium L3–L7, DNS egress whitelisting, explicit container boundaries.' },
  ],
  solutionsNav: [
    { slug: 'financial-services', title: 'Financial Services', blurb: 'Trading-desk segregation, DORA-aligned resilience, air-gapped model routing.' },
    { slug: 'healthcare', title: 'Healthcare & Life Sciences', blurb: 'PHI boundary enforcement, clinical tenant isolation, auditable tool execution.' },
    { slug: 'b2b-saas', title: 'Multi-Tenant B2B SaaS', blurb: 'Customer-scoped RAG, noisy-neighbor token caps, zero-trust code execution.' },
    { slug: 'platform-engineering', title: 'Platform Engineering', blurb: 'Golden Helm paths, Argo CD / Flux GitOps, self-service agent namespaces.' },
  ],
  home: {
    eyebrow: 'Kubernetes-native agent runtime // Helm & GitOps ready',
    h1: 'Run AI agents like any other hardened Kubernetes workload.',
    subtitle:
      'Bring the LangGraph, CrewAI, AutoGen, or custom Python agent you already wrote. Zelkor wraps it in a gVisor kernel sandbox, brokers every LLM and MCP call through a policy-enforced gateway, isolates tenant state at the database layer, and records every hop in OpenTelemetry—deployed via a single Helm chart.',
    primaryCta: { label: 'Deploy Community Chart', href: '/docs/quickstart' },
    secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
    install: helm,
    marqueeLabel: 'Cloud-native primitives & guarantees',
    marquee: [
      'RuntimeClass: gvisor (runsc)',
      'Cilium L3/L4/L7 default-deny',
      'Zero upstream API keys in agent pods',
      'PostgreSQL row-level security (RLS)',
      'OpenTelemetry GenAI semantic conventions',
      'Helm 3 + Argo CD / Flux native',
      'Container resource requests & limits enforced',
      'Framework-agnostic (LangGraph, CrewAI, custom HTTP)',
    ],
    bridgeKicker: 'The platform engineering gap',
    bridgeHeading: 'Application teams ship agents in days. Platform teams spend months trying to make them safe for the cluster.',
    bridge:
      'Standard Kubernetes primitives protect stateless microservices, not autonomous loops that execute untrusted code, call external tools, and hold long-lived credentials. Zelkor gives platform engineers a declarative control plane—expressed in standard Helm values, NetworkPolicy, and RuntimeClass—so application teams can deploy any agent container without bypassing cluster security.',
    tabsHeadline: 'One Helm release. Four enforced runtime boundaries.',
    tabs: [
      {
        id: 'sandbox',
        label: 'Sandbox',
        headline: 'Kernel-level pod isolation',
        copy: 'Agent pods and dynamic code-interpreter sessions run under RuntimeClass: gvisor with read-only root filesystems, dropped Linux capabilities, and explicit CPU/memory requests and limits.',
        lang: 'yaml',
        code: `agentRuntime:
  runtimeClassName: gvisor
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    readOnlyRootFilesystem: true
    allowPrivilegeEscalation: false
    capabilities: { drop: ["ALL"] }
  resources:
    requests: { cpu: 250m, memory: 512Mi }
    limits: { cpu: "1", memory: 2Gi }`,
      },
      {
        id: 'gateway',
        label: 'Gateway',
        headline: 'Credential brokering & guardrails',
        copy: 'Agents never mount OPENAI_API_KEY or ANTHROPIC_API_KEY. They authenticate to the internal Zelkor AI Gateway with a short-lived workload token; the gateway scans prompts, enforces budgets, and injects upstream credentials on egress.',
        lang: 'yaml',
        code: `aiGateway:
  upstreamProviders:
    - name: openai-prod
      secretRef: zelkor-upstream-llm-keys
  guardrails:
    promptInjectionScan: enforce
    piiRedaction: enforce
  budgets:
    defaultTenantDailyUsd: 50.00
    maxTokensPerRequest: 16384
    maxTurnsPerSession: 25`,
      },
      {
        id: 'mcp',
        label: 'MCP & Tenants',
        headline: 'Scoped tools & data perimeters',
        copy: 'Every MCP tool invocation and backing data store query carries a cryptographically verified tenant context. Cross-tenant reads fail closed at the proxy and database engine.',
        lang: 'yaml',
        code: `mcpProxy:
  servers:
    - name: code-interpreter
      transport: http
      endpoint: http://zelkor-sandbox-pool.zelkor-system.svc:8080
      allowedAgents: ["finserve-analyst"]
tenancy:
  header: X-Zelkor-Tenant
  postgresRls:
    enabled: true
    sessionVariable: app.current_tenant_id`,
      },
      {
        id: 'trace',
        label: 'Trace',
        headline: 'Correlated OpenTelemetry flight recorder',
        copy: 'Every prompt, guardrail verdict, token cost, MCP tool argument, and sandbox execution is emitted as a correlated OTel trace to Tempo, Jaeger, or your existing observability stack.',
        lang: 'json',
        code: `{
  "trace_id": "7f9a2c4e8b1d6f305a9e1c2b4d8f6a10",
  "span_name": "zelkor.gateway.chat_completions",
  "attributes": {
    "zelkor.tenant.id": "desk-equities-eu",
    "zelkor.agent.name": "finserve-analyst",
    "zelkor.guardrail.verdict": "allow",
    "gen_ai.request.model": "gpt-4o-2024-11-20"
  }
}`,
      },
    ],
    stepsHeadline: 'Declarative lifecycle. Zero SDK lock-in.',
    steps: [
      {
        title: 'Install the chart',
        subtitle: 'Step 01',
        body: 'Provision the target namespace via cluster admin tooling, then install the Zelkor control plane using helm upgrade --install. Every pod ships with strict resources.requests and resources.limits.',
      },
      {
        title: 'Point the agent',
        subtitle: 'Step 02',
        body: 'Keep your existing Dockerfile and agent framework. Set OPENAI_BASE_URL and MCP_SERVER_URL to the cluster-internal Zelkor services. Remove upstream provider secrets from the workload namespace.',
      },
      {
        title: 'Promote via GitOps',
        subtitle: 'Step 03',
        body: 'Commit agent deployment values, tool allowlists, and token budgets to Git. Let Argo CD or Flux reconcile dev, staging, and production clusters without manual kubectl patches.',
      },
    ],
    proofsHeadline: 'Don’t trust architecture diagrams. Run the cluster proofs.',
    proofsSub: 'Every Zelkor installation includes an automated verification suite that executes five live adversarial scenarios against your cluster.',
    proofs: [
      { title: 'Proof 01 — The Vanishing Key', scenario: 'An attacker dumps /proc/self/environ, mounted volumes, and process memory to steal the upstream LLM API key.', control: 'Zero upstream keys exist inside the pod. The agent holds only a cluster-scoped, short-lived gateway token unusable outside the NetworkPolicy perimeter.', result: 'Verified by proof-vanishing-key.' },
      { title: 'Proof 02 — The Flight Recorder', scenario: 'A compliance auditor requests the exact prompt, PII redaction diff, MCP payload, and token cost for a run 30 days ago.', control: 'A single trace ID reconstructs the full execution DAG—from ingress HTTP header to gVisor sandbox exit code—via OpenTelemetry spans.', result: 'Verified by proof-flight-recorder.' },
      { title: 'Proof 03 — The Shell Moved', scenario: 'A prompt injection runs curl to 169.254.169.254 or writes a binary to /usr/bin.', control: 'Rootfs is read-only, cloud metadata IPs are dropped by Cilium, and tool execution is routed over MCP to an ephemeral network-isolated runsc pod destroyed after the turn.', result: 'Verified by proof-shell-moved.' },
      { title: 'Proof 04 — Two Desks, One Graph', scenario: 'Tenant-A crafts a Cypher/SQL/vector query for Tenant-B rows.', control: 'The data proxy binds verified tenant identity to PostgreSQL RLS, Qdrant collection filters, and Neo4j subgraphs.', result: 'Tenant-B records are structurally invisible.' },
      { title: 'Proof 05 — Loop Dies at the Door', scenario: 'A recursive planning loop fires 500 consecutive LLM calls.', control: 'The AI Gateway trips the per-session turn ceiling and per-tenant daily budget circuit breaker with HTTP 429 BudgetExceeded.', result: 'Verified by proof-loop-dies-at-door.' },
    ],
    personasHeadline: 'Built for the whole platform triad.',
    personas: [
      { title: 'Platform / SRE Team', role: 'Standardize hosting', body: 'Helm-only lifecycle, mandatory container resource requests/limits for LimitRange compliance, Cilium network policies, and Prometheus/OTel metrics out of the box.', points: ['Helm-only lifecycle', 'Quota-ready pods', 'Cilium + Prometheus'] },
      { title: 'Application AI Team', role: 'No rewrite', body: 'Standard OpenAI-compatible and MCP endpoints, managed Python/Node code-interpreter sandboxes, and instant trace debugging when prompts or tools misbehave.', points: ['OpenAI-compatible gateway', 'Managed sandboxes', 'Trace debugging'] },
      { title: 'Security & Compliance Team', role: 'Defense in depth', body: 'Userspace kernel isolation (gVisor), zero upstream secrets in workload pods, deterministic tenant boundaries, and immutable audit trails mapped to SOC 2, HIPAA, and DORA.', points: ['gVisor isolation', 'Zero secrets in pods', 'SOC 2 / HIPAA / DORA mapping'] },
    ],
    finalHeadline: 'Ready to put your agents on a hardened Kubernetes control plane?',
    finalSub: 'Start with the open-source Community chart on your own cluster, or schedule a technical walkthrough of our multi-tenant reference topology.',
    finalPrimary: { label: 'Deploy Community Chart', href: '/docs/quickstart' },
    finalSecondary: { label: 'Request Architecture Review', href: '/contact' },
  },
  products: {
    sandbox: {
      slug: 'sandbox',
      eyebrow: 'Product // gVisor sandbox (runsc)',
      h1: 'Kernel-isolated execution for agents and untrusted code.',
      subtitle: 'Isolate both the persistent agent container and dynamic code-interpreter runs inside Google’s runsc userspace kernel—preventing host kernel syscall exploitation, container breakouts, and filesystem tampering.',
      primaryCta: { label: 'View Sandbox Helm Values', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Cloud-native architecture',
      overview: 'Zelkor decouples agent orchestration from code execution: the agent pod runs rootless under RuntimeClass: gvisor, and any exec tool call is dispatched via MCP to a warm pool of ephemeral, network-dark runsc sandbox pods recycled after completion.',
      capabilities: [
        { title: 'Userspace kernel interception (runsc)', text: 'Every syscall is intercepted by the gVisor Sentry, shielding the host Linux kernel.' },
        { title: 'Warm ephemeral sandbox pool', text: 'Pre-warmed pods eliminate cold-start latency while guaranteeing filesystem state and memory are wiped between sessions.' },
        { title: 'Rootless, read-only container hardening', text: 'runAsNonRoot, readOnlyRootFilesystem, allowPrivilegeEscalation: false, capabilities.drop ALL, bounded emptyDir scratch.' },
        { title: 'Quota-safe resource boundaries', text: 'Explicit requests and limits for CPU, memory, and ephemeral storage on every agent and sandbox container.' },
      ],
      snippetTitle: 'sandboxPool values',
      snippetLang: 'yaml',
      snippet: `sandboxPool:
  enabled: true
  replicas: 4
  runtimeClassName: gvisor
  recycleAfterExecutions: 1
  executionTimeoutSeconds: 30
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 65532
  resources:
    requests: { cpu: 500m, memory: 1Gi }
    limits: { cpu: "2", memory: 4Gi }`,
      bottomHeadline: 'See The Shell Moved proof in action.',
      bottomPrimary: { label: 'Run Sandbox Proof', href: '/docs' },
      bottomSecondary: { label: 'Talk to a Platform Architect', href: '/contact' },
    },
    gateway: {
      slug: 'gateway',
      eyebrow: 'Product // AI gateway & guardrails',
      h1: 'One ingress point for every model call, budget, and guardrail.',
      subtitle: 'Remove upstream LLM API keys from agent namespaces. Route all model traffic through a cluster-internal proxy that enforces token budgets, scans for prompt injection and PII, and fails over across providers.',
      primaryCta: { label: 'Explore Gateway Config', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Cloud-native architecture',
      overview: 'Workload pods hold zero upstream keys. Agents point their standard SDK at http://zelkor-gateway.zelkor-system.svc:8000/v1. The gateway validates the caller’s ServiceAccount and tenant token, runs guardrails, checks Redis token budgets, and attaches credentials only as the request leaves the cluster.',
      capabilities: [
        { title: 'Zero-trust credential brokering', text: 'Upstream keys live exclusively in a locked-down gateway Secret inside zelkor-system.' },
        { title: 'Real-time cost & loop circuit breakers', text: 'Hard limits on tokens per request, turns per session, and daily/monthly spend per tenant or agent.' },
        { title: 'Inline prompt & PII inspection', text: 'Injection classifiers, regex/NER PII redactors, and secret-leakage detectors with log or enforce modes.' },
        { title: 'Unified multi-provider routing', text: 'OpenAI, Anthropic, Azure, Bedrock, or cluster-local vLLM/Ollama with declarative aliases and fallback.' },
      ],
      snippetTitle: 'gateway values',
      snippetLang: 'yaml',
      snippet: `gateway:
  replicaCount: 2
  upstreamSecretName: zelkor-llm-provider-credentials
  routing:
    defaultModel: "gpt-4o-mini"
  guardrails:
    input:
      promptInjectionPolicy: enforce
      redactPiiEntities: ["EMAIL", "SSN", "CREDIT_CARD", "IBAN"]
  rateLimits:
    maxTurnsPerTrace: 20
    tenantDailyBudgetUsd: 100.00`,
      bottomHeadline: 'Verify The Vanishing Key and Loop Dies at the Door on your cluster.',
      bottomPrimary: { label: 'Read Gateway Docs', href: '/docs' },
      bottomSecondary: { label: 'Request Architecture Review', href: '/contact' },
    },
    mcp: {
      slug: 'mcp',
      eyebrow: 'Product // MCP proxy & tool isolation',
      h1: 'Zero-trust mediation for Model Context Protocol servers.',
      subtitle: 'Control which agents can invoke which tools, validate JSON-RPC schemas in transit, and strip unauthorized arguments before any MCP tool touches an internal API or database.',
      primaryCta: { label: 'View MCP Proxy Docs', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Cloud-native architecture',
      overview: 'Zelkor interposes a stateless, horizontally scalable MCP Proxy between agent pods and MCP tool servers. Every tools/list and tools/call is authenticated, filtered to an allowlist, validated against JSON Schema, and logged as an OpenTelemetry span.',
      capabilities: [
        { title: 'Per-agent tool allowlists', text: 'Bind agents to specific MCP servers and methods; hide unauthorized tools from tools/list.' },
        { title: 'JSON-RPC schema & argument validation', text: 'Enforce parameter types, path prefixes, and query constraints at the proxy layer.' },
        { title: 'Tenant identity injection', text: 'Inject verified X-Zelkor-Tenant metadata so tool servers cannot be spoofed.' },
        { title: 'High-risk action gates', text: 'Flag mutating calls (delete_record, execute_wire, merge_pr) for policy denial or approval webhooks.' },
      ],
      snippetTitle: 'mcpProxy values',
      snippetLang: 'yaml',
      snippet: `mcpProxy:
  enabled: true
  replicaCount: 2
  policies:
    - agentId: "customer-support-triage"
      allowedServers:
        - server: "crm-mcp"
          allowedTools: ["get_ticket", "list_customer_orders", "add_draft_note"]
          deniedTools: ["delete_customer", "issue_refund"]`,
      bottomHeadline: 'Lock down MCP tool surfaces without rewriting your tool servers.',
      bottomPrimary: { label: 'Explore MCP Reference', href: '/docs' },
      bottomSecondary: { label: 'Request Architecture Review', href: '/contact' },
    },
    tenancy: {
      slug: 'tenancy',
      eyebrow: 'Product // multi-tenant data perimeter',
      h1: 'Cryptographic tenant isolation across relational, vector, and graph stores.',
      subtitle: 'Stop relying on prompt instructions to keep Customer A out of Customer B’s data. Zelkor binds tenant identity at the infrastructure layer across PostgreSQL, Qdrant, Neo4j, and MinIO.',
      primaryCta: { label: 'Read Multi-Tenancy Architecture', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Cloud-native architecture',
      overview: 'Ingress authenticates the caller and mints a signed tenant context (X-Zelkor-Tenant). Every downstream adapter sets tenant context at the storage engine—PostgreSQL RLS, Qdrant payload filters, Neo4j subgraphs, MinIO S3 prefixes.',
      capabilities: [
        { title: 'PostgreSQL Row-Level Security', text: 'Connection pools wrap every transaction with SET LOCAL app.current_tenant_id.' },
        { title: 'Scoped vector retrieval', text: 'RAG proxies inject immutable tenant filter predicates into every vector search.' },
        { title: 'Graph & object storage partitioning', text: 'Desk- and tenant-level subgraph isolation in Neo4j and prefix-scoped MinIO/S3 credentials.' },
        { title: 'End-to-end context propagation', text: 'Tenant identity travels in signed headers and OTel baggage through every async worker and MCP hop.' },
      ],
      snippetTitle: 'tenancy values',
      snippetLang: 'yaml',
      snippet: `tenancy:
  enforcementMode: strict
  tenantHeader: "X-Zelkor-Tenant"
  postgres:
    rlsEnabled: true
    sessionVariable: "app.current_tenant_id"
  qdrant:
    isolationStrategy: "payload_filter"
    tenantFieldKey: "tenant_id"
  neo4j:
    isolationStrategy: "property_guard"
    tenantPropertyKey: "desk_id"`,
      bottomHeadline: 'See how Two Desks, One Graph prevents cross-tenant leakage.',
      bottomPrimary: { label: 'View Proof 04 Details', href: '/docs' },
      bottomSecondary: { label: 'Request Architecture Review', href: '/contact' },
    },
    observability: {
      slug: 'observability',
      eyebrow: 'Product // flight recorder tracing',
      h1: 'Full-fidelity OpenTelemetry traces for every agent turn.',
      subtitle: 'Correlate ingress HTTP requests, gateway guardrail checks, LLM token consumption, MCP tool payloads, and gVisor sandbox execution into a single distributed trace.',
      primaryCta: { label: 'Explore Observability Stack', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Cloud-native architecture',
      overview: 'Zelkor instruments the data plane using native OpenTelemetry and GenAI semantic conventions. Gateway, MCP proxy, data perimeter, and sandbox controller propagate W3C traceparent headers to Grafana or your enterprise SIEM/APM.',
      capabilities: [
        { title: 'Correlated multi-hop trace DAGs', text: 'Follow a single trace_id from user ingress through LLM turns, MCP calls, database queries, and sandboxed subprocesses.' },
        { title: 'Guardrail & policy audit spans', text: 'Record evaluations, redacted PII token counts, and allow/deny decisions without leaking raw payloads.' },
        { title: 'Per-tenant token & cost telemetry', text: 'Prometheus counters tagged by tenant_id, agent_name, and model.' },
        { title: 'Bring-your-own OTLP backend', text: 'Bundled Grafana + Tempo + Prometheus + Loki, or forward to Datadog, Honeycomb, Splunk, Elastic.' },
      ],
      snippetTitle: 'observability values',
      snippetLang: 'yaml',
      snippet: `observability:
  otelCollector:
    enabled: true
    exporters:
      otlp:
        endpoint: "tempo.zelkor-system.svc.cluster.local:4317"
    attributes:
      includeTenantId: true
      includeGuardrailVerdicts: true
      redactPromptPayloadsInLogs: true`,
      bottomHeadline: 'Reconstruct any historical agent decision in seconds.',
      bottomPrimary: { label: 'See Flight Recorder Proof', href: '/docs' },
      bottomSecondary: { label: 'Request Architecture Review', href: '/contact' },
    },
    network: {
      slug: 'network',
      eyebrow: 'Product // network & cluster armor',
      h1: 'Default-deny Cilium policies and strict Kubernetes workload hygiene.',
      subtitle: 'Lock down east-west pod traffic, block unauthorized egress and cloud metadata endpoints, and enforce container resource limits across every component in the chart.',
      primaryCta: { label: 'Inspect NetworkPolicy Templates', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Cloud-native architecture',
      overview: 'Zelkor ships declarative Kubernetes NetworkPolicy and CiliumNetworkPolicy manifests that place every agent and sandbox pod in a default-deny posture. Agents can only communicate with the internal AI Gateway and MCP Proxy.',
      capabilities: [
        { title: 'Default-deny ingress & egress', text: 'No public internet, other tenant pods, Kubernetes API, or backing databases—only gateway and MCP proxy ports.' },
        { title: 'Cloud metadata & link-local blocking', text: 'Explicit CIDR deny for 169.254.169.254/32 and internal node subnets.' },
        { title: 'Cilium L7 DNS & FQDN egress control', text: 'Where external API access is required, restrict to approved domain names and TLS ports.' },
        { title: 'Quota-ready pod specifications', text: 'Every Deployment, StatefulSet, and Job defines mandatory CPU and memory requests and limits.' },
      ],
      snippetTitle: 'CiliumNetworkPolicy',
      snippetLang: 'yaml',
      snippet: `apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: zelkor-agent-zero-trust-egress
  namespace: zelkor-workloads
spec:
  endpointSelector:
    matchLabels: { zelkor.io/component: agent-workload }
  egressDeny:
    - toCIDR: ["169.254.169.254/32"]`,
      bottomHeadline: 'Deploy zero-trust network boundaries via standard Helm values.',
      bottomPrimary: { label: 'View Security Hardening Guide', href: '/docs' },
      bottomSecondary: { label: 'Request Architecture Review', href: '/contact' },
    },
  },
  solutions: {
    'financial-services': {
      slug: 'financial-services',
      eyebrow: 'Solutions // financial services & capital markets',
      h1: 'Desk-isolated AI agents with deterministic auditability and zero key exposure.',
      subtitle: 'Deploy quantitative research, compliance surveillance, and client advisory agents on Kubernetes while enforcing ethical walls between desks, DORA-aligned operational resilience, and full OpenTelemetry lineage.',
      primaryCta: { label: 'Explore FinServe Reference Topology', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      risks: [
        { title: 'Cross-desk information leakage', text: 'X-Zelkor-Tenant binds desk identity to PostgreSQL RLS, Qdrant filters, and Neo4j property guards (Proof 04).' },
        { title: 'Exfiltration of upstream model credentials', text: 'Upstream keys never enter workload namespaces (Proof 01).' },
        { title: 'Unbounded quantitative code execution', text: 'Ephemeral network-dark gVisor sandboxes with read-only root filesystems (Proof 03).' },
        { title: 'Incomplete regulatory audit trails', text: 'Correlated OTel Flight Recorder spans (Proof 02).' },
        { title: 'Runaway agent loops', text: 'Per-desk token budgets and per-session turn circuit breakers (Proof 05).' },
        { title: 'Unauthorized internal API mutation via MCP', text: 'Per-agent tool allowlists block mutating JSON-RPC methods.' },
      ],
      mappingTitle: 'Compliance & Kubernetes control mapping',
      mapping: [
        { framework: 'Information barriers / MNPI', requirement: 'Desk segregation', control: 'PostgreSQL RLS + Neo4j/Qdrant tenant scoping (Proof 04)' },
        { framework: 'DORA ICT operational resilience', requirement: 'Circuit breaking and resource isolation', control: 'Gateway budgets + Pod resources (Proof 05)' },
        { framework: 'Host & workload isolation', requirement: 'Untrusted code off the node kernel', control: 'RuntimeClass gvisor + rootless PSS (Proof 03)' },
        { framework: 'Secret management', requirement: 'Least privilege credentials', control: 'Gateway credential brokering + Cilium default-deny (Proof 01)' },
        { framework: 'Supervisory recordkeeping', requirement: 'Lineage of automated decisions', control: 'OTel GenAI spans (Proof 02)' },
      ],
      scenariosTitle: 'Production topologies',
      scenarios: [
        { title: 'Multi-desk private cloud', text: 'Shared zelkor-system with dedicated workload namespaces per business unit and desk-scoped data perimeters.' },
        { title: 'Air-gapped / on-premises model serving', text: 'Private OCI registry, zero public egress, gateway to cluster-local vLLM / NVIDIA NIM.' },
        { title: 'Hybrid cloud gateway federated routing', text: 'On-prem execution and PII redaction; scrubbed prompts over mTLS/PrivateLink to managed foundation models.' },
      ],
      bottomHeadline: 'Deploy the FinServe multi-desk reference architecture on your cluster.',
      bottomCta: { label: 'Request Architecture Review', href: '/contact' },
    },
    healthcare: {
      slug: 'healthcare',
      eyebrow: 'Solutions // healthcare & life sciences',
      h1: 'PHI-safe clinical and bioinformatics agents on Kubernetes.',
      subtitle: 'Run prior-authorization, clinical documentation, and genomics research agents with inline PHI redaction, tenant-isolated patient records, and sandboxed bioinformatics tool execution.',
      primaryCta: { label: 'Read Healthcare Architecture Guide', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      risks: [
        { title: 'Unintended PHI transmission to external LLMs', text: 'Synchronous AI Gateway guardrails detect and redact PHI entities before requests leave the cluster.' },
        { title: 'Cross-clinic / cross-study contamination', text: 'Deterministic X-Zelkor-Tenant across PostgreSQL RLS and vector stores.' },
        { title: 'Untrusted bioinformatics script execution', text: 'Ephemeral gVisor sandboxes with zero external network egress and bounded CPU/memory.' },
        { title: 'Over-privileged EHR / FHIR tool access', text: 'MCP Proxy allowlists restrict agents to explicit read-only FHIR methods.' },
        { title: 'Missing audit logs for clinical decision support', text: 'Full Flight Recorder traces of every tool invocation and data source query.' },
        { title: 'Noisy-neighbor resource contention', text: 'LimitRange plus per-workload AI Gateway token budgets.' },
      ],
      mappingTitle: 'Healthcare mapping',
      mapping: [
        { framework: 'HIPAA minimum necessary & PHI protection', requirement: 'Redact and restrict ePHI', control: 'Gateway inline PII/PHI redaction + MCP allowlists' },
        { framework: 'Multi-provider / study segregation', requirement: 'No cross-cohort retrieval', control: 'PostgreSQL RLS + Qdrant tenant filters (Proof 04)' },
        { framework: 'Access control & credential hygiene', requirement: 'No raw keys in agent pods', control: 'Proof 01 vanishing-key' },
        { framework: 'Audit controls 45 CFR §164.312(b)', requirement: 'Record ePHI activity', control: 'Proof 02 flight-recorder' },
        { framework: 'Bioinformatics compute isolation', requirement: 'Untrusted scripts contained', control: 'gVisor + Cilium default-deny (Proof 03)' },
      ],
      scenariosTitle: 'Production topologies',
      scenarios: [
        { title: 'VPC-isolated BAA model routing', text: 'HIPAA-eligible cluster; PrivateLink to BAA-covered Azure OpenAI or AWS Bedrock.' },
        { title: 'Self-hosted clinical LLM cluster', text: 'Zelkor runtime and local medical models inside hospital-managed nodes with zero external egress.' },
        { title: 'Multi-institution research enclave', text: 'Strict tenant boundaries per study and warm gVisor pools for isolated statistical analysis.' },
      ],
      bottomHeadline: 'Architect a PHI-aware agent runtime on your Kubernetes infrastructure.',
      bottomCta: { label: 'Request Architecture Review', href: '/contact' },
    },
    'b2b-saas': {
      slug: 'b2b-saas',
      eyebrow: 'Solutions // multi-tenant B2B SaaS',
      h1: 'Ship customer-facing AI agents without cross-tenant leaks or runaway COGS.',
      subtitle: 'Give every SaaS customer their own isolated agent workspace, strict RAG data boundary, sandboxed code execution, and hard token budget—on a single shared Kubernetes cluster.',
      primaryCta: { label: 'View SaaS Multi-Tenancy Guide', href: '/products/tenancy' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      risks: [
        { title: 'Cross-customer RAG & memory leaks', text: 'Cryptographic X-Zelkor-Tenant enforces PostgreSQL RLS and vector collection filters (Proof 04).' },
        { title: 'Margin erosion from noisy-neighbor token spend', text: 'Per-tenant USD budgets and per-session turn caps (Proof 05).' },
        { title: 'RCE via customer uploads', text: 'File parsing and code execution in disposable gVisor sandboxes (Proof 03).' },
        { title: 'Lateral movement across SaaS microservices', text: 'Cilium L3–L7 restricts agent egress solely to gateway and MCP proxy.' },
        { title: 'Opaque incident debugging', text: 'Tenant-tagged OTel traces reconstruct the complete execution graph (Proof 02).' },
        { title: 'Secret exposure via prompt injection', text: 'Agent pods contain zero upstream API keys (Proof 01); outbound guardrails block secret patterns.' },
      ],
      mappingTitle: 'SaaS platform mapping',
      mapping: [
        { framework: 'SOC 2 logical tenant isolation', requirement: 'Signed tenant header + storage filters', control: 'Proof 04' },
        { framework: 'Per-customer COGS & rate governance', requirement: 'Budget ledger + session turn limits', control: 'Proof 05' },
        { framework: 'Untrusted input / code execution safety', requirement: 'Ephemeral gVisor + read-only rootfs', control: 'Proof 03' },
        { framework: 'Zero-secret workload containers', requirement: 'Gateway credential brokering', control: 'Proof 01' },
        { framework: 'Per-tenant usage billing', requirement: 'Prometheus zelkor_tokens_total{tenant_id}', control: 'OTel / Prometheus scrape' },
      ],
      scenariosTitle: 'Production topologies',
      scenarios: [
        { title: 'Shared pool multi-tenancy', text: 'High-density pods serving thousands of SMB tenants, isolated logically via headers, RLS, and gateway budget buckets.' },
        { title: 'Namespace-per-enterprise-tier', text: 'Shared zelkor-system with dedicated namespaces and gVisor node pools for high-tier customers.' },
        { title: 'BYOK tenant routing', text: 'Gateway dynamically selects each enterprise customer’s vaulted OpenAI/Bedrock key from verified X-Zelkor-Tenant.' },
      ],
      bottomHeadline: 'Build multi-tenant SaaS agents with infrastructure-enforced boundaries.',
      bottomCta: { label: 'Deploy Community Chart', href: '/docs/quickstart' },
    },
    'platform-engineering': {
      slug: 'platform-engineering',
      eyebrow: 'Solutions // platform engineering & SRE',
      h1: 'A golden Kubernetes path for every AI agent in your organization.',
      subtitle: 'Stop reviewing bespoke Dockerfiles and ad-hoc firewall rules for every new agent project. Standardize packaging, sandboxing, secret brokering, and observability behind a single Helm chart and GitOps workflow.',
      primaryCta: { label: 'Inspect Chart Architecture', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      risks: [
        { title: 'Snowflake agent deployments', text: 'A standardized Helm chart and workload template onboard any HTTP/MCP agent container onto one governed runtime.' },
        { title: 'ResourceQuota and LimitRange admission failures', text: 'Every container, initContainer, and sandbox template defines explicit CPU and memory requests and limits.' },
        { title: 'Imperative kubectl drift in CI/CD', text: '100% Helm-native into admin-provisioned namespaces, reconcilable by Argo CD and Flux.' },
        { title: 'Unrestricted egress & lateral movement', text: 'Pre-built Cilium and NetworkPolicy templates enforce default-deny from day one.' },
        { title: 'Host node compromise via runc escape', text: 'Declarative RuntimeClass: gvisor assignment for agents and dynamic sandboxes.' },
        { title: 'Blind spots in existing observability', text: 'Native OTel and Prometheus exporters plug into existing cluster monitoring stacks.' },
      ],
      mappingTitle: 'Platform engineering standards',
      mapping: [
        { framework: 'GitOps declarative reconciliation', requirement: 'Versioned Helm + values in Git', control: 'Argo CD / Flux sync health + helm lint' },
        { framework: 'Namespace & quota hygiene', requirement: 'Admin-created namespaces + mandatory resources', control: 'ResourceQuota / LimitRange admission' },
        { framework: 'Pod Security Standards (Restricted)', requirement: 'runAsNonRoot, readOnlyRootFilesystem, drop ALL', control: 'Kubernetes PSA' },
        { framework: 'East-west & north-south segmentation', requirement: 'CiliumNetworkPolicy + NetworkPolicy', control: 'Cilium connectivity tests' },
        { framework: 'Automated post-deploy verification', requirement: '5 built-in cluster proofs', control: 'CI/CD post-sync Helm verification suite' },
      ],
      scenariosTitle: 'Production topologies',
      scenarios: [
        { title: 'Hub-and-spoke namespace model', text: 'Platform manages zelkor-system; teams deploy agent charts into quota-enforced team namespaces.' },
        { title: 'Multi-cluster GitOps promotion', text: 'Argo CD ApplicationSets promote image digests, MCP allowlists, and token budgets across env clusters via PRs.' },
        { title: 'Dedicated sandbox node pool', text: 'Taints and tolerations schedule gVisor sandbox pods onto dedicated, autoscaled workers isolated from stateful DBs.' },
      ],
      bottomHeadline: 'Give developers self-service agent infrastructure without sacrificing cluster control.',
      bottomCta: { label: 'Read the Helm Reference', href: '/docs' },
    },
  },
  editions: {
    eyebrow: 'Editions & licensing // transparent capabilities',
    h1: 'One Kubernetes architecture. Scaled to your governance boundary.',
    subtitle: 'Start with the open-source Community Edition on any Kubernetes cluster. Upgrade to Pro or Enterprise when you need multi-cluster fleet management, enterprise SSO/RBAC, or regulated compliance packs.',
    primaryCta: { label: 'Deploy Community Edition', href: '/docs/quickstart' },
    secondaryCta: { label: 'Contact Sales for Pro / Enterprise', href: '/contact' },
    cards: [
      {
        name: 'Community Edition (CE)',
        kicker: 'Open-source core // self-hosted',
        tagline: 'Individual platform engineers, security evaluations, and single-cluster production workloads.',
        highlights: [
          'Full Helm chart on any conformant Kubernetes cluster',
          'gVisor (runsc) agent & code-interpreter isolation',
          'AI Gateway with credential brokering and guardrails',
          'All 5 reproducible cluster proofs',
        ],
        cta: { label: 'Install via Helm', href: '/docs/quickstart' },
        featured: true,
      },
      {
        name: 'Pro Edition',
        kicker: 'Production platform teams // commercial support',
        tagline: 'Multi-team engineering organizations running multiple agent workloads with centralized cost and policy governance.',
        highlights: [
          'Centralized policy & budget management UI',
          'Adaptive warm pool autoscaling',
          'OIDC / SAML SSO and operator RBAC',
          'Webhook approval for high-risk MCP tools',
        ],
        cta: { label: 'Request Pro Evaluation', href: '/contact' },
      },
      {
        name: 'Enterprise Edition',
        kicker: 'Regulated & air-gapped fleets // custom SLA',
        tagline: 'Financial institutions, healthcare systems, and large B2B SaaS providers across multiple clusters or sovereign environments.',
        highlights: [
          'Air-gapped OCI bundles with signed SBOMs',
          'Multi-cluster federated gateway routing',
          'External KMS / Vault / HSM',
          '24/7 enterprise support + dedicated architect',
        ],
        cta: { label: 'Book Enterprise Architecture Review', href: '/contact' },
      },
    ],
    matrix: [
      { capability: 'Helm-native Kubernetes deployment', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'gVisor (runsc) kernel sandboxing', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'Ephemeral code-interpreter sandbox pool', ce: 'Static warm pool', pro: 'Adaptive autoscaling', enterprise: 'Multi-node-group isolated pools' },
      { capability: 'AI Gateway credential brokering', ce: 'Included', pro: 'Included', enterprise: 'Included + Vault / HSM' },
      { capability: 'Inline prompt injection & PII guardrails', ce: 'Included', pro: 'Included + custom classifier rules', enterprise: 'Included + custom domain models' },
      { capability: 'Token budgets & loop circuit breakers', ce: 'Per-tenant & per-session', pro: 'Namespace & team hierarchy', enterprise: 'Cross-cluster federated budgets' },
      { capability: 'MCP Proxy & per-agent tool allowlists', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'High-risk MCP tool approval gates', ce: 'Policy allow / deny', pro: 'Async webhook approvals', enterprise: 'ITSM / PagerDuty / Slack flows' },
      { capability: 'Multi-tenant data perimeter', ce: 'Included', pro: 'Included', enterprise: 'Included + BYOK tenant encryption' },
      { capability: 'OpenTelemetry Flight Recorder', ce: 'Included', pro: 'Included', enterprise: 'Included + WORM / SIEM sinks' },
      { capability: 'Cilium L3–L7 & NetworkPolicies', ce: 'Included', pro: 'Included', enterprise: 'Included + multi-cluster mesh' },
      { capability: '5 automated cluster verification proofs', ce: 'Included', pro: 'Included', enterprise: 'Included + continuous compliance runner' },
      { capability: 'Identity, SSO & operator RBAC', ce: 'kubeconfig / static tokens', pro: 'OIDC / SAML + team RBAC', enterprise: 'ABAC + SCIM' },
      { capability: 'Air-gapped & signed supply chain', ce: 'Public GHCR', pro: 'Private registry mirror', enterprise: 'Offline bundles + Cosign / SLSA' },
      { capability: 'Support', ce: 'GitHub Discussions', pro: 'Business-hours SLA', enterprise: '24/7 SLA + dedicated architect' },
    ],
    faqs: [
      { q: 'Do we need to rewrite existing LangGraph, CrewAI, or custom Python agents?', a: 'No. Zelkor is framework-agnostic. Point OPENAI_BASE_URL at the cluster-internal AI Gateway and your MCP client at the MCP Proxy. No proprietary SDK wrapper is required.' },
      { q: 'Does the Helm chart work with ResourceQuota, LimitRange, and no --create-namespace?', a: 'Yes. Every container and initContainer defines explicit CPU and memory requests and limits. Install workflows assume the target namespace is pre-created by a cluster administrator.' },
      { q: 'How does Zelkor prevent an agent from leaking upstream API keys if the container is compromised?', a: 'Upstream keys are never mounted inside agent pods. Agents authenticate to the internal gateway using a short-lived cluster-scoped token. The gateway injects the upstream credential only as the request leaves the cluster (Proof 01).' },
      { q: 'Is Zelkor claiming to make LLMs 100% jailbreak-proof?', a: 'No. Zelkor assumes prompt-level filters can be bypassed—which is why we enforce gVisor sandboxes, read-only filesystems, Cilium default-deny, MCP allowlists, and database-enforced RLS underneath the model.' },
      { q: 'What Kubernetes cluster prerequisites are required?', a: 'Any conformant cluster (EKS, GKE, AKS, OpenShift, k3s, kubeadm). Worker nodes hosting agents/sandboxes need the gVisor runsc shim and RuntimeClass. Cilium is recommended for L7 DNS policies.' },
      { q: 'Can we integrate with existing Argo CD, Flux, or Prometheus/Grafana?', a: 'Yes. Gateway guardrails, tenant budgets, and MCP allowlists are Helm values so GitOps can reconcile them. Telemetry is standard OTLP and Prometheus scrape endpoints.' },
    ],
  },
}
