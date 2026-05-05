# POC: MCP Azure DevOps Server — AI-Powered DevOps Automation

**Author:** Naveen Babu Mummadi  
**Date:** May 2026  
**Status:** ✅ Complete  
**Confluence Page:** [POC - GCSR Space](https://aitrios.atlassian.net/wiki/spaces/GCSR/pages/2569273345/POC)

---

## 1. Overview

This POC demonstrates a **Model Context Protocol (MCP) Server** that connects **Claude AI (Anthropic)** directly to our Azure DevOps infrastructure. It enables an AI assistant to perform real-time DevOps operations through natural language — without dashboards, CLI, or manual context switching.

### Problem Statement

DevOps engineers spend significant time switching between multiple tools (Azure Portal, kubectl, GitHub, Jira) to diagnose and resolve incidents. There's no unified natural-language interface to query infrastructure state.

### Solution

Build an MCP Server that exposes AKS, GitHub Actions, Azure Monitor, Cost Management, and Jira as AI-callable tools. Claude Desktop uses these tools to answer DevOps queries in real time.

---

## 2. Architecture

```
┌─────────────────┐        HTTPS         ┌──────────────────┐
│  Claude Desktop │ ◄──────────────────► │  Anthropic Cloud  │
│  (Local App)    │                      │  (Claude LLM)     │
└────────┬────────┘                      └──────────────────┘
         │ STDIO (JSON-RPC)
         ▼
┌─────────────────────────────────────────────────────────────┐
│              MCP Azure DevOps Server (Python)                │
│                     (Local Machine)                          │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────┐ ┌────────────┐ ┌─────────────┐ ┌─────────┐ │
│  │ AKS Tools │ │GitHub Tools│ │Monitor Tools│ │Cost Tools│ │
│  └─────┬─────┘ └─────┬──────┘ └──────┬──────┘ └────┬────┘ │
│        │              │               │              │      │
│  ┌─────┴──────────────┴───────────────┴──────────────┴────┐ │
│  │                   Jira Tools                           │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         │               │              │              │
         ▼               ▼              ▼              ▼
   ┌──────────┐   ┌──────────┐  ┌───────────┐  ┌──────────┐
   │ AKS API  │   │GitHub API│  │Azure Mon. │  │  Jira    │
   │(K8s API) │   │(REST)    │  │(REST)     │  │  Cloud   │
   └──────────┘   └──────────┘  └───────────┘  └──────────┘
```

### Communication Flow

1. User types question in Claude Desktop
2. Claude Desktop sends message to Anthropic API (cloud) + list of 15 available tools
3. Claude LLM decides which tool to call based on the question
4. Claude Desktop executes tool call on local MCP server via **stdio** (stdin/stdout)
5. MCP server authenticates to Azure/GitHub/Jira and fetches real-time data
6. Result sent back to LLM for formatting
7. User sees human-friendly response

---

## 3. Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| LLM | Claude (Anthropic) | Latest |
| MCP Framework | Python MCP SDK | ≥ 1.0.0 |
| Language | Python | 3.11 |
| Azure Auth | azure-identity (Service Principal) | ≥ 1.15.0 |
| Kubernetes Client | kubernetes (Python) | ≥ 29.0.0 |
| AKS Management | azure-mgmt-containerservice | ≥ 30.0.0 |
| Monitoring | azure-mgmt-monitor | ≥ 6.0.0 |
| Cost Management | azure-mgmt-costmanagement | ≥ 4.0.0 |
| HTTP Client | httpx | ≥ 0.27.0 |
| Config | python-dotenv, pydantic | ≥ 2.0 |
| CI/CD | GitHub Actions | - |
| Transport | STDIO (JSON-RPC) | MCP Spec |

---

## 4. MCP Tools — Complete List (15 Tools)

### 4.1 AKS Tools (5)

| # | Tool Name | Description | Parameters |
|---|-----------|-------------|------------|
| 1 | `get_aks_pod_status` | Get status of all pods in a namespace | `namespace` (required), `deployment` (optional) |
| 2 | `restart_deployment` | Rolling restart of a deployment | `deployment`, `namespace` |
| 3 | `scale_deployment` | Scale deployment replicas (1-20) | `deployment`, `namespace`, `replicas` |
| 4 | `get_aks_events` | Get recent K8s events for diagnostics | `namespace`, `limit` |
| 5 | `get_pod_logs` | Fetch recent logs from a pod | `pod_name`, `namespace`, `tail_lines` |

### 4.2 GitHub Actions Tools (4)

| # | Tool Name | Description | Parameters |
|---|-----------|-------------|------------|
| 6 | `get_pipeline_status` | Get recent workflow run statuses | `repo`, `workflow`, `limit` |
| 7 | `get_pipeline_logs` | Fetch logs from a workflow run | `repo`, `run_id` |
| 8 | `trigger_pipeline` | Trigger workflow_dispatch event | `repo`, `workflow`, `branch`, `inputs` |
| 9 | `get_failed_jobs` | Get failed job details with step breakdown | `repo`, `run_id` |

### 4.3 Azure Monitor Tools (2)

| # | Tool Name | Description | Parameters |
|---|-----------|-------------|------------|
| 10 | `get_azure_alerts` | Get active alerts by severity | `resource_group`, `severity` |
| 11 | `get_app_insights_errors` | Query App Insights exceptions | `app_name`, `hours`, `limit` |

### 4.4 Cost Management Tools (2)

| # | Tool Name | Description | Parameters |
|---|-----------|-------------|------------|
| 12 | `get_cost_report` | Azure spend by service (last N days) | `subscription_id`, `days`, `resource_group` |
| 13 | `get_cost_anomalies` | Detect cost spikes vs previous period | `subscription_id`, `threshold_pct` |

### 4.5 Jira Tools (2)

| # | Tool Name | Description | Parameters |
|---|-----------|-------------|------------|
| 14 | `create_incident_ticket` | Create incident with severity | `title`, `description`, `severity`, `project_key`, `assignee` |
| 15 | `get_open_incidents` | List open incidents in a project | `project_key`, `limit` |

---

## 5. Project Structure

```
mcp-azure-devops/
├── src/
│   ├── server.py              # Main MCP server — tool registration & routing
│   ├── tools/
│   │   ├── aks_tools.py       # AKS/Kubernetes operations
│   │   ├── github_tools.py    # GitHub Actions operations
│   │   ├── azure_monitor.py   # Azure Monitor & App Insights
│   │   ├── cost_tools.py      # Cost Management queries
│   │   └── jira_tools.py      # Jira incident management
│   └── utils/
│       ├── config.py          # Env var loading (dataclass)
│       └── logger.py          # Structured logging
├── tests/
│   └── test_tools.py          # Unit tests (7 tests)
├── conftest.py                # Path setup for pytest
├── .env.example               # Environment variable template
├── .github/workflows/
│   └── mcp-ci.yml             # CI pipeline
├── Dockerfile                 # Container build
├── requirements.txt           # Python dependencies
└── README.md
```

---

## 6. Authentication & Security

| Service | Auth Method | Credential |
|---------|------------|------------|
| Azure (AKS, Monitor, Cost) | Service Principal (ClientSecretCredential) | `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` |
| GitHub API | Personal Access Token | `GITHUB_TOKEN` |
| Jira Cloud | API Token + Email | `JIRA_API_TOKEN`, `JIRA_EMAIL` |

All secrets are passed as **environment variables** via Claude Desktop config — never stored in code.

---

## 7. Setup & Installation

### Prerequisites
- Python 3.11+
- Claude Desktop (Anthropic)
- Azure subscription with AKS cluster
- GitHub repository with Actions workflows
- Jira Cloud project

### Steps

```bash
# 1. Clone repository
git clone https://github.com/naveenbabu01/flux-naveen.git
cd flux-naveen/mcp-azure-devops

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Fill in real values in .env

# 4. Run locally (test)
python src/server.py

# 5. Run tests
pytest tests/ -v
```

### Claude Desktop Configuration

File: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "azure-devops": {
      "command": "python",
      "args": ["C:\\path\\to\\mcp-azure-devops\\src\\server.py"],
      "env": {
        "AZURE_SUBSCRIPTION_ID": "<your-sub-id>",
        "AZURE_TENANT_ID": "<your-tenant-id>",
        "AZURE_CLIENT_ID": "<your-sp-client-id>",
        "AZURE_CLIENT_SECRET": "<your-sp-secret>",
        "AKS_CLUSTER_NAME": "aks-test",
        "AKS_RESOURCE_GROUP": "rg-test",
        "GITHUB_TOKEN": "<your-github-pat>",
        "JIRA_URL": "https://your-domain.atlassian.net",
        "JIRA_EMAIL": "your-email@company.com",
        "JIRA_API_TOKEN": "<your-jira-token>",
        "JIRA_PROJECT_KEY": "SUP"
      }
    }
  }
}
```

---

## 8. Usage Examples

| Natural Language Query | Tool Called | Action |
|----------------------|------------|--------|
| "Show me pods in production namespace" | `get_aks_pod_status` | Fetches pod list from AKS |
| "Restart the frontend deployment" | `restart_deployment` | Rolling restart via K8s API |
| "What's the latest CI/CD status?" | `get_pipeline_status` | Queries GitHub Actions |
| "Show Azure spend last 7 days" | `get_cost_report` | Pulls cost data from Azure |
| "Create a P1 incident for API downtime" | `create_incident_ticket` | Creates Jira ticket |
| "Any active alerts in rg-test?" | `get_azure_alerts` | Queries Azure Monitor |

---

## 9. CI/CD Pipeline

**GitHub Actions workflow:** `.github/workflows/mcp-ci.yml`

- Triggers on push to `main` and PRs
- Runs `pytest` with all 7 unit tests
- Linting and dependency checks
- Docker image build validation

---

## 10. Testing

```bash
$ pytest tests/ -v

