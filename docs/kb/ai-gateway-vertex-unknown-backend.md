# AI Gateway: Vertex `gemini-*` returns 500 `unknown backend`

## Symptom

- `POST /v1/chat/completions` with `model` matching `gemini-*` returns **500** (body may be generic `server_error`).
- Envoy access log `response_code_details` includes `ext_proc_error` and text like `unknown backend: …/zelkor-platform-backend-vertex/route/…`.
- Other models on the same gateway (for example Ollama Cloud) still return **200**.
- `AIServiceBackend` for Vertex may show **Accepted** even while requests fail.

## Cause

Envoy AI Gateway builds the dataplane backend list from `BackendSecurityPolicy` auth. For Vertex with a service-account file, the controller must mint a token into Secret `ai-eg-bsp-<backend-security-policy-name>` (key `gcpAccessToken`). If rotation fails, the controller **skips** the Vertex backend in filter config while the route still references it — ext_proc then reports **unknown backend**.

Common rotation failures:

- Secret referenced by `existingSecret` lacks key **`service_account.json`** (wrong key name).
- Invalid, revoked, or deleted GCP service account key JSON.
- GCP OAuth error such as `invalid_grant` / `account not found` on the `BackendSecurityPolicy` status.

## Confirm

Run against your platform namespace (example: `zelkor`):

```bash
kubectl -n zelkor get secret <vertex-existingSecret> -o go-template='{{range $k,$v := .data}}{{$k}}{{"\n"}}{{end}}'
```

Expect `service_account.json`.

```bash
kubectl -n zelkor get secret ai-eg-bsp-<release>-vertex-gcp -o go-template='{{range $k,$v := .data}}{{$k}}{{"\n"}}{{end}}'
```

Expect `gcpAccessToken`. If the Secret is missing, rotation never succeeded.

```bash
kubectl -n zelkor get backendsecuritypolicy <release>-vertex-gcp -o yaml
```

Check `status.conditions` for `ReconciliationFailed` and the rotation error message.

Search AI Gateway controller logs for `vertex-gcp`, `service_account`, or `Skipping this backend`.

## Fix

1. Create a valid GCP service account key JSON for the project in `workspace.models.providers.vertex.project`.
2. Recreate the Secret with the required key name (no pod restart required):

```bash
kubectl -n zelkor create secret generic zelkor-platform-vertex-sa \
  --from-file=service_account.json=./sa.json \
  --dry-run=client -o yaml | kubectl apply -f -
```

3. Wait until `BackendSecurityPolicy` is **Accepted** and `ai-eg-bsp-*-vertex-gcp` contains `gcpAccessToken`.
4. Retry `POST /v1/chat/completions` with `model: gemini-2.5-flash` (or your configured id).

**Alternatives:** set `workspace.models.providers.vertex.credentialsJson` in Helm instead of `existingSecret`, or leave both empty for ADC / Workload Identity on GKE.

## See also

- [Adding LLM providers and models — Vertex credentials](../adding-llm-providers-and-models.md#vertex-credentials)
