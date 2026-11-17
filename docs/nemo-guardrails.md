---
title: Customize NeMo Guardrails
description: Add custom safety policies and topical guardrails via Helm overlays.
type: how-to
sidebar_group: Agents
sidebar_order: 50
audience: both
edition: ce
---

# Customize NeMo Guardrails

Zelkor uses NVIDIA NeMo Guardrails to intercept and verify prompts and completions before they reach the model or the agent. The platform provides safe defaults, but you can add your own custom rails using Helm overlays.

## Configuration

Custom rails go in your platform values file under `workspace.policies.nemo`. The chart validates these keys against its schema; any other key under `nemo` fails the install.

| Key | What the chart does with it |
| :--- | :--- |
| `extraRailsConfig` | Merged under `rails.config` of the `content_safety` config (for example `regex_detection`). |
| `extraInputFlows` | Flow names appended to the input rails, after `self check input`. |
| `extraColang` | Colang text appended to the `content_safety` flows file. |
| `selfCheck.input` | `log` (default): check each prompt and log the verdict (`guardrail_verdict`) without refusing. `block`: refuse with `safetyRefusal`. `none`: skip the check. |
| `selfCheck.output` | Same values for the model's answer. Default `none`, because it adds a second model call to every request. |
| `selfCheck.timeoutMs` | Time limit per check (default `15000`). The input check runs before the answer, so a slow check delays the request by up to this long. A check with no verdict (timeout, error, unclear answer) logs `guardrail_unavailable` or `guardrail_unparseable`. |
| `selfCheck.onUnavailable` | What `block` mode does when a check has no verdict: `allow` (default) lets the request through, `block` refuses it. Ignored in `log` mode. |
| `selfCheck.model` | Model id for the self-check rails. Empty uses the NeMo model (`workspace.policies.nemo.model`, then `workspace.models.defaultModel`). Use a model id your AI Gateway routes. |
| `safetyRefusal` | Text returned when a rail blocks a request. |

The result of every check is on the check's own model call (`self_check_input <model>` or `self_check_output <model>`) as `zelkor.guardrail.mode` (`log` / `block`), `verdict` (`allow` / `block` / `none`), `status` (`ok` / `timeout` / `error` / `unparseable`), `enforced` (true only when the request was refused) and `latency_ms`, and in Langfuse as `guardrail_*` metadata, so you can filter for checks that would have blocked in `log` mode, or for timeouts. The guardrails request span (`POST /v1/chat/completions`) carries the same fields per side (`guardrail_input_mode`, `guardrail_input_verdict`, …), and a `guardrail self_check input` span repeats them. A check with no verdict makes its model call an error (level ERROR in Langfuse) whose status message says whether the request was allowed or refused, for example `self-check timeout; request allowed`. A 4xx answer from the guardrails service, such as a 429 rate limit, is also an error span with the message `HTTP 429`.

Create an overlay file (e.g., `my-nemo-overlay.yaml`). This one blocks off-topic requests with NeMo's built-in regex input rail:

```yaml
workspace:
  policies:
    nemo:
      extraInputFlows:
        - regex check input
      extraRailsConfig:
        regex_detection:
          input:
            case_insensitive: true
            patterns:
              - "\\bpoem\\b"
              - "\\bweather\\b"
```

## Apply the Overlay

Upgrade your platform Helm release to apply the new guardrails:

```bash
helm upgrade zelkor-platform charts/zelkor-platform \
  --namespace zelkor \
  --reuse-values \
  -f my-nemo-overlay.yaml
```

The NeMo interceptor will automatically reload its configuration. Any agent deployed on the platform will instantly inherit these new safety rails.
