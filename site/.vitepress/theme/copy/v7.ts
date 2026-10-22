import type { VariantCopy } from './types'

const helm = `helm upgrade --install zelkor-platform charts/zelkor-platform \\
  --namespace zelkor \\
  -f profiles/values-production.yaml \\
  -f profiles/values-gateway-greenfield.yaml \\
  --wait`

const sandboxYaml = `security:
  sandbox:
    enabled: true
    runtimeClass: gvisor
workspace:
  tools:
    sandboxMCP:
      enabled: true
      warmPool:
        replicas: 3`

const gatewayYaml = `workspace:
  models:
    rateLimit:
      enabled: true
      requestsPerMinute: 50
  policies:
    nemo:
      enabled: true
      intercept:
        enabled: true`

const mcpYaml = `workload:
  agents:
    mcpInject:
      enabled: true
workspace:
  tools:
    enabled: true
    postgresMCP:
      enabled: true
    qdrantMCP:
      enabled: true`

const tenancyYaml = `platform:
  tenants:
    jwt:
      issuer: "https://idp.enterprise.internal"
      audiences:
        - "zelkor"
      jwksConfigMap: "zelkor-tenant-jwks"
      tenantClaims:
        - tenant_id`

const observabilityYaml = `platform:
  telemetry:
    level: INFO
    langfuse:
      enabled: true
observability:
  serviceMonitor:
    enabled: true`

const networkYaml = `platform:
  isolation:
    agentNamespaces: true
security:
  networkPolicies:
    enabled: true
gateway:
  hosts:
    agents: "agents.example.com"
    langfuse: "langfuse.example.com"`

