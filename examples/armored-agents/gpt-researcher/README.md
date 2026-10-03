# GPT Researcher (deep agents)

Bring GPT Researcher's unmodified `deep_agents/` graph. Zelkor sandboxes the worker — it can't break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation.

The agent pod uses gVisor. LLM calls go through the in-cluster AI Gateway. Traces land in Langfuse.

## Prerequisites

- Zelkor CE installed; `zelkor env use` points at that cluster
- RuntimeClass `gvisor` on the cluster
- Image `ghcr.io/devopssquaddev/zelkor-armored-gpt-researcher` pullable (tag matches Chart `appVersion`, or `dev` in a lab)
- A Tavily key for web retrieval (private overlay; not in git)

## Deploy and run

```bash
zelkor deploy -f examples/armored-agents/gpt-researcher/values.yaml
zelkor run --graph-id gpt-researcher --input "Summarize the latest gVisor isolation model"
```

See [Deploy an Agent](../../../docs/agent-deploy.md).

## Tavily

GPT Researcher calls Tavily from the worker. Keep the key out of git. A private overlay:

```yaml
extraEnv:
  - name: TAVILY_API_KEY
    value: "<your-tavily-key>"
```

When platform NetworkPolicies are enabled, agent egress is in-cluster only. Web retrieval then fails until search is an in-cluster MCP extra backend.

## What Zelkor adds

`langgraph.json` and `graph.py` call unmodified `build_agent`. The wrap maps `DEFAULT_LLM_MODEL` (`openai/…`) to `openai:…` so the gateway intercepts `/v1`.
