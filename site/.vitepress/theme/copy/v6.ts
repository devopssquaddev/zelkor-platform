import type { VariantCopy } from './types'

const helm = `helm upgrade --install zelkor-platform charts/zelkor-platform \\
  --namespace zelkor \\
  -f profiles/values-production.yaml \\
  -f profiles/values-gateway-greenfield.yaml \\
  --wait`

const sandboxYaml = `# charts/zelkor-platform/values.yaml (v2.3.2)
security:
  sandbox:
    enabled: true
    runtimeClass: gvisor
    nodes:
      selector:
        zelkor.io/gvisor-ready: "true"

workspace:
  tools:
    sandboxMCP:
      enabled: true
      runtimeClassName: gvisor
      warmPool:
        replicas: 3
      workerImage:
        repository: ghcr.io/devopssquaddev/zelkor-sandbox-worker
        tag: "2.3.2"
      worker:
        resources:
          requests:
            cpu: 50m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi`

const gatewayYaml = `# charts/zelkor-platform/values.yaml (v2.3.2)
workspace:
  models:
    rateLimit:
      enabled: true
      requestsPerMinute: 50
    providers:
      openai:
        apiKey: "sk-..."
        models: ["*"]
      anthropic:
        apiKey: "sk-ant-..."
        models: ["*"]
  policies:
    nemo:
      enabled: true
      intercept:
        enabled: true
      defaultConfigId: content_safety
      image:
        repository: ghcr.io/devopssquaddev/zelkor-guardrails
        tag: "2.3.2"
      resources:
        requests:
          cpu: 100m
          memory: 256Mi
        limits:
          cpu: 500m
          memory: 1Gi`

const mcpYaml = `# charts/zelkor-platform/values.yaml (v2.3.2)
workload:
  agents:
    mcpInject:
      enabled: true

workspace:
  tools:
    enabled: true
    image:
      repository: ghcr.io/devopssquaddev/zelkor-mcp
      tag: "2.3.2"
    postgresMCP:
      enabled: true
      resources:
        requests: { cpu: 50m, memory: 64Mi }
        limits: { cpu: 500m, memory: 256Mi }
    qdrantMCP:
      enabled: true
      collection: documents
    objectMCP:
      enabled: true
      allowDelete: false
      maxReadBytes: 262144
      maxWriteBytes: 262144
    extraBackends:
      - name: tavily
        fqdn:
          hostname: mcp.tavily.com
          port: 443
        path: /mcp
        apiKey:
          secretRef:
            name: tavily-mcp-key`

const tenancyYaml = `# charts/zelkor-platform/values.yaml (v2.3.2)
platform:
  tenants:
    jwt:
      issuer: "https://idp.enterprise.internal"
      audiences:
        - "zelkor"
      jwksConfigMap: "zelkor-tenant-jwks"
      tenantClaims:
        - tenant_id
        - org_id
        - sub`

const observabilityYaml = `# charts/zelkor-platform/values.yaml (v2.3.2)
platform:
  telemetry:
    level: INFO
    format: json
    nemoOtel:
      enabled: true
      captureContent: false
    langfuse:
      enabled: true
      image:
        repository: langfuse/langfuse
        tag: "4.50.0"
      surfaces:
        evaluators:
          seedCode: true
          sampling: 0.1
observability:
  serviceMonitor:
    enabled: true
    interval: 30s`

const networkYaml = `# charts/zelkor-platform/values.yaml (v2.3.2)
platform:
  isolation:
    agentNamespaces: true

security:
  networkPolicies:
    enabled: true

gateway:
  hosts:
    agents: "agents.example.com"
    langfuse: "langfuse.example.com"
    mcp: ""
    nemo: ""`

