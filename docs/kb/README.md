# Knowledge base

Short articles for a **specific symptom** (error text, HTTP status, one failing path). Use these when the happy path in [adding-llm-providers-and-models.md](../adding-llm-providers-and-models.md) or [agent-install.md](../agent-install.md) is not enough.

General rules that apply to every install stay in the main `docs/` guides. Add a KB article when the fix is narrow but the failure mode is easy to misread as a platform bug.

## Index

| Article | Symptom |
| :--- | :--- |
| [ai-gateway-vertex-unknown-backend.md](ai-gateway-vertex-unknown-backend.md) | `POST /v1/chat/completions` with `gemini-*` returns 500; access log `unknown backend` for `*-backend-vertex` |
