# Runtime examples

Minimal deploy-first agents (`agent.json` + `AGENTS.md`) for the non-Aegra runtimes. Each runs behind `zelkor-sidecar`, which handles tenant auth, threads and the agent's only egress (AI Gateway and MCP gateway).

| Folder | Runtime | Deploy |
| :--- | :--- | :--- |
| `pydantic-ai/` | Pydantic AI over A2A | `zelkor deploy --runtime a2a --tools postgres,sandbox` |
| `crewai/` | CrewAI over A2A | `zelkor deploy --runtime a2a --a2a-framework crewai --tools postgres,sandbox` |
| `opencode/` | OpenCode | `zelkor deploy --runtime opencode --tools postgres,sandbox` |

The model is the platform default (`DEFAULT_LLM_MODEL`). See [Choose a runtime](../../docs/agent-deploy.md#choose-a-runtime).

For FinServe's advisor and quant on these runtimes, see [examples/finserve/runtimes](../finserve/runtimes/README.md).
