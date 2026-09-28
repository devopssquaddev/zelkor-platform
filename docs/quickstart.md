# Local Quickstart

Deploy Zelkor Community Edition locally on your laptop using `kind`. This guide gets you a fully functional, self-hosted agentic runtime in under 5 minutes.

For an existing cluster (no kind), use `./scripts/install-quickstart.sh` — see [Existing Cluster Deployment](helm-install.md). For production, see [Production Deployment](production.md).

## Prerequisites

- macOS (Docker Desktop / OrbStack), Linux, or Windows (WSL2)
- [Docker](https://docs.docker.com/get-docker/) **installed and running** (Desktop or Engine — start it before running the install script)
- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [Helm](https://helm.sh/docs/intro/install/) 3.x
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- **One LLM provider API key** (e.g., OpenAI, Anthropic, Gemini)

## Installation

Clone the repository and run the install script, providing your LLM API key as an environment variable.

```bash
git clone https://github.com/devopssquaddev/zelkor-platform.git
cd zelkor-platform

# Example using OpenAI (Recommended)
OPENAI_API_KEY="sk-..." ./install.sh
```

**Supported Providers:**

| Provider | Install Command | Default Model |
| :--- | :--- | :--- |
| **OpenAI** | `OPENAI_API_KEY="sk-..." ./install.sh` | `openai/gpt-4o-mini` |
| **Anthropic** | `ANTHROPIC_API_KEY="sk-ant-..." ./install.sh` | `anthropic/claude-3-5-sonnet` |
| **Gemini** | `GEMINI_API_KEY="..." ./install.sh` | `gemini/gemini-2.0-flash` |
| **Ollama Cloud** | `OLLAMA_API_KEY="..." ./install.sh` | `gpt-oss:20b` |
| **Ollama Local** | `OLLAMA_LOCAL_HOST="http://host.docker.internal:11434" ./install.sh` | `ollama/llama3.2` |
| **vLLM** | `VLLM_BACKEND_URL="http://host:8000/v1" ./install.sh` | `vllm/default` |
| **Azure OpenAI** | `AZURE_OPENAI_API_KEY="..." AZURE_OPENAI_ENDPOINT="https://res.openai.azure.com" ./install.sh` | `azure/gpt-4o-mini` |
| **AWS Bedrock** | `AWS_ACCESS_KEY_ID="..." AWS_SECRET_ACCESS_KEY="..." AWS_REGION="us-east-1" ./install.sh` | `bedrock/amazon.titan-text-lite-v1` |
| **Vertex AI** | `VERTEX_PROJECT="..." VERTEX_REGION="us-central1" ./install.sh` | `gemini-2.0-flash` (use `vertex/gemini-*` only when AI Studio `GEMINI_API_KEY` is also set) |
| **Cohere** | `COHERE_API_KEY="..." ./install.sh` | `cohere/command-r` |

*Note: The script will first download necessary container images before starting the installation timer.*

## Verifying Access

Once the installation completes, you can verify the deployment:

```bash
kubectl --context kind-zelkor get pods -A
helm --kube-context kind-zelkor list
```

All services and Web UIs are accessible via the Kubernetes Gateway API on port `8088`:

| Component | URL | Auth |
| :--- | :--- | :--- |
| **Langfuse Observability** | [http://langfuse.localhost:8088](http://langfuse.localhost:8088) | Admin user/password from `profiles/values-local.yaml` (kind overlay only) |
| **Envoy AI Gateway** | [http://ai-gateway.localhost:8088](http://ai-gateway.localhost:8088) | `Authorization: Bearer <consumerKey>` — `workspace.models.consumerKey` in the kind overlay (gateway credential, not tenant identity) |
| **Agent Protocol** | [http://agents.localhost:8088](http://agents.localhost:8088) | `Authorization: Bearer <tenant JWT>` — mint with `zelkor token mint` (see below) |
| **MCP (Envoy MCPRoute)** | [http://mcp.localhost:8088/mcp](http://mcp.localhost:8088/mcp) | Same tenant JWT as Agent Protocol |

Kind installs enable **`platform.tenants.jwt.localSigning`** in `profiles/values-local.yaml` (applied by `./install.sh`). That is lab-only; production uses your IdP JWKS via `install-production.sh` (`--jwt-issuer`, `--jwks-file`, `--jwt-audience`). Agents reach native tools at in-cluster `http://<release>-mcp` (`MCP_URL`); the public MCP host above is optional debugging.

### Mint a tenant JWT (kind)

```bash
pip install -e ./cli
export AUTH_JWT_ISSUER=https://local.zelkor.invalid
TOKEN=$(zelkor token mint --release zelkor-platform --tenant seed --namespace default --context kind-zelkor)
```

Use `--tenant` matching your workload (`seed` is the default lab tenant in the kind overlay). Set `--namespace` to the namespace where you installed the platform release.

### Quick Test

Test the AI Gateway with the overlay consumer key only (no tenant header). Harmful prompts are refused by NeMo Guardrails on the default route:

```bash
curl -X POST http://ai-gateway.localhost:8088/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-key" \
  -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"Hello from Zelkor!"}]}'
```

*(Replace `dev-key` with your overlay `workspace.models.consumerKey` if you changed it. Ensure the `model` matches your provider.)*

Call MCP or Agent Protocol with the minted JWT:

```bash
curl -sS http://mcp.localhost:8088/mcp \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Deploying an Agent

Zelkor includes a CLI to easily deploy your own agents.

```bash
# Install the CLI
pip install -e ./cli

# Configure the environment
zelkor env add local --kube-context kind-zelkor --namespace default

# Initialize a new agent project
zelkor init my-agent
cd my-agent

# Deploy to the cluster
zelkor deploy

# Run the agent
zelkor run --input "hello"

# View logs
zelkor logs --no-follow --tail 50

# Remove the agent
zelkor undeploy
```

`zelkor deploy` copies the platform Postgres and Valkey URLs. Do not provision a new database for the agent. Isolation between agents is `redis.prefix` on the shared Valkey. If CI already builds the image, use a Helm overlay with `platform.releaseName` instead of `zelkor deploy` — [agent-deploy.md](agent-deploy.md#cli-vs-gitops). Persistence: [agent-deploy.md](agent-deploy.md#persistence-do-not-provision-a-database).

## Uninstalling

On an existing (non-kind) cluster use `./scripts/uninstall.sh` — see [Existing Cluster Deployment](helm-install.md). To remove a local kind cluster and all data:

```bash
helm --kube-context kind-zelkor uninstall finserve --ignore-not-found
helm --kube-context kind-zelkor uninstall zelkor-platform --ignore-not-found
kind delete cluster --name zelkor
```

---

## Advanced Configuration

### Installation Profiles

The install script uses a "fast" profile by default. You can upgrade an existing installation to the "full" profile, which includes NetworkPolicies, Langfuse evaluator seeds, and DEBUG logging.

```bash
# Run on an existing cluster that was installed with the default profile
INSTALL_PROFILE=full OPENAI_API_KEY="..." ./install.sh
```

### Installation Options

You can customize the installation behavior using environment variables:

- `PREFETCH_IMAGES=false`: Skip the initial image download phase (kubelet pulls on demand).
- `LOCAL_REGISTRY=false`: Pull directly from upstream registries instead of using local proxies.
- `INSTALL_STRICT=true`: Exit non-zero if any component degrades during installation.
- `INSTALL_EXAMPLES=false`: Skip installing the FinServe demo application.
- `RUN_DEMO_TOUR=false`: Skip the automated FinServe e2e smoke tests.
- `DEFAULT_LLM_MODEL="..."`: Override the default model for your provider.

### Bring Your Own MCP (SaaS)

Zelkor native MCP provides infrastructure tools (Postgres, Qdrant, sandbox). To connect SaaS tools (ServiceNow, Jira, etc.):

1. Deploy your MCP image as a ClusterIP workload in the cluster.
2. Register it in your local values overlay (`profiles/values-local.yaml`) under `workspace.tools.extraBackends`.

Full recipes (bearer auth, private CA, egress CIDRs): [mcp-extra-backends.md](mcp-extra-backends.md).

```yaml
workspace:
  tools:
    extraBackends:
      - name: acme
        url: http://acme-mcp-servicenow.acme-tools.svc:8080
```