export const v6: VariantCopy = {
  id: 6,
  name: 'Emerald Defense',
  short: '6 · Emerald',
  announcement: {
    badge: 'Live demo scenarios',
    text: '5 reproducible security proofs in Zelkor 2.3.2: Zero upstream API keys in agent pods • gVisor (runsc) MCP code sandbox • Fail-closed JWT tenant isolation • HTTP 429 RPM circuit breaker',
    linkLabel: 'Explore the 5 Proofs',
    href: '/#proofs',
  },
  brandSub: 'v2.3.2',
  navCta: { label: 'Book Architecture Review', href: '/contact' },
  productsNav: [
    { slug: 'sandbox', title: 'Code Sandbox', blurb: 'Isolated runsc gVisor warm pool over MCP' },
    { slug: 'gateway', title: 'AI Gateway', blurb: 'Envoy AI Gateway, credential custody, RPM limits & NeMo Guardrails' },
    { slug: 'mcp', title: 'MCP Tool Gateway', blurb: 'Single MCP_URL router for native & external MCP servers' },
    { slug: 'tenancy', title: 'Multi-Tenant Auth', blurb: 'Front-door JWT verification & identity-bound data scopes' },
    { slug: 'observability', title: 'Observability', blurb: 'Zero-SDK OpenTelemetry traces & Langfuse v4 evaluators' },
    { slug: 'network', title: 'Network Isolation', blurb: 'Kubernetes NetworkPolicy egress lockdown & gateway topologies' },
  ],
  solutionsNav: [
    { slug: 'financial-services', title: 'Financial Services', blurb: 'Quantitative and advisory agents under strict egress, key custody, and audit controls.' },
    { slug: 'healthcare', title: 'Healthcare & Life Sciences', blurb: 'Clinical and research agents inside tenant, network, and redaction boundaries.' },
    { slug: 'b2b-saas', title: 'Multi-Tenant B2B SaaS', blurb: 'One agent deployment, thousands of customer tenants, zero cross-tenant tool calls.' },
    { slug: 'platform-engineering', title: 'Platform Engineering', blurb: 'One Helm chart, explicit resource limits, standard Kubernetes primitives.' },
  ],
  home: {
    eyebrow: 'Kubernetes runtime for LangGraph, LangChain & Deep Agents · Zelkor 2.3.2',
    h1: 'Ship agents, not cluster breaches.',
    subtitle:
      'Bring the LangGraph, LangChain, or Deep Agents application you already wrote. Zelkor runs it on Kubernetes behind Envoy Gateway with zero upstream LLM keys in agent pods, routes untrusted Python to a dedicated gVisor (runsc) worker pool over MCP, enforces JWT tenant identity across Postgres, Qdrant, and S3, and records every hop in self-hosted Langfuse v4.',
    primaryCta: { label: 'Deploy Quickstart (CE)', href: '/docs/quickstart' },
    secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
    githubCta: { label: 'View Helm Chart on GitHub (v2.3.2) →', href: '#github' },
    install: helm,
    marqueeLabel: 'Verified on Zelkor 2.3.2',
    marquee: [
      'Envoy Gateway + Envoy AI Gateway',
      'gVisor (runsc) sandbox workers',
      'NVIDIA NeMo Guardrails (/v1)',
      'Unified MCP Tool Gateway',
      'Fail-closed JWT tenancy',
      'Self-hosted Langfuse v4 (4.50.0) + OTel',
      'Kubernetes NetworkPolicy lockdown',
    ],
    bridgeKicker: 'Prompt filters are probabilistic.',
    bridgeHeading: 'Kernel, network, and credential boundaries are deterministic.',
    bridge:
      'System prompts cannot stop an injected tool call from reading /proc/self/environ, dialing an external IP, or passing another customer’s tenant_id. Zelkor moves every security invariant out of the prompt and into the Kubernetes infrastructure layer surrounding your agent pod.',
    tabsHeadline: '4-tab interactive architecture walkthrough',
    tabs: [
      {
        id: 'sandbox',
        label: 'Sandbox',
        headline: 'Untrusted Python runs in gVisor workers, never in the agent pod',
        copy: 'Your agent pod runs on the standard container runtime with your graph code and dependencies intact. When the agent calls sandbox__execute_python, the request travels over MCP (http://zelkor-mcp:8010/mcp) to zelkor-sandbox-worker:2.3.2 pods running under runtimeClassName: gvisor (runsc).',
        points: [
          'Warm Pool Isolation: warmPool.replicas: 3 pre-warmed gVisor workers execute arbitrary Python inside a user-space kernel boundary.',
          'No Direct Pod-to-Worker Path: Agent pods have no SANDBOX_WORKER_URLS environment variable and are blocked by Kubernetes NetworkPolicy from reaching worker port :8081 directly.',
          'Authenticated Worker Execution: Worker /run requires an internal worker token (failClosed: true).',
        ],
        lang: 'yaml',
        code: sandboxYaml,
      },
      {
        id: 'gateway',
        label: 'Gateway',
        headline: 'Zero upstream provider keys in agent pods',
        copy: 'Agent pods never hold sk-ant-* or sk-proj-* credentials. They receive only a cluster-local consumer token (OPENAI_API_KEY) and OPENAI_BASE_URL pointing to Envoy AI Gateway (/v1).',
        points: [
          'Centralized Secret Custody: Upstream credentials for OpenAI, Anthropic, Gemini, AWS Bedrock, Google Vertex, Azure OpenAI, Cohere, Ollama, vLLM, and openaiCompat live in Kubernetes Secrets mounted only by the gateway.',
          'Deterministic Request Cap: workspace.models.rateLimit.requestsPerMinute: 50 enforces a global RPM circuit breaker at /v1—request 51 in a 60-second window returns HTTP 429 Too Many Requests before reaching the upstream LLM.',
          'Inline NeMo Verification: When workspace.policies.nemo.enabled: true, /v1/chat/completions is inspected by zelkor-guardrails:2.3.2 (NVIDIA NeMo Guardrails with Colang and content/topic safety rails) in fail-closed mode.',
        ],
        lang: 'yaml',
        code: gatewayYaml,
      },
      {
        id: 'mcp',
        label: 'MCP & Tenants',
        headline: 'Cryptographic tenant context from front door to datastore',
        copy: 'Every /runs, /runs/wait, and /threads call is authenticated at the front door via JWT (platform.tenants.jwt). Unsigned tokens, alg: none, or missing tenant claims fail with HTTP 401/403—there is no fallback tenant.',
        points: [
          'Unified MCP Router (zelkor-mcp:2.3.2): Exposes a single MCP_URL supporting Mode A (direct MCP client) and Mode B (workload.agents.mcpInject.enabled: true startup binding).',
          'Tamper-Proof tools/call: Tenant identity is extracted exclusively from verified langgraph_auth_user headers. If a prompt-injected model passes a tenant_id tool argument, the MCP Gateway rejects the call.',
          'Per-Backend Enforcement: postgresMCP runs read-only queries after SET LOCAL app.current_tenant for Postgres RLS; qdrantMCP injects mandatory tenant_id payload filters; objectMCP prefixes S3/SeaweedFS keys by tenant with 256 KB read/write caps; extraBackends attaches K8s Secrets for external HTTPS MCP servers without leaking the caller’s Zelkor JWT.',
        ],
        lang: 'yaml',
        code: tenancyYaml,
      },
      {
        id: 'trace',
        label: 'Trace',
        headline: 'One run, one OpenTelemetry waterfall in self-hosted Langfuse v4',
        copy: 'Zelkor instruments the runtime automatically without requiring Langfuse or OpenTelemetry SDK code inside your agent graph.',
        points: [
          'Full-Stack Correlation: Joins the Aegra run root (zelkor-aegra:2.3.2), Envoy AI Gateway /v1 model calls, NeMo guardrails checks, and MCP tools/call spans under a single sessionId and run_id.',
          'Redacted by Default: captureContent: false ensures INFO+ logs and default traces never record Bearer tokens, upstream API keys, or sensitive prompt bodies.',
          '8 Automated Trace Evaluators: Self-hosted Langfuse 4.50.0 (seedCode: true) scores every run on zelkor-mcp-prefix, zelkor-tenant-userid, zelkor-tool-repeat, zelkor-sandbox-clean, zelkor-step-budget (≤25 tool calls), zelkor-tool-names, zelkor-refusal-present, and zelkor-tool-succeeded.',
        ],
        lang: 'yaml',
        code: observabilityYaml,
      },
    ],
    stepsHeadline: 'From existing graph to hardened production',
    stepsSub: '3-step workflow',
    steps: [
      {
        title: 'Wrap Any Agent',
        body: 'Package your existing LangGraph, LangChain, or Deep Agents graph with the Aegra runtime (ghcr.io/devopssquaddev/zelkor-aegra:2.3.2 or zelkor-aegra-deep:2.3.2). Expose standard Agent Protocol endpoints (/runs, /runs/wait, /threads) routed by Envoy Gateway via the X-Graph-ID header—zero rewrites to your graph state machine.',
      },
      {
        title: 'Lock Every Door',
        body: 'Deploy charts/zelkor-platform (2.3.2) via helm upgrade --install into your pre-created namespace. Enable security.networkPolicies.enabled: true, bind workload.agents.mcpInject.enabled: true, point /v1 to Envoy AI Gateway, and offload sandbox__execute_python to the gvisor warm pool.',
      },
      {
        title: 'Scale Across Teams',
        body: 'Isolate agent workloads into dedicated namespaces labeled zelkor.io/namespace-role: agent (platform.isolation.agentNamespaces: true), enforce container resources.requests and resources.limits on every container and initContainer for OpenShift/K8s ResourceQuota compliance, and audit every run in self-hosted Langfuse v4.',
      },
    ],
    proofsHeadline: '5 live proof scenarios',
    proofsSub: 'Reproducible on Zelkor 2.3.2',
    proofs: [
      {
        title: 'Proof 1: The Vanishing Key',
        scenario: 'An adversarial prompt tricks the agent into inspecting os.environ and /proc/self/environ to exfiltrate OPENAI_API_KEY or ANTHROPIC_API_KEY.',
        control: 'The agent pod contains zero upstream provider keys—only a cluster-local consumer token scoped to Envoy AI Gateway (http://zelkor-ai-gateway/v1). Upstream provider secrets reside exclusively in gateway-mounted Kubernetes Secrets, and Kubernetes NetworkPolicy blocks the agent pod from dialing api.openai.com or any external IP.',
        result: 'No upstream key exists in the pod to steal, and the local token is useless outside the cluster network.',
      },
      {
        title: 'Proof 2: The Flight Recorder',
        scenario: 'Security and SRE teams need to prove exactly which model calls, guardrails checks, and MCP tools fired during an incident—without trusting developers to manually instrument every node.',
        control: 'OpenTelemetry auto-instrumentation correlates Aegra run spans, Envoy AI Gateway /v1 calls, NeMo verification spans, and MCP tools/call executions by sessionId and run_id inside self-hosted Langfuse 4.50.0 (ClickHouse + Postgres + SeaweedFS S3), while captureContent: false keeps secrets and raw prompts out of logs.',
        result: 'One run produces one unified waterfall trace automatically scored by 8 built-in zelkor-* trace evaluators.',
      },
      {
        title: 'Proof 3: The Shell Moved',
        scenario: 'Generated Python code invokes subprocess, probes the container filesystem, or attempts a kernel syscall exploit during sandbox__execute_python.',
        control: 'Code never executes inside the agent pod. The call traverses MCP to a dedicated zelkor-sandbox-worker:2.3.2 pod running under runtimeClassName: gvisor (runsc) in a 3-replica warm pool (warmPool.replicas: 3), authenticated by an internal worker token (failClosed) with zero direct network path from the agent pod to worker port :8081.',
        result: 'Syscalls are intercepted by the runsc user-space kernel; the agent pod’s memory, service account, and filesystem are never exposed.',
      },
      {
        title: 'Proof 4: Two Desks, One Graph',
        scenario: 'Tenant A’s session is prompt-injected into calling qdrant__search_documents or postgres__query with {"tenant_id": "tenant-b"} to read another customer’s records.',
        control: 'Front-door JWT verification (platform.tenants.jwt) validates issuer, audience, and JWKS signature, rejecting unsigned or alg: none tokens. On MCP tools/call, tenant identity is derived solely from verified langgraph_auth_user headers—client or model-supplied tenant_id arguments fail closed. Qdrant filters are forcibly injected, Object MCP keys are tenant-prefixed, and Postgres transactions execute SET LOCAL app.current_tenant for customer RLS enforcement.',
        result: 'The forged tenant_id argument is rejected before reaching the datastore, and cross-tenant rows remain unreachable.',
      },
      {
        title: 'Proof 5: Loop Dies at the Door',
        scenario: 'A recursive reasoning loop fires hundreds of /v1/chat/completions requests per minute, threatening upstream LLM rate limits and runaway API spend.',
        control: 'Envoy AI Gateway enforces workspace.models.rateLimit.requestsPerMinute: 50 at the /v1 ingress boundary, while Langfuse’s zelkor-step-budget evaluator flags runs exceeding 25 tool calls and zelkor-tool-repeat detects repetitive tool loops.',
        result: 'Call 51 within the minute immediately receives HTTP 429 Too Many Requests at the cluster gateway without invoking the upstream LLM provider.',
      },
    ],
    personasHeadline: 'Built for 3 core personas',
    personas: [
      {
        title: 'CISOs & Security Architects',
        role: 'Verifiable Kubernetes controls',
        body: 'Replace trust in prompt engineering with verifiable Kubernetes controls: runsc gVisor isolation for code execution, zero upstream credentials in workload pods, fail-closed NeMo Guardrails on /v1/chat/completions, default-deny egress NetworkPolicy, and cryptographic JWT tenant propagation.',
        points: [
          'runsc gVisor isolation for code execution',
          'Zero upstream credentials in workload pods',
          'Fail-closed NeMo Guardrails on /v1/chat/completions',
          'Default-deny egress NetworkPolicy',
          'Cryptographic JWT tenant propagation',
        ],
      },
      {
        title: 'Platform Engineering Directors',
        role: 'One Helm chart',
        body: 'Deploy a single Helm chart (charts/zelkor-platform 2.3.2) using helm upgrade --install --namespace "$NS" --wait. Support greenfield, layered, or shared Envoy Gateway topologies, enforce namespace isolation (zelkor.io/namespace-role: agent), and satisfy strict ResourceQuota / LimitRange policies with explicit resources.requests and resources.limits on every container and initContainer.',
        points: [
          'helm upgrade --install --namespace "$NS" --wait',
          'greenfield, layered, or shared Envoy Gateway topologies',
          'zelkor.io/namespace-role: agent isolation',
          'Explicit resources.requests and resources.limits',
        ],
      },
      {
        title: 'AI & Agent Developers',
        role: 'Keep writing standard graphs',
        body: 'Keep writing standard Python graphs with LangGraph, LangChain, and Deep Agents. Deploy on zelkor-aegra:2.3.2 or zelkor-aegra-deep:2.3.2, auto-bind MCP tools at startup with mcpInject.enabled: true, and get full Langfuse v4 waterfall traces without adding a single line of OpenTelemetry boilerplate.',
        points: [
          'LangGraph, LangChain, and Deep Agents',
          'zelkor-aegra:2.3.2 or zelkor-aegra-deep:2.3.2',
          'mcpInject.enabled: true startup binding',
          'Langfuse v4 traces with zero OTel boilerplate',
        ],
      },
    ],
    finalHeadline: 'Ready to put deterministic boundaries around your agents?',
    finalSub: 'Install Zelkor Community Edition (2.3.2) on your Kubernetes cluster in minutes, or walk through the 5 live security proofs with our architecture team.',
    finalPrimary: { label: 'Install Zelkor 2.3.2 (CE)', href: '/docs/quickstart' },
    finalSecondary: { label: 'Book Architecture Review', href: '/contact' },
  },
  products: {
    sandbox: {
      slug: 'sandbox',
      eyebrow: 'Product · Code Sandbox (zelkor-sandbox-worker:2.3.2)',
      h1: 'Execute untrusted Python in gVisor workers—never inside your agent pod.',
      subtitle:
        'Zelkor keeps your LangGraph, LangChain, or Deep Agents pod on the standard container runtime while routing every sandbox__execute_python call over MCP to a dedicated warm pool of runtimeClassName: gvisor (runsc) worker pods.',
      primaryCta: { label: 'Deploy Sandbox Pool', href: '/docs/quickstart' },
      secondaryCta: { label: 'Review Sandbox Architecture', href: '/docs' },
      overviewTitle: 'Why static containers fail',
      overview:
        'Running exec() or subprocess inside the same container that holds your agent runtime, graph state, and cluster network identity means a single prompt injection gives attacker-controlled Python full access to the pod’s filesystem, environment variables, and service account token. Even worse, running a separate container on the default runc runtime still shares the host Linux kernel syscall table with every neighboring workload on the node.',
      capabilities: [
        {
          title: 'Dedicated runsc gVisor warm pool',
          text: 'zelkor-sandbox-worker:2.3.2 pods run with runtimeClassName: gvisor, intercepting application syscalls in a user-space kernel. Pre-warmed replicas (warmPool.replicas: 3) eliminate cold-start latency for sandbox__execute_python.',
        },
        {
          title: 'MCP-mediated execution (sandboxMCP)',
          text: 'Agents never invoke worker pods directly. Code execution is exposed as the sandbox__execute_python tool on the unified MCP Gateway (zelkor-mcp:2.3.2), keeping execution decoupled from the agent runtime container.',
        },
        {
          title: 'Fail-closed internal worker token & network block',
          text: 'Agent pods do not receive SANDBOX_WORKER_URLS and are blocked by Kubernetes NetworkPolicy from connecting to worker port :8081. The worker /run endpoint requires an internal worker token (failClosed: true) held only by the MCP Gateway.',
        },
        {
          title: 'Automated node provisioning & detection',
          text: 'Provision gVisor nodes via --install-gvisor with node selector labels (zelkor.io/gvisor-ready=true), or leverage automatic runtime detection on GKE Sandbox and Talos Linux clusters.',
        },
      ],
      snippetTitle: 'Verified configuration (charts/zelkor-platform/values.yaml v2.3.2)',
      snippetLang: 'yaml',
      snippet: sandboxYaml,
      bottomHeadline: 'Isolate agent code execution without breaking agent dependencies.',
      bottomPrimary: { label: 'Deploy Zelkor 2.3.2', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    gateway: {
      slug: 'gateway',
      eyebrow: 'Product · AI Gateway (Envoy AI Gateway + NeMo Guardrails 2.3.2)',
      h1: 'Zero upstream LLM keys in agent pods. Deterministic rate limits and prompt rails at /v1.',
      subtitle:
        'Built on Envoy Gateway and Envoy AI Gateway, Zelkor centralizes upstream provider credentials inside gateway Kubernetes Secrets, caps request velocity with a deterministic RPM circuit breaker, and verifies /v1/chat/completions through NVIDIA NeMo Guardrails.',
      primaryCta: { label: 'Configure AI Gateway', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why static containers fail',
      overview:
        'Injecting OPENAI_API_KEY or ANTHROPIC_API_KEY directly into agent deployment manifests scatters high-privilege billing credentials across dozens of pods. If an agent is compromised or enters an infinite retry loop, it can exfiltrate the raw key or burn thousands of calls directly against api.openai.com with no cluster-side circuit breaker or central policy check.',
      capabilities: [
        {
          title: 'Brokered upstream credential custody',
          text: 'Agent pods receive only a cluster-local consumer key (OPENAI_API_KEY) and OPENAI_BASE_URL pointing to /v1. Real upstream keys for OpenAI, Anthropic, Gemini, AWS Bedrock, Google Vertex, Azure OpenAI, Cohere, Ollama, vLLM, and openaiCompat stay in Kubernetes Secrets mounted exclusively on the gateway.',
        },
        {
          title: 'Global RPM circuit breaker (HTTP 429)',
          text: 'Configure workspace.models.rateLimit.requestsPerMinute: 50 on /v1. When aggregate traffic hits request 51 within a minute, Envoy AI Gateway immediately returns HTTP 429 Too Many Requests without forwarding the request to the upstream LLM provider.',
        },
        {
          title: 'Fail-closed NVIDIA NeMo Guardrails (zelkor-guardrails:2.3.2)',
          text: 'Enable workspace.policies.nemo.enabled: true to route /v1/chat/completions through zelkor-guardrails:2.3.2. Enforces Colang rails and content/topic safety checks before prompts reach the model or responses return to the agent, operating fail-closed when enabled.',
        },
        {
          title: 'Agent Protocol routing via X-Graph-ID',
          text: 'Envoy Gateway fronts both /v1 model traffic and Aegra Agent Protocol endpoints (/runs, /runs/wait, /threads), routing client requests to the target LangGraph, LangChain, or Deep Agents deployment via the X-Graph-ID header.',
        },
      ],
      snippetTitle: 'Verified configuration (charts/zelkor-platform/values.yaml v2.3.2)',
      snippetLang: 'yaml',
      snippet: gatewayYaml,
      bottomHeadline: 'Remove upstream API keys from every agent pod today.',
      bottomPrimary: { label: 'Deploy Zelkor 2.3.2', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    mcp: {
      slug: 'mcp',
      eyebrow: 'Product · Unified MCP Gateway (zelkor-mcp:2.3.2)',
      h1: 'One MCP_URL for every native datastore and external tool server.',
      subtitle:
        'zelkor-mcp:2.3.2 gives every agent a single governed endpoint for Postgres, Qdrant, S3/SeaweedFS Object storage, the gVisor code sandbox, and external MCP backends—injecting backend secrets at the gateway and never forwarding your caller’s Zelkor JWT to third-party SaaS.',
      primaryCta: { label: 'Explore MCP Configuration', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why static containers fail',
      overview:
        'When agents connect directly to databases, vector stores, and third-party SaaS APIs, every agent pod requires database credentials, S3 keys, and SaaS tokens in its environment, plus broad network egress. Worse, nothing stops a hallucinating or prompt-injected model from running destructive SQL (DROP, UPDATE) or leaking internal session JWTs to an external tool endpoint.',
      capabilities: [
        {
          title: 'Mode A (direct client) & Mode B (mcpInject startup binding)',
          text: 'Connect custom MCP clients directly to MCP_URL (Mode A), or set workload.agents.mcpInject.enabled: true (Mode B) so Aegra dynamically discovers and binds allowed MCP tools into your LangGraph, LangChain, or Deep Agents workload at startup.',
        },
        {
          title: 'Built-in governed native servers',
          text: 'postgresMCP exposes postgres__query, postgres__list_tables, and postgres__get_schema with read-only query enforcement and per-transaction SET LOCAL app.current_tenant. qdrantMCP exposes qdrant__search_documents and qdrant__upsert_document with mandatory tenant_id payload filter injection. objectMCP exposes object__list, object__stat, object__read_text, object__write_text, object__copy, and opt-in object__delete on S3/SeaweedFS with 256 KB read/write payload caps. sandboxMCP exposes sandbox__execute_python backed by the gVisor worker warm pool.',
        },
        {
          title: 'External & cluster MCP backends (extraBackends)',
          text: 'Register in-cluster ClusterIP MCP services or external HTTPS FQDNs (such as mcp.tavily.com) under workspace.tools.extraBackends. The gateway attaches backend API keys from Kubernetes Secrets, forwards configured headers, and enforces reserved tool prefix rules (postgres__, qdrant__, sandbox__, object__ cannot be spoofed).',
        },
        {
          title: 'Zero caller JWT leakage to external SaaS',
          text: 'When proxying tools/call to an external HTTPS backend in extraBackends, zelkor-mcp:2.3.2 strips the caller’s internal Zelkor JWT (langgraph_auth_user) and authenticates using only the backend’s configured Secret.',
        },
      ],
      snippetTitle: 'Verified configuration (charts/zelkor-platform/values.yaml v2.3.2)',
      snippetLang: 'yaml',
      snippet: mcpYaml,
      bottomHeadline: 'Govern every database query, vector search, and SaaS tool call behind one MCP endpoint.',
      bottomPrimary: { label: 'Deploy Zelkor 2.3.2', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    tenancy: {
      slug: 'tenancy',
      eyebrow: 'Product · Multi-tenant auth & data isolation',
      h1: 'Fail-closed JWT tenant isolation from /runs to Postgres RLS, Qdrant, and S3.',
      subtitle:
        'Zelkor verifies caller JWTs at the front door, isolates thread and run state in Aegra’s TenantAuth, derives MCP tool tenancy exclusively from verified langgraph_auth_user headers, and binds every database, vector, and object operation to that cryptographic tenant identity.',
      primaryCta: { label: 'Review Tenancy Controls', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why static containers fail',
      overview:
        'Passing tenant_id inside system prompts or trusting tool call arguments generated by the LLM means any prompt injection can instruct the model to request {"tenant_id": "competitor-corp"}. Without cryptographic propagation from the HTTP ingress header down to the datastore transaction, one shared agent graph becomes a cross-tenant data breach waiting to happen.',
      capabilities: [
        {
          title: 'Strict front-door JWT verification (platform.tenants.jwt)',
          text: 'Validates issuer, audiences, and signatures via jwksConfigMap, remoteJwksUri, or localSigning. Unsigned requests, tokens with alg: none, or tokens missing the required tenant claim are rejected immediately with HTTP 401/403—there is never a default fallback tenant.',
        },
        {
          title: 'Isolated thread & run state (TenantAuth)',
          text: 'Inside zelkor-aegra:2.3.2 and zelkor-aegra-deep:2.3.2, TenantAuth scopes every /threads, /runs, and /runs/wait operation to the authenticated tenant_id. Tenant A cannot list, resume, or inspect Tenant B’s conversation threads or checkpoint state.',
        },
        {
          title: 'Fail-closed MCP tools/call identity propagation',
          text: 'When an agent invokes an MCP tool, zelkor-mcp:2.3.2 reads the tenant identity exclusively from the verified langgraph_auth_user header. If the model or client attempts to supply or override a tenant_id argument in the tool payload, the call fails closed.',
        },
        {
          title: 'Datastore-native tenant enforcement',
          text: 'postgresMCP executes SET LOCAL app.current_tenant = \'<tenant_id>\' inside every read-only transaction so Postgres Row-Level Security (RLS) policies enforce row-level isolation. qdrantMCP overwrites/injects a mandatory tenant_id payload filter on every qdrant__search_documents and qdrant__upsert_document call. objectMCP enforces tenant-prefixed keys (<tenant_id>/...) on every S3/SeaweedFS read, write, list, stat, copy, and delete operation.',
        },
      ],
      snippetTitle: 'Verified configuration (charts/zelkor-platform/values.yaml v2.3.2)',
      snippetLang: 'yaml',
      snippet: tenancyYaml,
      bottomHeadline: 'Serve thousands of enterprise tenants from one agent graph without cross-tenant leakage.',
      bottomPrimary: { label: 'Deploy Zelkor 2.3.2', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    observability: {
      slug: 'observability',
      eyebrow: 'Product · Observability (self-hosted Langfuse 4.50.0 + OTel)',
      h1: 'One run, one waterfall trace—with zero tracing SDK in your agent code.',
      subtitle:
        'Zelkor ships with self-hosted Langfuse v4 (4.50.0) backed by ClickHouse, Postgres, and SeaweedFS S3. OpenTelemetry joins Aegra runs, Envoy AI Gateway /v1 calls, NeMo Guardrails checks, and MCP tools/call spans into a single trace while keeping secrets and prompt bodies out of default logs.',
      primaryCta: { label: 'Explore Trace Evaluators', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why static containers fail',
      overview:
        'Standard container stdout logs fragment a single agent run across uncorrelated pods, dump sensitive Bearer tokens or customer prompts into cluster log aggregators, and break the moment an engineer forgets to wrap a new LangGraph node in a proprietary tracing decorator.',
      capabilities: [
        {
          title: 'Zero-SDK OpenTelemetry correlation',
          text: 'Without adding Langfuse or OTel SDK imports to your agent code, Zelkor correlates the Aegra run root, Envoy AI Gateway /v1 model spans, NeMo guardrails checks, and MCP tools/call spans using shared sessionId and run_id context inside self-hosted Langfuse 4.50.0.',
        },
        {
          title: 'Redacted-by-default telemetry (captureContent: false)',
          text: 'Out of the box, captureContent: false ensures that INFO+ container logs and default trace metadata never leak Authorization: Bearer tokens, upstream LLM API keys, or raw customer prompt bodies.',
        },
        {
          title: '8 built-in Langfuse trace evaluators (seedCode: true)',
          text: 'Zelkor automatically seeds 8 trace evaluators into Langfuse v4: zelkor-mcp-prefix, zelkor-tenant-userid, zelkor-tool-repeat, zelkor-sandbox-clean, zelkor-step-budget (≤25 tool calls), zelkor-tool-names, zelkor-refusal-present, and zelkor-tool-succeeded.',
        },
        {
          title: 'Self-hosted storage stack & Prometheus ServiceMonitor',
          text: 'All trace data stays inside your cluster across Langfuse 4.50.0, ClickHouse, Postgres, and SeaweedFS S3—plus an optional Prometheus ServiceMonitor for scraping gateway and runtime metrics into your existing cluster monitoring stack.',
        },
      ],
      snippetTitle: 'Verified configuration (charts/zelkor-platform/values.yaml v2.3.2)',
      snippetLang: 'yaml',
      snippet: observabilityYaml,
      bottomHeadline: 'Get complete flight-recorder visibility across every agent run inside your own cluster.',
      bottomPrimary: { label: 'Deploy Zelkor 2.3.2', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    network: {
      slug: 'network',
      eyebrow: 'Product · Kubernetes NetworkPolicy & gateway topologies',
      h1: 'Default-deny agent egress. Zero public routes to internal tools or datastores.',
      subtitle:
        'Zelkor uses standard Kubernetes NetworkPolicy (security.networkPolicies.enabled: true) to block agent pods from dialing the public internet, Qdrant, sandbox workers (:8081), or external MCP backends directly—allowing traffic only to the AI Gateway (/v1), MCP Gateway, and checkpointer datastores.',
      primaryCta: { label: 'Review Network Topologies', href: '/docs' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why static containers fail',
      overview:
        'By default, Kubernetes allows every pod in a cluster to open outbound TCP connections to any public IP address and any internal ClusterIP service across namespaces. If an agent pod is compromised via prompt injection or a malicious dependency, it can exfiltrate data directly to an attacker’s webhook or probe internal vector databases and sandbox workers on :8081.',
      capabilities: [
        {
          title: 'Egress lockdown via standard Kubernetes NetworkPolicy',
          text: 'With security.networkPolicies.enabled: true, agent pods are blocked from reaching the public internet, Qdrant, sandbox worker port :8081, and extraBackends directly. Egress is restricted strictly to Envoy AI Gateway (/v1), the MCP Gateway (zelkor-mcp), and the Aegra checkpointer datastore.',
        },
        {
          title: 'Namespace role isolation (zelkor.io/namespace-role: agent)',
          text: 'When platform.isolation.agentNamespaces: true is set, network policies restrict checkpointer datastore ingress exclusively to pods running in namespaces labeled zelkor.io/namespace-role: agent, preventing lateral movement from unrelated cluster workloads.',
        },
        {
          title: 'Zero public HTTPRoute exposure for internal services',
          text: 'Only the authenticated Envoy Gateway front door is exposed. Internal services—including zelkor-mcp, zelkor-guardrails (NeMo), Postgres, Qdrant, SeaweedFS, sandbox workers, and individual agent ClusterIP services—never receive public HTTPRoute bindings.',
        },
        {
          title: 'Flexible Envoy topologies & strict ResourceQuota compliance',
          text: 'Deploy using greenfield (Envoy Gateway acts as the LoadBalancer), layered (behind an existing NGINX, Traefik, or ALB Ingress), or shared (attaching HTTPRoute to an existing cluster Gateway). Every container and initContainer defines explicit resources.requests and resources.limits (cpu and memory), and deployment uses helm upgrade --install --namespace "$NS" --wait.',
        },
      ],
      snippetTitle: 'Verified configuration (charts/zelkor-platform/values.yaml v2.3.2)',
      snippetLang: 'yaml',
      snippet: networkYaml,
      bottomHeadline: 'Lock down agent network paths with standard Kubernetes primitives that work on every CNI.',
      bottomPrimary: { label: 'Deploy Zelkor 2.3.2', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
  },
  solutions: {
    'financial-services': {
      slug: 'financial-services',
      eyebrow: 'Solutions · Financial services & banking',
      h1: 'Run quantitative & advisory agents under strict egress, key custody, and audit controls.',
      subtitle:
        'Deploy LangGraph, LangChain, and Deep Agents workloads on Kubernetes with zero upstream LLM keys in agent pods, runsc gVisor isolation for Python analytics, read-only RLS-scoped Postgres queries, and full trace retention in self-hosted Langfuse v4.',
      primaryCta: { label: 'Book Financial Architecture Review', href: '/contact' },
      secondaryCta: { label: 'Inspect Compliance Mapping', href: '#mapping' },
      risks: [
        { title: 'Unbrokered upstream API keys', text: 'Developers embedding OpenAI or Bedrock credentials in pod specs risk credential exfiltration. Zelkor fix: keys stay in Envoy AI Gateway Kubernetes Secrets; pods hold only a local /v1 consumer token.' },
        { title: 'Untrusted Python execution in quantitative tools', text: 'Portfolio calculation scripts executed via exec() in the agent pod can read service account tokens. Zelkor fix: sandbox__execute_python runs over MCP in a 3-replica runtimeClassName: gvisor (runsc) worker pool.' },
        { title: 'Cross-client portfolio leakage', text: 'Shared advisory graphs queried by multiple wealth desks risk returning another client’s holdings. Zelkor fix: front-door JWT verification + SET LOCAL app.current_tenant on Postgres RLS and forced tenant_id filters in Qdrant.' },
        { title: 'Destructive SQL generation', text: 'Hallucinated UPDATE or DELETE statements against core financial tables. Zelkor fix: postgresMCP enforces read-only queries (postgres__query, postgres__list_tables, postgres__get_schema).' },
        { title: 'Unbounded model loop spend', text: 'Recursive research loops firing hundreds of requests per minute. Zelkor fix: Envoy AI Gateway enforces requestsPerMinute: 50 (HTTP 429 on call 51) and Langfuse zelkor-step-budget flags runs over 25 tool calls.' },
        { title: 'Raw PII/prompt leakage in cluster logs', text: 'Standard stdout logging captures sensitive client account prompts. Zelkor fix: captureContent: false keeps Bearer tokens, API keys, and prompt bodies out of INFO+ logs and default traces.' },
      ],
      mappingTitle: 'Compliance & control mapping',
      mappingLabels: {
        framework: 'Regulatory / enterprise requirement',
        requirement: 'Zelkor 2.3.2 shipped technical control',
        control: 'Verification mechanism',
      },
      mapping: [
        { framework: 'DORA / PCI-DSS network segmentation', requirement: 'Kubernetes NetworkPolicy (security.networkPolicies.enabled: true) blocks agent egress to public internet, :8081 workers, and raw datastores.', control: 'Proof 1 & Proof 3 network block verification' },
        { framework: 'SOC 2 CC6.1 credential custody & access', requirement: 'Zero upstream keys in agent pods; front-door JWT validation (platform.tenants.jwt) rejects unsigned / alg: none tokens with HTTP 401/403.', control: 'Pod env inspection & JWT negative test suite' },
        { framework: 'Multi-desk data segregation (Chinese Wall)', requirement: 'langgraph_auth_user header propagation to MCP; SET LOCAL app.current_tenant for Postgres RLS; forced Qdrant tenant_id filters; tenant-prefixed Object keys.', control: 'Proof 4: Two Desks, One Graph' },
        { framework: 'Model risk governance & audit trail (SR 11-7)', requirement: 'Self-hosted Langfuse 4.50.0 (ClickHouse + Postgres + SeaweedFS) with 8 seeded evaluators (seedCode: true) and NeMo Guardrails (zelkor-guardrails:2.3.2).', control: 'Proof 2: The Flight Recorder waterfall trace' },
      ],
      scenariosTitle: '3 financial services workflows',
      scenarios: [
        { title: 'Multi-desk institutional research agent', text: 'Serves equity research across isolated institutional desks using a single LangGraph deployment (zelkor-aegra:2.3.2), enforcing desk-level tenant isolation across Qdrant embeddings and Postgres RLS tables.' },
        { title: 'Sandboxed quantitative Python modeling', text: 'Executes agent-generated valuation and backtesting Python scripts inside the zelkor-sandbox-worker:2.3.2 gVisor warm pool (warmPool.replicas: 3) with zero access to the agent pod or external internet.' },
        { title: 'Guardrailed client advisory copilot', text: 'Routes every /v1/chat/completions call through fail-closed NVIDIA NeMo Guardrails (zelkor-guardrails:2.3.2) for topic/content safety and caps traffic at 50 RPM at the Envoy AI Gateway.' },
      ],
      bottomHeadline: 'Deploy auditable, air-tight financial agents on your own Kubernetes clusters.',
      bottomCta: { label: 'Book Financial Architecture Review', href: '/contact' },
      bottomSecondary: { label: 'View Helm Chart (v2.3.2)', href: '#github' },
    },
    healthcare: {
      slug: 'healthcare',
      eyebrow: 'Solutions · Healthcare & life sciences',
      h1: 'Keep clinical and research agents inside strict tenant, network, and redaction boundaries.',
      subtitle:
        'Run LangGraph, LangChain, and Deep Agents workloads with captureContent: false log hygiene, self-hosted Langfuse v4 observability that never leaves your cluster, fail-closed JWT tenant isolation, and gVisor-isolated bioinformatics Python execution.',
      primaryCta: { label: 'Book Healthcare Architecture Review', href: '/contact' },
      secondaryCta: { label: 'Review Isolation Architecture', href: '/products/network' },
      risks: [
        { title: 'PHI / prompt leakage into cluster log streams', text: 'Container logs accidentally recording patient context or Bearer tokens. Zelkor fix: captureContent: false by default prevents INFO+ logs and default traces from storing prompt bodies or credentials.' },
        { title: 'Third-party telemetry SaaS exposure', text: 'Sending agent execution traces to an external cloud observability vendor. Zelkor fix: Langfuse 4.50.0 runs entirely self-hosted inside your cluster on ClickHouse, Postgres, and SeaweedFS S3.' },
        { title: 'Cross-hospital / cross-study data bleed', text: 'Multi-institution clinical trial agents querying the wrong study cohort. Zelkor fix: fail-closed JWT verification binds langgraph_auth_user to Postgres SET LOCAL app.current_tenant, Qdrant tenant_id filters, and S3 key prefixes.' },
        { title: 'Unsafe execution of biostatistical Python', text: 'Agent-written statistical scripts running inside the main runtime pod. Zelkor fix: offloaded over MCP (sandbox__execute_python) to runtimeClassName: gvisor (runsc) worker pods.' },
        { title: 'Unverified clinical prompt trajectories', text: 'Unchecked prompt inputs or off-topic responses reaching clinical users. Zelkor fix: zelkor-guardrails:2.3.2 (NVIDIA NeMo Guardrails) enforces Colang and content/topic safety rails fail-closed on /v1/chat/completions.' },
        { title: 'Caller token leakage to external research tools', text: 'Forwarding internal hospital JWTs when calling external literature search MCP servers. Zelkor fix: extraBackends strips the caller’s Zelkor JWT and authenticates with dedicated Kubernetes Secrets.' },
      ],
      mappingTitle: 'Compliance & control mapping',
      mappingLabels: {
        framework: 'Healthcare security requirement',
        requirement: 'Zelkor 2.3.2 shipped technical control',
        control: 'Verification mechanism',
      },
      mapping: [
        { framework: 'Log & telemetry minimisation', requirement: 'platform.observability.langfuse.captureContent: false suppresses prompt bodies, API keys, and Bearer tokens in INFO+ logs and default traces.', control: 'Container log & Langfuse span inspection' },
        { framework: 'In-cluster audit residency', requirement: 'Self-hosted Langfuse 4.50.0 backed by in-cluster ClickHouse, Postgres, and SeaweedFS S3—zero external telemetry SaaS required.', control: 'Kubernetes NetworkPolicy & PVC audit' },
        { framework: 'Cohort & institution segregation', requirement: 'Front-door JWT validation + MCP langgraph_auth_user enforcement; client-supplied tenant_id arguments fail closed.', control: 'Proof 4: Two Desks, One Graph' },
        { framework: 'Bioinformatics compute isolation', requirement: 'zelkor-sandbox-worker:2.3.2 with runtimeClassName: gvisor (runsc) and internal worker token authentication (failClosed: true).', control: 'Proof 3: The Shell Moved' },
      ],
      scenariosTitle: '3 healthcare & life sciences workflows',
      scenarios: [
        { title: 'Multi-site clinical trial cohort assistant', text: 'Queries study metadata via read-only postgresMCP (SET LOCAL app.current_tenant for site RLS) and protocol documents via qdrantMCP without cross-site data leakage.' },
        { title: 'Sandboxed biostatistical Python analysis', text: 'Runs survival analysis and data normalization scripts via sandbox__execute_python inside the 3-replica gVisor worker warm pool while keeping the agent pod isolated.' },
        { title: 'Literature synthesis with governed external MCP', text: 'Connects to external research MCP endpoints via workspace.tools.extraBackends using gateway-injected K8s Secrets while never exposing internal clinician JWTs.' },
      ],
      bottomHeadline: 'Run clinical and research agents with self-hosted observability and deterministic isolation.',
      bottomCta: { label: 'Book Healthcare Architecture Review', href: '/contact' },
      bottomSecondary: { label: 'View Helm Chart (v2.3.2)', href: '#github' },
    },
    'b2b-saas': {
      slug: 'b2b-saas',
      eyebrow: 'Solutions · Multi-tenant B2B SaaS',
      h1: 'One agent deployment. Thousands of customer tenants. Zero cross-tenant tool calls.',
      subtitle:
        'Eliminate per-customer agent silos. Zelkor lets B2B SaaS teams serve every customer from shared LangGraph, LangChain, or Deep Agents deployments while enforcing cryptographic tenant boundaries across threads, Postgres RLS, Qdrant vectors, and S3 objects.',
      primaryCta: { label: 'Book SaaS Architecture Review', href: '/contact' },
      secondaryCta: { label: 'Explore Multi-Tenancy', href: '/products/tenancy' },
      risks: [
        { title: 'Prompt-injected tenant_id spoofing', text: 'A malicious user instructs your SaaS copilot to call tools with another customer’s tenant_id. Zelkor fix: zelkor-mcp:2.3.2 ignores and rejects model/client tenant_id arguments, reading identity solely from verified langgraph_auth_user headers.' },
        { title: 'Cross-tenant thread & checkpoint hijacking', text: 'Customer A guesses or enumerates thread IDs belonging to Customer B. Zelkor fix: Aegra’s TenantAuth scopes /threads, /runs, and /runs/wait state strictly to the JWT’s verified tenant claim.' },
        { title: 'Unfiltered vector search across customers', text: 'Shared RAG indexes returning chunks uploaded by another SaaS tenant. Zelkor fix: qdrantMCP forcibly injects a mandatory tenant_id payload filter on every qdrant__search_documents and qdrant__upsert_document call.' },
        { title: 'Shared object storage bucket traversal', text: 'Agents reading or overwriting files in another tenant’s S3 path. Zelkor fix: objectMCP enforces tenant-prefixed keys (<tenant_id>/...), 256 KB read/write caps, and opt-in-only delete (allowDelete: false by default).' },
        { title: 'Noisy-neighbor runaway tool loops', text: 'A buggy customer workflow triggers an endless agent loop that exhausts upstream LLM rate limits. Zelkor fix: global /v1 RPM cap (requestsPerMinute: 50 → HTTP 429) plus Langfuse zelkor-step-budget (≤25 calls) and zelkor-tool-repeat evaluators.' },
        { title: 'Unsigned or forged internal requests', text: 'Internal microservices calling agent endpoints without a valid tenant token. Zelkor fix: platform.tenants.jwt rejects unsigned tokens, alg: none, or missing tenant claims with HTTP 401/403—no default fallback tenant exists.' },
      ],
      mappingTitle: 'Compliance & control mapping',
      mappingLabels: {
        framework: 'B2B SaaS multi-tenancy requirement',
        requirement: 'Zelkor 2.3.2 shipped technical control',
        control: 'Verification mechanism',
      },
      mapping: [
        { framework: 'Ingress tenant authentication', requirement: 'platform.tenants.jwt validates issuer, audiences, and JWKS (jwksConfigMap, remoteJwksUri, or localSigning), failing closed on invalid tokens.', control: 'HTTP 401/403 on missing/invalid JWT' },
        { framework: 'Conversation & state isolation', requirement: 'Aegra TenantAuth isolates /threads and /runs checkpoint state per authenticated tenant_id.', control: 'Cross-tenant thread access test' },
        { framework: 'Database & vector row/payload isolation', requirement: 'postgresMCP sets SET LOCAL app.current_tenant for Postgres RLS; qdrantMCP forces tenant_id payload filters; objectMCP prefixes S3 keys.', control: 'Proof 4: Two Desks, One Graph' },
        { framework: 'Per-run quality & loop scoring', requirement: 'Langfuse 4.50.0 evaluators score zelkor-tenant-userid, zelkor-step-budget, zelkor-tool-repeat, and zelkor-tool-succeeded automatically.', control: 'Proof 2: The Flight Recorder' },
      ],
      scenariosTitle: '3 multi-tenant B2B SaaS workflows',
      scenarios: [
        { title: 'Customer-facing SaaS copilot', text: 'Authenticates customer JWTs at Envoy Gateway, routes to your graph via X-Graph-ID, and scopes every postgres__query and qdrant__search_documents call to that customer’s tenant ID.' },
        { title: 'Tenant-scoped document & artifact processing', text: 'Reads and writes customer text artifacts up to 256 KB in S3/SeaweedFS via objectMCP (object__read_text, object__write_text, object__list) under strict tenant key prefixes.' },
        { title: 'Dynamic tool injection across SaaS tiers', text: 'Uses workload.agents.mcpInject.enabled: true (Mode B) to bind native and extraBackends MCP tools into LangGraph or Deep Agents workloads at startup without hardcoding tool credentials in the app repo.' },
      ],
      bottomHeadline: 'Ship multi-tenant AI features faster with infrastructure-enforced tenant boundaries.',
      bottomCta: { label: 'Book SaaS Architecture Review', href: '/contact' },
      bottomSecondary: { label: 'View Helm Chart (v2.3.2)', href: '#github' },
    },
    'platform-engineering': {
      slug: 'platform-engineering',
      eyebrow: 'Solutions · Platform engineering & SRE',
      h1: 'One Helm chart. Explicit resource limits. Standard Kubernetes primitives.',
      subtitle:
        'Give application teams a self-service runtime for LangGraph, LangChain, and Deep Agents without violating cluster governance. Zelkor 2.3.2 installs exclusively via helm upgrade --install, sets resources.requests and resources.limits on every container and initContainer, and integrates cleanly with your existing Envoy Gateway and CNI.',
      primaryCta: { label: 'Inspect Helm Values (v2.3.2)', href: '#github' },
      secondaryCta: { label: 'Book Platform Architecture Review', href: '/contact' },
      risks: [
        { title: 'Pods rejected by ResourceQuota and LimitRange', text: 'Upstream AI charts frequently ship containers or initContainers without CPU/memory limits, failing deployment on enterprise Kubernetes and OpenShift clusters. Zelkor fix: every container and initContainer in charts/zelkor-platform renders explicit resources.requests and resources.limits.' },
        { title: 'Imperative manifest drift in CI pipelines', text: 'CI pipelines that scatter raw kubectl apply scripts or require cluster-admin namespace creation fail under least-privilege RBAC. Zelkor fix: pure Helm deployment into admin-provisioned namespaces (helm upgrade --install "$RELEASE" charts/zelkor-platform --namespace "$NS" --wait).' },
        { title: 'Gateway collisions on shared clusters', text: 'AI platforms that demand exclusive cluster-wide ingress controllers break existing platform routing. Zelkor fix: supports greenfield, layered, and shared Envoy Gateway topologies.' },
        { title: 'Sprawling internal HTTPRoute exposure', text: 'Accidental ingress exposure of vector stores, guardrails services, or MCP servers. Zelkor fix: zero public HTTPRoute objects for MCP, NeMo, datastores, or agent ClusterIP services.' },
        { title: 'Lateral movement into checkpointer datastores', text: 'Unrelated pods in shared clusters connecting to agent state databases. Zelkor fix: platform.isolation.agentNamespaces: true restricts checkpointer network access to namespaces labeled zelkor.io/namespace-role: agent.' },
        { title: 'CNI-specific lock-in for network isolation', text: 'Requiring proprietary eBPF CRDs just to block pod egress. Zelkor fix: uses standard Kubernetes NetworkPolicy (security.networkPolicies.enabled: true) portable across any compliant CNI, plus node label (zelkor.io/gvisor-ready=true) or GKE Sandbox / Talos auto-detection for gVisor workers.' },
      ],
      mappingTitle: 'Compliance & control mapping',
      mappingLabels: {
        framework: 'Platform engineering requirement',
        requirement: 'Zelkor 2.3.2 shipped technical control',
        control: 'Verification mechanism',
      },
      mapping: [
        { framework: 'GitOps & Helm-only delivery', requirement: 'Single versioned chart (charts/zelkor-platform 2.3.2); installed via helm upgrade --install --namespace "$NS" --wait into admin-provisioned namespaces.', control: 'CI pipeline lint & helm template check' },
        { framework: 'ResourceQuota / LimitRange compliance', requirement: 'Explicit resources.requests and resources.limits (cpu, memory) on all containers and initContainers across platform and workload templates.', control: 'Kubernetes admission quota enforcement' },
        { framework: 'Namespace & datastore isolation', requirement: 'platform.isolation.agentNamespaces: true + zelkor.io/namespace-role: agent namespace selector on checkpointer NetworkPolicy.', control: 'Cross-namespace connectivity test' },
        { framework: 'Prometheus & OTel integration', requirement: 'Optional Prometheus ServiceMonitor + zero-SDK OpenTelemetry collector wiring into self-hosted Langfuse 4.50.0.', control: 'Prometheus target scrape & Langfuse UI' },
      ],
      scenariosTitle: '3 platform engineering workflows',
      scenarios: [
        { title: 'Layered multi-team cluster rollout', text: 'Platform SREs deploy shared gateway/infrastructure components once and onboard product teams into dedicated namespaces labeled zelkor.io/namespace-role: agent using the layered or shared Envoy Gateway topology.' },
        { title: 'Turnkey agent onboarding (zelkor-aegra / zelkor-aegra-deep)', text: 'App teams bring their LangGraph, LangChain, or Deep Agents container image; the platform automatically injects OPENAI_BASE_URL (/v1), MCP_URL, and OpenTelemetry environment variables.' },
        { title: 'Automated gVisor node pool binding', text: 'Platform ops provision a dedicated node pool with --install-gvisor (zelkor.io/gvisor-ready=true) or GKE Sandbox / Talos, scheduling zelkor-sandbox-worker:2.3.2 warm pools onto runtimeClassName: gvisor while keeping standard agent pods on general-purpose nodes.' },
      ],
      bottomHeadline: 'Standardize how every engineering team deploys AI agents on Kubernetes.',
      bottomCta: { label: 'Inspect Helm Chart on GitHub (v2.3.2)', href: '#github' },
      bottomSecondary: { label: 'Book Platform Architecture Review', href: '/contact' },
    },
  },
  editions: {
    eyebrow: 'Editions & deployment models · Zelkor 2.3.2',
    h1: 'Full security architecture in Community Edition. Expert architecture advisory when you scale.',
    subtitle:
      'Every security control in Zelkor 2.3.2—from the runsc gVisor sandbox warm pool and Envoy AI Gateway to NVIDIA NeMo Guardrails, unified MCP tenancy, and self-hosted Langfuse v4—ships in our open-source Helm chart (charts/zelkor-platform). Choose the deployment topology and engineering partnership that fits your team.',
    primaryCta: { label: 'Install Community Edition (v2.3.2)', href: '/docs/quickstart' },
    secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
    cards: [
      {
        name: 'Quickstart & Evaluation (CE)',
        kicker: 'Free & open source · Apache-2.0 / CE',
        tagline: 'Local/dev Kubernetes clusters, security proof reproduction, and single-namespace agent evaluation.',
        highlights: [
          'Full charts/zelkor-platform (2.3.2) Helm chart install',
          'zelkor-aegra:2.3.2 & zelkor-aegra-deep:2.3.2 runtimes (LangGraph, LangChain, Deep Agents)',
          'greenfield Envoy Gateway + Envoy AI Gateway topology',
          '3-replica zelkor-sandbox-worker:2.3.2 gVisor (runsc) pool',
          'Self-hosted Langfuse 4.50.0 with 8 seeded evaluators',
          'Reproducible 5 live security proofs out of the box',
        ],
        cta: { label: 'Deploy Quickstart (CE)', href: '/docs/quickstart' },
        featured: true,
      },
      {
        name: 'Production Operator HA (CE)',
        kicker: 'Free & open source · Self-hosted production topology',
        tagline: 'Platform engineering teams running multi-tenant production workloads under strict Kubernetes governance.',
        highlights: [
          'Everything in Quickstart (CE), configured for production hardening',
          'layered or shared Envoy Gateway topology integration',
          'security.networkPolicies.enabled: true default-deny agent egress',
          'platform.isolation.agentNamespaces: true (zelkor.io/namespace-role: agent)',
          'Fail-closed JWT verification (jwksConfigMap / remoteJwksUri / localSigning)',
          'Fail-closed NVIDIA NeMo Guardrails (zelkor-guardrails:2.3.2) & /v1 RPM caps',
          'Explicit resources.requests & resources.limits for ResourceQuota clusters',
        ],
        cta: { label: 'Deploy Production Values (CE)', href: '/docs' },
      },
      {
        name: 'Enterprise Architecture Advisory',
        kicker: 'Custom engagement · Direct engineering partnership',
        tagline: 'Regulated enterprises requiring custom topology design, Postgres RLS/JWT integration reviews, and production go-live validation.',
        highlights: [
          'Everything in Production Operator HA (CE)',
          'Architecture review for layered / shared Envoy Gateway & CNI NetworkPolicy',
          'Custom gVisor node pool provisioning review (GKE Sandbox, Talos, --install-gvisor)',
          'End-to-end JWT JWKS, Postgres RLS (app.current_tenant), and Qdrant tenancy review',
          'Custom NVIDIA NeMo Guardrails Colang rail authoring & validation workshop',
          'External MCP backend (extraBackends) security & secret custody review',
          'Live execution & sign-off of the 5 security proof scenarios on your target cluster',
        ],
        cta: { label: 'Book Architecture Review', href: '/contact' },
      },
    ],
    matrixLabels: {
      capability: 'Capability / control (charts/zelkor-platform 2.3.2)',
      ce: 'Quickstart & Evaluation (CE)',
      pro: 'Production Operator HA (CE)',
      enterprise: 'Enterprise Architecture Advisory',
    },
    matrix: [
      { capability: '1. Supported agent frameworks', ce: 'LangGraph, LangChain, Deep Agents (zelkor-aegra:2.3.2 / zelkor-aegra-deep:2.3.2)', pro: 'LangGraph, LangChain, Deep Agents (zelkor-aegra:2.3.2 / zelkor-aegra-deep:2.3.2)', enterprise: 'LangGraph, LangChain, Deep Agents + custom graph packaging review' },
      { capability: '2. Agent Protocol & X-Graph-ID routing', ce: 'Included (/runs, /runs/wait, /threads)', pro: 'Included (/runs, /runs/wait, /threads)', enterprise: 'Included + multi-graph routing design' },
      { capability: '3. Envoy Gateway topologies', ce: 'greenfield default', pro: 'greenfield, layered, or shared', enterprise: 'Hands-on layered / shared cluster integration' },
      { capability: '4. Envoy AI Gateway credential custody (/v1)', ce: 'Included (10 provider types in K8s Secrets; zero upstream keys in agent pods)', pro: 'Included (10 provider types in K8s Secrets; zero upstream keys in agent pods)', enterprise: 'Included + enterprise Secret rotation workflow design' },
      { capability: '5. Global request rate limiting (/v1)', ce: 'Configurable (requestsPerMinute: 50 → HTTP 429)', pro: 'Enforced (requestsPerMinute: 50 → HTTP 429)', enterprise: 'Included + capacity sizing workshop' },
      { capability: '6. NVIDIA NeMo Guardrails (zelkor-guardrails:2.3.2)', ce: 'Optional / configurable (workspace.policies.nemo)', pro: 'Enabled (failClosed: true on /v1/chat/completions)', enterprise: 'Included + custom Colang & topic rail authoring' },
      { capability: '7. gVisor (runsc) sandbox pool (zelkor-sandbox-worker:2.3.2)', ce: 'Included (warmPool.replicas: 3, sandbox__execute_python)', pro: 'Included (runtimeClassName: gvisor, failClosed worker token)', enterprise: 'Included + GKE Sandbox / Talos / --install-gvisor node sizing' },
      { capability: '8. Unified MCP Gateway (zelkor-mcp:2.3.2)', ce: 'Included (Mode A direct & Mode B mcpInject.enabled: true)', pro: 'Included (Mode A direct & Mode B mcpInject.enabled: true)', enterprise: 'Included + custom tool governance review' },
      { capability: '9. Native governed MCP servers', ce: 'postgresMCP (read-only + RLS), qdrantMCP, objectMCP (256 KB cap), sandboxMCP', pro: 'postgresMCP (read-only + RLS), qdrantMCP, objectMCP (256 KB cap), sandboxMCP', enterprise: 'Included + Postgres RLS policy verification' },
      { capability: '10. External & cluster MCP backends (extraBackends)', ce: 'Included (K8s Secret injection, reserved prefix check, zero JWT leak)', pro: 'Included (K8s Secret injection, reserved prefix check, zero JWT leak)', enterprise: 'Included + third-party MCP threat modeling' },
      { capability: '11. Front-door JWT verification (platform.tenants.jwt)', ce: 'Configurable (localSigning / jwksConfigMap / remoteJwksUri)', pro: 'Enforced (failClosed: true, rejects alg: none & unsigned with 401/403)', enterprise: 'Included + enterprise IdP / JWKS integration' },
      { capability: '12. End-to-end tenant propagation', ce: 'Aegra TenantAuth + MCP langgraph_auth_user header enforcement', pro: 'Aegra TenantAuth + MCP langgraph_auth_user header enforcement', enterprise: 'Included + cross-tenant penetration test sign-off' },
      { capability: '13. Self-hosted Langfuse v4 (4.50.0) + OTel', ce: 'Included (ClickHouse, Postgres, SeaweedFS S3, captureContent: false)', pro: 'Included + Prometheus ServiceMonitor', enterprise: 'Included + retention & storage sizing review' },
      { capability: '14. Seeded Langfuse trace evaluators (seedCode: true)', ce: 'All 8 zelkor-* evaluators included (≤25 step budget)', pro: 'All 8 zelkor-* evaluators included (≤25 step budget)', enterprise: 'Included + custom evaluation workflow review' },
      { capability: '15. Kubernetes NetworkPolicy & namespace isolation', ce: 'Optional in quickstart', pro: 'Enforced (security.networkPolicies.enabled: true + zelkor.io/namespace-role: agent)', enterprise: 'Included + cluster CNI & ResourceQuota audit' },
    ],
    faqs: [
      {
        q: 'Which agent frameworks does Zelkor 2.3.2 run?',
        a: 'Zelkor wraps LangGraph, LangChain, and Deep Agents via the Aegra runtime images (ghcr.io/devopssquaddev/zelkor-aegra:2.3.2 and ghcr.io/devopssquaddev/zelkor-aegra-deep:2.3.2). Your graphs are served over standard Agent Protocol endpoints (/runs, /runs/wait, /threads) and routed by Envoy Gateway using the X-Graph-ID header.',
      },
      {
        q: 'Does the entire agent pod run inside gVisor?',
        a: 'No. Your agent pod stays on the standard container runtime so your Python packages, native extensions, and graph dependencies run without compatibility friction. Untrusted code execution (sandbox__execute_python) is sent over MCP to a dedicated warm pool (warmPool.replicas: 3) of zelkor-sandbox-worker:2.3.2 pods running with runtimeClassName: gvisor (runsc). Agent pods have no SANDBOX_WORKER_URLS and are blocked by NetworkPolicy from reaching worker port :8081 directly.',
      },
      {
        q: 'How does Zelkor enforce database isolation in Postgres, Qdrant, and S3?',
        a: 'At the front door, platform.tenants.jwt verifies the caller’s JWT and rejects unsigned tokens, alg: none, or missing tenant claims with HTTP 401/403. On MCP tools/call, zelkor-mcp:2.3.2 takes tenant identity exclusively from verified langgraph_auth_user headers—any client or model-supplied tenant_id argument fails closed. In Qdrant, qdrantMCP forces a tenant_id payload filter. In Object MCP, keys are tenant-prefixed with 256 KB read/write caps. In Postgres, postgresMCP enforces read-only queries and executes SET LOCAL app.current_tenant on every transaction so your Postgres Row-Level Security (RLS) policies enforce row isolation.',
      },
      {
        q: 'How do rate limiting and prompt verification work at the AI Gateway?',
        a: 'Envoy AI Gateway fronts /v1 and holds all upstream LLM credentials (OpenAI, Anthropic, Gemini, Bedrock, Vertex, Azure, Cohere, Ollama, vLLM, openaiCompat) in Kubernetes Secrets. Rate limiting is a deterministic global request cap (workspace.models.rateLimit.requestsPerMinute: 50) on /v1: request 51 within a minute immediately returns HTTP 429 Too Many Requests without calling the upstream provider. Prompt verification runs through NVIDIA NeMo Guardrails (workspace.policies.nemo, zelkor-guardrails:2.3.2) with Colang and content/topic safety rails on /v1/chat/completions, operating fail-closed when enabled.',
      },
      {
        q: 'Do I need to install a specific CNI or add tracing SDKs to my agent code?',
        a: 'Neither. Network isolation uses standard Kubernetes NetworkPolicy (security.networkPolicies.enabled: true), which works on any compliant Kubernetes CNI without requiring CNI-specific CRDs. Observability is wired via OpenTelemetry at the runtime/gateway layer into self-hosted Langfuse v4 (4.50.0) with zero tracing SDK required in your agent code, and captureContent: false ensures default logs and traces never leak Bearer tokens, API keys, or prompt bodies.',
      },
      {
        q: 'Can Zelkor deploy into clusters with strict ResourceQuota and least-privilege namespace RBAC?',
        a: 'Yes. Every container and initContainer in charts/zelkor-platform (2.3.2) sets explicit resources.requests and resources.limits for cpu and memory. The chart deploys cleanly with helm upgrade --install "$RELEASE" charts/zelkor-platform --namespace "$NS" --wait into an admin-provisioned namespace.',
      },
    ],
    finalHeadline: 'Deploy Zelkor 2.3.2 on your cluster today.',
    finalSub: 'Start with the open-source Helm chart or schedule a technical architecture review to walk through your Kubernetes topology, JWT tenancy, and gVisor node setup.',
    finalPrimary: { label: 'Install via Helm (v2.3.2)', href: '/docs/quickstart' },
    finalSecondary: { label: 'Book Architecture Review', href: '/contact' },
  },
}
