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
| `selfCheck.model` | Model id for the yes/no self-check rails. Empty uses the NeMo model (`workspace.policies.nemo.model`, then `workspace.models.defaultModel`). Use a model id your AI Gateway routes. |
| `safetyRefusal` | Text returned when a rail blocks a request. |

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
