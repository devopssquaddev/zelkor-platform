import type { VariantCopy } from './types'

const helm =
  'helm upgrade --install zelkor oci://ghcr.io/zelkor-ai/charts/zelkor-platform --namespace zelkor-system --wait'

export const v2: VariantCopy = {
  id: 2,
  name: 'Obsidian Perimeter',
  short: 'Obsidian',
  announcement: {
    badge: 'Zero-trust',
    text: 'Assume the prompt will be injected. Enforce the boundary in Kubernetes.',
    linkLabel: 'Run the 5 security proofs →',
    href: '/docs',
  },
  brandSub: 'Zero-trust Kubernetes runtime',
  navCta: { label: 'Book an Architecture Review', href: '/contact' },
  productsNav: [
    { slug: 'sandbox', title: 'gVisor Sandbox', blurb: 'Kernel syscall interception, read-only rootfs, zero-credential pods.' },
    { slug: 'gateway', title: 'AI Gateway & Guardrails', blurb: 'Upstream secret vaulting, prompt verification, hard token budgets.' },
    { slug: 'mcp', title: 'MCP Proxy & Tool Isolation', blurb: 'Per-call JSON-RPC inspection, tool allowlists, credential brokering.' },
    { slug: 'tenancy', title: 'Multi-Tenant Data Perimeter', blurb: 'JWT propagation across Postgres RLS, Qdrant, and Neo4j.' },
    { slug: 'observability', title: 'Flight Recorder Tracing', blurb: 'Immutable OpenTelemetry & Langfuse trails for every turn.' },
    { slug: 'network', title: 'Network & Cluster Armor', blurb: 'Default-deny Cilium L3–L7 egress and SPIFFE/SPIRE mTLS.' },
  ],
  solutionsNav: [
    { slug: 'financial-services', title: 'Financial Services', blurb: 'Desk-level isolation and SR 11-7, SEC, FINRA, DORA controls.' },
    { slug: 'healthcare', title: 'Healthcare & Life Sciences', blurb: 'PHI boundary enforcement and zero-retention egress (HIPAA).' },
    { slug: 'b2b-saas', title: 'Multi-Tenant B2B SaaS', blurb: 'Per-customer blast-radius containment on shared clusters (SOC 2).' },
    { slug: 'platform-engineering', title: 'Platform Engineering', blurb: 'Self-service Helm with mandatory cluster-wide guardrails.' },
  ],
  home: {
    eyebrow: 'Zero-trust agent runtime on Kubernetes (runtimeClassName: gvisor)',
    h1: 'Assume the prompt will be injected. Enforce the boundary in Kubernetes.',
    subtitle:
      'Language models cannot enforce their own security perimeter. Zelkor wraps the Python or TypeScript agents you already wrote in gVisor userspace kernels, strips raw API keys from pod memory, brokers every MCP tool call, and enforces tenant isolation down to the database row.',
    primaryCta: { label: 'Run the 5 Security Proofs', href: '/docs' },
    secondaryCta: { label: 'Book an Architecture Review', href: '/contact' },
    install: helm,
    marqueeLabel: 'Works unmodified with your existing agent code',
    marquee: [
      'LangGraph', 'CrewAI', 'OpenAI Agents SDK', 'PydanticAI', 'AutoGen', 'LlamaIndex',
      'Anthropic MCP', 'FastAPI', 'gVisor (runsc)', 'Cilium eBPF', 'Envoy AI Gateway',
      'LiteLLM', 'Langfuse', 'OpenTelemetry',
    ],
    bridgeKicker: 'Why application-level guardrails fail on their own',
    bridgeHeading: 'Move enforcement out of the prompt and into the infrastructure layer.',
    bridge:
      'When an agent parses untrusted documents, emails, or web payloads, indirect prompt injection is a matter of when, not if. If your agent container holds OPENAI_API_KEY in os.environ, shares a database pool across customers, or runs on the shared host Linux kernel with unrestricted egress, a single hijacked turn compromises the entire workload. Zelkor moves enforcement where the agent cannot override it.',
    tabsHeadline: 'Four enforcement planes. The agent cannot turn them off.',
    tabs: [
      {
        id: 'sandbox',
        label: 'Sandbox',
        headline: 'Contain arbitrary code execution inside a userspace kernel.',
        copy: 'Every agent pod runs under runtimeClassName: gvisor (runsc), intercepting Linux syscalls in userspace. Root filesystems are read-only, all capabilities are dropped, privilege escalation is blocked, and pods execute as non-root UID 65532.',
        lang: 'yaml',
        code: `apiVersion: zelkor.io/v1alpha1
kind: AgentWorkload
metadata:
  name: equity-research-agent
  namespace: zelkor-agents
spec:
  runtimeClassName: gvisor
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    readOnlyRootFilesystem: true
    allowPrivilegeEscalation: false
    capabilities:
      drop: ["ALL"]`,
      },
      {
        id: 'gateway',
        label: 'Gateway',
        headline: 'Verify prompts, cap spend, and inject upstream keys at the edge.',
        copy: 'Agent containers never receive upstream LLM API keys. Pods authenticate to the in-cluster Zelkor AI Gateway using short-lived workload tokens. The gateway verifies prompts, redacts secrets, enforces token budgets, and attaches provider credentials only on the outbound TLS hop.',
        lang: 'yaml',
        code: `gateway:
  upstreamCredentials:
    injectAtGatewayOnly: true
    secretRef: llm-provider-vault
  guardrails:
    verifyInputPrompts: true
    redactOutputSecrets: true
  budgets:
    maxTokensPerRun: 50000
    maxSpendPerTenantHourlyUsd: 25.00
    loopCircuitBreakerTurns: 15`,
      },
      {
        id: 'mcp',
        label: 'MCP & Tenants',
        headline: 'Authorize every tool call and scope every query to the caller’s tenant.',
        copy: 'Agents cannot call MCP servers or databases directly. Every JSON-RPC invocation passes through the Zelkor MCP Proxy, which validates the tool name against the manifest and propagates the signed tenant_id into PostgreSQL RLS, Qdrant filters, and Neo4j partitions.',
        lang: 'yaml',
        code: `mcpProxy:
  defaultPolicy: deny
  allowedServers:
    - name: portfolio-sql-mcp
      allowedTools: ["get_positions", "list_trades"]
      requireTenantClaim: true
      rlsSessionVariable: "app.current_tenant"`,
      },
      {
        id: 'trace',
        label: 'Trace',
        headline: 'Reconstruct every prompt, tool payload, and policy decision.',
        copy: 'All LLM turns, MCP calls, and egress flows traverse Zelkor’s proxy plane. Telemetry cannot be disabled by agent code. Every span is correlated by trace_id, tenant_id, and agent_id.',
        lang: 'json',
        code: `{
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "tenant_id": "desk-rates-eu",
  "agent_id": "equity-research-agent",
  "event": "mcp.tool.invocation",
  "tool": "portfolio-sql-mcp/get_positions",
  "rls_context": "app.current_tenant=desk-rates-eu",
  "gateway_guardrail": "PASS",
  "verdict": "ALLOWED"
}`,
      },
    ],
    stepsHeadline: 'Three steps to a verified perimeter.',
    steps: [
      { title: 'Install the perimeter chart (5 min)', body: 'Deploy the Zelkor control and data plane into your existing cluster via Helm. No custom CRD rewrites in your application repo.' },
      { title: 'Point your unmodified agent image (2 min)', body: 'Keep your LangGraph, CrewAI, or custom container. Set OPENAI_BASE_URL to the in-cluster gateway and register allowed MCP endpoints in values.yaml.' },
      { title: 'Verify with deterministic security proofs (3 min)', body: 'Run the adversarial verification suite against your live deployment to prove key isolation, syscall containment, tenant separation, and budget circuit breaking.' },
    ],
    proofsHeadline: 'Five reproducible security proofs',
    proofsSub: 'Every installation includes five live, deterministic adversarial tests you can run in your own cluster.',
    proofs: [
      { title: 'Proof 01 — The Vanishing Key', scenario: 'Force the agent to dump /proc/self/environ and memory strings to exfiltrate OPENAI_API_KEY.', control: 'Keys do not exist in the agent namespace. The pod holds only an ephemeral cluster-local token accepted exclusively by the gateway.', result: 'Exfiltration returns zero upstream credentials.' },
      { title: 'Proof 02 — The Flight Recorder', scenario: 'Instruct compromised code to suppress logging or omit tool arguments.', control: 'OpenTelemetry and Langfuse spans are emitted by the out-of-process gateway and MCP proxy, not by the Python runtime.', result: '100% of prompts, completions, tool calls, and policy blocks are recorded.' },
      { title: 'Proof 03 — The Shell Moved', scenario: 'Container escape, host mounts, reverse shell to /usr/bin, or raw socket to 169.254.169.254.', control: 'runsc intercepts syscalls, rootfs is immutable, capabilities dropped, Cilium blocks metadata.', result: 'Syscalls fail with EPERM/EROFS; metadata drops at eBPF.' },
      { title: 'Proof 04 — Two Desks, One Graph', scenario: 'Desk A injects WHERE 1=1 OR tenant_id=desk-b across Postgres, Qdrant, and Neo4j.', control: 'The data proxy extracts signed tenant_id and enforces RLS, payload filters, and subgraph scoping.', result: 'Zero cross-tenant rows, vectors, or nodes.' },
      { title: 'Proof 05 — Loop Dies at the Door', scenario: 'Recursive tool-calling loop designed to exhaust token quotas.', control: 'The AI Gateway tracks tokens, dollar cost, and turn depth per run_id and tenant_id.', result: 'HTTP 429 BudgetExceeded at the configured threshold.' },
    ],
    personasHeadline: 'Built for your seat at the review table.',
    personas: [
      { title: 'CISO', role: 'Board and regulators', body: 'Move AI agents from unapproved shadow experiment to an auditable control framework. Prompt injection cannot pivot into credential theft, cross-customer leakage, or unlogged actions.', points: ['Auditable control framework', 'No silent tool calls', 'Proofs you can rerun'] },
      { title: 'Staff Security Architect', role: 'Defense in depth', body: 'Stop relying on system-prompt instructions as a security boundary. Enforce Linux namespaces, gVisor runsc, Cilium L7, SPIFFE mTLS, and proxy-enforced Postgres RLS.', points: ['gVisor runsc', 'Cilium L7 DNS/FQDN', 'Proxy-enforced RLS'] },
      { title: 'Platform SRE / Kubernetes Lead', role: 'One chart', body: 'Standardize every team’s agent deployments behind a single Helm chart. Guarantee CPU/memory limits, token circuit breakers, and unified OpenTelemetry dashboards.', points: ['helm upgrade --install --namespace', 'Quota-ready containers', 'Unified OTel'] },
    ],
    finalHeadline: 'Don’t trust the model to police itself. Verify the perimeter in your own cluster.',
    finalSub: 'Deploy Zelkor Community Edition in 10 minutes or schedule a live threat-model walkthrough with security engineering.',
    finalPrimary: { label: 'Book an Architecture Review', href: '/contact' },
    finalSecondary: { label: 'Explore Community & Enterprise Editions', href: '/editions' },
  },
  products: {
    sandbox: {
      slug: 'sandbox',
      eyebrow: 'Product // sandbox',
      h1: 'Kernel-level isolation for agents that execute code and parse untrusted inputs.',
      subtitle: 'Isolate every agent pod inside a dedicated gVisor (runsc) userspace kernel with an immutable root filesystem, zero Linux capabilities, and strict resource quotas.',
      primaryCta: { label: 'Deploy the Sandbox Chart', href: '/docs/quickstart' },
      secondaryCta: { label: 'See Proof 03: The Shell Moved', href: '/#proofs' },
      overviewTitle: 'The threat / the control',
      overview: 'On shared-kernel runc, a kernel CVE or unpatched binary exploit inside the agent container exposes the worker node. Zelkor mandates runtimeClassName: gvisor, interposing an application kernel written in memory-safe Go between the container and the host.',
      capabilities: [
        { title: 'gVisor (runsc) syscall interception', text: 'Hostile or malformed syscalls never directly touch the host node kernel.' },
        { title: 'Immutable root filesystem', text: 'Mounts / as read-only with size-bounded, noexec ephemeral /tmp volumes that wipe on termination.' },
        { title: 'Zero privilege & capability drop', text: 'runAsNonRoot, UID/GID 65532, allowPrivilegeEscalation: false, Seccomp RuntimeDefault, capabilities.drop ALL.' },
        { title: 'Quota-ready resource governance', text: 'Every container and initContainer ships with explicit CPU and memory requests and limits.' },
      ],
      snippetTitle: 'values-sandbox.yaml',
      snippetLang: 'yaml',
      snippet: `agentSandbox:
  runtimeClassName: gvisor
  automountServiceAccountToken: false
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 65532
    seccompProfile: { type: RuntimeDefault }
  containerSecurityContext:
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: true
    capabilities: { drop: ["ALL"] }
  resources:
    requests: { cpu: 250m, memory: 512Mi }
    limits: { cpu: "1", memory: 2Gi }`,
      bottomHeadline: 'Ready to lock down agent execution on your nodes?',
      bottomPrimary: { label: 'Read the Sandbox Hardening Guide', href: '/docs' },
      bottomSecondary: { label: 'Book an Architecture Review', href: '/contact' },
    },
    gateway: {
      slug: 'gateway',
      eyebrow: 'Product // gateway',
      h1: 'Strip API keys from agent pods. Verify every prompt. Cap every budget.',
      subtitle: 'Route all model traffic through Zelkor’s in-cluster AI Gateway—credential vaulting, real-time guardrails, and deterministic token circuit breakers.',
      primaryCta: { label: 'Configure the AI Gateway', href: '/docs' },
      secondaryCta: { label: 'See Proof 01 & Proof 05', href: '/#proofs' },
      overviewTitle: 'The threat / the control',
      overview: 'Passing OPENAI_API_KEY into agent containers means any SSRF or prompt injection hands attackers billing access. Zelkor separates model access from agent compute: pods hold zero upstream keys.',
      capabilities: [
        { title: 'Zero-key pod architecture', text: 'Upstream keys live exclusively in the gateway vault—never in agent environment variables or volumes.' },
        { title: 'Inline prompt verification & redaction', text: 'Inspects messages and completions for injection signatures, PII, and secret patterns.' },
        { title: 'Granular token & cost circuit breakers', text: 'Hard limits per run_id, agent_id, and tenant_id across tokens, turn depth, and USD spend.' },
        { title: 'Multi-provider routing & failover', text: 'Unified OpenAI-compatible endpoint with fallback policies and model allowlists.' },
      ],
      snippetTitle: 'values-gateway.yaml',
      snippetLang: 'yaml',
      snippet: `aiGateway:
  enabled: true
  allowedModels: ["claude-3-7-sonnet", "gpt-4.1"]
  upstreamSecretRef: "zelkor-llm-provider-keys"
  guardrails:
    inputVerification:
      blockPromptInjectionSignatures: true
      redactPII: ["SSN", "CREDIT_CARD", "IBAN"]
    outputVerification:
      blockSecretPatterns: true
  budgetControl:
    maxTurnsPerSession: 20
    maxTokensPerSession: 100000
    maxDailySpendPerTenantUsd: 100.00`,
      bottomHeadline: 'Eliminate raw LLM API keys and uncapped token spend.',
      bottomPrimary: { label: 'Explore Gateway Reference', href: '/docs' },
      bottomSecondary: { label: 'Book an Architecture Review', href: '/contact' },
    },
    mcp: {
      slug: 'mcp',
      eyebrow: 'Product // MCP proxy',
      h1: 'Zero-trust mediation for every Model Context Protocol tool call.',
      subtitle: 'Inspect JSON-RPC payloads, enforce least-privilege tool allowlists, validate JSON schemas, and broker downstream credentials without exposing secrets to the agent.',
      primaryCta: { label: 'Secure Your MCP Servers', href: '/docs' },
      secondaryCta: { label: 'Book an Architecture Review', href: '/contact' },
      overviewTitle: 'The threat / the control',
      overview: 'When an agent connects directly to an MCP server with broad permissions, an injected instruction can invoke delete_record or export_all_users. Zelkor terminates every MCP connection at the proxy.',
      capabilities: [
        { title: 'Per-agent tool & method allowlists', text: 'Allow read_ticket while blocking delete_ticket on the same MCP server.' },
        { title: 'JSON-RPC schema & argument policy', text: 'Validate every tool invocation against JSON Schemas and regex rules before forwarding.' },
        { title: 'Downstream credential brokering', text: 'Keep GitHub, Jira, Slack, and internal tokens inside the proxy tier.' },
        { title: 'Sandboxed MCP server hosting', text: 'Run third-party MCP servers inside their own gVisor-isolated pods.' },
      ],
      snippetTitle: 'values-mcp.yaml',
      snippetLang: 'yaml',
      snippet: `mcpProxy:
  enabled: true
  policies:
    - agentSelector: "support-triage-agent"
      servers:
        - name: "zendesk-mcp"
          endpoint: "http://zendesk-mcp.zelkor-tools.svc:8080/mcp"
          allowedTools: ["get_ticket", "add_internal_note"]
          deniedTools: ["delete_ticket", "update_requester_email"]`,
      bottomHeadline: 'Give agents the tools they need—and nothing they don’t.',
      bottomPrimary: { label: 'Read the MCP Security Architecture', href: '/docs' },
      bottomSecondary: { label: 'Book an Architecture Review', href: '/contact' },
    },
    tenancy: {
      slug: 'tenancy',
      eyebrow: 'Product // tenancy',
      h1: 'Cryptographic tenant isolation across SQL, vectors, and graphs.',
      subtitle: 'Bind every agent turn to a verified tenant identity and enforce hard data boundaries in PostgreSQL RLS, Qdrant collections, and Neo4j graphs.',
      primaryCta: { label: 'See Proof 04: Two Desks, One Graph', href: '/#proofs' },
      secondaryCta: { label: 'Read the Tenancy Spec', href: '/docs' },
      overviewTitle: 'The threat / the control',
      overview: 'Relying on the LLM to append WHERE tenant_id = acme is a critical vulnerability. Zelkor treats the agent as an untrusted client. Tenant identity is established via a signed JWT and bound into the database session before any query executes.',
      capabilities: [
        { title: 'PostgreSQL RLS binding', text: 'Injects verified JWT claims into SET LOCAL app.current_tenant on every pool checkout.' },
        { title: 'Vector store mandatory filtering', text: 'Rewrites Qdrant payload filters at the proxy so semantic search never crosses tenants.' },
        { title: 'Graph partition enforcement', text: 'Scopes Cypher traversals to tenant-labeled subgraphs verified against the signed identity.' },
        { title: 'End-to-end JWT context propagation', text: 'Preserves tenant claims across multi-agent handoffs and MCP calls without trusting agent-supplied parameters.' },
      ],
      snippetTitle: 'Postgres RLS',
      snippetLang: 'sql',
      snippet: `ALTER TABLE portfolio_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_positions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_policy ON portfolio_positions
  USING (tenant_id = current_setting('app.current_tenant', true));
-- SELECT * FROM portfolio_positions WHERE 1=1
-- still returns ONLY the bound session tenant.`,
      bottomHeadline: 'Prove to customers and auditors that Tenant A can never read Tenant B.',
      bottomPrimary: { label: 'Explore Multi-Tenant Reference Architecture', href: '/docs' },
      bottomSecondary: { label: 'Book an Architecture Review', href: '/contact' },
    },
    observability: {
      slug: 'observability',
      eyebrow: 'Product // observability',
      h1: 'Tamper-evident flight recorder for every prompt, tool call, and policy verdict.',
      subtitle: 'Capture complete OpenTelemetry and Langfuse traces out-of-process at the gateway and proxy layer—where compromised agent code cannot mute the audit log.',
      primaryCta: { label: 'See Proof 02: The Flight Recorder', href: '/#proofs' },
      secondaryCta: { label: 'View Telemetry Schema', href: '/docs' },
      overviewTitle: 'The threat / the control',
      overview: 'In-app OpenTelemetry exporters run inside the same process as the agent. If an attacker achieves code execution, they can disable callbacks or forge telemetry. Zelkor captures at the infrastructure perimeter.',
      capabilities: [
        { title: 'Out-of-process perimeter capture', text: 'Spans are generated by the gateway and MCP proxy rather than in-pod SDKs.' },
        { title: 'Native Langfuse & OpenTelemetry', text: 'Stream traces to self-hosted Langfuse or your SIEM/OTel collector.' },
        { title: 'Security verdict auditing', text: 'Blocked injections, redacted PII, denied tools, and tripped budgets emit dedicated spans.' },
        { title: 'Cost & latency by tenant', text: 'Token consumption and dollar spend broken down by tenant_id, agent_id, and model.' },
      ],
      snippetTitle: 'values-observability.yaml',
      snippetLang: 'yaml',
      snippet: `observability:
  flightRecorder:
    enabled: true
    capturePayloads: true
    redactSecretsInSpans: true
  langfuse:
    enabled: true
    selfHostedInCluster: true
  otelCollector:
    enabled: true
    exporters:
      otlp:
        endpoint: "otel-collector.zelkor-system.svc:4317"`,
      bottomHeadline: 'Give SOC and compliance complete forensic replay of every agent run.',
      bottomPrimary: { label: 'Read the Observability Guide', href: '/docs' },
      bottomSecondary: { label: 'Book an Architecture Review', href: '/contact' },
    },
    network: {
      slug: 'network',
      eyebrow: 'Product // network & cluster armor',
      h1: 'Default-deny egress, L7 FQDN policies, and cryptographic workload identity.',
      subtitle: 'Lock down pod-to-pod and external paths with Cilium eBPF, block cloud metadata SSRF, and authenticate every internal hop with mTLS.',
      primaryCta: { label: 'Review the Network Topology', href: '/docs' },
      secondaryCta: { label: 'Book an Architecture Review', href: '/contact' },
      overviewTitle: 'The threat / the control',
      overview: 'By default Kubernetes allows every pod to reach every other pod and the internet. A prompt-injected agent can scan internal services, query 169.254.169.254, or exfiltrate data. Zelkor ships default-deny ingress and egress.',
      capabilities: [
        { title: 'Default-deny L3/L4/L7 NetworkPolicies', text: 'Agents can only reach explicitly declared cluster proxies.' },
        { title: 'DNS-aware FQDN egress filtering', text: 'Cilium L7 DNS policies restrict outbound connections to exact approved FQDNs over TLS 443.' },
        { title: 'Cloud metadata & SSRF blocking', text: 'Blocks 169.254.169.254/32, fd00:ec2::254/128, and RFC1918 management ranges.' },
        { title: 'Helm-only reproducible posture', text: 'Network, quota, and RBAC topology is packaged in versioned Helm templates—no kubectl apply drift.' },
      ],
      snippetTitle: 'CiliumNetworkPolicy',
      snippetLang: 'yaml',
      snippet: `apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: zelkor-agent-default-deny
  namespace: zelkor-agents
spec:
  endpointSelector:
    matchLabels: { zelkor.io/component: agent-pod }
  ingress: []
  egress:
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: zelkor-system
            zelkor.io/component: ai-gateway`,
      bottomHeadline: 'Close every unauthorized network path before the first agent goes live.',
      bottomPrimary: { label: 'Inspect the Helm Network Templates', href: '/docs' },
      bottomSecondary: { label: 'Book an Architecture Review', href: '/contact' },
    },
  },
  solutions: {
    'financial-services': {
      slug: 'financial-services',
      eyebrow: 'Solutions // financial services',
      h1: 'Deploy autonomous research, quant, and operations agents under strict regulatory & desk boundaries.',
      subtitle: 'Enforce Chinese-wall information barriers between desks, maintain immutable audit logs for every model turn, and govern model risk across equities, credit, banking, and insurance workflows.',
      primaryCta: { label: 'Book a Financial Services Architecture Review', href: '/contact' },
      secondaryCta: { label: 'See Proof 04: Two Desks, One Graph', href: '/#proofs' },
      risks: [
        { title: 'Cross-desk MNPI leakage', text: 'An equities agent retrieves non-public deal documents indexed by an advisory desk. Mitigated by cryptographic desk claims in Postgres RLS, Qdrant, and Neo4j.' },
        { title: 'Unlogged model decisions', text: 'Out-of-band Flight Recorder traces in OpenTelemetry and Langfuse.' },
        { title: 'Indirect injection via filings & PDFs', text: 'Gateway prompt verification, MCP allowlists, and default-deny egress.' },
        { title: 'Credential theft from code sandboxes', text: 'gVisor isolation and zero-key gateway vaulting.' },
        { title: 'Unauthorized order-management tools', text: 'MCP Proxy per-agent method allowlists and JSON Schema validation.' },
        { title: 'Runaway token spend', text: 'Per-desk and per-run token and dollar circuit breakers.' },
      ],
      mappingTitle: 'Compliance & control mapping',
      mapping: [
        { framework: 'SEC 17a-4 / FINRA 3110 & 4511', requirement: 'Non-rewriteable preservation of electronic communications', control: 'Out-of-process gateway & MCP capture into OTel/Langfuse (Proof 02)' },
        { framework: 'SR 11-7 / OCC 2011-12', requirement: 'Model risk management and change control', control: 'Versioned Helm, model allowlists, prompt verification, per-model telemetry' },
        { framework: 'EU DORA', requirement: 'ICT incident containment and third-party resilience', control: 'Multi-provider failover, circuit breakers, gVisor, Cilium (Proof 03 & 05)' },
        { framework: 'Information barriers / MNPI', requirement: 'Separation of public-side and private-side desks', control: 'Signed JWT desk_id into RLS, Qdrant, Neo4j (Proof 04)' },
        { framework: 'SOC 2 Type II CC6.1 / CC6.6 / CC7.2', requirement: 'Logical access, boundary protection, monitoring', control: 'Zero-key pods, mTLS, non-root read-only containers, OTel security spans' },
      ],
      scenariosTitle: 'Deployment scenarios',
      scenarios: [
        { title: 'Multi-desk equity & credit research copilot', text: 'LangGraph agents synthesize filings and desk notes while Desk A never queries Desk B’s coverage universe.' },
        { title: 'Sandboxed quant code-execution', text: 'Python backtests inside ephemeral gVisor pods with zero host kernel exposure and no internet egress.' },
        { title: 'Automated KYC / AML triage', text: 'Document-review agents call internal case tools via MCP with read/append permissions and FINRA/SEC-ready trails.' },
      ],
      bottomHeadline: 'See the FinServe reference topology running live on Kubernetes.',
      bottomCta: { label: 'Book a Financial Services Architecture Review', href: '/contact' },
    },
    healthcare: {
      slug: 'healthcare',
      eyebrow: 'Solutions // healthcare & life sciences',
      h1: 'Zero-trust PHI boundaries for clinical, claims, and R&D agents.',
      subtitle: 'Keep Protected Health Information inside your Kubernetes perimeter, redact identifiers at the AI Gateway, isolate patient records by tenant, and log every access for HIPAA audits.',
      primaryCta: { label: 'Book a Healthcare Architecture Review', href: '/contact' },
      secondaryCta: { label: 'Explore Data Perimeter Controls', href: '/products/tenancy' },
      risks: [
        { title: 'Unintended PHI egress', text: 'Model allowlists, inline PII/PHI redaction, and Cilium default-deny egress.' },
        { title: 'Cross-patient context bleed', text: 'Signed tenant_id / patient_scope in Postgres RLS and Qdrant.' },
        { title: 'EHR mutation via over-privileged tools', text: 'MCP Proxy read-only tool allowlists and JSON-RPC schema enforcement.' },
        { title: 'Malicious medical documents', text: 'gVisor syscall interception and read-only root filesystems.' },
        { title: 'Missing ePHI audit trails', text: 'Flight Recorder traces correlating clinician_id, agent_id, and tool_call.' },
        { title: 'Exposed FHIR credentials', text: 'Zero-key pods and MCP credential brokering.' },
      ],
      mappingTitle: 'HIPAA & SOC 2 mapping',
      mapping: [
        { framework: 'HIPAA §164.312(a)(1) Access Control', requirement: 'Restrict ePHI to authorized entities', control: 'JWT identity into MCP, RLS, and Qdrant (Proof 04)' },
        { framework: 'HIPAA §164.312(b) Audit Controls', requirement: 'Record activity in systems containing ePHI', control: 'Out-of-process Flight Recorder (Proof 02)' },
        { framework: 'HIPAA §164.312(e)(1) Transmission Security', requirement: 'Guard ePHI in transit', control: 'Cilium default-deny, mTLS, BAA-approved or self-hosted endpoints' },
        { framework: 'SOC 2 Privacy & Confidentiality', requirement: 'Redaction and logical separation', control: 'Inline PII/PHI at the gateway + gVisor sandboxes' },
      ],
      scenariosTitle: 'Deployment scenarios',
      scenarios: [
        { title: 'Prior-authorization & claims review', text: 'Parse clinical PDFs in gVisor; query payer rules via read-only MCP without exposing EHR credentials.' },
        { title: 'Multi-hospital documentation copilot', text: 'Shared Kubernetes platform with cryptographic RLS ensuring separation between provider organizations.' },
        { title: 'Pharmacovigilance literature synthesis', text: 'Strict FQDN egress allowlists and deterministic budget caps.' },
      ],
      bottomHeadline: 'Protect ePHI at the Kubernetes infrastructure layer.',
      bottomCta: { label: 'Book a Healthcare Architecture Review', href: '/contact' },
    },
    'b2b-saas': {
      slug: 'b2b-saas',
      eyebrow: 'Solutions // multi-tenant B2B SaaS',
      h1: 'Ship customer-facing AI agents on shared Kubernetes clusters without cross-tenant blast radius.',
      subtitle: 'Enforce per-customer data isolation in Postgres and Qdrant, meter and cap token spend per tenant, and pass enterprise security questionnaires on day one.',
      primaryCta: { label: 'Book a SaaS Architecture Review', href: '/contact' },
      secondaryCta: { label: 'See All 5 Security Proofs', href: '/#proofs' },
      risks: [
        { title: 'Cross-customer RAG leakage', text: 'Proxy-enforced JWT tenant_id in Postgres RLS, Qdrant, and Neo4j.' },
        { title: 'Noisy-neighbor token exhaustion', text: 'Per-tenant token and USD rate limits at the AI Gateway.' },
        { title: 'RCE lateral movement', text: 'runtimeClassName: gvisor per-pod plus Cilium default-deny.' },
        { title: 'Stolen master API keys', text: 'Zero-key pods and credential brokering in gateway and MCP proxy.' },
        { title: 'Blocked enterprise deals', text: 'Reproducible Kubernetes security proofs, not prompt instructions.' },
        { title: 'Zero per-customer unit economics', text: 'Flight Recorder tenant-tagged telemetry in Langfuse and OpenTelemetry.' },
      ],
      mappingTitle: 'Customer / auditor mapping',
      mapping: [
        { framework: 'SOC 2 Type II CC6.1 & CC6.8', requirement: 'Logical tenant isolation and unauthorized execution prevention', control: 'RLS / Qdrant filters + gVisor (Proof 03 & 04)' },
        { framework: 'CAIQ / SIG questionnaires', requirement: 'Customer data cannot leak via LLM prompts', control: 'Zero-key pods, JWT propagation, prompt verification (Proof 01)' },
        { framework: 'FinOps & tenant SLA', requirement: 'Single-tenant abuse cannot degrade the platform', control: 'Circuit breakers + container CPU/memory limits (Proof 05)' },
      ],
      scenariosTitle: 'Deployment scenarios',
      scenarios: [
        { title: 'Support & onboarding agents', text: 'Query each customer’s workspace via RLS without cross-organization bleed.' },
        { title: 'Sandboxed data analysis', text: 'In-app Python analysis in gVisor pods with strict limits and zero egress.' },
        { title: 'Per-tenant webhook automations', text: 'MCP Proxy brokers scoped per-tenant Slack/Jira/CRM credentials.' },
      ],
      bottomHeadline: 'Turn AI security architecture into a competitive sales advantage.',
      bottomCta: { label: 'Book a SaaS Architecture Review', href: '/contact' },
    },
    'platform-engineering': {
      slug: 'platform-engineering',
      eyebrow: 'Solutions // platform engineering',
      h1: 'One Helm chart to standardize, sandbox, and observe every AI agent team in your company.',
      subtitle: 'Stop bespoke dockerfiles and shadow API keys. Give developers a golden path for LangGraph, CrewAI, and MCP while enforcing quotas, gVisor, and network policies by default.',
      primaryCta: { label: 'Explore the Helm Chart Docs', href: '/docs' },
      secondaryCta: { label: 'Book an Architecture Review', href: '/contact' },
      risks: [
        { title: 'Sprawl of unmanaged shadow agents', text: 'Standardized Helm chart enforces security baselines automatically.' },
        { title: 'Quota & LimitRange admission failures', text: 'Explicit resources.requests and resources.limits on every container and initContainer.' },
        { title: 'kubectl apply drift', text: '100% Helm-native packaging (helm upgrade --install --namespace).' },
        { title: 'Fragmented observability', text: 'Unified out-of-process OpenTelemetry and Langfuse at the gateway and MCP proxy.' },
        { title: 'Inconsistent secret management', text: 'Upstream LLM and tool secrets stay in the gateway/proxy namespace.' },
        { title: 'Runaway staging bills', text: 'Cluster-wide and per-namespace token/spend budgets.' },
      ],
      mappingTitle: 'Platform standards',
      mapping: [
        { framework: 'Pod Security Standards (Restricted)', requirement: 'Non-root, drop capabilities, Seccomp, no privilege escalation', control: 'Chart defaults plus runtimeClassName: gvisor' },
        { framework: 'ResourceQuota & LimitRange', requirement: 'Every container declares CPU and memory', control: 'Explicit resources in values.yaml' },
        { framework: 'GitOps & Helm-only delivery', requirement: 'No kubectl in CI; pre-provisioned namespaces', control: 'helm upgrade --install --namespace --wait' },
        { framework: 'SRE golden signals', requirement: 'Latency, errors, saturation, token spend', control: 'Prometheus, OTel, Langfuse per namespace' },
      ],
      scenariosTitle: 'Deployment scenarios',
      scenarios: [
        { title: 'IDP self-service onboarding', text: 'Teams supply only their image and allowed MCP tools; they inherit gVisor, Cilium, and Gateway.' },
        { title: 'Air-gapped regulated clusters', text: 'Route to internal vLLM/Ollama or private cloud model gateways.' },
        { title: 'Multi-environment CI/CD promotion', text: 'Immutable Helm versions and automated execution of the 5 security proofs.' },
      ],
      bottomHeadline: 'Give developers speed and security a hard Kubernetes boundary.',
      bottomCta: { label: 'Read the Platform Operator Guide', href: '/docs' },
    },
  },
  editions: {
    eyebrow: 'Editions & packaging',
    h1: 'Same zero-trust Kubernetes foundation. Built to scale from single-cluster proof to global enterprise governance.',
    subtitle: 'Start with Zelkor Community Edition in your own cluster today, or partner for multi-cluster federation, custom compliance mappings, and 24/7 SLAs.',
    primaryCta: { label: 'Install Community Edition', href: '/docs/quickstart' },
    secondaryCta: { label: 'Contact Sales & Architecture', href: '/contact' },
    cards: [
      {
        name: 'Community Edition (CE)',
        kicker: 'Open & self-hosted',
        tagline: 'Full core sandbox and zero-key perimeter for individual teams and production validation.',
        highlights: [
          'runtimeClassName: gvisor with read-only rootfs',
          'Zero-key AI Gateway',
          'Core MCP Proxy allowlists',
          '5 reproducible Security Proofs',
        ],
        cta: { label: 'Deploy Community Edition', href: '/docs/quickstart' },
        featured: true,
      },
      {
        name: 'Pro Edition',
        kicker: 'Annual subscription',
        tagline: 'Advanced policy automation, multi-team governance, and commercial support.',
        highlights: [
          'Custom PII/PHI pipelines',
          'Hierarchical token & USD budgets',
          'JSON-RPC schema validation',
          'Business-hours support',
        ],
        cta: { label: 'Request Pro Access', href: '/contact' },
      },
      {
        name: 'Enterprise Edition',
        kicker: 'Custom agreement',
        tagline: 'Multi-cluster federation, hardware-backed identity, regulated compliance packs, 24/7 SLAs.',
        highlights: [
          'SPIFFE/SPIRE + Vault/KMS',
          'WORM audit export',
          'SR 11-7, FINRA/SEC, DORA, HIPAA, SOC 2 packs',
          'Air-gapped offline Helm bundle',
        ],
        cta: { label: 'Book an Enterprise Architecture Review', href: '/contact' },
      },
    ],
    matrix: [
      { capability: 'gVisor kernel sandbox & read-only rootfs', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'Container resource requests/limits', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'Zero-key AI Gateway', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'Cilium default-deny egress & metadata blocking', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: '5 reproducible Security Proofs', ce: 'Included', pro: 'Included + CI runner', enterprise: 'Included + custom proofs' },
      { capability: 'MCP Proxy tool allowlists', ce: 'Static per-agent', pro: 'Dynamic + JSON Schema', enterprise: 'Federated + OPA/Rego' },
      { capability: 'Multi-tenant data perimeter', ce: 'Core JWT binding', pro: 'Multi-namespace pooler', enterprise: 'Cross-cluster + HSM' },
      { capability: 'Inline prompt verification & PII redaction', ce: 'Baseline rules', pro: 'Custom regex/NER', enterprise: 'Custom classifiers + DLP' },
      { capability: 'Token, turn & dollar circuit breakers', ce: 'Per-run & static tenant', pro: 'Hierarchical + webhooks', enterprise: 'Global quota ledger' },
      { capability: 'Flight Recorder (OTel & Langfuse)', ce: 'Self-hosted', pro: 'Extended retention', enterprise: 'WORM SIEM export' },
      { capability: 'Secret store & KMS', ce: 'Kubernetes Secrets', pro: 'External Secrets Operator', enterprise: 'Vault / Cloud KMS' },
      { capability: 'Workload identity', ce: 'Cluster TLS + ServiceTokens', pro: 'cert-manager mTLS', enterprise: 'SPIFFE/SPIRE' },
      { capability: 'Air-gapped packaging', ce: 'Public GHCR', pro: 'Signed images + SBOMs', enterprise: 'Offline bundle' },
      { capability: 'Compliance evidence packs', ce: 'Self-service docs', pro: 'SOC 2 templates', enterprise: 'SR 11-7, FINRA, DORA, HIPAA, SOC 2' },
      { capability: 'Support', ce: 'GitHub Discussions', pro: 'Business-hours SLA', enterprise: '24/7 + dedicated architect' },
    ],
    faqs: [
      { q: 'Does Zelkor claim to make LLMs 100% jailbreak-proof?', a: 'No—and you should distrust any vendor that claims they can. Zelkor assumes the prompt will be injected. When injection succeeds, the turn still cannot extract upstream keys (Proof 01), mute the audit log (Proof 02), escape gVisor (Proof 03), query another tenant (Proof 04), or exceed its token budget (Proof 05).' },
      { q: 'Do we have to rewrite existing LangGraph, CrewAI, or custom agents?', a: 'No. Point your existing OpenAI/Anthropic SDK at the cluster-local gateway URL and route MCP through the Zelkor MCP Proxy.' },
      { q: 'How does Zelkor prevent OPENAI_API_KEY leakage if an attacker gets code execution?', a: 'Those keys never enter the agent pod. The pod receives a short-lived internal token valid only between that identity and the in-cluster gateway. The gateway attaches the provider key only when forwarding a verified, within-budget request.' },
      { q: 'Why is database isolation enforced in the proxy rather than agent retrieval code?', a: 'If the agent holds a shared connection string and relies on generated SQL to include WHERE tenant_id = X, any bug or injection can bypass the filter. Zelkor terminates data connections outside the pod and sets SET LOCAL app.current_tenant from the signed request context.' },
      { q: 'Can Zelkor deploy on OpenShift with ResourceQuota and no cluster-admin Helm hooks?', a: 'Yes. helm upgrade --install --namespace <precreated-ns> with no --create-namespace. Every container defines explicit CPU and memory requests and limits.' },
      { q: 'Can we run completely self-hosted or air-gapped with local models?', a: 'Yes. gVisor sandboxes, AI Gateway, MCP Proxy, PostgreSQL, Qdrant, Neo4j, and Langfuse/OTel all run in your cluster. Route to commercial APIs, private cloud endpoints, or vLLM/TGI/Ollama.' },
    ],
  },
}
