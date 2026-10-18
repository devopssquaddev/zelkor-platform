import type { VariantCopy } from './types'

const helm = `helm upgrade --install zelkor oci://ghcr.io/zelkor-ai/charts/zelkor \\
  --namespace zelkor-system --wait`

export const v3: VariantCopy = {
  id: 3,
  name: 'Swiss Editorial',
  short: 'Swiss',
  announcement: {
    badge: 'Specification v0.8',
    text: 'Deterministic runtime boundaries for untrusted agent execution on Kubernetes — gVisor runsc, Envoy ext_proc guardrails, and storage-enforced tenant perimeters.',
    linkLabel: 'Read the Architecture Reference →',
    href: '/docs',
  },
  brandSub: 'Runtime control plane',
  navCta: { label: 'Request Architecture Review', href: '/contact' },
  productsNav: [
    { slug: 'sandbox', title: 'gVisor Sandbox', blurb: 'runsc userspace kernel & micro-VM execution pods.' },
    { slug: 'gateway', title: 'AI Gateway & Guardrails', blurb: 'Envoy AI Gateway, ext_proc inspection & token budgets.' },
    { slug: 'mcp', title: 'MCP Proxy & Tool Isolation', blurb: 'JSON-RPC mediation, X-Tenant-ID synthesis & schema validation.' },
    { slug: 'tenancy', title: 'Multi-Tenant Data Perimeter', blurb: 'Valkey ACL prefixing, Qdrant filters & storage-layer isolation.' },
    { slug: 'observability', title: 'Flight Recorder Tracing', blurb: 'OpenTelemetry spans, Langfuse/Arize Phoenix sinks.' },
    { slug: 'network', title: 'Network & Cluster Armor', blurb: 'Cilium L7 FQDN policies, metadata deny & Kyverno admission.' },
  ],
  solutionsNav: [
    { slug: 'financial-services', title: 'Financial Services', blurb: 'DORA, PCI-DSS 4.0, air-gapped trading & credit agents.' },
    { slug: 'healthcare', title: 'Healthcare & Life Sciences', blurb: 'HIPAA ePHI perimeters, clinical synthesis & trial isolation.' },
    { slug: 'b2b-saas', title: 'Multi-Tenant B2B SaaS', blurb: 'Cryptographic tenant boundaries for embedded customer agents.' },
    { slug: 'platform-engineering', title: 'Platform Engineering', blurb: 'Self-service Kubernetes agent runtime for internal teams.' },
  ],
  home: {
    eyebrow: 'Kubernetes agent control plane // Apache 2.0 core',
    h1: 'The deterministic Kubernetes control plane between untrusted agent code and production data.',
    subtitle:
      'LLM outputs are probabilistic; your security boundaries cannot be. Deploy unmodified LangGraph, CrewAI, AutoGen, or custom Python/TypeScript agents inside gVisor-isolated pods where credentials never enter container memory, tool calls traverse a mediating MCP proxy, and tenant boundaries are enforced at the storage engine.',
    primaryCta: { label: 'Deploy Community Edition (Helm)', href: '/docs/quickstart' },
    secondaryCta: { label: 'Inspect Runtime Architecture', href: '/docs' },
    install: helm,
    marqueeLabel: 'Architectural invariants',
    marquee: [
      'RuntimeClass: gvisor runsc',
      'Zero provider keys in pod env',
      'Envoy ext_proc prompt & PII inspection',
      'Cilium L7 default-deny egress',
      'MCP JSON-RPC header synthesis',
      'Valkey & Qdrant tenant prefix enforcement',
      'OpenTelemetry flight recorder',
      'Kyverno PSS restricted admission',
    ],
    bridgeKicker: 'Bring the agent you already wrote.',
    bridgeHeading: 'Enforce the perimeter it cannot bypass.',
    bridge:
      'Application teams write prompts, graphs, and tool definitions. They should not implement syscall filters, credential rotation, token-rate circuit breakers, or multi-tenant vector partitioning in application code. Zelkor separates agent logic from runtime enforcement: the agent runs as an unprivileged workload inside a sealed Kubernetes pod; every packet, inference call, and state mutation crosses an out-of-process control plane.',
    tabsHeadline: 'Four contracts. Four artifacts.',
    tabs: [
      {
        id: 'sandbox',
        label: '01 / Sandbox',
        headline: 'Syscall & filesystem containment',
        copy: 'Agent containers and ephemeral execution sandboxes run under RuntimeClass: gvisor (runsc). Host Linux kernel syscalls are intercepted by a userspace sentry; container root filesystems mount readOnlyRootFilesystem: true with all Linux capabilities dropped.',
        lang: 'yaml',
        code: `apiVersion: zelkor.io/v1alpha1
kind: AgentWorkload
metadata:
  name: portfolio-rebalancer
  namespace: zelkor-agents
spec:
  image: ghcr.io/acme-corp/rebalancer:sha-8f92a1c
  runtimeClassName: gvisor
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    readOnlyRootFilesystem: true
    allowPrivilegeEscalation: false
    capabilities: { drop: ["ALL"] }
  sandboxPool:
    warmReplicas: 3
    maxExecutionSeconds: 30`,
      },
      {
        id: 'gateway',
        label: '02 / Gateway',
        headline: 'Out-of-process inference & guardrail mediation',
        copy: 'Agent pods hold zero upstream LLM API keys. Outbound inference routes to the in-cluster Envoy AI Gateway, which runs an ext_proc guardrail filter, enforces per-tenant token budgets, and injects upstream credentials from Kubernetes Secrets at the proxy edge.',
        lang: 'yaml',
        code: `apiVersion: gateway.zelkor.io/v1alpha1
kind: AIGatewayPolicy
metadata:
  name: prod-inference-contract
  namespace: zelkor-system
spec:
  upstreamCredentials:
    secretRef: llm-provider-keys
    injectAt: EgressProxyOnly
  extProcGuardrails:
    inboundPromptScan: Enforce
    outboundPiiRedaction: Enforce
    failMode: FailClosed
  budgets:
    window: 1h
    maxTokensPerTenant: 500000
    maxIterationsPerRun: 25`,
      },
      {
        id: 'mcp',
        label: '03 / MCP & Tenants',
        headline: 'Authenticated tool & storage partitioning',
        copy: 'Agents never connect directly to databases or internal APIs, nor do they self-declare tenant identity. The MCP Proxy authenticates the ServiceAccount token, strips any agent-supplied X-Tenant-ID, synthesizes the authoritative header from the verified session envelope, and scopes Valkey keys and Qdrant filters.',
        lang: 'yaml',
        code: `apiVersion: mcp.zelkor.io/v1alpha1
kind: MCPToolRoute
metadata:
  name: ledger-query-route
  namespace: zelkor-system
spec:
  identityPropagation:
    stripClientHeaders: ["X-Tenant-ID", "X-User-Role"]
    synthesizeHeader: "X-Tenant-ID"
    sourceClaim: "zelkor.io/tenant_id"
  storagePerimeter:
    valkeyKeyPrefix: "tenant:{{ .TenantID }}:"
    qdrantFilterField: "tenant_id"
  allowedTools:
    - { name: get_account_balance, readOnly: true }`,
      },
      {
        id: 'trace',
        label: '04 / Trace',
        headline: 'Deterministic flight recorder',
        copy: 'Because every LLM call, guardrail evaluation, MCP invocation, and sandbox execution traverses Zelkor’s proxies, telemetry is emitted out-of-process via OpenTelemetry. Even if an agent crashes, the full causal DAG is recorded without application-level SDK instrumentation.',
        lang: 'json',
        code: `{
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_name": "zelkor.mcp.tool_invoke",
  "attributes": {
    "zelkor.tenant.id": "tenant-alpha-902",
    "zelkor.runtime.class": "gvisor-runsc",
    "zelkor.gateway.guardrail_verdict": "PASS",
    "zelkor.mcp.header_synthesized": true
  }
}`,
      },
    ],
    stepsHeadline: 'Three-step deployment contract',
    steps: [
      { title: 'Install the control plane chart', body: 'Deploy Zelkor into pre-provisioned namespaces via a single Helm release. No CRDs that mutate host nodes outside standard RuntimeClass and CNI policies; zero kubectl apply scripts in CI.' },
      { title: 'Bind your existing agent image', body: 'Reference your unmodified container. Point OPENAI_BASE_URL to http://zelkor-gateway.zelkor-system.svc:8080/v1 and MCP_SERVER_URL to the in-cluster MCP proxy.' },
      { title: 'Verify the five runtime invariants', body: 'Execute zelkor verify to run deterministic conformance probes proving credential absence, syscall interception, cross-tenant storage rejection, egress blocking, and loop circuit-breaking.' },
    ],
    proofsHeadline: 'Five verifiable runtime invariants',
    proofs: [
      { title: 'INV-01 The Vanishing Key', scenario: 'Prompt injection dumps os.environ or /proc/self/environ to exfiltrate LLM API keys.', control: 'Agent pods receive only an ephemeral workload token. Upstream keys reside in zelkor-gateway and attach on the egress wire.', result: 'env | grep OPENAI inside the pod returns empty.' },
      { title: 'INV-02 The Flight Recorder', scenario: 'Compromised agent suppresses logging or crashes mid-execution.', control: 'Telemetry is captured at Envoy, MCP Proxy, and sandbox controller via OTLP—independent of the agent process.', result: 'Every prompt, guardrail score, tool payload, and token count appears even if the container is SIGKILLed.' },
      { title: 'INV-03 The Shell Moved', scenario: 'Untrusted code runs subprocess.Popen("/bin/sh") to probe the host kernel.', control: 'Ephemeral gVisor sandbox with read-only rootfs, dropped capabilities, automountServiceAccountToken: false, L3/L4/L7 egress blocked.', result: 'Kernel exploits hit the runsc sentry; sockets to 169.254.169.254 drop.' },
      { title: 'INV-04 Two Desks, One Graph', scenario: 'Tenant A instructs the shared graph to read Tenant B’s cached state.', control: 'MCP Proxy overwrites X-Tenant-ID from the verified token; Valkey ACL prefixes and Qdrant payload filters.', result: 'tenant:B:session_01 returns NOPERM at the storage proxy.' },
      { title: 'INV-05 Loop Dies at the Door', scenario: 'Recursive tool-call hallucination triggers thousands of consecutive LLM calls.', control: 'Envoy tracks per-run step counts and rolling tenant token budgets in Valkey.', result: 'HTTP 429 at maxIterationsPerRun; zelkor.budget.circuit_open span.' },
    ],
    personasHeadline: 'Three mandates. One control plane.',
    personas: [
      { title: 'Staff & Principal Architects', role: '01', body: 'Establish an auditable, defense-in-depth reference architecture without trusting probabilistic LLM guardrails alone.', points: ['Untrusted execution plane: zelkor-agents', 'Mediation plane: zelkor-system', 'Stateful data plane: zelkor-data'] },
      { title: 'Principal Platform & Security Engineers', role: '02', body: 'Run agent workloads under PSS restricted, ResourceQuotas, LimitRanges, Cilium, Kyverno, and Helm-only GitOps.', points: ['Explicit resources on every container', 'helm upgrade --install --namespace', 'Admission rejects unsandboxed pods'] },
      { title: 'AI Systems Leads', role: '03', body: 'Ship LangGraph, CrewAI, or custom multi-agent workflows without rewriting agent code to pass security review.', points: ['Drop-in OpenAI/Anthropic endpoints', 'Standard MCP tool routing', 'Langfuse/Phoenix correlation'] },
    ],
    finalHeadline: 'Inspect the Helm chart, run the five invariant probes, or review your topology with a systems architect.',
    finalSub: 'Specification first. Then the cluster.',
    finalPrimary: { label: 'Request Architecture Review', href: '/contact' },
    finalSecondary: { label: 'Browse Chart & Docs', href: '/docs' },
  },
  products: {
    sandbox: {
      slug: 'sandbox',
      eyebrow: 'Product // 01 — execution isolation',
      h1: 'Kernel-isolated execution pods for untrusted agent processes and generated code.',
      subtitle: 'Standard Linux containers share the host kernel syscall table. Zelkor runs agent workloads and ephemeral code-execution sandboxes inside gVisor (runsc) or Kata micro-VMs with read-only root filesystems, zero ambient capabilities, and pre-warmed sub-second allocation pools.',
      primaryCta: { label: 'Read the Sandbox Specification', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Architectural contract',
      overview: 'When an LLM synthesizes Python, Bash, or Node.js—or parses untrusted documents—treat the process as hostile. The sandbox controller schedules every execution inside an isolated RuntimeClass boundary.',
      capabilities: [
        { title: 'runsc userspace kernel interception', text: 'Intercepts 200+ Linux system calls in userspace before they reach the host kernel.' },
        { title: 'Immutable filesystem & capability strip', text: 'readOnlyRootFilesystem, runAsNonRoot, allowPrivilegeEscalation: false, capabilities.drop ALL. Scratch is an emptyDir with sizeLimit.' },
        { title: 'Zero-credential pod environment', text: 'automountServiceAccountToken: false on code-interpreter sandboxes; no upstream API keys in env or volumes.' },
        { title: 'Pre-warmed ephemeral sandbox pools', text: 'SandboxWarmPool claims a clean pod in milliseconds, executes within a wall-clock timeout, and destroys the pod after output collection.' },
      ],
      snippetTitle: 'SandboxWarmPool',
      snippetLang: 'yaml',
      snippet: `apiVersion: sandbox.zelkor.io/v1alpha1
kind: SandboxWarmPool
metadata:
  name: python-code-interpreter
  namespace: zelkor-sandboxes
spec:
  replicas: 5
  runtimeClassName: gvisor
  recycleMode: DestroyAfterSingleExecution
  maxWallClockSeconds: 20
  template:
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 65532`,
      bottomHeadline: 'Verify runsc isolation on your cluster in under ten minutes.',
      bottomPrimary: { label: 'Read the Sandbox Specification', href: '/docs' },
      bottomSecondary: { label: 'Request Architecture Review', href: '/contact' },
    },
    gateway: {
      slug: 'gateway',
      eyebrow: 'Product // 02 — inference mediation',
      h1: 'Out-of-process LLM proxy with Envoy ext_proc guardrails, credential injection, and deterministic token circuit breakers.',
      subtitle: 'Stop embedding provider API keys and prompt filters inside application containers. Zelkor routes all model traffic through an Envoy AI Gateway.',
      primaryCta: { label: 'Read the AI Gateway Specification', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Architectural contract',
      overview: 'Probabilistic guardrails alone cannot guarantee safety. Agent pods speak standard OpenAI/Anthropic HTTP using an internal workload token; the gateway authenticates, runs ext_proc, checks Valkey token counters, and injects the real credential only on outbound TLS.',
      capabilities: [
        { title: 'Egress-only credential injection', text: 'Upstream keys never enter zelkor-agents namespaces. Envoy swaps the ephemeral pod token for the provider key at egress.' },
        { title: 'Envoy ext_proc guardrail pipeline', text: 'Inspects inbound prompts and outbound completions with FailClosed semantics for injection, secrets, and PII.' },
        { title: 'Token, cost & iteration circuit breakers', text: 'Tracks consumption per tenant, workload, and trace run ID. HTTP 429 when maxIterationsPerRun is reached.' },
        { title: 'Semantic routing & deterministic failover', text: 'Primary and fallback providers by model family, latency SLO, or data-residency policy.' },
      ],
      snippetTitle: 'GuardrailAndBudgetPolicy',
      snippetLang: 'yaml',
      snippet: `apiVersion: gateway.zelkor.io/v1alpha1
kind: GuardrailAndBudgetPolicy
metadata:
  name: regulated-inference-policy
spec:
  credentialBinding:
    provider: anthropic
    secretName: anthropic-prod-key
  extProc:
    failureModeAllow: false
    scanners:
      - { type: PromptInjectionHeuristics, action: Block }
      - { type: PiiRedaction, action: RedactInPlace }
  rateLimits:
    perRunMaxSteps: 20
    perTenantTokensPerHour: 1000000`,
      bottomHeadline: 'Remove provider keys from your agent pods today.',
      bottomPrimary: { label: 'Read the AI Gateway Specification', href: '/docs' },
      bottomSecondary: { label: 'Request Architecture Review', href: '/contact' },
    },
    mcp: {
      slug: 'mcp',
      eyebrow: 'Product // 03 — tool & action mediation',
      h1: 'Zero-trust JSON-RPC mediation and cryptographic identity synthesis for MCP tools.',
      subtitle: 'An LLM with direct database credentials or unmediated MCP access is one injected prompt away from unauthorized writes.',
      primaryCta: { label: 'Read the MCP Proxy Specification', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Architectural contract',
      overview: 'Zelkor interposes a stateless MCP Proxy between zelkor-agents and zelkor-tools. Every JSON-RPC 2.0 frame is authenticated, checked against tool RBAC, sanitized against JSON Schema, and stamped with an unforgeable X-Tenant-ID.',
      capabilities: [
        { title: 'Authoritative header synthesis', text: 'Strips agent-supplied X-Tenant-ID, X-User-ID, and Authorization; synthesizes from the verified session token.' },
        { title: 'Per-agent method allowlisting', text: 'Unauthorized tools/call returns JSON-RPC -32601 or -32003 Permission denied.' },
        { title: 'Strict JSON Schema validation', text: 'Blocks SQL/command metacharacter smuggle attempts and oversized payloads.' },
        { title: 'High-risk tool approval gates', text: 'Flags write/delete/transfer/execute for synchronous human or policy-webhook approval.' },
      ],
      snippetTitle: 'MCPAccessPolicy',
      snippetLang: 'yaml',
      snippet: `apiVersion: mcp.zelkor.io/v1alpha1
kind: MCPAccessPolicy
metadata:
  name: customer-support-agent-mcp
spec:
  headerSynthesis:
    overwriteHeaders:
      X-Tenant-ID: "{{ .Token.Claims.tenant_id }}"
  upstreams:
    - serverName: crm-mcp-server
      allowedTools:
        - { name: lookup_ticket }
        - { name: issue_refund, approvalGate: { required: true } }`,
      bottomHeadline: 'Mediate every MCP tool call with cryptographic tenant context.',
      bottomPrimary: { label: 'Read the MCP Proxy Specification', href: '/docs' },
      bottomSecondary: { label: 'Request Architecture Review', href: '/contact' },
    },
    tenancy: {
      slug: 'tenancy',
      eyebrow: 'Product // 04 — state & memory isolation',
      h1: 'Storage-enforced tenant boundaries across Valkey session state, Qdrant vector indexes, and relational stores.',
      subtitle: 'Sharing a single LangGraph deployment across customers is safe only if the agent process cannot query across tenant boundaries. Zelkor enforces partitioning at the data-access proxy—never in prompt instructions.',
      primaryCta: { label: 'Read the Data Perimeter Specification', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Architectural contract',
      overview: 'Instructing an LLM to only query tenant_id = X is a broken pattern. Zelkor binds every execution context to a signed tenant claim and translates it into Valkey ACL prefixes, mandatory Qdrant filters, and Postgres RLS.',
      capabilities: [
        { title: 'Valkey ACL key-prefix enforcement', text: 'State under tenant:{id}:*. Cross-prefix GET/SET/SCAN/KEYS is rejected.' },
        { title: 'Proxy-injected Qdrant vector filters', text: 'Force-merges must: [{ key: tenant_id, match: verified_tenant }] into the request AST.' },
        { title: 'Postgres RLS context binding', text: 'SET LOCAL zelkor.tenant_id inside each transaction block.' },
        { title: 'Tiered isolation topologies', text: 'Logical key/filter partitioning, dedicated collections, or physical node-pool separation.' },
      ],
      snippetTitle: 'TenantDataPerimeter',
      snippetLang: 'yaml',
      snippet: `apiVersion: data.zelkor.io/v1alpha1
kind: TenantDataPerimeter
metadata:
  name: shared-rag-and-checkpoint-perimeter
spec:
  tenantClaimHeader: "X-Tenant-ID"
  rejectMissingTenant: true
  valkey:
    enforcedKeyPattern: "tenant:{{ .TenantID }}:*"
    blockedCommands: ["FLUSHALL", "FLUSHDB", "KEYS", "CONFIG"]
  qdrant:
    collectionStrategy: SharedCollectionMandatoryFilter
    mandatoryPayloadFilter: { field: "tenant_id" }`,
      bottomHeadline: 'Prove cross-tenant queries fail at the storage layer.',
      bottomPrimary: { label: 'Read the Data Perimeter Specification', href: '/docs' },
      bottomSecondary: { label: 'Request Architecture Review', href: '/contact' },
    },
    observability: {
      slug: 'observability',
      eyebrow: 'Product // 05 — deterministic audit & telemetry',
      h1: 'Out-of-process OpenTelemetry flight recording across prompts, guardrails, MCP calls, and sandbox syscalls.',
      subtitle: 'Application-level tracing SDKs fail when an agent hangs, crashes, or gets compromised. Zelkor captures the complete execution graph at the infrastructure boundary.',
      primaryCta: { label: 'Read the Observability Specification', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Architectural contract',
      overview: 'Zelkor propagates W3C traceparent and baggage across Envoy AI Gateway, MCP Proxy, and Sandbox Controller—emitting correlated spans regardless of which agent framework runs inside the container.',
      capabilities: [
        { title: 'Zero-SDK boundary capture', text: 'Captures LLM payloads, latency, token counts, and MCP frames directly from Envoy and the MCP Proxy.' },
        { title: 'PII-scrubbed audit sinks', text: 'Deterministic redaction before spans leave the gateway (Langfuse, Phoenix, Datadog, Splunk).' },
        { title: 'Causal DAG correlation', text: 'Parent HTTP → LLM inference → guardrail → MCP → sandbox → completion under one trace ID.' },
        { title: 'Cost & token attribution ledger', text: 'Prometheus and OTLP attributes tagged by tenant, workload, and model.' },
      ],
      snippetTitle: 'FlightRecorderConfig',
      snippetLang: 'yaml',
      snippet: `apiVersion: observability.zelkor.io/v1alpha1
kind: FlightRecorderConfig
spec:
  otlpExporter:
    endpoint: grpc://langfuse-otel.zelkor-obs.svc:4317
    protocol: grpc
  captureScope:
    recordPromptBodies: true
    recordMcpPayloads: true
    recordSandboxStdout: true
    redactBeforeExport: true`,
      bottomHeadline: 'Get full causal traces without touching application code.',
      bottomPrimary: { label: 'Read the Observability Specification', href: '/docs' },
      bottomSecondary: { label: 'Request Architecture Review', href: '/contact' },
    },
    network: {
      slug: 'network',
      eyebrow: 'Product // 06 — zero-trust Kubernetes perimeter',
      h1: 'Default-deny Cilium L7 egress, cloud metadata blocking, and Kyverno admission hardening for agent namespaces.',
      subtitle: 'Even if untrusted code executes inside a pod, it should have nowhere to go. Agent pods can reach only the in-cluster AI Gateway and MCP Proxy.',
      primaryCta: { label: 'Read the Network & Admission Specification', href: '/docs' },
      secondaryCta: { label: 'Request Architecture Review', href: '/contact' },
      overviewTitle: 'Architectural contract',
      overview: 'An agent workload should never initiate arbitrary outbound TCP, query the Kubernetes API server, or reach 169.254.169.254. Zelkor packages Cilium/NetworkPolicy, Kyverno, and ResourceQuota templates inside the Helm chart.',
      capabilities: [
        { title: 'Default-deny ingress & egress', text: 'Whitelists only the gateway and MCP proxy ports from zelkor-agents and zelkor-sandboxes.' },
        { title: 'Cloud IMDS & control-plane blackhole', text: 'Drops 169.254.169.254/32, link-local ranges, and the default/kubernetes API service IP.' },
        { title: 'Cilium L7 DNS/FQDN & HTTP filtering', text: 'Restricts remaining egress to approved FQDNs and HTTP paths/methods.' },
        { title: 'Kyverno PSS & quota enforcement', text: 'Rejects pods that omit runtimeClassName: gvisor, lack CPU/memory limits, mount host paths, or request root.' },
      ],
      snippetTitle: 'CiliumNetworkPolicy',
      snippetLang: 'yaml',
      snippet: `apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: zelkor-agent-strict-egress
  namespace: zelkor-agents
spec:
  endpointSelector:
    matchLabels: { zelkor.io/plane: agent-execution }
  egressDeny:
    - toCIDR: ["169.254.169.254/32", "10.0.0.0/8"]`,
      bottomHeadline: 'Seal agent namespaces against lateral movement and exfiltration.',
      bottomPrimary: { label: 'Read the Network & Admission Specification', href: '/docs' },
      bottomSecondary: { label: 'Request Architecture Review', href: '/contact' },
    },
  },
  solutions: {
    'financial-services': {
      slug: 'financial-services',
      eyebrow: 'Solution // 01 — financial services & capital markets',
      h1: 'Deterministic runtime controls for financial agents under DORA, PCI-DSS 4.0, and SEC/FINRA audit mandates.',
      subtitle: 'Deploy credit-underwriting, portfolio-research, and claims-processing agents inside air-gapped or private VPC Kubernetes clusters where ledger mutations require synchronous approval gates.',
      primaryCta: { label: 'Request Financial Architecture Review', href: '/contact' },
      secondaryCta: { label: 'See INV-04', href: '/#proofs' },
      risks: [
        { title: 'Unbounded ledger / wire mutation', text: 'MCP Proxy schema validation + synchronous approval gate (requiresApprovalGate: true).' },
        { title: 'Cross-account portfolio leakage', text: 'MCP Proxy overwrites X-Tenant-ID; Valkey and Qdrant reject cross-prefix queries (INV-04).' },
        { title: 'PAN / IBAN exfiltration', text: 'Envoy ext_proc PII/PCI scanner redacts PAN/IBAN in-flight, FailClosed.' },
        { title: 'Malicious quantitative code synthesis', text: 'Ephemeral gVisor pool, read-only rootfs, zero egress, 20-second wall-clock (INV-03).' },
        { title: 'Unreconstructible algorithmic decisions', text: 'OTLP Flight Recorder to immutable WORM/SIEM storage (INV-02).' },
        { title: 'Denial-of-wallet / runaway market loop', text: 'Hard per-run step caps and per-desk hourly token budgets (INV-05).' },
      ],
      mappingTitle: 'Regulatory mapping',
      mapping: [
        { framework: 'EU DORA Art. 9', requirement: 'ICT isolation, network segmentation, privileged execution restriction', control: 'RuntimeClass gvisor, Cilium default-deny, PSS restricted' },
        { framework: 'PCI-DSS v4.0 Req. 3 & 6.4', requirement: 'Prevent PAN exposure; mediate outbound traffic', control: 'ext_proc PAN/PII scrubbing + INV-01' },
        { framework: 'SEC 17a-4 / FINRA 4511 / MiFID II', requirement: 'Non-erasable reconstruction of automated communications', control: 'OTLP Flight Recorder to WORM object storage' },
        { framework: 'SR 11-7 / OSFI E-23', requirement: 'Deterministic operational boundaries and override switches', control: 'AIGatewayPolicy circuit breakers, MCP allowlists, approval gates' },
      ],
      scenariosTitle: 'Reference topologies',
      scenarios: [
        { title: 'Air-gapped on-prem / OpenShift', text: 'Self-hosted vLLM; zero external internet routes.' },
        { title: 'Hybrid Private Link', text: 'Gateway connects to Bedrock / Azure OpenAI over PrivateLink with customer-managed KMS.' },
        { title: 'Multi-desk institutional partitioning', text: 'Separate AgentWorkload namespaces per desk; central zelkor-system mediation plane.' },
      ],
      bottomHeadline: 'Review your DORA / PCI-DSS agent topology with our systems architects.',
      bottomCta: { label: 'Request Financial Architecture Review', href: '/contact' },
    },
    healthcare: {
      slug: 'healthcare',
      eyebrow: 'Solution // 02 — healthcare, clinical & life sciences',
      h1: 'HIPAA-grade ePHI perimeters and clinical tool isolation for healthcare AI workloads.',
      subtitle: 'Run clinical documentation, prior-authorization, and pharmacovigilance agents without exposing ePHI to unauthorized models, cross-patient sessions, or unlogged tool mutations.',
      primaryCta: { label: 'Request Healthcare Architecture Review', href: '/contact' },
      secondaryCta: { label: 'See tenancy', href: '/products/tenancy' },
      risks: [
        { title: 'Unredacted ePHI to non-BAA endpoints', text: 'Gateway restricts routing and runs ext_proc PHI redaction.' },
        { title: 'Cross-patient context bleed', text: 'Encounter scope bound to X-Tenant-ID; Valkey ACL and Qdrant filters (INV-04).' },
        { title: 'Unauthorized EHR write-back', text: 'Read-only FHIR tools separated from writes; clinician approval gates.' },
        { title: 'Bioinformatics script breakout', text: 'Ephemeral gVisor pods, memory-backed /tmp, default-deny egress (INV-03).' },
        { title: 'Credential theft from clinical pods', text: 'Zero secrets in agent pods (INV-01).' },
        { title: 'Incomplete clinical audit logs', text: 'OTLP Flight Recorder logs every FHIR tool call and resource ID (INV-02).' },
      ],
      mappingTitle: 'HIPAA / GxP mapping',
      mapping: [
        { framework: 'HIPAA §164.312(a)(1)', requirement: 'Unique identification and restricted ePHI access', control: 'X-Tenant-ID synthesis + Valkey/Qdrant partitioning' },
        { framework: 'HIPAA §164.312(b)', requirement: 'Record activity in systems with ePHI', control: 'Out-of-process OTel Flight Recorder' },
        { framework: 'HIPAA §164.312(e)(1)', requirement: 'Transmission security', control: 'In-cluster mTLS, Cilium L7 lock, ext_proc PHI scrubbing' },
        { framework: 'FDA 21 CFR Part 11 / EU Annex 11', requirement: 'Closed-system controls and immutable audit trails', control: 'MCP allowlists, approval gates, signed OTLP sinks' },
      ],
      scenariosTitle: 'Reference topologies',
      scenarios: [
        { title: 'Hospital EHR integration perimeter', text: 'FHIR strictly through MCP Proxy; read-only scopes and clinician-in-the-loop writes.' },
        { title: 'Clinical trial cohort isolation', text: 'Dedicated namespace and Qdrant collection per Study-ID.' },
        { title: 'Sovereign bio-compute sandbox', text: 'High-density SandboxWarmPool for untrusted genomic scripts.' },
      ],
      bottomHeadline: 'Architect a HIPAA-compliant runtime boundary.',
      bottomCta: { label: 'Request Healthcare Architecture Review', href: '/contact' },
    },
    'b2b-saas': {
      slug: 'b2b-saas',
      eyebrow: 'Solution // 03 — multi-tenant B2B SaaS platforms',
      h1: 'Ship customer-facing AI agents on shared Kubernetes infrastructure without cross-tenant data bleed or runaway COGS.',
      subtitle: 'Enterprise buyers block SaaS AI features when tenant isolation relies on prompt engineering. Zelkor gives cryptographic storage partitioning, per-customer token budgets, and isolated code execution.',
      primaryCta: { label: 'Request SaaS Architecture Review', href: '/contact' },
      secondaryCta: { label: 'See INV-04', href: '/#proofs' },
      risks: [
        { title: 'Prompt-engineered tenant spoofing', text: 'MCP Proxy strips agent-provided tenant parameters and injects X-Tenant-ID from the verified SaaS JWT (INV-04).' },
        { title: 'Vector search neighbor bleed', text: 'Data perimeter proxy injects mandatory tenant_id filters into every Qdrant query AST.' },
        { title: 'Noisy-neighbor token exhaustion', text: 'Per-tenant hourly token budgets and per-run iteration caps (INV-05).' },
        { title: 'Customer-uploaded file RCE', text: 'File parsing and code execution in single-use gVisor pods (INV-03).' },
        { title: 'Leaked SaaS master API keys', text: 'Master keys exist only in zelkor-system proxy memory (INV-01).' },
        { title: 'Zero per-customer attribution', text: 'Every OTLP span carries zelkor.tenant.id (INV-02).' },
      ],
      mappingTitle: 'Enterprise security mapping',
      mapping: [
        { framework: 'SOC 2 Type II CC6.1 / CC6.6', requirement: 'Logical separation of customer data', control: 'JWT-to-X-Tenant-ID + Valkey prefixes + Qdrant filters' },
        { framework: 'ISO/IEC 27001 A.8.20 / A.8.22', requirement: 'Network segregation', control: 'Cilium L7 isolating agents, sandboxes, and data' },
        { framework: 'OWASP LLM01 / LLM06', requirement: 'Prompt injection blast radius and excessive agency', control: 'ext_proc scanning + MCP allowlists' },
        { framework: 'Enterprise FinOps', requirement: 'Prevent single-tenant starvation; attribute COGS', control: 'Per-tenant rate limiting + ResourceQuota' },
      ],
      scenariosTitle: 'Reference topologies',
      scenarios: [
        { title: 'High-density shared graph', text: 'Pooled stateless pods; isolation per-request via synthesized headers.' },
        { title: 'Tiered enterprise pods', text: 'Enterprise-tier customers get dedicated namespaces, Qdrant collections, and BYOK.' },
        { title: 'Embedded code-interpreter SaaS', text: 'Dynamically scaled SandboxWarmPool for isolated per-customer Python analysis.' },
      ],
      bottomHeadline: 'Turn enterprise security reviews from a blocker into an architectural advantage.',
      bottomCta: { label: 'Request SaaS Architecture Review', href: '/contact' },
    },
    'platform-engineering': {
      slug: 'platform-engineering',
      eyebrow: 'Solution // 04 — internal developer & AI platforms',
      h1: 'Give every product squad a self-service Kubernetes runtime for AI agents—governed by one Helm chart.',
      subtitle: 'Stop reviewing bespoke Dockerfile hacks, scattered API keys, and unmonitored MCP servers. Developers bring any framework and inherit cluster-wide security by default.',
      primaryCta: { label: 'Request Platform Architecture Review', href: '/contact' },
      secondaryCta: { label: 'Browse docs', href: '/docs' },
      risks: [
        { title: 'Sprawling provider keys in Git & CI', text: 'Centralize LLM credentials in zelkor-gateway; application teams deploy pods with zero secrets (INV-01).' },
        { title: 'Framework lock-in vs governance drift', text: 'Enforce guardrails at network and proxy boundaries, independent of language or framework.' },
        { title: 'Cluster quota & node exhaustion', text: 'Every template renders explicit resources.requests and resources.limits.' },
        { title: 'Imperative kubectl drift', text: '100% Helm-native (helm upgrade --install --namespace) for Argo CD, Flux, GitLab CI.' },
        { title: 'Unvetted internal tool exposure', text: 'MCPToolRoute and MCPAccessPolicy CRDs mediate discovery and invocation.' },
        { title: 'Blind incident response', text: 'Unified OTel Flight Recorder with kill-switches (INV-02, INV-05).' },
      ],
      mappingTitle: 'Platform standards',
      mapping: [
        { framework: 'PSS restricted', requirement: 'Non-root, dropped capabilities, seccomp, no privilege escalation', control: 'Hardened pod security contexts + Kyverno' },
        { framework: 'GitOps', requirement: 'Zero kubectl in CI; versioned Helm into admin namespaces', control: 'Single Chart.yaml, --namespace install contract' },
        { framework: 'Multi-team resource governance', requirement: 'Prevent eviction and quota rejection', control: 'Mandatory CPU/memory in values.yaml' },
        { framework: 'CNCF interoperability', requirement: 'No proprietary black-box daemons', control: 'Envoy, gVisor, Cilium, Valkey, Qdrant, OpenTelemetry' },
      ],
      scenariosTitle: 'Reference topologies',
      scenarios: [
        { title: 'Shared central control plane', text: 'Platform operates zelkor-system; squads deploy into team-*-agents.' },
        { title: 'Environment-per-cluster GitOps', text: 'Identical chart promoted via Argo CD ApplicationSets; FailClosed in prod.' },
        { title: 'OpenShift / restricted enterprise cluster', text: 'SCC compatible; pre-provisioned namespaces; no --create-namespace.' },
      ],
      bottomHeadline: 'Standardize how your organization runs AI agents on Kubernetes.',
      bottomCta: { label: 'Request Platform Architecture Review', href: '/contact' },
    },
  },
  editions: {
    eyebrow: 'Editions & deployment packaging',
    h1: 'One deterministic runtime architecture across open-source and commercial editions.',
    subtitle: 'Start with the Apache 2.0 Community Edition to enforce all five runtime invariants on your cluster today.',
    primaryCta: { label: 'Deploy Community Edition', href: '/docs/quickstart' },
    secondaryCta: { label: 'Contact Architecture & Sales', href: '/contact' },
    cards: [
      {
        name: 'Community Edition (CE)',
        kicker: 'Apache 2.0',
        tagline: 'Single-cluster production deployments, architectural evaluation, and self-managed platform teams.',
        highlights: ['gVisor sandbox controller & warm pools', 'Envoy AI Gateway vanishing key', 'MCP Proxy X-Tenant-ID synthesis', 'OTLP Flight Recorder'],
        cta: { label: 'Deploy Community Edition', href: '/docs/quickstart' },
        featured: true,
      },
      {
        name: 'Pro Edition',
        kicker: 'Commercial subscription',
        tagline: 'Multi-team B2B SaaS and scaling engineering organizations.',
        highlights: ['ML-backed ext_proc classifiers', 'HITL approval workflows', 'Per-tenant BYOK vault bindings', 'Business-hours engineering support'],
        cta: { label: 'Request Pro Evaluation', href: '/contact' },
      },
      {
        name: 'Enterprise Edition',
        kicker: 'Enterprise commercial license',
        tagline: 'Regulated financial, healthcare, defense, and large-scale platform engineering.',
        highlights: ['Kata / Firecracker profiles', 'Air-gapped signed bundles', 'WORM audit sinks for DORA / SEC / HIPAA', '24/7 Sev-1 SLA + staff architect'],
        cta: { label: 'Contact Architecture & Sales', href: '/contact' },
      },
    ],
    matrix: [
      { capability: 'Helm-native control plane (--namespace)', ce: 'Included', pro: 'Included', enterprise: 'Included + air-gapped OCI bundle' },
      { capability: 'gVisor sandbox pods & warm pools', ce: 'Included', pro: 'Included', enterprise: 'Included + Kata / micro-VM' },
      { capability: 'Egress credential injection', ce: 'Kubernetes Secrets', pro: 'K8s Secrets + per-tenant BYOK', enterprise: 'External KMS / Vault / HSM' },
      { capability: 'Envoy ext_proc prompt & PII guardrails', ce: 'Baseline heuristics', pro: 'Contextual ML classifiers', enterprise: 'Custom domain models' },
      { capability: 'Token, cost & loop circuit breakers', ce: 'Per-run & static tenant', pro: 'Dynamic tiered quotas', enterprise: 'Global multi-cluster ledger' },
      { capability: 'MCP JSON-RPC mediation', ce: 'Included', pro: 'Included', enterprise: 'Included' },
      { capability: 'X-Tenant-ID header synthesis', ce: 'Static / JWT mapping', pro: 'OIDC token exchange', enterprise: 'SPIFFE/SPIRE & SAML' },
      { capability: 'High-risk MCP approval gates', ce: 'Webhook stub', pro: 'Managed HITL queue', enterprise: 'Multi-party sign-off' },
      { capability: 'Valkey + Qdrant data perimeter', ce: 'Key-prefix & payload filter', pro: 'Per-tenant provisioning', enterprise: 'Physical node-pool isolation' },
      { capability: 'OTLP Flight Recorder', ce: 'OTLP export', pro: 'Retention & cost UI', enterprise: 'Signed WORM sinks' },
      { capability: 'Cilium L7 egress lock', ce: 'Included', pro: 'Included', enterprise: 'Included + FQDN discovery' },
      { capability: 'Kyverno admission & quota templates', ce: 'Included', pro: 'Included', enterprise: 'OpenShift SCC profiles' },
      { capability: 'zelkor verify CLI', ce: '5 core probes', pro: 'Scheduled conformance', enterprise: 'Compliance evidence export' },
      { capability: 'Supply chain artifacts', ce: 'Public GHCR', pro: 'Cosign-signed images', enterprise: 'SLSA L3 + SBOMs' },
      { capability: 'Support', ce: 'GitHub community', pro: 'Business-hours', enterprise: '24/7 + dedicated architect' },
    ],
    faqs: [
      { q: 'Does Zelkor require modifying existing LangGraph, CrewAI, or AutoGen code?', a: 'No. Configure two environment variables—OPENAI_BASE_URL / ANTHROPIC_BASE_URL to zelkor-gateway and MCP client to zelkor-mcp-proxy—and deploy with runtimeClassName: gvisor. All enforcement occurs out of process.' },
      { q: 'Does Zelkor claim to make LLMs 100% jailbreak-proof?', a: 'No. Zelkor assumes prompt injection will eventually succeed at the model layer. The architectural guarantee is blast-radius containment: INV-01 through INV-05.' },
      { q: 'Why enforce tenant isolation in the MCP Proxy and storage layer instead of system prompts?', a: 'System prompts live in the same token stream as untrusted input. Zelkor extracts tenant identity from the authenticated invocation token outside the pod and enforces prefix and payload filter rules at Valkey and Qdrant.' },
      { q: 'How does Zelkor handle ResourceQuota, LimitRange, and no cluster-admin CI?', a: 'Every container and initContainer defines explicit CPU and memory requests and limits. Zelkor never uses --create-namespace or kubectl in deployment pipelines.' },
      { q: 'What is the latency overhead?', a: 'Envoy header injection and Valkey budget checks add sub-2ms p99. Synchronous ext_proc adds 5–40ms. SandboxWarmPool keeps pre-initialized runsc pods so assignment completes in tens of milliseconds.' },
      { q: 'Can we run completely air-gapped with self-hosted models?', a: 'Yes. Zero runtime phone-home. Mirror images and the Helm chart into Harbor/Artifactory/Quay and route exclusively to vLLM, TGI, Ollama, or NVIDIA NIM.' },
    ],
  },
}
