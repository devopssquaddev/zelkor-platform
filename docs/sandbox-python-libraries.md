---
title: Add Python libraries to the sandbox
description: Install private packages and pinned wheels into the gVisor sandbox worker image.
type: how-to
sidebar_group: Agents
sidebar_order: 35
audience: both
edition: ce
---

# Add Python libraries to the sandbox

The stock sandbox worker includes **pandas** and **numpy**. It has no outbound network. Install extra libraries in an image you build `FROM` that worker, then set that image on the warm pool. Every call uses environment `python-base`. Libraries come from `workspace.tools.sandboxMCP.workerImage`.

The worked copy is [examples/sandbox-python](../examples/sandbox-python/README.md): private package `desk_risk` plus `python-dateutil==4.0.0` and `tzdata==2026.6`.

## Prerequisites

- A running platform release.
- Docker. Push the image to a registry the nodes pull, or load it onto the nodes.
- Helm access to that platform release.

## Build the image

From the platform repository, with the same tag as the worker you extend:

```bash
IMAGES=zelkor-example-sandbox-python IMAGE_TAG=2.4.2 ./scripts/build-images.sh --push
```

Your own library uses the same Dockerfile shape: `FROM` the sandbox worker, `pip install` pinned requirements, then `pip install` the private package, and leave the process as uid `1000`.

## Point the pool at it

```bash
helm upgrade <platform-release> charts/zelkor-platform \
  --namespace <platform-namespace> \
  --reuse-values \
  -f examples/sandbox-python/values-platform-overlay.yaml
kubectl -n <platform-namespace> rollout status deploy/<platform-release>-mcp-sandbox-worker-0
```

`workspace.tools.sandboxMCP.workerImage` is the only knob. The overlay tag is `2.4.2`. If the running workers use another tag, set `workerImage.tag` to that tag before the upgrade. pandas and numpy remain, because the example image starts from the stock worker.

## Confirm

```bash
kubectl -n <platform-namespace> exec deploy/<platform-release>-mcp-sandbox-worker-0 -- \
  python -c "import desk_risk; from datetime import date; print(desk_risk.herfindahl({'AAPL': 40, 'MSFT': 30, 'GOOGL': 30})); print(desk_risk.next_review(date(2026, 11, 5)))"
```

Expect `0.34` and `2027-11-05`. An agent uses the same import in `sandbox__execute_python`. A Deep Agent passes the program as `execute(command=...)`.

Native extensions must match Python 3.14. If the process needs more than the worker memory limit (`512Mi`), raise `workspace.tools.sandboxMCP.worker` memory on the same upgrade.

To restore the stock worker, set `workerImage.repository` back to `ghcr.io/devopssquaddev/zelkor-sandbox-worker` and the tag you run. `--reuse-values` keeps the example repository until you do.
