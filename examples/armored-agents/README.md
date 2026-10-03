# Armored catalog

Bring an agent you already wrote. Zelkor sandboxes it — it can't break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation.

Unmodified company-shaped agents as worker overlays. Zelkor CE must already be installed. Docker must be on PATH. The worker pod uses gVisor. Model keys stay on the AI Gateway. Each run is one Langfuse waterfall.

```bash
zelkor deploy -f examples/armored-agents/gpt-researcher/values.yaml
zelkor run --graph-id gpt-researcher --input "Summarize the latest gVisor isolation model"
```

`deploy -f` builds the sibling Dockerfile, kind-loads on kind, or pushes when `--registry` / `ZELKOR_IMAGE_REGISTRY` is set. `ZELKOR_SKIP_BUILD=1` skips the build when the image is already in the registry. This catalog is not installed with `./install.sh`.

| Overlay | Upstream |
| :--- | :--- |
| [gpt-researcher](gpt-researcher/README.md) | GPT Researcher `deep_agents/` |

See [Deploy an Agent](../../docs/agent-deploy.md).
