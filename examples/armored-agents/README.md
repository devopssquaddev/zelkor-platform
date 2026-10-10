# Armored catalog

You get to bring the agent you already wrote. Zelkor sandboxes it — it can't break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation. Tenants stay isolated. You declare a model, a tool, and an agent, and those same objects run from laptop to production.

Editions are layers on that sandbox: Community Edition is the self-hosted runtime; Pro adds SSO, team controls (budgets and approvals), and production HA / GitOps; Enterprise adds isolation and compliance on Pro (hardware sandbox, mTLS, retained audit, HIPAA-ready safeguards).

This catalog demonstrates running unmodified, complex open-source agents (like autonomous researchers or coding assistants) as worker overlays on Zelkor. These original cases showcase how Zelkor secures real-world, third-party workloads without requiring you to rewrite their core logic.

Zelkor CE must already be installed. Docker must be on PATH. The worker pod uses gVisor. Model keys stay on the AI Gateway. Each run is one Langfuse waterfall.

```bash
zelkor deploy -f examples/armored-agents/gpt-researcher/values.yaml
zelkor run --graph-id gpt-researcher --input "Summarize the latest gVisor isolation model"
```

`deploy -f` builds the sibling Dockerfile, kind-loads on kind, or pushes when `--registry` / `ZELKOR_IMAGE_REGISTRY` is set. `ZELKOR_SKIP_BUILD=1` skips the build when the image is already in the registry. This catalog is not installed with `./install.sh`.

| Overlay | Original Case | Upstream |
| :--- | :--- | :--- |
| [gpt-researcher](gpt-researcher/README.md) | Autonomous online research and comprehensive report generation | GPT Researcher `deep_agents/` |

See [Deploy an Agent](../../docs/agent-deploy.md).
