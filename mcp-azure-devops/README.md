# 🤖 Azure DevOps MCP Server

**Author:** Naveen Babu Mummadi  
**Stack:** Python 3.11 · MCP SDK · Azure SDK · Kubernetes Client · GitHub REST API

An MCP (Model Context Protocol) server that gives Claude native access to your
Azure AKS cluster, GitHub Actions pipelines, Azure Monitor, Cost Management, and Jira.

---

## 🗂️ Project Structure

```
mcp-azure-devops/
├── src/
│   ├── server.py               ← Main MCP server (entry point)
│   ├── tools/
│   │   ├── aks_tools.py        ← AKS pod status, restart, scale, logs
│   │   ├── github_tools.py     ← GitHub Actions pipeline tools
│   │   ├── azure_monitor.py    ← Azure Monitor alerts + App Insights
│   │   ├── cost_tools.py       ← Azure Cost Management
│   │   └── jira_tools.py       ← Jira incident tickets
│   └── utils/
│       ├── config.py           ← Environment variable loader
│       └── logger.py           ← Structured logging
├── tests/
│   └── test_tools.py           ← Unit tests with mocks
├── .github/
│   └── workflows/
│       └── mcp-ci.yml          ← CI: lint + test + docker build on every push
├── Dockerfile
├── requirements.txt
├── .env.example                ← Copy to .env and fill values
└── README.md
```

---

## ⚡ Quick Setup (5 steps)

### Step 1 — Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/mcp-azure-devops.git
cd mcp-azure-devops
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Step 2 — Create Azure Service Principal

```bash
# Login to Azure
az login

# Create service principal with Contributor role
az ad sp create-for-rbac \
  --name "mcp-devops-server" \
  --role Contributor \
  --scopes /subscriptions/YOUR_SUBSCRIPTION_ID \
  --output json
```
Copy the output `appId`, `password`, `tenant` into your `.env` file.

### Step 3 — Configure Environment

```bash
cp .env.example .env
# Edit .env with your real values
nano .env
```

### Step 4 — Test the Server Locally

```bash
# Run unit tests first
pytest tests/ -v

# Start the MCP server (stdio mode)
python src/server.py
```

### Step 5 — Connect to Claude Desktop

Add to your Claude Desktop config file:

**Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "azure-devops": {
      "command": "python",
      "args": ["/absolute/path/to/mcp-azure-devops/src/server.py"],
      "env": {
        "AZURE_SUBSCRIPTION_ID": "your-sub-id",
        "AZURE_TENANT_ID":       "your-tenant-id",
        "AZURE_CLIENT_ID":       "your-app-id",
        "AZURE_CLIENT_SECRET":   "your-password",
        "AKS_RESOURCE_GROUP":    "your-rg",
        "AKS_CLUSTER_NAME":      "your-cluster",
        "GITHUB_TOKEN":          "ghp_xxxx",
        "JIRA_URL":              "https://yourco.atlassian.net",
        "JIRA_EMAIL":            "naveen@yourco.com",
        "JIRA_API_TOKEN":        "your-jira-token"
      }
    }
  }
}
```

Restart Claude Desktop. You'll see a 🔌 icon confirming the MCP server is connected.

---

## 💬 Example Claude Prompts (after connecting)

Once connected, you can talk to Claude naturally:

```
"Show me all pods in the production namespace"
→ Calls: get_aks_pod_status(namespace="production")

"Why did the last GitHub Actions run fail on naveen/myapp?"
→ Calls: get_pipeline_status + get_failed_jobs

"Restart the api-gateway deployment in production"
→ Calls: restart_deployment(deployment="api-gateway", namespace="production")

"What's our Azure spend this week vs last week?"
→ Calls: get_cost_report + get_cost_anomalies

"Create a Critical Jira ticket — 3 pods are in CrashLoopBackOff"
→ Calls: create_incident_ticket(severity="Critical", ...)

"Show me all active Azure Monitor alerts in rg-production"
→ Calls: get_azure_alerts(resource_group="rg-production")

"Trigger the deploy.yml pipeline on main branch"
→ Calls: trigger_pipeline(repo="naveen/myapp", workflow="deploy.yml")
```

---

## 🛠️ Available Tools

| Tool | Description |
|---|---|
| `get_aks_pod_status` | Pod health, restarts, age, container status |
| `restart_deployment` | Rolling restart of a deployment |
| `scale_deployment` | Scale replicas up or down |
| `get_aks_events` | Warning events for failure diagnosis |
| `get_pod_logs` | Last N lines of pod logs |
| `get_pipeline_status` | Recent GitHub Actions workflow runs |
| `get_pipeline_logs` | Full logs from a specific run |
| `trigger_pipeline` | Manually trigger a workflow |
| `get_failed_jobs` | Failed jobs + steps breakdown |
| `get_azure_alerts` | Active Azure Monitor alerts by severity |
| `get_app_insights_errors` | Top exceptions from App Insights |
| `get_cost_report` | Azure spend grouped by service |
| `get_cost_anomalies` | Detect cost spikes vs prior period |
| `create_incident_ticket` | Create Jira incident with severity + priority |
| `get_open_incidents` | List open Jira incidents |

---

## 🐳 Docker

```bash
# Build
docker build -t mcp-azure-devops .

# Run (pass env vars)
docker run --rm --env-file .env mcp-azure-devops
```

---

## 🧪 Running Tests

```bash
pytest tests/ -v --tb=short
```

Tests use mocks — no real Azure/GitHub/Jira credentials needed to run them.

---

## 🔐 Azure Permissions Required

| Resource | Required Role |
|---|---|
| AKS Cluster | Azure Kubernetes Service Cluster User Role |
| Resource Group | Reader |
| Cost Management | Cost Management Reader |
| Monitor | Monitoring Reader |

```bash
# Assign AKS role
az role assignment create \
  --assignee YOUR_CLIENT_ID \
  --role "Azure Kubernetes Service Cluster User Role" \
  --scope /subscriptions/SUB_ID/resourceGroups/RG_NAME/providers/Microsoft.ContainerService/managedClusters/CLUSTER_NAME
```

---

## 📌 Interview Talking Points

> "I built an MCP server in Python that exposes 15 tools across AKS, GitHub Actions,
> Azure Monitor, Cost Management, and Jira — allowing Claude to manage infrastructure
> through natural language. It uses the standard MCP protocol so it works with any
> MCP-compatible AI model, not just Claude."
