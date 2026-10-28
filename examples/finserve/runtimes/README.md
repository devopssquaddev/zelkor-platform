# FinServe on other runtimes

The FinServe advisor and quant as deploy-first agents (`agent.json` + `AGENTS.md`), so the same agent runs on CrewAI, Pydantic AI or OpenCode behind `zelkor-sidecar`. Install the FinServe chart first: it seeds the tenant portfolios these agents query.

| Folder | Same as Aegra graph | `--tools` |
| :--- | :--- | :--- |
| `advisor/` | `finserve-advisor` | `postgres` |
| `quant/` | `finserve-quant` | `sandbox` |

## Deploy

Give each runtime its own graph id so it sits next to the Aegra agents:

```bash
cd examples/finserve/runtimes
zelkor deploy advisor --runtime a2a --a2a-framework crewai --tools postgres --graph-id finserve-advisor-crewai
zelkor deploy advisor --runtime a2a --tools postgres --graph-id finserve-advisor-pydantic-ai
zelkor deploy advisor --runtime opencode --tools postgres --graph-id finserve-advisor-opencode
zelkor deploy quant --runtime a2a --a2a-framework crewai --tools sandbox --graph-id finserve-quant-crewai
zelkor deploy quant --runtime a2a --tools sandbox --graph-id finserve-quant-pydantic-ai
zelkor deploy quant --runtime opencode --tools sandbox --graph-id finserve-quant-opencode
```

Clients call the same agents endpoint with the same tenant token; only `X-Graph-ID` changes.

## Test

The FinServe tenant-isolation and sandbox smokes take the graph id from env:

```bash
FINSERVE_GRAPH_ADVISOR=finserve-advisor-crewai FINSERVE_GRAPH_QUANT=finserve-quant-crewai \
  pytest examples/finserve/tests/test_base02_tenant_isolation.py \
         examples/finserve/tests/test_base03_gvisor_sandbox.py -k "not coder"
```

## Differences from the Aegra agents

- **Tool scope is per backend.** `--tools postgres` allows every `postgres__*` tool; the Aegra graph allows only `postgres__query`. Tenant rows are still limited by the database, not the prompt.
- **The prompt is the agent.** The LangChain code in `chart/files/*_agent.py` is not reused; `AGENTS.md` carries the same instructions.
