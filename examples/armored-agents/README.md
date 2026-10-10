# Armored catalog

This catalog demonstrates running unmodified, complex open-source agents (like autonomous researchers or coding assistants) as worker overlays on Zelkor. These original cases showcase how Zelkor secures real-world, third-party workloads without requiring you to rewrite their core logic.

Zelkor CE must already be installed. Docker must be on PATH. The worker pod uses gVisor. Model keys stay on the AI Gateway. Each run is one Langfuse waterfall.

```bash
zelkor deploy -f examples/armored-agents/gpt-researcher/values.yaml
zelkor run --graph-id gpt-researcher --input "Summarize the latest gVisor isolation model"
```

`deploy -f` builds the sibling Dockerfile, kind-loads on kind, or pushes when `--registry` / `ZELKOR_IMAGE_REGISTRY` is set. `ZELKOR_SKIP_BUILD=1` skips the build when the image is already in the registry. This catalog is not installed with `./install.sh`.

| Overlay | Original Case | Upstream | Version & License |
| :--- | :--- | :--- | :--- |
| [gpt-researcher](gpt-researcher/README.md) | Autonomous online research and comprehensive report generation | [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) (`deep_agents/`) | `v3.7.0` (Apache-2.0) |

See [Deploy an Agent](../../docs/agent-deploy.md).
