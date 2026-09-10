# zelkor CLI

```bash
pip install -e ./cli
zelkor --help
```

One packager for LangGraph / Aegra and Deep Agents. Named envs are kubecontext + namespace only — no hosts, tokens, or DSNs in the env file.

Requires a live Zelkor platform (`./install.sh` on kind, or [Path B](../docs/path-b.md) on customer Kubernetes). Does not install the platform.

```bash
zelkor init my-agent
zelkor deploy
zelkor run --input "hello"
zelkor logs --no-follow --tail 50
zelkor undeploy
```