export const v7: VariantCopy = {
  id: 7,
  name: 'Emerald Buyer',
  short: '7 · Buyer',
  announcement: {
    badge: 'Live demo scenarios',
    text: '5 reproducible security proofs: No provider API keys in agent pods • gVisor Python sandbox • Cryptographic tenant isolation • Gateway request circuit breaker',
    linkLabel: 'Explore the 5 Proofs',
    href: '/#proofs',
  },
  navCta: { label: 'Book Architecture Review', href: '/contact' },
  productsNav: [
    { slug: 'sandbox', title: 'Code Sandbox', blurb: 'Isolated gVisor worker pool for untrusted Python' },
    { slug: 'gateway', title: 'AI Gateway', blurb: 'Key custody, request caps, and NVIDIA NeMo Guardrails' },
    { slug: 'mcp', title: 'MCP Tool Gateway', blurb: 'Single governed endpoint for databases, files, and external tools' },
    { slug: 'tenancy', title: 'Multi-Tenant Auth', blurb: 'Front-door JWT verification and tenant-scoped data access' },
    { slug: 'observability', title: 'Observability', blurb: 'Self-hosted Langfuse traces without SDK changes' },
    { slug: 'network', title: 'Network Isolation', blurb: 'Kubernetes NetworkPolicy egress lockdown' },
  ],
  solutionsNav: [
    { slug: 'financial-services', title: 'Financial Services', blurb: 'Research and advisory agents under strict egress, key custody, and audit controls.' },
    { slug: 'healthcare', title: 'Healthcare & Life Sciences', blurb: 'Clinical and research agents inside tenant, network, and log-redaction boundaries.' },
    { slug: 'b2b-saas', title: 'Multi-Tenant B2B SaaS', blurb: 'One agent deployment. Thousands of customer tenants. Zero cross-tenant tool calls.' },
    { slug: 'platform-engineering', title: 'Platform Engineering', blurb: 'One Helm chart. Resource limits on every container. Standard Kubernetes primitives.' },
  ],
  home: {
    eyebrow: 'The self-hosted agent runtime',
    h1: 'Ship agents, not cluster breaches.',
    subtitle:
      'Bring the agent you already wrote — it can\'t break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation; tenants stay isolated.',
    primaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
    secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
    githubCta: { label: 'View on GitHub →', href: '#github' },
    install: helm,
    marqueeLabel: '',
    marquee: [
      'gVisor code sandbox',
      'Brokered model keys',
      'NeMo Guardrails',
      'Governed MCP tools',
      'Verified JWT tenancy',
      'Self-hosted Langfuse traces',
      'Egress network lockdown',
    ],
    bridgeKicker: 'Prompt filters are probabilistic.',
    bridgeHeading: 'Kernel, network, and credential boundaries are not.',
    bridge:
      'System prompts cannot stop a hijacked tool call from reading environment variables, dialing an external server, or asking a database for another customer’s records. Zelkor enforces those boundaries in the Kubernetes infrastructure around your agent pod, not inside the prompt.',
    tabsHeadline: '4-tab architecture walkthrough',
    tabs: [
      {
        id: 'sandbox',
        label: 'Sandbox',
        headline: 'Untrusted Python runs outside the agent pod',
        copy: 'Your agent pod runs your graph and Python dependencies on the standard container runtime. When the agent needs to execute generated Python, the code is sent over MCP to a separate pool of warm gVisor worker pods. Your agent pod’s memory, files, and service account are never exposed to that code.',
        points: [
          'Dedicated gVisor Pool: Three warm worker replicas run untrusted code inside a user-space kernel boundary.',
          'No Direct Network Path: Agent pods cannot dial sandbox workers directly; all code requests pass through the MCP gateway.',
          'Authenticated Execution: Sandbox workers require an internal gateway token and reject unauthenticated requests.',
        ],
        lang: 'bash',
        code: helm,
      },
      {
        id: 'gateway',
        label: 'Gateway',
        headline: 'Upstream model keys stay out of agent pods',
        copy: 'Agent pods never hold provider keys for OpenAI, Anthropic, or Bedrock. They talk only to a cluster-local Envoy AI Gateway using an internal token. The gateway attaches real provider secrets from Kubernetes Secrets, checks prompts, and enforces a global request limit.',
        points: [
          'Central Key Custody: Provider credentials live only on the gateway, never in workload environment variables.',
          'Loop Circuit Breaker: A global cap (50 requests per minute by default) rejects runaway agent loops before the upstream provider is called.',
          'Inline Guardrails: NVIDIA NeMo Guardrails inspects chat completions and fails closed when enabled.',
        ],
        lang: 'bash',
        code: helm,
      },
      {
        id: 'mcp',
        label: 'MCP & Tenants',
        headline: 'Tenant identity comes from the verified user, never the model',
        copy: 'Every run and thread request is authenticated at the front door with a signed JWT. When the agent calls a database, vector store, or object bucket over MCP, the gateway reads the tenant identity from the verified user context. If a prompt-injected model tries to pass another customer’s tenant ID in tool arguments, the call is rejected.',
        points: [
          'Single Tool Endpoint: One MCP gateway fronts Postgres, Qdrant, S3 object storage, the code sandbox, and external MCP servers.',
          'Database and Storage Scopes: Postgres runs read-only queries with your tenant session set for Row-Level Security; Qdrant searches are filtered by tenant; S3 keys are prefixed by tenant.',
          'Protected External Calls: External MCP tools authenticate with dedicated Kubernetes Secrets, and the caller’s internal JWT is never forwarded.',
        ],
        lang: 'bash',
        code: helm,
      },
      {
        id: 'trace',
        label: 'Trace',
        headline: 'Full run traces without adding SDKs to agent code',
        copy: 'Zelkor traces every agent run, gateway call, guardrail check, and MCP tool execution automatically in self-hosted Langfuse. Developers do not need to add tracing decorators or SDK imports to their graph code. Sensitive prompt bodies and keys stay out of default logs.',
        points: [
          'One Trace Per Run: Model calls, guardrail checks, and tool invocations link together under a single run waterfall.',
          'Redacted by Default: Default logs and trace metadata omit prompt bodies, bearer tokens, and API keys.',
          'Automated Run Checks: Built-in Langfuse checks score every run for tool loops, step budgets, and tenant attribution.',
        ],
        lang: 'bash',
        code: helm,
      },
    ],
    stepsHeadline: '3 steps to production',
    steps: [
      {
        title: 'Bring your agent',
        body: 'Package the LangGraph, LangChain, or Deep Agents application you already built. You keep your state machine and dependencies as they are.',
      },
      {
        title: 'Close the doors',
        body: 'Install the Zelkor Helm chart into a namespace your cluster admin created. Turn on Kubernetes NetworkPolicy, route model calls through the AI gateway, and send untrusted Python to the gVisor worker pool.',
      },
      {
        title: 'Run it for teams',
        body: 'Onboard multiple teams into isolated agent namespaces with CPU and memory requests and limits set on every container. Track every run and tool call in self-hosted Langfuse.',
      },
    ],
    proofsHeadline: '5 live security proofs',
    proofs: [
      {
        title: 'The Vanishing Key — Prompt Injection Dumps Environment Variables',
        scenario: 'A malicious prompt tricks the agent into reading its own environment variables to steal your OpenAI or Anthropic API key.',
        control: 'The agent pod holds no upstream provider keys—only a local token for the cluster AI gateway. Kubernetes NetworkPolicy also blocks the pod from calling external model APIs directly.',
        result: 'Inspecting the pod environment reveals no provider secret to steal, and the local token does not work outside the cluster.',
      },
      {
        title: 'The Flight Recorder — Reconstructing an Incident Without Developer SDKs',
        scenario: 'An agent misbehaves in production, and security needs to know which prompts, guardrails, and tools ran—even though developers never added tracing code.',
        control: 'The runtime and gateways record OpenTelemetry spans automatically into self-hosted Langfuse, while keeping raw prompts and secrets out of default logs.',
        result: 'A single waterfall trace in Langfuse shows the entire run, gateway checks, and tool calls, alongside automated run scores.',
      },
      {
        title: 'The Shell Moved — Generated Python Tries to Escape the Container',
        scenario: 'Agent-generated Python code runs shell commands, reads local files, or probes the kernel to break out of the container.',
        control: 'Untrusted Python never runs in the agent pod. It executes in a separate pool of warm gVisor workers reached only through the MCP gateway.',
        result: 'System calls are trapped by the gVisor user-space kernel, and the agent pod’s filesystem and service account are untouched.',
      },
      {
        title: 'Two Desks, One Graph — Prompt Injection Requests Another Tenant’s Data',
        scenario: 'A user in Tenant A tricks the model into calling a database or vector search tool with Tenant B’s identifier.',
        control: 'Front-door JWT verification locks in the caller’s identity. The MCP gateway takes the tenant solely from that verified user context and rejects model-supplied tenant IDs.',
        result: 'The cross-tenant tool call is rejected before reaching Postgres, Qdrant, or S3, and Tenant B’s records stay hidden.',
      },
      {
        title: 'Loop Dies at the Door — Runaway Agent Loop Burns Model Quota',
        scenario: 'A broken reasoning loop fires dozens of model requests in seconds, threatening upstream rate limits and API bills.',
        control: 'Envoy AI Gateway enforces a global request cap per minute at the cluster boundary, and Langfuse run checks flag excessive tool steps.',
        result: 'Once the per-minute cap is reached, the extra model call is rejected at the gateway before reaching the LLM provider.',
      },
    ],
    personasHeadline: 'Built for 3 core personas',
    personas: [
      {
        title: 'Security & CISO Teams',
        role: '',
        body: 'Stop relying on system prompts as a security control. Enforce gVisor sandboxing for untrusted code, keep provider keys out of workload pods, lock down pod egress with Kubernetes NetworkPolicy, and bind data access to verified JWTs.',
        points: [
          'gVisor sandboxing for untrusted code',
          'Provider keys out of workload pods',
          'Kubernetes NetworkPolicy egress lockdown',
          'Data access bound to verified JWTs',
        ],
      },
      {
        title: 'Platform Engineering Directors',
        role: '',
        body: 'Deploy one Helm chart into an existing namespace without cluster-admin scripts or custom CNIs. Every container ships with CPU and memory requests and limits to pass strict cluster quotas, and Envoy integrates cleanly with your existing ingress.',
        points: [
          'One Helm chart into an existing namespace',
          'CPU and memory requests and limits on every container',
          'Envoy integrates with your existing ingress',
        ],
      },
      {
        title: 'Agent Developers',
        role: '',
        body: 'Keep building in standard LangGraph, LangChain, and Deep Agents. Your graph gets governed MCP tools at startup and complete Langfuse traces without adding infrastructure boilerplate to your code.',
        points: [
          'LangGraph, LangChain, and Deep Agents',
          'Governed MCP tools at startup',
          'Langfuse traces without infrastructure boilerplate',
        ],
      },
    ],
    finalHeadline: 'Put real boundaries around the agents you already wrote.',
    finalSub: 'Deploy Zelkor Community Edition on your Kubernetes cluster, or walk through the five live security proofs with our engineering team.',
    finalPrimary: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
    finalSecondary: { label: 'Book Architecture Review', href: '/contact' },
  },
  products: {
    sandbox: {
      slug: 'sandbox',
      eyebrow: 'Capability · Code Sandbox',
      h1: 'Run untrusted Python in a dedicated gVisor pool, never inside your agent pod.',
      subtitle:
        'Your LangGraph, LangChain, or Deep Agents container stays on the standard Kubernetes runtime so your libraries work without friction. Whenever the agent runs generated Python, the code is sent over MCP to a separate pool of gVisor worker pods.',
      primaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why Running Code in the Agent Pod Fails',
      overview:
        'If an agent executes generated Python inside its own container, a single prompt injection gives that script access to the pod’s filesystem, memory, environment variables, and Kubernetes service account. Even moving code to a second standard container still shares the host Linux kernel with neighboring workloads on the node.',
      capabilities: [
        {
          title: 'Warm gVisor Worker Pool',
          text: 'Three pre-warmed worker replicas run under gVisor, intercepting system calls in a user-space kernel so untrusted Python cannot reach the host kernel or neighboring pods.',
        },
        {
          title: 'Routed Through MCP',
          text: 'Code execution is exposed as a governed MCP tool. Your agent pod sends the code over MCP and gets the output back without running an interpreter locally.',
        },
        {
          title: 'No Direct Agent-to-Worker Access',
          text: 'Agent pods do not know worker IP addresses and are blocked by Kubernetes NetworkPolicy from connecting to sandbox workers directly. Workers require an internal token held only by the MCP gateway.',
        },
        {
          title: 'Simple Node Scheduling',
          text: 'Schedule sandbox workers onto gVisor-enabled nodes using a standard node label, or use automatic detection on GKE Sandbox and Talos Linux clusters.',
        },
      ],
      snippetTitle: 'How Teams Use It',
      snippetLang: 'yaml',
      snippet: sandboxYaml,
      bottomHeadline: 'Isolate agent-generated Python without breaking your agent runtime.',
      bottomPrimary: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    gateway: {
      slug: 'gateway',
      eyebrow: 'Capability · AI Gateway',
      h1: 'Keep LLM provider keys out of agent pods and stop runaway loops at the door.',
      subtitle:
        'Built on Envoy AI Gateway, Zelkor holds your upstream model credentials in gateway Secrets, caps request rates before calls leave the cluster, and checks prompts with NVIDIA NeMo Guardrails.',
      primaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why Putting API Keys in Agent Pods Fails',
      overview:
        'Putting OpenAI, Anthropic, or Bedrock keys directly into agent deployment manifests spreads high-value credentials across dozens of pods. If one pod is compromised or gets stuck in a retry loop, it can leak the raw key or burn through thousands of upstream API calls with no central cutoff.',
      capabilities: [
        {
          title: 'Central Provider Key Custody',
          text: 'Agent pods receive only a local gateway token and cluster URL. Real credentials for OpenAI, Anthropic, Gemini, Bedrock, Vertex, Azure OpenAI, Cohere, Ollama, and vLLM stay in Kubernetes Secrets mounted only on the gateway.',
        },
        {
          title: 'Global Request Circuit Breaker',
          text: 'A configurable per-minute cap (50 requests per minute by default) stops runaway agent loops at the gateway. Extra model calls are rejected inside the cluster before reaching your provider.',
        },
        {
          title: 'Fail-Closed NVIDIA NeMo Guardrails',
          text: 'When enabled, chat completions pass through NVIDIA NeMo Guardrails for topic and content safety checks before reaching the model or returning to the caller. If a check fails, the call is blocked.',
        },
        {
          title: 'Header-Based Agent Routing',
          text: 'Envoy fronts both model traffic and standard agent run and thread endpoints, routing incoming requests to the right LangGraph, LangChain, or Deep Agents deployment by graph header.',
        },
      ],
      snippetTitle: 'How Teams Use It',
      snippetLang: 'yaml',
      snippet: gatewayYaml,
      bottomHeadline: 'Remove upstream API keys from every agent pod.',
      bottomPrimary: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    mcp: {
      slug: 'mcp',
      eyebrow: 'Capability · MCP Tool Gateway',
      h1: 'One governed MCP endpoint for databases, vector search, files, and external tools.',
      subtitle:
        'Zelkor gives every agent a single MCP endpoint for Postgres, Qdrant, S3 object storage, the gVisor code sandbox, and external MCP servers—holding backend secrets at the gateway and never leaking your caller’s JWT to third parties.',
      primaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why Direct Tool Connections From Agent Pods Fail',
      overview:
        'When agents connect straight to databases, S3 buckets, and third-party APIs, every agent pod needs database passwords, storage keys, and broad outbound network access. Worse, nothing stops a prompt-injected model from running destructive SQL statements or sending internal user tokens to an external vendor.',
      capabilities: [
        {
          title: 'Automatic or Direct Tool Binding',
          text: 'Let the runtime automatically discover and bind allowed MCP tools into your LangGraph, LangChain, or Deep Agents workload at startup, or connect your own MCP client directly to the gateway URL.',
        },
        {
          title: 'Built-In Scoped Data Tools',
          text: 'Postgres: read-only queries and schema inspection with the caller’s tenant set on every transaction for Row-Level Security. Qdrant: document search and upsert with mandatory tenant filters injected automatically. Object Storage: tenant-prefixed file reads and writes on S3-compatible storage with a 256 KB payload cap and delete off by default. Code Sandbox: Python execution routed to the gVisor worker pool.',
        },
        {
          title: 'Governed External MCP Backends',
          text: 'Register internal cluster services or external HTTPS MCP servers on the gateway. The gateway attaches the backend’s API key from a Kubernetes Secret and prevents external servers from spoofing built-in tool names.',
        },
        {
          title: 'No Caller JWT Leakage',
          text: 'When calling an external MCP server, the gateway strips the user’s internal Zelkor JWT and authenticates using only the secret configured for that backend.',
        },
      ],
      snippetTitle: 'How Teams Use It',
      snippetLang: 'yaml',
      snippet: mcpYaml,
      bottomHeadline: 'Put every database query, vector search, and SaaS tool call behind one control point.',
      bottomPrimary: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    tenancy: {
      slug: 'tenancy',
      eyebrow: 'Capability · Multi-Tenant Auth',
      h1: 'Cryptographic tenant isolation from the front door down to the database row.',
      subtitle:
        'Zelkor verifies caller JWTs at ingress, isolates conversation threads and runs per tenant, derives tool tenancy solely from the verified user, and enforces that tenant across Postgres, Qdrant, and S3.',
      primaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why Prompt-Based Multi-Tenancy Fails',
      overview:
        'Passing a tenant ID in a system prompt or trusting the LLM to fill in a tenant_id tool argument is not isolation. Any prompt injection can tell the model to ask for another customer’s ID, turning a shared agent deployment into a cross-tenant data leak.',
      capabilities: [
        {
          title: 'Front-Door JWT Verification',
          text: 'Every request is checked for a valid issuer, audience, and cryptographic signature using your identity provider’s keys. Unsigned tokens or requests missing a tenant claim are rejected immediately—there is no default fallback tenant.',
        },
        {
          title: 'Isolated Threads and Runs',
          text: 'Conversation history, checkpoints, and run state are scoped to the authenticated tenant. One customer cannot list, inspect, or resume another customer’s threads.',
        },
        {
          title: 'Tamper-Proof Tool Identity',
          text: 'When an agent calls an MCP tool, the gateway reads the tenant identity exclusively from the verified user header. If the model passes a tenant_id parameter in the tool call, the request is rejected.',
        },
        {
          title: 'Datastore-Level Enforcement',
          text: 'Postgres sets the verified tenant on every read-only transaction so your Postgres Row-Level Security policies filter rows at the database engine. Qdrant forces a tenant filter onto every vector search and document write. Object Storage prefixes every S3 object path with the verified tenant ID.',
        },
      ],
      snippetTitle: 'How Teams Use It',
      snippetLang: 'yaml',
      snippet: tenancyYaml,
      bottomHeadline: 'Serve every customer from one shared agent graph without cross-tenant data leaks.',
      bottomPrimary: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    observability: {
      slug: 'observability',
      eyebrow: 'Capability · Observability',
      h1: 'One trace per agent run in self-hosted Langfuse—with zero SDKs in your code.',
      subtitle:
        'Zelkor links agent runs, AI gateway calls, guardrail checks, and MCP tool executions into a single trace inside self-hosted Langfuse, while keeping prompts and keys out of default logs.',
      primaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why Standard Container Logs Fail for Agents',
      overview:
        'Standard pod logs scatter a single agent run across multiple services, dump sensitive customer prompts or bearer tokens into cluster log pipelines, and leave gaps whenever a developer forgets to wrap a new graph node in a tracing library.',
      capabilities: [
        {
          title: 'Zero-SDK Run Correlation',
          text: 'Without adding Langfuse or OpenTelemetry imports to your agent code, Zelkor automatically joins the agent run, gateway model calls, NeMo guardrail checks, and MCP tool calls under one trace.',
        },
        {
          title: 'Prompts and Keys Redacted by Default',
          text: 'Default logs and trace metadata do not record raw prompt bodies, bearer tokens, or upstream API keys, keeping sensitive data out of cluster log collectors.',
        },
        {
          title: 'Built-In Run Checks',
          text: 'Self-hosted Langfuse comes pre-configured with automated checks that score runs for tool call budgets, repeated tool loops, sandbox cleanliness, guardrail refusals, and tenant attribution.',
        },
        {
          title: 'In-Cluster Storage and Prometheus Metrics',
          text: 'All trace data stays inside your cluster on self-hosted Langfuse, ClickHouse, Postgres, and S3-compatible storage, alongside an optional Prometheus ServiceMonitor for cluster monitoring.',
        },
      ],
      snippetTitle: 'How Teams Use It',
      snippetLang: 'yaml',
      snippet: observabilityYaml,
      bottomHeadline: 'Get complete flight-recorder visibility for every agent run inside your own cluster.',
      bottomPrimary: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
    network: {
      slug: 'network',
      eyebrow: 'Capability · Network Isolation',
      h1: 'Lock down agent egress with standard Kubernetes NetworkPolicy.',
      subtitle:
        'Zelkor blocks agent pods from calling the public internet, vector stores, sandbox workers, or external tools directly—allowing outbound traffic only to the AI gateway, the MCP gateway, and run state storage.',
      primaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      overviewTitle: 'Why Default Kubernetes Networking Fails for Agents',
      overview:
        'By default, any Kubernetes pod can open outbound connections to the public internet and to internal services across namespaces. If an agent pod is compromised through a prompt or dependency, it can post stolen data to an external server or probe internal databases directly.',
      capabilities: [
        {
          title: 'Default-Deny Agent Egress',
          text: 'Standard Kubernetes NetworkPolicy blocks agent pods from reaching the internet, Qdrant, sandbox workers, and external MCP servers directly. Outbound connections are limited to the AI gateway, MCP gateway, and checkpointer database.',
        },
        {
          title: 'Isolated Agent Namespaces',
          text: 'When namespace isolation is enabled, only pods in designated agent namespaces can connect to the run-state database, blocking lateral movement from unrelated workloads on the cluster.',
        },
        {
          title: 'No Public Routes to Internal Services',
          text: 'Only the authenticated Envoy front door is exposed outside the cluster. Internal services—including the MCP gateway, NeMo Guardrails, databases, and sandbox workers—never get public routes.',
        },
        {
          title: 'Works With Your Ingress and Quotas',
          text: 'Deploy Envoy as a standalone load balancer, behind your existing ingress controller, or attached to a shared cluster gateway. Every container includes CPU and memory requests and limits to pass strict namespace quotas.',
        },
      ],
      snippetTitle: 'How Teams Use It',
      snippetLang: 'yaml',
      snippet: networkYaml,
      bottomHeadline: 'Lock down agent network traffic using standard Kubernetes controls on any CNI.',
      bottomPrimary: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
  },
  solutions: {
    'financial-services': {
      slug: 'financial-services',
      eyebrow: 'Solutions · Financial Services & Banking',
      h1: 'Run research and advisory agents under strict egress, key custody, and audit controls.',
      subtitle:
        'Deploy LangGraph, LangChain, and Deep Agents workloads on Kubernetes with zero model keys in agent pods, gVisor isolation for quantitative Python scripts, read-only tenant-scoped Postgres queries, and self-hosted Langfuse traces.',
      primaryCta: { label: 'Book Architecture Review', href: '/contact' },
      secondaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      risks: [
        { title: 'Exposed Model API Keys', text: 'Putting OpenAI or Bedrock credentials in agent pods risks key theft during a prompt injection. How Zelkor stops it: Provider keys stay in gateway Kubernetes Secrets; agent pods hold only a local gateway token.' },
        { title: 'Unsafe Quantitative Python Execution', text: 'Running generated portfolio math inside the agent container exposes the pod’s filesystem and service account. How Zelkor stops it: Untrusted Python runs over MCP in a warm pool of gVisor worker pods.' },
        { title: 'Cross-Desk Data Leakage', text: 'Shared research graphs queried by multiple desks risk returning another client’s holdings. How Zelkor stops it: Verified JWT identity sets the tenant session for Postgres Row-Level Security and forces tenant filters on Qdrant.' },
        { title: 'Destructive Database Queries', text: 'Hallucinated SQL statements attempting to modify or delete core financial records. How Zelkor stops it: The Postgres MCP tool enforces read-only queries.' },
        { title: 'Runaway Model Loops', text: 'Recursive agent loops firing hundreds of model calls per minute. How Zelkor stops it: The AI gateway enforces a per-minute request cap and rejects extra calls before reaching the provider.' },
        { title: 'Client Prompts in Cluster Logs', text: 'Standard container logs capturing sensitive account numbers and prompts. How Zelkor stops it: Default log settings omit prompt bodies, bearer tokens, and API keys.' },
      ],
      mappingTitle: 'Compliance & Control Mapping',
      mappingLabels: {
        framework: 'Requirement',
        requirement: 'What Zelkor Does',
        control: 'How You Check It',
      },
      mapping: [
        { framework: 'Network Segmentation (DORA / PCI-DSS)', requirement: 'Kubernetes NetworkPolicy blocks agent pods from calling the internet, sandbox workers, or databases directly.', control: 'Run The Vanishing Key and The Shell Moved network proofs.' },
        { framework: 'Credential Custody & Access (SOC 2)', requirement: 'Keeps upstream LLM keys on the gateway and rejects unsigned or invalid JWTs at the front door.', control: 'Inspect pod environment variables and run negative JWT tests.' },
        { framework: 'Multi-Desk Information Barriers', requirement: 'Propagates verified user identity to MCP tools, sets Postgres tenant sessions for RLS, and filters Qdrant by tenant.', control: 'Run Two Desks, One Graph cross-tenant proof.' },
        { framework: 'Model Risk Audit Trail (SR 11-7)', requirement: 'Records full run waterfalls and automated run checks in self-hosted Langfuse; inspects prompts with NeMo Guardrails.', control: 'Review run traces in Langfuse via The Flight Recorder proof.' },
      ],
      scenariosTitle: '3 Financial Services Workflows',
      scenarios: [
        { title: 'Multi-Desk Institutional Research', text: 'Serve equity and credit research across separate desks from one LangGraph deployment while enforcing desk-level isolation in Postgres and Qdrant.' },
        { title: 'Sandboxed Quantitative Backtesting', text: 'Execute agent-written Python valuation models inside the warm gVisor worker pool with no access to the agent pod or external networks.' },
        { title: 'Guardrailed Client Advisory Copilot', text: 'Route every chat completion through fail-closed NVIDIA NeMo Guardrails for topic safety and cap request rates at the cluster gateway.' },
      ],
      bottomHeadline: 'Deploy auditable financial agents inside your own Kubernetes cluster.',
      bottomCta: { label: 'Book Architecture Review', href: '/contact' },
      bottomSecondary: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
    },
    healthcare: {
      slug: 'healthcare',
      eyebrow: 'Solutions · Healthcare & Life Sciences',
      h1: 'Keep clinical and research agents inside strict tenant, network, and log-redaction boundaries.',
      subtitle:
        'Run LangGraph, LangChain, and Deep Agents workloads with prompts and keys kept out of default logs, self-hosted Langfuse traces that never leave your cluster, verified JWT tenant isolation, and gVisor-isolated Python execution.',
      primaryCta: { label: 'Book Architecture Review', href: '/contact' },
      secondaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      risks: [
        { title: 'Patient Context in Container Logs', text: 'Standard stdout logging accidentally capturing clinical prompts or auth tokens. How Zelkor stops it: Prompts and keys stay out of default logs and trace metadata.' },
        { title: 'Traces Sent to External Cloud Vendors', text: 'Shipping execution traces containing research workflow data to a third-party SaaS. How Zelkor stops it: Langfuse runs self-hosted inside your cluster on ClickHouse, Postgres, and S3-compatible storage.' },
        { title: 'Cross-Study Data Bleed', text: 'Multi-site clinical trial assistants querying records from the wrong institution or cohort. How Zelkor stops it: Verified JWT identity binds every Postgres query, Qdrant search, and S3 path to the caller’s tenant.' },
        { title: 'Unisolated Biostatistical Python', text: 'Agent-generated statistical scripts running inside the main application container. How Zelkor stops it: Untrusted Python runs over MCP in a separate warm pool of gVisor workers.' },
        { title: 'Unchecked Clinical Prompt Trajectories', text: 'Off-topic or unsafe completions reaching clinical staff. How Zelkor stops it: NVIDIA NeMo Guardrails inspects chat completions and fails closed when enabled.' },
        { title: 'Leaking Internal Tokens to External Tools', text: 'Forwarding hospital JWTs when querying external literature MCP servers. How Zelkor stops it: External MCP backends authenticate with dedicated Kubernetes Secrets; the caller’s JWT is stripped.' },
      ],
      mappingTitle: 'Compliance & Control Mapping',
      mappingLabels: {
        framework: 'Requirement',
        requirement: 'What Zelkor Does',
        control: 'How You Check It',
      },
      mapping: [
        { framework: 'Log & Telemetry Minimization', requirement: 'Omits raw prompt bodies, bearer tokens, and API keys from default container logs and trace metadata.', control: 'Inspect pod stdout logs and Langfuse span attributes.' },
        { framework: 'In-Cluster Audit Residency', requirement: 'Stores all traces and automated run scores in self-hosted Langfuse inside your Kubernetes cluster.', control: 'Verify cluster storage claims and outbound NetworkPolicy.' },
        { framework: 'Cohort & Institution Separation', requirement: 'Verifies front-door JWTs and rejects any model-supplied tenant ID on MCP tool calls.', control: 'Run Two Desks, One Graph cross-tenant proof.' },
        { framework: 'Isolated Scientific Compute', requirement: 'Runs generated Python inside gVisor worker pods that require an internal gateway token.', control: 'Run The Shell Moved sandbox proof.' },
      ],
      scenariosTitle: '3 Healthcare & Life Sciences Workflows',
      scenarios: [
        { title: 'Multi-Site Clinical Trial Assistant', text: 'Query trial metadata through read-only Postgres with site-level Row-Level Security and search protocol documents in Qdrant without cross-site leakage.' },
        { title: 'Sandboxed Biostatistics Execution', text: 'Run survival analysis and data normalization scripts in the warm gVisor worker pool while keeping the agent pod isolated.' },
        { title: 'Governed Literature Search', text: 'Connect agents to external research MCP servers using gateway-managed Kubernetes Secrets without exposing internal clinician tokens.' },
      ],
      bottomHeadline: 'Run clinical and research agents with self-hosted traces and hard isolation boundaries.',
      bottomCta: { label: 'Book Architecture Review', href: '/contact' },
      bottomSecondary: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
    },
    'b2b-saas': {
      slug: 'b2b-saas',
      eyebrow: 'Solutions · Multi-Tenant B2B SaaS',
      h1: 'One agent deployment. Thousands of customer tenants. Zero cross-tenant tool calls.',
      subtitle:
        'Skip per-customer agent silos. Zelkor lets B2B SaaS teams serve every customer from shared LangGraph, LangChain, or Deep Agents deployments while enforcing cryptographic tenant boundaries across threads, Postgres, Qdrant, and S3.',
      primaryCta: { label: 'Book Architecture Review', href: '/contact' },
      secondaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      risks: [
        { title: 'Prompt-Injected Tenant Spoofing', text: 'A malicious user tricks your SaaS copilot into passing another customer’s tenant ID in a tool call. How Zelkor stops it: The MCP gateway takes the tenant solely from the verified user context and rejects model-supplied tenant IDs.' },
        { title: 'Cross-Tenant Thread Hijacking', text: 'Customer A tries to read or resume conversation threads belonging to Customer B. How Zelkor stops it: Thread and run state is scoped strictly to the verified tenant claim on the caller’s JWT.' },
        { title: 'Unfiltered Vector Search', text: 'Shared RAG indexes returning document chunks uploaded by another customer. How Zelkor stops it: The Qdrant MCP tool forces a tenant filter onto every vector search and document write.' },
        { title: 'Shared Bucket Path Traversal', text: 'An agent reading or overwriting files in another tenant’s storage path. How Zelkor stops it: The object storage tool enforces tenant prefixes on every key, caps reads and writes at 256 KB, and disables delete by default.' },
        { title: 'Noisy-Neighbor Runaway Loops', text: 'A buggy customer session enters a loop that burns shared LLM rate limits. How Zelkor stops it: The AI gateway enforces a per-minute request cap, and Langfuse checks flag excessive tool steps.' },
        { title: 'Unsigned Internal Requests', text: 'Microservices calling agent endpoints without a valid customer token. How Zelkor stops it: Front-door JWT verification rejects unsigned tokens or requests missing a tenant claim—there is no default tenant.' },
      ],
      mappingTitle: 'Compliance & Control Mapping',
      mappingLabels: {
        framework: 'Requirement',
        requirement: 'What Zelkor Does',
        control: 'How You Check It',
      },
      mapping: [
        { framework: 'Front-Door Tenant Authentication', requirement: 'Verifies JWT issuer, audience, and signature; rejects unsigned or incomplete tokens.', control: 'Test requests with missing or unsigned JWTs.' },
        { framework: 'Conversation & Checkpoint Isolation', requirement: 'Isolates threads and runs per authenticated tenant inside the runtime.', control: 'Attempt to fetch Tenant B’s thread with Tenant A’s token.' },
        { framework: 'Database, Vector & Storage Scoping', requirement: 'Sets Postgres tenant session for RLS, forces Qdrant tenant filters, and prefixes S3 keys by tenant.', control: 'Run Two Desks, One Graph cross-tenant proof.' },
        { framework: 'Automated Loop & Quality Checks', requirement: 'Scores runs in self-hosted Langfuse for step budgets, repeated tool calls, and tenant attribution.', control: 'Inspect automated scores in The Flight Recorder proof.' },
      ],
      scenariosTitle: '3 Multi-Tenant B2B SaaS Workflows',
      scenarios: [
        { title: 'Customer-Facing SaaS Copilot', text: 'Authenticate customer JWTs at the front door, route to your graph, and scope every Postgres query and Qdrant search to that customer’s verified tenant.' },
        { title: 'Tenant-Scoped File Processing', text: 'Read and write customer text artifacts up to 256 KB in S3-compatible storage under strict per-tenant path prefixes.' },
        { title: 'Startup Tool Injection', text: 'Bind built-in and external MCP tools into LangGraph or Deep Agents workloads at startup without embedding database or SaaS credentials in application repos.' },
      ],
      bottomHeadline: 'Ship multi-tenant AI features from a shared codebase without cross-tenant risk.',
      bottomCta: { label: 'Book Architecture Review', href: '/contact' },
      bottomSecondary: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
    },
    'platform-engineering': {
      slug: 'platform-engineering',
      eyebrow: 'Solutions · Platform Engineering & SRE',
      h1: 'One Helm chart. Resource limits on every container. Standard Kubernetes primitives.',
      subtitle:
        'Give product teams a self-service runtime for LangGraph, LangChain, and Deep Agents that passes cluster governance on the first deploy. Zelkor installs with a single Helm command into an existing namespace, sets CPU and memory requests and limits on every container, and works with your current CNI and ingress.',
      primaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
      risks: [
        { title: 'Pods Rejected by Cluster Quotas', text: 'Charts that ship containers or init containers without resource limits fail admission on enterprise Kubernetes and OpenShift clusters. How Zelkor stops it: Every container and init container defines CPU and memory requests and limits.' },
        { title: 'Cluster-Admin Script Sprawl', text: 'Installers that rely on imperative shell scripts or try to create namespaces fail under least-privilege CI pipelines. How Zelkor stops it: Deploys purely via Helm into a namespace your cluster admin already created.' },
        { title: 'Ingress Controller Collisions', text: 'AI platforms that demand exclusive ownership of cluster load balancers break existing routing. How Zelkor stops it: Envoy Gateway runs standalone, behind your existing ingress, or attached to a shared cluster gateway.' },
        { title: 'Accidental Public Exposure of Internal Tools', text: 'Misconfigured routes exposing vector databases, guardrails, or MCP servers to the internet. How Zelkor stops it: Only the front door is exposed; internal services never get public routes.' },
        { title: 'Lateral Movement to State Databases', text: 'Unrelated pods on shared clusters connecting to agent checkpoint databases. How Zelkor stops it: Namespace isolation restricts database access to designated agent namespaces.' },
        { title: 'Proprietary CNI Lock-In', text: 'Requiring custom kernel plugins just to restrict pod egress. How Zelkor stops it: Uses standard Kubernetes NetworkPolicy that works across any compliant CNI.' },
      ],
      mappingTitle: 'Compliance & Control Mapping',
      mappingLabels: {
        framework: 'Requirement',
        requirement: 'What Zelkor Does',
        control: 'How You Check It',
      },
      mapping: [
        { framework: 'Helm-Only GitOps Delivery', requirement: 'Installs via helm upgrade --install into an admin-created namespace with no imperative cluster scripts.', control: 'Run helm template and verify CI deploy logs.' },
        { framework: 'ResourceQuota & LimitRange Compliance', requirement: 'Sets explicit CPU and memory requests and limits on every container and init container.', control: 'Deploy into a namespace with an active ResourceQuota.' },
        { framework: 'Namespace & Database Isolation', requirement: 'Restricts run-state database ingress to namespaces labeled for agent workloads.', control: 'Test database connectivity from an unlabeled namespace.' },
        { framework: 'Cluster Monitoring Integration', requirement: 'Includes self-hosted Langfuse for traces plus an optional Prometheus ServiceMonitor for metrics.', control: 'Check Prometheus scrape targets and Langfuse UI.' },
      ],
      scenariosTitle: '3 Platform Engineering Workflows',
      scenarios: [
        { title: 'Multi-Team Cluster Rollout', text: 'Deploy the platform once behind your existing ingress controller and onboard product teams into isolated agent namespaces.' },
        { title: 'Zero-Boilerplate Agent Onboarding', text: 'Application teams bring their LangGraph, LangChain, or Deep Agents container image; the platform wires the AI gateway URL, MCP tools, and tracing automatically.' },
        { title: 'Dedicated gVisor Node Pool', text: 'Schedule the warm sandbox worker pool onto labeled gVisor nodes (or GKE Sandbox / Talos) while running standard agent pods on general-purpose nodes.' },
      ],
      bottomHeadline: 'Standardize how engineering teams run agents on Kubernetes.',
      bottomCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      bottomSecondary: { label: 'Book Architecture Review', href: '/contact' },
    },
  },
  editions: {
    eyebrow: 'Editions & Deployment',
    h1: 'Every security control ships in Community Edition. Enterprise adds architecture advisory.',
    subtitle:
      'We do not hold back security controls for a paid tier. The gVisor sandbox pool, Envoy AI Gateway, NVIDIA NeMo Guardrails, governed MCP tools, verified JWT tenancy, NetworkPolicy lockdown, and self-hosted Langfuse traces are all included in the open-source Helm chart.',
    primaryCta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
    secondaryCta: { label: 'Book Architecture Review', href: '/contact' },
    cards: [
      {
        name: 'Quickstart (CE)',
        kicker: 'Free & Open Source · Apache-2.0',
        tagline: 'Local or dev Kubernetes clusters, running the five security proofs, and single-namespace evaluation.',
        highlights: [
          'Single Helm chart install into an existing namespace',
          'Runs LangGraph, LangChain, and Deep Agents without graph rewrites',
          'Standalone Envoy Gateway and Envoy AI Gateway setup',
          'Warm gVisor worker pool (3 replicas) for untrusted Python',
          'Self-hosted Langfuse with built-in run checks',
          'Reproducible 5 Live Security Proofs out of the box',
        ],
        cta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
        featured: true,
      },
      {
        name: 'Production (CE)',
        kicker: 'Free & Open Source · Self-Hosted Production',
        tagline: 'Platform teams running multi-tenant agents under strict Kubernetes quotas, network policies, and identity controls.',
        highlights: [
          'Everything in Quickstart (CE), configured for production clusters',
          'Standalone, layered (behind existing ingress), or shared gateway topologies',
          'Kubernetes NetworkPolicy egress lockdown enabled',
          'Isolated agent namespaces for run-state database protection',
          'Front-door JWT verification and fail-closed NVIDIA NeMo Guardrails enabled',
          'CPU and memory requests and limits on every container for quota compliance',
        ],
        cta: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
      },
      {
        name: 'Enterprise Architecture Advisory',
        kicker: 'Custom Engagement · Direct Engineering Partnership',
        tagline: 'Regulated organizations that want hands-on topology design, identity and database isolation review, and go-live validation with our engineers.',
        highlights: [
          'Same open-source platform and security controls as Production (CE)',
          'Gateway topology and Kubernetes NetworkPolicy design for your cluster',
          'gVisor node pool sizing and scheduling review (GKE Sandbox, Talos, or labeled nodes)',
          'End-to-end JWT identity, Postgres Row-Level Security, and Qdrant tenancy review',
          'Custom NVIDIA NeMo Guardrails policy and external MCP secret custody review',
          'Live execution and sign-off of the 5 security proofs on your cluster',
        ],
        cta: { label: 'Book Architecture Review', href: '/contact' },
      },
    ],
    matrixLabels: {
      capability: 'Capability',
      ce: 'Quickstart (CE)',
      pro: 'Production (CE)',
      enterprise: 'Enterprise Advisory',
    },
    matrix: [
      { capability: '1. Agent Frameworks (LangGraph, LangChain, Deep Agents)', ce: 'Included', pro: 'Included', enterprise: 'Included + packaging review' },
      { capability: '2. Standard Run & Thread Endpoints', ce: 'Included', pro: 'Included', enterprise: 'Included + multi-graph routing review' },
      { capability: '3. Gateway Topologies', ce: 'Standalone default', pro: 'Standalone, behind ingress, or shared gateway', enterprise: 'Included + cluster ingress design' },
      { capability: '4. Model Key Custody on AI Gateway', ce: 'Included', pro: 'Included', enterprise: 'Included + secret rotation review' },
      { capability: '5. Global Request Cap (50/min default)', ce: 'Configurable', pro: 'On by default', enterprise: 'Included + capacity sizing' },
      { capability: '6. NVIDIA NeMo Guardrails', ce: 'Configurable', pro: 'On by default (fail-closed)', enterprise: 'Included + custom rail workshop' },
      { capability: '7. gVisor Python Sandbox Pool (3 warm replicas)', ce: 'Included', pro: 'Included', enterprise: 'Included + node pool sizing' },
      { capability: '8. Unified MCP Tool Gateway', ce: 'Included', pro: 'Included', enterprise: 'Included + tool governance review' },
      { capability: '9. Built-In MCP Tools (Postgres, Qdrant, S3, Sandbox)', ce: 'Included', pro: 'Included', enterprise: 'Included + Postgres RLS review' },
      { capability: '10. External MCP Backends (Dedicated Secret, No JWT Leak)', ce: 'Included', pro: 'Included', enterprise: 'Included + third-party threat review' },
      { capability: '11. Front-Door JWT Verification', ce: 'Configurable', pro: 'On by default (no default tenant)', enterprise: 'Included + IdP & JWKS integration' },
      { capability: '12. Verified Tenant Propagation to Tools & Threads', ce: 'Included', pro: 'Included', enterprise: 'Included + cross-tenant test sign-off' },
      { capability: '13. Self-Hosted Langfuse Traces (No SDK in Agent Code)', ce: 'Included', pro: 'Included + Prometheus metrics', enterprise: 'Included + storage sizing review' },
      { capability: '14. Redacted Default Logs & Built-In Run Checks', ce: 'On by default', pro: 'On by default', enterprise: 'Included + audit workflow review' },
      { capability: '15. Kubernetes NetworkPolicy & Container Resource Limits', ce: 'Limits on by default; NetworkPolicy optional', pro: 'Both on by default', enterprise: 'Included + CNI & quota audit' },
    ],
    faqs: [
      {
        q: 'Which agent frameworks work with Zelkor?',
        a: 'Zelkor runs applications built with LangGraph, LangChain, and Deep Agents. You bring the graph you already wrote, and Zelkor serves its thread and run endpoints behind Envoy without asking you to rewrite your state machine. You can also bind MCP tools into the graph automatically at startup.',
      },
      {
        q: 'Does my entire agent pod have to run inside gVisor?',
        a: 'No. Your agent pod runs on the standard Kubernetes container runtime so your Python packages and native extensions work normally. Only untrusted Python execution is sent over MCP to a dedicated pool of three warm gVisor worker pods. Agent pods cannot dial those workers directly, and workers require an internal token from the MCP gateway.',
      },
      {
        q: 'How does Zelkor keep one tenant from reading another tenant’s data?',
        a: 'Every request is verified at the front door using a signed JWT—unsigned tokens or requests without a tenant claim are rejected. When the agent calls a tool over MCP, the gateway reads the tenant only from that verified user context and rejects any tenant ID passed by the model. Postgres runs read-only queries with the tenant set on the session for Row-Level Security, Qdrant injects a mandatory tenant filter, and S3 keys are prefixed by tenant.',
      },
      {
        q: 'How does Zelkor stop a looping agent or a leaked model key?',
        a: 'Agent pods never hold upstream API keys for OpenAI, Anthropic, or Bedrock; those keys stay in Kubernetes Secrets on Envoy AI Gateway. The gateway enforces a global request cap (50 requests per minute by default) and rejects extra calls before reaching the provider. You can also enable NVIDIA NeMo Guardrails on the gateway to inspect chat completions and fail closed on policy violations.',
      },
      {
        q: 'Do I need a specific CNI or a tracing SDK in my agent code?',
        a: 'Neither. Network lockdown uses standard Kubernetes NetworkPolicy, so it works with the CNI you already run. Tracing is handled at the runtime and gateway layer and sent to self-hosted Langfuse inside your cluster, with no SDK imports required in your graph and no prompt bodies or keys written to default logs.',
      },
      {
        q: 'Is Enterprise a separate product with locked security features?',
        a: 'No. Every security control in Zelkor—including the gVisor sandbox pool, AI gateway key custody, NeMo Guardrails, MCP tenant enforcement, NetworkPolicy, and self-hosted Langfuse—is included in Community Edition. Enterprise is a direct architecture advisory engagement where our engineers help you integrate Zelkor with your cluster ingress, identity provider, Postgres RLS policies, and compliance sign-off.',
      },
    ],
    finalHeadline: 'Run your agents inside hard Kubernetes boundaries.',
    finalSub: 'Install the open-source Helm chart into your cluster, or book an architecture review to map Zelkor to your network, identity, and database setup.',
    finalPrimary: { label: 'Deploy on Kubernetes', href: '/docs/quickstart' },
    finalSecondary: { label: 'Book Architecture Review', href: '/contact' },
  },
}
