# Legal redline example

You get to bring the agent you already wrote. Zelkor sandboxes it — it can't break out, reach unauthorized data or networks, its prompts are verified, budget controlled, and it is under observation. Tenants stay isolated. You declare a model, a tool, and an agent, and those same objects run from laptop to production.

Editions are layers on that sandbox: Community Edition is the self-hosted runtime; Pro adds SSO, team controls (budgets and approvals), and production HA / GitOps; Enterprise adds isolation and compliance on Pro (hardware sandbox, mTLS, retained audit, HIPAA-ready safeguards).

**Original Case:** This example demonstrates a single-pass clause review agent. The house contract is a small plain-text file in object storage. The sandbox prints a decision (accept/reject/modify) based on hardcoded rules. The model then writes only the comment for the lawyer, respecting the sandbox's decision. 

One ClusterIP graph, `legal-redline`, reviews a single counterparty sentence. This chart is not part of the platform install. Deploy it after Zelkor is already running.

## Deploy

Build the image, then install the chart against your platform release.

```bash
IMAGES=zelkor-example-legal-redline IMAGE_TAG=2.3.1 ./scripts/build-images.sh --push
helm dependency update examples/legal-redline/chart
helm upgrade --install legal-redline examples/legal-redline/chart \
  --namespace <platform-namespace> \
  --set legalRedline.platform.releaseName=<platform-release> \
  --set legalRedline.sharedRoute.host=<agents-host> \
  --set platform.releaseName=<platform-release> \
  --set objectStore.endpoint=http://<platform-release>-seaweedfs:8333 \
  --set objectStore.bucket=<object-bucket> \
  --set objectStore.accessKey=<object-access-key> \
  --set objectStore.secretKey=<object-secret-key>
```

On the platform release, enable object MCP and point it at the same object store. Platform `objectMCP.enabled` stays false until you apply this example's overlay.

```bash
helm upgrade <platform-release> charts/zelkor-platform \
  --namespace <platform-namespace> \
  --reuse-values \
  -f examples/legal-redline/chart/values-platform-overlay.yaml \
  --set workspace.tools.objectMCP.s3.endpoint=http://<platform-release>-seaweedfs:8333 \
  --set workspace.tools.objectMCP.s3.bucket=<object-bucket> \
  --set workspace.tools.objectMCP.s3.auth.accessKey=<object-access-key> \
  --set workspace.tools.objectMCP.s3.auth.secretKey=<object-secret-key> \
  --set seaweedfs.objectIdentity.accessKey=<object-access-key> \
  --set seaweedfs.objectIdentity.secretKey=<object-secret-key>
```

`seaweedfs.objectIdentity` must be a different access key than `seaweedfs.auth`. Reusing the admin key scopes that key to the object bucket and Langfuse event uploads fail.

Clients call the platform Agent Protocol host with `X-Graph-ID: legal-redline`. Do not put a provider key on the worker. Seed tenants are `harborline-freight` and `brightpath-clinics`. The fixture is not legal advice.
