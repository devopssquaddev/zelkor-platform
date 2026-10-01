---
title: AI Gateway route not found
description: POST /v1/chat/completions returns 404 route_not_found after a Helm upgrade.
type: kb
sidebar_group: KB
sidebar_order: 22
audience: both
edition: ce
---

# AI Gateway: `404` `route_not_found` on `/v1/chat/completions`

## Symptom

- Agent chat fails. The worker log may only show `unhandled errors in a TaskGroup (1 sub-exception)`.
- Deeper in that log (or Envoy): `POST /v1/chat/completions` **404** `route_not_found`.
- `kubectl -n zelkor get aigatewayroute` is empty for the platform release.

## Cause

The chart renders `AIGatewayRoute` only when a provider credential is set. `helm upgrade -f overlay.yaml` with `workspace.models.providers.*.apiKey: ""` replaces a previous secret and deletes the route. Helm `--reuse-values` does not keep a key that the overlay explicitly clears.

## Confirm

```bash
kubectl -n zelkor get aigatewayroute,backend
helm get values zelkor-platform -n zelkor
```

Expect a backend and route for the provider you use. If `apiKey` (or `vllm.backendUrl` / `ollamaLocal.host`) is empty and `defaultModel` is set, Helm now fails at template time instead of shipping a dead gateway.

## Fix

1. Pass the credential again (do not commit it):

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  --set-file workspace.models.providers.openai.apiKey=./openai.key
```

Use the provider key you actually run (for example `ollamaCloud.apiKey`).

2. Keep secrets out of git overlays. Empty `apiKey: ""` in a file you `-f` on every upgrade will wipe the route.

3. Retry the agent call.

## See also

- [Add LLM providers and models](../adding-llm-providers-and-models.md)
