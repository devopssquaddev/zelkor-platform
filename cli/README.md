# zelkor CLI

```bash
pip install -e ./cli
zelkor --help
```

One packager for LangGraph / Aegra and Deep Agents. Named envs are kubecontext + namespace only — no hosts, tokens, or DSNs in the env file.

Requires a live Zelkor platform ([Local Quickstart](../docs/quickstart.md) or [Install on a cluster](../docs/helm-install.md)). Full command reference: [Use the zelkor CLI](../docs/cli.md). Does not install the platform.

```bash
zelkor init my-agent
zelkor deploy
zelkor run --input "hello"
zelkor logs --no-follow --tail 50
zelkor undeploy
```
