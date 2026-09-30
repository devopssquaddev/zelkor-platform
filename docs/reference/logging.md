---
title: Platform Logging
description: Stdout JSON log structure, levels, and environment variables.
type: reference
sidebar_group: Reference
sidebar_order: 50
audience: human
edition: all
---

# Platform Logging

All Zelkor platform components (Aegra, MCP servers, Envoy interceptors, and guardrails) emit structured JSON logs to `stdout`.

## Configuration

Logging is controlled via Helm values and injected as environment variables into the pods. 

```yaml
logging:
  level: INFO
  format: json
```

* `ZELKOR_LOG_LEVEL`: Controls the verbosity. Valid values are `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. The default is `INFO`.
* `ZELKOR_LOG_FORMAT`: Controls the output format. Valid values are `json` and `text`. The default is `json`.

> **Note:** The `text` format is intended only for local development via `profiles/values-local.yaml`. Production deployments should always use `json`.

## Security Guarantees

Zelkor enforces strict log hygiene to prevent data leaks:

* **Secrets:** Tokens, JWTs, API keys, and `Authorization` headers are never logged at `INFO` or higher.
* **Payloads:** Prompt bodies and model completions are not logged to stdout. (They are captured as OpenTelemetry traces and sent to Langfuse, which has its own retention and masking rules).
* **Health Probes:** Liveness and readiness probes are silenced at `INFO` level to prevent log spam.

## Troubleshooting with Logs

If a test or run fails, inspect the component logs for `ERROR` or `WARNING` lines. Unexpected `ERROR` logs indicate a system failure, such as an unreachable database, a failed MCP tool execution, or a crashed sandbox worker.

```bash
kubectl logs -n zelkor deploy/zelkor-platform-mcp
```
