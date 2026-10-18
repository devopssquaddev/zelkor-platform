import type { VariantCopy } from './types'

const helm =
  'helm upgrade --install zelkor oci://ghcr.io/zelkor-ai/charts/zelkor-platform --namespace zelkor-system --wait'

export const v4: VariantCopy = {
  id: 4,
  name: 'Signal Crimson-Slate',
  short: 'Signal',
  announcement: {
    badge: 'Live demo scenarios',
    text: 'Prompts get injected. Models hallucinate. Contain the blast radius at the kernel, network, and token layer.',
    linkLabel: 'See the 5 live proofs →',
    href: '/#proofs',
  },
  brandSub: 'Runtime defense',
  navCta: { label: 'Book Architecture Review', href: '/contact' },
  productsNav: [
    { slug: 'sandbox', title: 'gVisor Sandbox', blurb: 'Userspace kernel isolation for untrusted agent code & shell execution.' },
    { slug: 'gateway', title: 'AI Gateway & Guardrails', blurb: 'Keyless LLM routing, prompt shields, and hard token budgets.' },
    { slug: 'mcp', title: 'MCP Proxy & Tool Isolation', blurb: 'Sandboxed MCP servers with per-tool policy.' },
    { slug: 'tenancy', title: 'Multi-Tenant Data Perimeter', blurb: 'Tenant-scoped credentials, storage, and vector/graph boundaries.' },
    { slug: 'observability', title: 'Flight Recorder Tracing', blurb: 'OpenTelemetry + Langfuse of every prompt, tool call, and syscall.' },
    { slug: 'network', title: 'Network & Cluster Armor', blurb: 'Cilium L7 DNS lock, IMDS block, and Kyverno admission.' },
  ],
  solutionsNav: [
    { slug: 'financial-services', title: 'Financial Services', blurb: 'Desk-level isolation and SR 11-7 / DORA runtime controls.' },
    { slug: 'healthcare', title: 'Healthcare & Life Sciences', blurb: 'HIPAA minimum-necessary tool gating and PHI egress containment.' },
    { slug: 'b2b-saas', title: 'Multi-Tenant B2B SaaS', blurb: 'Stop cross-customer context bleed and runaway tenant token burn.' },
    { slug: 'platform-engineering', title: 'Platform Engineering', blurb: 'One Helm chart to standardize agent sandboxes on Kubernetes.' },
  ],
  home: {
    eyebrow: 'Open-source Kubernetes agent sandbox · Apache 2.0',
    h1: 'Ship agents, not cluster breaches.',
    subtitle:
      'Bring the LangGraph, CrewAI, AutoGen, or custom Python agent you already wrote. Zelkor wraps it in a gVisor kernel sandbox, strips raw LLM API keys from the pod, locks egress to explicit FQDNs, enforces hard token budgets, and records every tool call.',
    primaryCta: { label: 'Install Community Edition (Helm)', href: '/docs/quickstart' },
    secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
    install: helm,
    marqueeLabel: 'Frameworks, runtimes & standards',
    marquee: [
      'LangGraph', 'CrewAI', 'AutoGen', 'OpenAI Agents SDK', 'Anthropic MCP',
      'gVisor (runsc)', 'Cilium eBPF', 'LiteLLM', 'Llama Guard', 'Langfuse',
      'OpenTelemetry', 'Kyverno',
    ],
    bridgeKicker: 'Prompt filters are probabilistic.',
    bridgeHeading: 'Kernel, network, and credential boundaries are deterministic.',
    bridge:
      'Every week, a new indirect prompt injection bypasses system instructions. When an agent reads a poisoned document, ticket, or webpage, your last line of defense cannot be another prompt. Zelkor assumes the model will be tricked—and enforces hard OS, network, credential, and budget boundaries outside the agent process.',
    tabsHeadline: 'Four doors. All locked from outside the process.',
    tabs: [
      {
        id: 'sandbox',
        label: 'Sandbox',
        headline: 'Untrusted code hits a userspace kernel, never your host Linux kernel.',
        copy: 'Agents that run Python, Bash, or file parsers inside standard runc containers share the node kernel. Zelkor schedules agent pods and sandbox-exec workers onto RuntimeClassName: gvisor with rootless execution, read-only rootfs, and dropped capabilities.',
        lang: 'yaml',
        code: `apiVersion: v1
kind: Pod
metadata:
  name: agent-finserve-analyst
  labels: { zelkor.io/sandbox: "enforced" }
spec:
  runtimeClassName: gvisor
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    seccompProfile: { type: RuntimeDefault }
  containers:
    - name: agent
      securityContext:
        readOnlyRootFilesystem: true
        allowPrivilegeEscalation: false
        capabilities: { drop: ["ALL"] }`,
      },
      {
        id: 'gateway',
        label: 'Gateway',
        headline: 'Zero provider API keys inside the agent container. Hard budget cutoffs at the proxy.',
        copy: 'Agent pods hold no OPENAI_API_KEY or ANTHROPIC_API_KEY. They authenticate to the in-cluster Zelkor AI Gateway using short-lived workload tokens. The gateway screens inputs and outputs against Llama Guard / NeMo Guardrails and injects upstream credentials only in transit.',
        lang: 'yaml',
        code: `gateway:
  upstreamKeyInjection: true
  guardrails:
    inputShield: llama-guard-3
    piiRedaction: enabled
  budgets:
    maxTokensPerRun: 32000
    maxCostPerTenantDailyUsd: 50.00
    loopDetection:
      maxIdenticalToolCalls: 3
      action: terminate_run`,
      },
      {
        id: 'mcp',
        label: 'MCP & Tenants',
        headline: 'Dedicated MCP tool pods and cryptographic tenant boundaries.',
        copy: 'Don’t bundle database drivers and filesystem tools inside the reasoning loop. Zelkor runs MCP servers in isolated sandboxes and routes queries to tenant-scoped storage so Desk A can never query Desk B’s records—even under indirect prompt injection.',
        lang: 'yaml',
        code: `mcpServers:
  - name: code-interpreter
    runtimeClassName: gvisor
    networkPolicy: zero-egress
  - name: falkordb-graph
    tenantHeaderRequired: X-Zelkor-Tenant-ID
    allowedGraphsByRole:
      equity-research: ["graph:equities"]
      mna-advisory: ["graph:mna"]`,
      },
      {
        id: 'trace',
        label: 'Trace',
        headline: 'Reconstruct every prompt, tool call, guardrail verdict, and egress attempt.',
        copy: 'When an incident or audit happens, stdout logs are useless. Zelkor emits correlated OpenTelemetry spans into Langfuse and Prometheus—linking user identity, tenant ID, prompt/completion, MCP arguments, token spend, and guardrail decision in one immutable tree.',
        lang: 'json',
        code: `{
  "trace_id": "tr_9f82c10a4b",
  "tenant_id": "desk-equities-eu",
  "agent": "finserve-analyst",
  "guardrail_verdict": "PASS",
  "mcp_call": { "server": "sandbox-exec", "tool": "run_python", "runtime": "gvisor-runsc" },
  "egress_policy": "ALLOW: api.sec.gov:443"
}`,
      },
    ],
    stepsHeadline: 'Wrap. Lock. Scale.',
    steps: [
      { title: 'Wrap any agent', body: 'Keep your existing Python/TypeScript code and framework. Point OPENAI_BASE_URL to the in-cluster Zelkor Gateway and deploy with the Zelkor Helm chart.' },
      { title: 'Lock every door', body: 'Kyverno admission policies enforce gvisor, strip automountServiceAccountToken, mount read-only root filesystems, and apply Cilium default-deny egress with explicit FQDN allowlists.' },
      { title: 'Scale across teams', body: 'Onboard new business units or customer tenants with isolated namespaces, per-tenant token budgets, scoped MCP permissions, and full Langfuse flight-recorder trails.' },
    ],
    proofsHeadline: 'Five live proofs',
    proofs: [
      { title: 'The Vanishing Key', scenario: 'Indirect prompt injection dumps os.environ and /proc/self/environ to steal the production API key.', control: 'The pod only sees an ephemeral cluster-local proxy token valid against the internal gateway from that pod IP.', result: 'EXFILTRATION NEUTRALIZED — ZERO UPSTREAM KEYS IN POD' },
      { title: 'The Flight Recorder', scenario: 'A compliance officer asks which data sources, prompts, and tool executions produced an automated credit memo at 14:03 UTC.', control: 'Every reasoning turn, guardrail check, MCP call, and token cost is captured under a single OTel/Langfuse trace ID.', result: '100% AUDITABLE LINEAGE — PROMPT TO SYSCALL' },
      { title: 'The Shell Moved', scenario: 'Arbitrary shell/Python payload attempts kernel privilege escalation and lateral movement to IMDS and kubernetes.default.svc.', control: 'Execution inside a dedicated sandbox-exec pod under gVisor with read-only rootfs, UID 65532, no SA token, Cilium blocking IMDS, RFC1918, and K8s API.', result: 'SYSCALL INTERCEPTED IN USERSPACE · LATERAL EGRESS DROPPED' },
      { title: 'Two Desks, One Graph', scenario: 'An Equity Research analyst prompts an agent to summarize confidential M&A deal notes.', control: 'Tenant identity is cryptographically bound at the gateway and enforced at the FalkorDB / vector data layer.', result: 'CHINESE WALL ENFORCED AT DATA PERIMETER' },
      { title: 'Loop Dies at the Door', scenario: 'A malformed tool output traps two agents in an infinite retry loop at 2:00 AM.', control: 'The AI Gateway tracks per-run token budgets and repetitive tool-call signatures and trips the circuit breaker.', result: 'CIRCUIT BREAKER TRIPPED — BUDGET HARD-CAPPED' },
    ],
    personasHeadline: 'Three jobs. One perimeter.',
    personas: [
      { title: 'CISOs & Security Architects', role: 'Unmonitored RCE surface', body: 'Agents combine untrusted inputs, shell execution, and internal credentials. Zelkor gives deterministic gVisor sandboxing, Cilium L7 egress, zero LLM keys in pods, and immutable OTel trails.', points: ['gVisor kernel sandbox', 'Cilium L7 allowlists', 'Immutable audit'] },
      { title: 'Platform Engineering Directors', role: 'Ad-hoc agent containers', body: 'Every squad deploys with hardcoded secrets, root privileges, and no resource quotas. Zelkor is a single Helm-deployed platform with Kyverno, standardized limits, and multi-tenant namespace templates.', points: ['One Helm chart', 'Kyverno admission', 'Quota-ready'] },
      { title: 'AI & Agent Developers', role: 'Security reviews stall launches', body: 'Zero rewrite of your LangGraph, CrewAI, or Python agent. Swap OPENAI_BASE_URL, connect via standard MCP, and ship.', points: ['No framework swap', 'Standard MCP', 'Ship to production'] },
    ],
    finalHeadline: 'Don’t wait for a prompt injection to test your cluster perimeter.',
    finalSub: 'Deploy Zelkor Community Edition in 5 minutes via Helm, or walk through the 5 live breach-containment scenarios with our systems engineers.',
    finalPrimary: { label: 'Deploy with Helm', href: '/docs/quickstart' },
    finalSecondary: { label: 'Book Architecture Review', href: '/contact' },
  },
  products: {
    sandbox: {
      slug: 'sandbox',
      eyebrow: 'Product · /products/sandbox',
      h1: 'Userspace kernel isolation for untrusted agent execution.',
      subtitle: 'Standard Docker/OCI containers share your host Linux kernel. Zelkor runs agent workloads and tool execution pods inside gVisor (runsc) with rootless, read-only filesystems and strict Kubernetes admission enforcement.',
      primaryCta: { label: 'Read Sandbox Docs', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why static containers fail',
      overview: 'AI agents dynamically synthesize and execute Python scripts, shell commands, and document parsers from untrusted prompts. Running that inside default runc exposes 300+ host Linux kernel syscalls to container-escape exploits.',
      capabilities: [
        { title: 'gVisor (runsc) syscall interception', text: 'Application syscalls terminate at gVisor’s Sentry userspace kernel rather than the host OS kernel.' },
        { title: 'Rootless, read-only root filesystem', text: 'UID 65532, readOnlyRootFilesystem, allowPrivilegeEscalation: false, capabilities.drop ALL, bounded emptyDir scratch.' },
        { title: 'Kyverno admission enforcement', text: 'Cluster policies reject any pod in agent namespaces missing gvisor, resource limits, or security context.' },
        { title: 'Zero K8s API token mounting', text: 'automountServiceAccountToken: false so a compromised process cannot read the service account token.' },
      ],
      snippetTitle: 'Kyverno ClusterPolicy',
      snippetLang: 'yaml',
      snippet: `apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: zelkor-require-gvisor-sandbox
spec:
  validationFailureAction: Enforce
  rules:
    - name: check-runtime-and-security-context
      match:
        any:
          - resources:
              kinds: ["Pod"]
              namespaces: ["zelkor-agents-*"]
      validate:
        pattern:
          spec:
            runtimeClassName: gvisor
            automountServiceAccountToken: false`,
      bottomHeadline: 'Isolate agent code execution from your host nodes today.',
      bottomPrimary: { label: 'Install via Helm', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    gateway: {
      slug: 'gateway',
      eyebrow: 'Product · /products/gateway',
      h1: 'Keyless LLM routing, prompt shields, and hard token budgets.',
      subtitle: 'Strip raw OpenAI, Anthropic, and Bedrock keys out of agent pods. Route every inference call through an in-cluster gateway that enforces Llama Guard screening, PII redaction, loop circuit breakers, and per-tenant spend caps.',
      primaryCta: { label: 'Explore Gateway Reference', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why static containers fail',
      overview: 'Hardcoding OPENAI_API_KEY into Secrets mounted into agent pods means a single prompt injection compromises billing. Without an inline proxy, a recursive loop can burn through frontier quota before alerts fire.',
      capabilities: [
        { title: 'Upstream key injection', text: 'Agents authenticate with scoped workload tokens. The gateway attaches upstream keys only on outbound TLS.' },
        { title: 'Inline input & output guardrails', text: 'Screen prompts and tool outputs through Llama Guard / NeMo Guardrails before they reach the model or caller.' },
        { title: 'Deterministic token & cost ceilings', text: 'When a run hits its token ceiling, the gateway returns HTTP 429 BudgetExceeded.' },
        { title: 'Recursive loop circuit breaker', text: 'Detect oscillating tool calls and halt runaway multi-agent loops.' },
      ],
      snippetTitle: 'values-gateway.yaml',
      snippetLang: 'yaml',
      snippet: `gateway:
  policies:
    defaultRunTokenLimit: 25000
    loopBreaker:
      windowTurns: 5
      maxRepeatedToolSignature: 3
    guardrails:
      provider: llama-guard
      blockOnCategories: ["S1", "S2", "S6", "S9", "PROMPT_INJECTION"]`,
      bottomHeadline: 'Take raw LLM API keys out of your agent containers.',
      bottomPrimary: { label: 'Install via Helm', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    mcp: {
      slug: 'mcp',
      eyebrow: 'Product · /products/mcp',
      h1: 'Run MCP servers and code tools in dedicated blast-radius pods.',
      subtitle: 'Decouple your agent’s reasoning loop from its tool execution environment. Zelkor isolates MCP servers and sandbox-exec workers in separate gVisor pods with per-tool policy enforcement.',
      primaryCta: { label: 'View MCP Architecture', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why static containers fail',
      overview: 'Most tutorials run the LLM loop, Python exec(), shells, and database connectors in a single process. Compromise a PDF parser and you inherit memory, conversation history, and network permissions of the orchestrator.',
      capabilities: [
        { title: 'Out-of-process sandbox-exec workers', text: 'Code execution runs in ephemeral, zero-egress gVisor worker pods over MCP—never inside the primary agent container.' },
        { title: 'Per-tool authorization matrix', text: 'Allow read_query on SQL MCP while blocking drop_table or write_file.' },
        { title: 'Scoped credential brokering', text: 'Database passwords live inside the MCP server pod that needs them, never in the LLM agent pod.' },
        { title: 'Argument schema & payload validation', text: 'Block malformed payloads and path-traversal attempts before execution.' },
      ],
      snippetTitle: 'values-mcp.yaml',
      snippetLang: 'yaml',
      snippet: `mcpProxy:
  enabled: true
  servers:
    - name: sandbox-exec
      runtimeClassName: gvisor
      egress: deny-all
      allowedTools: ["run_python", "inspect_csv"]
      timeoutSeconds: 15
    - name: enterprise-graph
      allowedTools: ["cypher_read_only"]
      injectTenantContext: true`,
      bottomHeadline: 'Stop running exec() inside your orchestrator pod.',
      bottomPrimary: { label: 'Install via Helm', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    tenancy: {
      slug: 'tenancy',
      eyebrow: 'Product · /products/tenancy',
      h1: 'Cryptographic tenant walls for shared agent infrastructure.',
      subtitle: 'Prevent cross-tenant context bleed across business desks and SaaS customers. Zelkor binds tenant identity at ingress and enforces hard partitioning across namespaces, MCP tools, FalkorDB graphs, and vector stores.',
      primaryCta: { label: 'Read Tenancy Spec', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why static containers fail',
      overview: 'Relying on a system prompt (“Only answer questions for tenant_id = 42”) is a guaranteed data breach. Indirect prompt injection will trick the agent into querying another customer’s records.',
      capabilities: [
        { title: 'Identity-bound context propagation', text: 'Tenant ID and role claims are verified at the gateway via JWT/mTLS and propagated in signed headers the prompt cannot spoof.' },
        { title: 'Graph & vector store partitioning', text: 'Connectors automatically scope every query to the authenticated tenant’s graph or namespace partition.' },
        { title: 'Namespace & secret isolation', text: 'Per-tenant or per-desk namespaces with dedicated Secrets, ResourceQuotas, and NetworkPolicies from one Helm release.' },
        { title: 'Per-tenant quota & rate governance', text: 'Independent CPU/memory limits and per-tenant daily LLM token budgets.' },
      ],
      snippetTitle: 'values-tenants.yaml',
      snippetLang: 'yaml',
      snippet: `tenancy:
  mode: strict-header-binding
  tenants:
    - id: desk-equities
      namespace: zelkor-tenant-equities
      allowedGraphs: ["equities_research"]
      dailyTokenBudget: 5000000
    - id: desk-mna
      namespace: zelkor-tenant-mna
      allowedGraphs: ["mna_advisory_restricted"]`,
      bottomHeadline: 'Enforce Chinese Walls in infrastructure, not system prompts.',
      bottomPrimary: { label: 'Install via Helm', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    observability: {
      slug: 'observability',
      eyebrow: 'Product · /products/observability',
      h1: 'Black-box flight recorder for every agent run.',
      subtitle: 'Full OpenTelemetry and Langfuse observability out of the box. Capture every prompt, completion, guardrail decision, MCP invocation, latency breakdown, and token cost in a single correlated trace.',
      primaryCta: { label: 'Explore Observability Docs', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why static containers fail',
      overview: 'Standard APM tells you a container returned HTTP 200 in 4.2 seconds. It has zero visibility into the 7 internal reasoning steps, 3 MCP calls, guardrail evaluations, and token spend inside that request.',
      capabilities: [
        { title: 'Zero-code gateway & MCP telemetry', text: 'Spans are captured even if the developer forgot to instrument agent code.' },
        { title: 'Langfuse session & trace trees', text: 'Inspect multi-turn trajectories, nested tool I/O, model parameters, and token costs with tenant attribution.' },
        { title: 'Security & guardrail audit events', text: 'Blocked injections, PII redaction, budget cutoffs, and denied egress generate SIEM-ready events.' },
        { title: 'Prometheus cost & latency metrics', text: 'Token burn rates, guardrail block ratios, MCP error rates, and p95 inference latency.' },
      ],
      snippetTitle: 'values-observability.yaml',
      snippetLang: 'yaml',
      snippet: `observability:
  otelCollector: { enabled: true }
  langfuse:
    enabled: true
    capturePayloads: true
    redactPatterns:
      - "(?i)bearer\\\\s+[a-z0-9_\\\\-\\\\.]+"
  prometheus:
    serviceMonitor: { enabled: true, interval: 15s }`,
      bottomHeadline: 'Give SOC and compliance auditors complete agent lineage.',
      bottomPrimary: { label: 'Install via Helm', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    network: {
      slug: 'network',
      eyebrow: 'Product · /products/network',
      h1: 'Default-deny egress and L7 DNS lock for every agent pod.',
      subtitle: 'Stop data exfiltration, SSRF, and lateral movement cold. Zelkor pairs Cilium eBPF L7 policies with cloud IMDS blocking so compromised agents can only reach explicitly approved FQDNs.',
      primaryCta: { label: 'Read Network Policy Docs', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why static containers fail',
      overview: 'In a default cluster, any pod can open outbound connections to the internet, query 169.254.169.254 for node IAM, or scan RFC1918. When an agent is tricked into fetching an attacker URL, default Kubernetes networking lets the payload walk out.',
      capabilities: [
        { title: 'Default-deny egress perimeter', text: 'Agent and sandbox-exec pods start with zero outbound access except the internal gateway and MCP proxy.' },
        { title: 'Cilium L7 FQDN allowlists', text: 'Allow by exact DNS name and TLS port (api.sec.gov:443) rather than brittle IP ranges.' },
        { title: 'Cloud metadata & K8s API blackhole', text: 'Drop 169.254.169.254/32 and kubernetes.default.svc.' },
        { title: 'Cross-pod lateral movement block', text: 'Prevent probes of sibling pods, databases, or admin dashboards across RFC1918.' },
      ],
      snippetTitle: 'CiliumNetworkPolicy',
      snippetLang: 'yaml',
      snippet: `apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: zelkor-agent-egress-lock
spec:
  egressDeny:
    - toCIDR: ["169.254.169.254/32", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
  egress:
    - toFQDNs: [{ matchName: "api.sec.gov" }]
      toPorts: [{ ports: [{ port: "443", protocol: TCP }] }]`,
      bottomHeadline: 'Lock down agent network egress down to the exact FQDN.',
      bottomPrimary: { label: 'Install via Helm', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
  },
  solutions: {
    'financial-services': {
      slug: 'financial-services',
      eyebrow: 'Solutions · financial services',
      h1: 'Deploy autonomous financial agents without breaking Chinese Walls.',
      subtitle: 'Run equity research, credit underwriting, and compliance agents inside deterministic gVisor sandboxes with desk-scoped data perimeters, keyless LLM gateways, and full SR 11-7 / DORA audit trails.',
      primaryCta: { label: 'Book Architecture Review', href: '/contact' },
      secondaryCta: { label: 'Explore Editions', href: '/editions' },
      risks: [
        { title: 'Cross-desk information barrier breach', text: 'Cryptographic tenant headers at the FalkorDB / MCP layer.' },
        { title: 'Poisoned earnings / filing ingestion', text: 'Parsing and code execution inside zero-egress gVisor sandbox-exec pods.' },
        { title: 'LLM API key exfiltration', text: 'Provider keys stay in the gateway; agent pods hold zero upstream secrets.' },
        { title: 'Unexplainable automated decisions', text: 'Flight Recorder logs every prompt, retrieval chunk, tool call, and guardrail verdict.' },
        { title: 'Unauthorized external data egress', text: 'Cilium L7 drops traffic to non-allowlisted FQDNs.' },
        { title: 'Runaway quantitative agent loops', text: 'Gateway trips the loop circuit breaker and enforces hard per-run token caps.' },
      ],
      mappingTitle: 'Compliance mapping',
      mapping: [
        { framework: 'FINRA 3110 / SEC 17a-4', requirement: 'Supervision and immutable record retention', control: 'OTel + Langfuse Flight Recorder' },
        { framework: 'Fed SR 11-7', requirement: 'Conceptual soundness, monitoring, boundary enforcement', control: 'Llama Guard, token/loop ceilings, Prometheus telemetry' },
        { framework: 'SEC Reg S-P / FINRA 2024', requirement: 'Chinese Walls between IB/M&A and research/trading', control: 'X-Zelkor-Tenant-ID partition separation' },
        { framework: 'EU DORA', requirement: 'ICT third-party risk containment and circuit breaking', control: 'gVisor, Kyverno, Cilium L7, multi-provider failover' },
        { framework: 'SOC 2 Type II CC6.1 / CC6.6', requirement: 'Logical access, secret management, network boundary', control: 'Zero keys in pods, no SA token, default-deny egress' },
      ],
      scenariosTitle: 'Workflows',
      scenarios: [
        { title: 'Multi-desk equity & M&A research', text: 'Shared infrastructure; isolated FalkorDB partitions with mathematically enforced barriers.' },
        { title: 'Sandboxed financial document analysis', text: 'Python against CSVs and SEC filings inside ephemeral zero-egress gVisor pods.' },
        { title: 'Audited compliance & AML triage', text: 'Read-only MCP servers with complete trace lineage for internal audit and regulators.' },
      ],
      bottomHeadline: 'Walk through the FinServe multi-desk reference architecture.',
      bottomCta: { label: 'Book Architecture Review', href: '/contact' },
    },
    healthcare: {
      slug: 'healthcare',
      eyebrow: 'Solutions · healthcare & life sciences',
      h1: 'Contain PHI and clinical tool execution inside HIPAA-grade sandboxes.',
      subtitle: 'Run clinical documentation, prior-authorization, and bioinformatics agents with inline PII/PHI redaction, minimum-necessary MCP tool gating, and zero unauthorized network egress.',
      primaryCta: { label: 'Review Healthcare Controls', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      risks: [
        { title: 'Unintended PHI leakage to public LLMs', text: 'Inline PII/PHI redaction and approved BAA upstream routing.' },
        { title: 'Over-privileged EHR database access', text: 'Scoped MCP servers enforcing minimum-necessary read policies.' },
        { title: 'Bioinformatics code execution breakout', text: 'Rootless gVisor (runsc) pods.' },
        { title: 'Indirect injection via external medical records', text: 'Cilium L7 default-deny egress blocks outbound connections.' },
        { title: 'Missing audit trail on clinical assistance', text: 'Every MCP tool call and prompt span is recorded.' },
        { title: 'Cross-study / cross-site contamination', text: 'Strict tenant and study partitioning at storage and graph layer.' },
      ],
      mappingTitle: 'HIPAA / HITRUST mapping',
      mapping: [
        { framework: 'HIPAA §164.312(a)(1)', requirement: 'Access control and Minimum Necessary for ePHI', control: 'Per-tool MCP matrix and tenant-scoped connectors' },
        { framework: 'HIPAA §164.312(b)', requirement: 'Record activity in systems containing ePHI', control: 'Flight Recorder logging every prompt, tool call, and data access span' },
        { framework: 'HIPAA §164.312(e)(1)', requirement: 'Transmission security', control: 'Cilium L7 default-deny, IMDS blocking, inline PHI redaction' },
        { framework: 'SOC 2 / HITRUST CSF', requirement: 'Workload isolation and least-privilege execution', control: 'gVisor, read-only rootfs, runAsNonRoot, Kyverno' },
      ],
      scenariosTitle: 'Workflows',
      scenarios: [
        { title: 'Prior-authorization & clinical summarization', text: 'Scoped encounter records via FHIR MCP; identifiers scrubbed at the gateway.' },
        { title: 'Sandboxed bioinformatics', text: 'LLM-generated Python pipelines inside gVisor sandbox-exec with zero internet egress.' },
        { title: 'Multi-cohort trial operations', text: 'Cryptographic tenant boundaries while sharing a single Kubernetes control plane.' },
      ],
      bottomHeadline: 'Protect patient data with deterministic runtime boundaries.',
      bottomCta: { label: 'Book Architecture Review', href: '/contact' },
    },
    'b2b-saas': {
      slug: 'b2b-saas',
      eyebrow: 'Solutions · multi-tenant B2B SaaS',
      h1: 'Ship customer-facing AI agents without cross-tenant data leaks or margin wipeouts.',
      subtitle: 'Give every SaaS customer a cryptographically isolated data perimeter, gVisor-sandboxed tool execution, and hard per-tenant token budgets—all from one Kubernetes Helm chart.',
      primaryCta: { label: 'See SaaS Tenancy Architecture', href: '/products/tenancy' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      risks: [
        { title: 'Cross-customer context bleed', text: 'X-Zelkor-Tenant-ID bound at the gateway; hard storage partitioning.' },
        { title: 'Customer-uploaded malware / prompt injection', text: 'File parsing and code tools in isolated gVisor sandbox-exec pods.' },
        { title: 'Gross margin destruction by power users', text: 'Real-time per-tenant and per-run token budgets at the AI Gateway.' },
        { title: 'SSRF against internal microservices', text: 'Cilium blocks RFC1918 and cloud metadata access.' },
        { title: 'Shared API key blast radius', text: 'Provider keys in the gateway; agent pods never hold upstream secrets.' },
        { title: 'Blocked enterprise questionnaires', text: 'Verifiable gVisor, Cilium, Kyverno, and OpenTelemetry controls.' },
      ],
      mappingTitle: 'Customer / auditor mapping',
      mapping: [
        { framework: 'SOC 2 Type II logical isolation', requirement: 'Tenant A cannot access Tenant B even if prompts fail', control: 'Signed tenant context + partitioning across namespaces, graphs, MCP' },
        { framework: 'OWASP LLM01 / LLM02 / LLM07', requirement: 'Prompt injection, disclosure, system prompt leakage', control: 'Llama Guard, keyless pods, L7 egress allowlists' },
        { framework: 'OWASP LLM06 Excessive Agency', requirement: 'Restrict autonomous tool execution', control: 'Out-of-process sandbox-exec under gVisor + per-tool MCP policy' },
        { framework: 'FinOps & COGS governance', requirement: 'Prevent unbounded variable LLM spend', control: 'Per-run ceilings, per-tenant daily caps, loop breakers' },
      ],
      scenariosTitle: 'Workflows',
      scenarios: [
        { title: 'Customer-facing data analyst', text: 'Natural-language Python charts inside ephemeral zero-egress gVisor sandboxes.' },
        { title: 'Tenant-scoped knowledge copilots', text: 'Strict tenant header binding and full Langfuse trace attribution.' },
        { title: 'Tiered AI plan enforcement', text: 'Map Free/Pro/Enterprise to gateway token budgets, model routing, and rate limits.' },
      ],
      bottomHeadline: 'Pass enterprise AI security reviews on the first call.',
      bottomCta: { label: 'Book Architecture Review', href: '/contact' },
    },
    'platform-engineering': {
      slug: 'platform-engineering',
      eyebrow: 'Solutions · platform engineering',
      h1: 'One Helm chart to standardize every AI agent on Kubernetes.',
      subtitle: 'Stop bespoke Dockerfiles, hardcoded API keys, and unquotad pods. Give application teams a golden path for LangGraph, CrewAI, and custom agents with built-in gVisor, Cilium, Kyverno, and OpenTelemetry.',
      primaryCta: { label: 'Read Helm Chart Docs', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      risks: [
        { title: 'Shadow AI sprawl', text: 'Single Helm chart and Kyverno admission rules standardize deployment.' },
        { title: 'Quota failures & node starvation', text: 'Explicit resources.requests and resources.limits on every container.' },
        { title: 'kubectl / manifest drift', text: '100% Helm-native; versioned in Chart.yaml; zero inline manifest hacks.' },
        { title: 'Host kernel exposure on shared nodes', text: 'Agent pods scheduled onto RuntimeClassName: gvisor with dropped capabilities.' },
        { title: 'Zero visibility into LLM spend', text: 'Prometheus metrics and OpenTelemetry traces per namespace and agent.' },
        { title: 'Vendor lock-in to proprietary cloud sandboxes', text: 'Runs on EKS, GKE, AKS, OpenShift, bare-metal/Hetzner on open-source standards.' },
      ],
      mappingTitle: 'Platform standards',
      mapping: [
        { framework: 'PSS Restricted', requirement: 'Non-root, read-only rootfs, dropped capabilities, seccomp RuntimeDefault', control: 'Helm templates + Kyverno ClusterPolicy' },
        { framework: 'ResourceQuota & LimitRange', requirement: 'Every container and initContainer declares CPU/memory', control: 'Configurable resources on all chart components' },
        { framework: 'Zero-trust cluster networking', requirement: 'Block IMDS, K8s API, unauthorized internet egress', control: 'No SA token + Cilium L7 FQDN allowlists' },
        { framework: 'GitOps & Helm-only delivery', requirement: 'No kubectl or --create-namespace', control: 'helm upgrade --install into admin-provisioned namespaces' },
      ],
      scenariosTitle: 'Workflows',
      scenarios: [
        { title: 'Golden-path onboarding in 10 minutes', text: 'Bring an existing agent image, set OPENAI_BASE_URL, deploy via standardized values.' },
        { title: 'Automated policy at admission', text: 'Kyverno rejects pods missing gvisor, runAsNonRoot, or CPU/memory limits.' },
        { title: 'Centralized multi-cluster observability', text: 'Feed OTel and Prometheus from all agent namespaces into Grafana, Langfuse, and SIEM.' },
      ],
      bottomHeadline: 'Give your developers a paved road for autonomous agents.',
      bottomCta: { label: 'Install via Helm', href: '/docs/quickstart' },
    },
  },
  editions: {
    eyebrow: 'Editions & licensing',
    h1: 'Open-source core. Enterprise-grade multi-tenancy and governance.',
    subtitle: 'Start immediately with Zelkor Community Edition (Apache 2.0) on any Kubernetes cluster. Upgrade to Pro or Enterprise when you need multi-tenant data perimeters, SSO/RBAC, HA control planes, and compliance mappings.',
    primaryCta: { label: 'Install Community Edition', href: '/docs/quickstart' },
    secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
    cards: [
      {
        name: 'Community Edition (CE)',
        kicker: 'Open source · Apache 2.0',
        tagline: 'Individual AI engineers, security researchers, and teams hardening their first production agent on a single cluster.',
        highlights: ['gVisor sandbox scheduling', 'Keyless AI Gateway (LiteLLM)', 'Llama Guard + per-run token budgets', 'Cilium default-deny + Flight Recorder'],
        cta: { label: 'Deploy from GitHub / GHCR', href: '/docs/quickstart' },
        featured: true,
      },
      {
        name: 'Pro Edition',
        kicker: 'Production teams',
        tagline: 'Platform and engineering organizations running multiple agents across departments or customer tenants.',
        highlights: ['X-Zelkor-Tenant-ID + graph partitioning', 'Per-tenant budgets & loop breakers', 'Kyverno pack with drift reporting', 'Business-hours SLA'],
        cta: { label: 'Request Pro Access', href: '/contact' },
      },
      {
        name: 'Enterprise Edition',
        kicker: 'Regulated & mission-critical',
        tagline: 'Financial institutions, healthcare providers, and large B2B SaaS platforms.',
        highlights: ['Multi-cluster HA gateway', 'SSO / OIDC / SAML & RBAC', 'Air-gapped registry', 'FINRA, SR 11-7, DORA, HIPAA, SOC 2 packs'],
        cta: { label: 'Book Architecture Review', href: '/contact' },
      },
    ],
    matrix: [
      { capability: 'gVisor kernel sandbox & rootless pod security', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'Out-of-process sandbox-exec MCP isolation', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'Keyless AI Gateway', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'Inline Llama Guard / PII redaction', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'Cilium default-deny, IMDS block, FQDN allowlists', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'Flight Recorder (OTel + Langfuse)', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'Per-run token ceilings & basic loop detection', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'Kyverno admission pack', ce: 'Core policies', pro: 'Full pack + drift alerts', enterprise: 'Custom org policies' },
      { capability: 'Multi-tenant data perimeter', ce: 'Single tenant', pro: 'Multi-tenant', enterprise: 'Multi-tenant + cross-cluster' },
      { capability: 'Per-tenant spend governance', ce: '—', pro: 'Included', enterprise: 'Included' },
      { capability: 'Granular MCP tool authorization', ce: 'Static allowlist', pro: 'Dynamic RBAC', enterprise: 'OIDC / claims-driven' },
      { capability: 'Enterprise SSO & RBAC', ce: '—', pro: '—', enterprise: 'Included' },
      { capability: 'SIEM audit streaming & compliance packs', ce: '—', pro: '—', enterprise: 'Included' },
      { capability: 'Air-gapped / private registry & multi-cluster HA', ce: '—', pro: '—', enterprise: 'Included' },
      { capability: 'Support', ce: 'GitHub community', pro: 'Business hours SLA', enterprise: '24/7 dedicated + FDE advisory' },
    ],
    faqs: [
      { q: 'Do we have to rewrite existing LangGraph, CrewAI, or custom Python agents?', a: 'No. Keep your orchestration code, swap OPENAI_BASE_URL to the cluster-local gateway, and move high-risk code/tool execution to Zelkor’s MCP sandbox-exec pods.' },
      { q: 'Does Zelkor claim to make LLMs 100% immune to prompt injection?', a: 'Never. Anyone claiming 100% immunity is selling snake oil. Zelkor pairs Llama Guard with deterministic infrastructure: gVisor stops host breakouts, keyless pods prevent API key theft, Cilium blocks unauthorized egress, tenant headers prevent cross-customer reads.' },
      { q: 'What Kubernetes distributions are supported?', a: 'Any conformant cluster where a gvisor RuntimeClass and CNI (Cilium recommended) can be configured—EKS, GKE, AKS, OpenShift, bare-metal or Hetzner.' },
      { q: 'How does Zelkor handle ResourceQuota and LimitRange?', a: 'Every container and initContainer declares explicit CPU and memory requests and limits, and deploys into admin-precreated namespaces without --create-namespace.' },
      { q: 'Where do upstream credentials live?', a: 'Exclusively in a Kubernetes Secret inside the isolated gateway namespace. Agent pods only receive scoped, short-lived gateway tokens.' },
      { q: 'How do we evaluate Pro or Enterprise on our own cluster?', a: 'Install Community Edition from GHCR using Helm, or book a 45-minute architecture review to walk through the 5 live proofs and scope a pilot.' },
    ],
    finalHeadline: 'Ready to harden your agent runtime?',
    finalSub: 'Deploy Community Edition in minutes or schedule a technical architecture review for your security and platform teams.',
  },
}
