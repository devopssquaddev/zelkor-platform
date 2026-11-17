---
title: Call HTTP APIs Without Giving Agents the Key
description: The gateway adds the API key and checks method and path; agents never hold the key.
type: how-to
sidebar_group: Agents
sidebar_order: 32
audience: both
edition: ce
---

# Call HTTP APIs Without Giving Agents the Key

*What you get: your agent calls a plain HTTP API, the gateway adds the API key, and the agent never sees the key. Each call is checked against your method and path rules. Anything you did not allow gets `403`.*

Works in both profiles ([full](quickstart.md) and [perimeter](perimeter.md)). For MCP servers, use [extra MCP backends](mcp-extra-backends.md) instead: `apiKey` injects their credential and `workspace.tools.policy.deny` restricts tools.

## Before you start

- The platform is installed with its AI gateway on (the default). The API relays use the same agent key as `/v1`.
- Your agent runs behind the Zelkor sidecar: deploy it with `zelkor deploy` on a perimeter platform, or with `zelkor deploy --egress-only` on a full one. Agents that run inside the platform's own Aegra host do not get the relay URLs.

## 1. Store the credential

The Secret's `credential` key holds the **whole header value**, exactly as the API expects it:

```bash
kubectl -n zelkor create secret generic github-api \
  --from-literal=credential="Bearer $GITHUB_TOKEN"
```

## 2. Declare the API and its rules

```yaml
workspace:
  tools:
    httpApis:
      - name: github
        url: https://api.github.com
        credential:
          secretRef: github-api
        rules:
          - action: Deny
            methods: [DELETE]
          - action: Allow
            methods: [GET]
            path: /repos/
          - action: Allow
            methods: [POST]
            path: {type: RegularExpression, value: "^/repos/[^/]+/[^/]+/issues$"}
```

```bash
helm upgrade zelkor-platform charts/zelkor-platform -n zelkor --reuse-values -f github-api.yaml
```

| Field | Meaning |
| :--- | :--- |
| `name` | Lower-case DNS label. The relay is `<release>-api-<name>`. |
| `url` | `http://` or `https://` base URL. A path (for example `/api/v2`) is prepended to every call. HTTPS uses the system CA bundle. |
| `credential.secretRef` | Secret in the platform namespace whose key `credential` is the header value. Optional. |
| `credential.header` | Header to set. Default `Authorization`. Whatever the caller sent in that header is replaced. |
| `rules` | Checked top to bottom; the first match decides. No match means `403`. At least one `Allow` is required. |
| `rules[].methods` | Upper-case HTTP methods. Empty means any method. |
| `rules[].path` | A string is a path prefix. Or `{type: Exact \| PathPrefix \| RegularExpression, value}`. Matched on the path the agent sent, without the query string. |

## 3. Deploy (or redeploy) the agent

```bash
zelkor deploy
```

The CLI reads the platform's APIs, and each one gets an environment variable in your agent container:

```python
import os, httpx

base = os.environ["ZELKOR_API_GITHUB_URL"]
issues = httpx.get(f"{base}/repos/acme/app/issues").json()
```

Send no key. The sidecar adds the agent's gateway key. The gateway checks the rules, swaps in the GitHub token, and forwards the call. A name such as `gh-enterprise` becomes `ZELKOR_API_GH_ENTERPRISE_URL`.

## Check it

| Call | Result |
| :--- | :--- |
| `GET $ZELKOR_API_GITHUB_URL/repos/acme/app` | GitHub's answer |
| `DELETE $ZELKOR_API_GITHUB_URL/repos/acme/app` | `403` from the gateway; GitHub never sees it |
| `GET $ZELKOR_API_GITHUB_URL/user` | `403` (no rule allows it) |
| Any call from a pod without the agent key | `401` |

`kubectl -n <agent-namespace> get secret github-api` returns `NotFound`: the token lives only in the platform namespace.

## Limits

- Rules see the method and path, not the request body.
- Every API is available to every sidecar-wrapped agent in the workspace. Per-team scoping and human approval of risky calls are not part of Community Edition.
