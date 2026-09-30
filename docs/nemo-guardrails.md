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

Custom rails are configured in your platform values file under `workspace.policies.nemo`. You can supply Colang scripts and YAML configurations directly as multi-line strings.

Create an overlay file (e.g., `my-nemo-overlay.yaml`):

```yaml
workspace:
  policies:
    nemo:
      config:
        # Your custom Colang and YAML content goes here.
        # Do not dump massive Colang files directly into the values if they are complex;
        # keep them focused on critical topical or safety rails.
        "custom_rails.co": |
          define user ask about politics
            "What do you think about the election?"
            "Who are you voting for?"

          define flow politics
            user ask about politics
            bot refuse to respond about politics

          define bot refuse to respond about politics
            "I am a financial advisor agent. I cannot discuss politics."
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
