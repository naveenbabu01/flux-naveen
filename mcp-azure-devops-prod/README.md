# MCP Azure DevOps Server — Production (AKS Deployment)

Production-ready MCP server deployed on AKS with:
- **DefaultAzureCredential** (Managed Identity on AKS, `az login` locally)
- **Azure Key Vault** for GitHub/Jira secrets
- **HTTP/SSE transport** (accessible by multiple team members)
- **Kubernetes manifests** for AKS deployment
- **Helm chart** for parameterized deployment
- **Health checks** and structured logging

## Architecture

```
┌──────────────────┐       HTTPS/SSE       ┌─────────────────────────────┐
│  Claude Desktop  │ ◄───────────────────► │  MCP Server (AKS Pod)       │
│  (Team members)  │                       │  + Managed Identity          │
└──────────────────┘                       │  + Key Vault secrets         │
                                           └──────────────┬──────────────┘
                                                          │
                                    ┌─────────────────────┼──────────────────┐
                                    │                     │                  │
                                    ▼                     ▼                  ▼
                              AKS K8s API          GitHub/Jira API    Azure Monitor
                           (Managed Identity)     (Key Vault secrets) (Managed Identity)
```

## Quick Start (Local Dev)

```bash
# Uses az login — no secrets needed
az login
pip install -r requirements.txt
python src/server.py --transport http --port 8000
```

## Deploy to AKS

```bash
# 1. Build and push image
az acr build --registry pythonacrtest --image mcp-server-prod:latest .

# 2. Deploy to AKS
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/

# 3. Verify
kubectl get pods -n mcp-server
```

## Environment Variables

| Variable | Source | Required |
|----------|--------|----------|
| `AZURE_SUBSCRIPTION_ID` | Env / ConfigMap | Yes |
| `AKS_RESOURCE_GROUP` | Env / ConfigMap | Yes |
| `AKS_CLUSTER_NAME` | Env / ConfigMap | Yes |
| `KEY_VAULT_NAME` | Env / ConfigMap | Yes |
| `TRANSPORT` | Env (http/stdio) | No (default: http) |
| `PORT` | Env | No (default: 8000) |

Secrets (GitHub token, Jira token) are fetched from Azure Key Vault at runtime.
