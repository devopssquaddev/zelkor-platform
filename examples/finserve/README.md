# FinServe AI: Multi-Tenant Wealth Management Reference Agent

FinServe AI is the reference application for the **Zelkor Platform**. It demonstrates how to build and operate multi-tenant, compliance-ready AI agents with native guardrails, vector memory, untrusted code sandboxing, policy-governed LLM routing, and full OpenTelemetry tracing.

---

## 1. Capabilities & Platform Pillars

| Pillar | Implementation in FinServe AI | Platform Subsystem |
| :--- | :--- | :--- |
| **Conversational Guardrails** | Rejects off-topic, chit-chat, and out-of-domain queries | **NeMo Guardrails CPU** (FastAPI / Colang) |
| **Multi-Tenant Isolation** | Scopes relational records (`portfolios`) and vector policies (`finserve_policies`) by `tenant_id` | **PostgreSQL** + **Qdrant** |
| **Untrusted Code Execution** | Executes arbitrary quantitative calculations & projections in user-space isolation | **gVisor** (`RuntimeClass: gvisor`) |
| **Policy-Governed LLM Routing** | Standardized OpenAI-compatible inference with consumer key and rate-limit policies | **Envoy AI Gateway** (`/v1/chat/completions`) |
| **Full-Stack Observability** | Ingests multi-span execution waterfalls, token usage, and security tags | **Langfuse v2** (`/api/public/ingestion`) |
| **Stateful Orchestration** | FinServe LangGraph (`files/finserve_agent.py`, graph id `finserve`) | **Aegra** (`aegra-api`; platform ships no graphs) |

---

## 2. Architecture Diagram

```mermaid
flowchart TD
    UserAlpha["User (Bank_Alpha)"]
    UserBeta["User (Bank_Beta)"]
    
    subgraph platform ["Zelkor Platform"]
        Gateway["Envoy Gateway (HTTPRoute: finserve.localhost)"]
        Agent["FinServe graph (example chart; in-process until Aegra registration)"]
        NeMo["NeMo Guardrails CPU (Topic Boundary)"]
        AIGateway["Envoy AI Gateway (LLM Router)"]
        Aegra["Aegra (Agent Protocol, empty graphs)"]
        Postgres[("PostgreSQL (Portfolios)")]
        Qdrant[("Qdrant (Semantic Policies)")]
        Langfuse["Langfuse v2 (Telemetry & Prompts)"]
        
        subgraph sandbox ["Untrusted Execution"]
            CodeExec["Code Executor (gVisor Sentry)"]
        end
    end

    UserAlpha --> Gateway
    UserBeta --> Gateway
    Gateway --> Agent
    
    Agent -->|"1. Guardrails Check"| NeMo
    Agent -->|"2. MCP postgres"| Postgres
    Agent -->|"3. MCP qdrant"| Qdrant
    Agent -->|"4. Sandboxed Python"| CodeExec
    Agent -->|"5. Chat Completions"| AIGateway
    Agent -.->|"graph not registered yet"| Aegra
    Agent -.->|"OTel Spans & Tags"| Langfuse
```

---

## 3. Quickstart & Usage

### A. Deploy via Helm

FinServe is packaged as a standalone Helm release in `examples/finserve/chart`:

```bash
helm upgrade --install finserve examples/finserve/chart \
  -f examples/finserve/chart/values-local.yaml \
  --wait --timeout 10m
```

### B. Querying the Agent via Gateway API

Execute queries using either `Authorization: Bearer dev:<tenant_id>` or `X-Tenant-ID`:

```bash
# Query Bank_Alpha portfolio holdings
curl -X POST http://127.0.0.1:8088/runs/stream \
  -H "Host: finserve.localhost" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev:Bank_Alpha" \
  -d '{
    "assistant_id": "finserve_agent",
    "input": {
      "messages": [{"role": "user", "content": "What is our asset allocation policy for high-growth tech?"}]
    }
  }'
```

```bash
# Execute sandboxed financial projection on gVisor
curl -X POST http://127.0.0.1:8088/runs/stream \
  -H "Host: finserve.localhost" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev:Bank_Alpha" \
  -d '{
    "assistant_id": "finserve_agent",
    "input": {
      "messages": [{"role": "user", "content": "Predict my portfolio growth over 5 years assuming 7% variance."}]
    }
  }'
```

---

## 4. Observability & Tracing

Open the Langfuse UI at [http://langfuse.localhost:8088](http://langfuse.localhost:8088) (`admin@zelkor.local` / `zelkor-dev-password`) to inspect live traces under the **FinServe AI** project:

- `nemo_guardrails_input_check`: Topic moderation latency and refusal status.
- `query_database_postgres`: Parameterized SQL query execution and record count.
- `search_policies_qdrant`: Semantic vector similarity scores and matched policy payloads.
- `execute_code_gvisor`: Sandboxed subprocess stdout, stderr, and container escape containment status.
- `ai_gateway_llm_chat`: Upstream model latency, token counts, and completion responses.

---

## 5. Automated Validation Matrix

Gate A validation is split across two layers:

```bash
# Platform conformance (MCP, NeMo, gVisor)
pytest tests/test_mcp_postgres.py tests/test_mcp_qdrant.py tests/test_mcp_sandbox.py tests/test_nemo_guardrails.py tests/test_mcp_gateway.py -v

# FinServe E2E smokes
pytest examples/finserve/tests/ -v
```

| Layer | Location | Coverage |
| :--- | :--- | :--- |
| Platform Gate | `tests/test_mcp_*.py`, `tests/test_nemo_guardrails.py` | Direct MCP tenant SQL, Qdrant isolation, gVisor sandbox, NeMo guardrails |
| FinServe E2E | `examples/finserve/tests/test_base*.py` | Agent `/runs/stream` smokes (200, tenant_id, guardrails, traces) |

---

## 6. Native MCP Architecture (Implemented)

FinServe is a **LangGraph ReAct agent** that discovers tools from the unified MCP gateway and lets the LLM choose calls via OpenAI-style tool calling (`MCP_URL`):

- `postgres__query` — read-only SQL; FinServe passes `WHERE tenant_id = %s`
- `qdrant__search_documents` — tenant payload-filtered vector search (`finserve_policies` via overlay)
- `sandbox__execute_python` — gVisor warm pool code execution

Input guardrails delegate to platform NeMo only (no agent-side topic regex). Sandbox workers run as platform `mcp-sandbox-worker` pods (`RuntimeClass: gvisor`).