tests/test_tools.py::test_aks_tools_init PASSED
tests/test_tools.py::test_github_tools_init PASSED
tests/test_tools.py::test_monitor_tools_init PASSED
tests/test_tools.py::test_cost_tools_init PASSED
tests/test_tools.py::test_jira_tools_init PASSED
tests/test_tools.py::test_config_loading PASSED
tests/test_tools.py::test_server_tool_count PASSED

7 passed ✅
```

---

## 11. Infrastructure Details

| Resource | Value |
|----------|-------|
| Azure Subscription | `9f6136f9-c8b1-414d-9a23-a40c0023225e` |
| Resource Group | `rg-test` |
| AKS Cluster | `aks-test` (K8s 1.33.8) |
| ACR | `pythonacrtest.azurecr.io` |
| Azure OpenAI | `test-ai-poc-nav` (East US) |
| GitHub Repo | [naveenbabu01/flux-naveen](https://github.com/naveenbabu01/flux-naveen) |
| Jira Project | [SUP - naveenmcp.atlassian.net](https://naveenmcp.atlassian.net) |

---

## 12. Key Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| STDIO transport (not HTTP) | Simpler setup, no port management, Claude Desktop native support |
| Service Principal auth | Automated, no user login required, scoped permissions |
| Python over Node.js | Better Azure SDK support, team familiarity |
| Single MCP server (all tools) | Simpler config, single process to manage |
| Local execution (not cloud-hosted) | Lower latency, secrets stay on machine |

---

## 13. Future Enhancements

- [ ] Add Terraform tools (plan/apply/state)
- [ ] Add Slack notification tool
- [ ] Add ArgoCD sync status tool
- [ ] Deploy MCP server as container on AKS (remote mode via HTTP/SSE)
- [ ] Add RBAC-based tool access control
- [ ] Multi-cluster support

---

## 14. References

| Resource | Link |
|----------|------|
| GitHub Repository | https://github.com/naveenbabu01/flux-naveen |
| Confluence POC Page | https://aitrios.atlassian.net/wiki/spaces/GCSR/pages/2569273345/POC |
| MCP Specification | https://modelcontextprotocol.io |
| Claude Desktop | https://claude.ai/download |
| Azure AKS Docs | https://learn.microsoft.com/en-us/azure/aks/ |
| MCP Python SDK | https://github.com/modelcontextprotocol/python-sdk |
