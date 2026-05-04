# 📘 Implementation Document
# AI DevOps Incident Assistant — Real-Time AKS Pod Monitoring

---

## Document Information

| Field | Details |
|-------|---------|
| **Project Name** | AI DevOps Incident Assistant |
| **Version** | 2.0 |
| **Author** | Naveen Babu |
| **Date** | May 4, 2026 |
| **Status** | ✅ Implemented & Deployed |
| **Repository** | https://github.com/naveenbabu01/flux-naveen |
| **Live URL** | http://4.236.236.2 |

---

## 1. Executive Summary

This document describes the implementation of an **AI-powered DevOps Incident Assistant** that provides real-time monitoring of Kubernetes (AKS) pod failures and automated root cause analysis using **Azure OpenAI GPT-4.1**.

The system automatically detects pod failures such as `ImagePullBackOff`, `CrashLoopBackOff`, and `OOMKilled`, collects Kubernetes events and logs, and sends them to Azure OpenAI for intelligent analysis. Results are displayed on a live web dashboard with severity ratings, fix steps, CLI commands, and prevention recommendations.

**Key Metrics:**
- **Detection Time**: ~5 seconds (via Kubernetes Watch API)
- **AI Analysis Time**: ~10-15 seconds
- **Total Time (failure → diagnosis)**: ~15-20 seconds
- **Failure Types Detected**: 8 different K8s failure states
- **Namespaces Monitored**: All (except system namespaces)

---

## 2. Business Objective

### 2.1 Problem Statement

When Kubernetes pods fail in production or staging environments, the current manual troubleshooting process involves:

1. Engineer receives alert (or notices during deployment)
2. Runs `kubectl get pods` to identify the failing pod
3. Runs `kubectl describe pod <name>` to view events
4. Runs `kubectl logs <name>` to check container logs
5. Searches internal docs / Stack Overflow for the error
6. Identifies root cause and determines fix
7. Applies the fix and verifies

**Average resolution time**: 15-45 minutes per incident (varies by engineer experience)

### 2.2 Solution

An automated system that:
- **Eliminates steps 2-6** by automatically collecting context and using AI for analysis
- **Reduces resolution time to minutes** by providing ready-to-run fix commands
- **Levels up junior engineers** by providing expert-level diagnosis instantly
- **Operates 24/7** with real-time monitoring

### 2.3 Success Criteria

| Criteria | Target | Achieved |
|----------|--------|----------|
| Auto-detect pod failures | < 10 seconds | ✅ ~5 seconds |
| AI analysis completion | < 30 seconds | ✅ ~15 seconds |
| Failure types covered | ≥ 5 | ✅ 8 types |
| Dashboard availability | 99%+ | ✅ Running on AKS |
| Manual analysis support | Yes | ✅ Via web UI + API |
| CI/CD integration | Yes | ✅ GitHub Actions |

---

## 3. Solution Architecture

### 3.1 High-Level Architecture

```
                    ┌─────────────────────┐
                    │   DevOps Engineer    │
                    │   (Web Browser)      │
                    └──────────┬──────────┘
                               │ HTTP (port 80)
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                Azure Kubernetes Service (AKS)                │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Namespace: ai-devops-assistant                         │  │
│  │                                                        │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │ Pod: ai-devops-assistant                         │  │  │
│  │  │                                                  │  │  │
│  │  │  ┌─────────────┐    ┌─────────────────────────┐  │  │  │
│  │  │  │ FastAPI     │    │ PodMonitor              │  │  │  │
│  │  │  │ Web Server  │◄──►│ (Background Thread)     │  │  │  │
│  │  │  │ :8000       │    │ K8s Watch API           │  │  │  │
│  │  │  └──────┬──────┘    └──────────┬──────────────┘  │  │  │
│  │  │         │                      │                  │  │  │
│  │  │         │    ┌─────────────────┘                  │  │  │
│  │  │         │    │                                    │  │  │
│  │  │         ▼    ▼                                    │  │  │
│  │  │  ┌──────────────────┐                             │  │  │
│  │  │  │ AIIncident       │───── Azure OpenAI API ─────►│  │
│  │  │  │ Assistant        │                              │  │  │
│  │  │  └──────────────────┘                              │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                                                          │  │
│  │  ServiceAccount ──► ClusterRole (read pods/events/logs)  │  │
│  │  Service: LoadBalancer → External IP: 4.236.236.2        │  │
│  │  Secret: AZURE_OPENAI_KEY                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  Monitored Namespaces: default, ai-chatbot, k8s-troubleshooter│
│  (All namespaces except kube-system, kube-node-lease,          │
│   kube-public)                                                 │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
                ┌──────────────────────────┐
                │  Azure OpenAI Service    │
                │  Model: GPT-4.1          │
                │  Endpoint:               │
                │  test-ai-poc-nav         │
                │  Region: East US         │
                └──────────────────────────┘
```

### 3.2 Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Components                    │
│                                                             │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────┐  │
│  │   app.py         │  │  monitor.py       │  │ ai_assis- │  │
│  │   (FastAPI)      │  │  (PodMonitor)     │  │ tant.py   │  │
│  │                  │  │                   │  │           │  │
│  │  Routes:         │  │  - Watch API      │  │ - OpenAI  │  │
│  │  GET /           │  │  - Event detect   │  │   client  │  │
│  │  GET /health     │  │  - Log collect    │  │ - Prompt  │  │
│  │  GET /incidents  │  │  - Pod describe   │  │   engine  │  │
│  │  POST /scan      │  │  - Deduplication  │  │ - JSON    │  │
│  │  POST /analyze   │  │  - Thread mgmt   │  │   parser  │  │
│  └────────┬─────────┘  └────────┬─────────┘  └─────┬─────┘  │
│           │                     │                    │        │
│           └─────────────────────┼────────────────────┘        │
│                                 │                             │
│  ┌──────────────────────────────┴──────────────────────────┐  │
│  │               Shared: Incident Data Store               │  │
│  │               (In-memory list, last 50 incidents)       │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  index.html (Frontend Dashboard)                        │  │
│  │  - Live Monitor Tab (auto-refresh 10s)                  │  │
│  │  - Manual Analysis Tab                                  │  │
│  │  - Severity stats, expandable incident cards            │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Data Flow Diagram

```
┌────────┐     ┌──────────┐     ┌──────────────┐     ┌──────────┐
│  K8s   │────►│  Watch   │────►│   Collect     │────►│  Azure   │
│  API   │     │  Stream  │     │   Context     │     │  OpenAI  │
│ Server │     │  Event   │     │  (describe+   │     │  GPT-4.1 │
│        │     │  detect  │     │  events+logs) │     │          │
└────────┘     └──────────┘     └──────────────┘     └────┬─────┘
                                                          │
                    ┌─────────────────────────────────────┘
                    │  JSON Response
                    ▼
              ┌──────────────┐     ┌──────────────┐
              │   Store      │────►│  Dashboard    │
              │   Incident   │     │  (HTTP poll)  │
              │   + Analysis │     │  every 10s    │
              └──────────────┘     └──────────────┘
```

---

## 4. Infrastructure Setup

### 4.1 Azure Resources

| Resource | Service | Configuration |
|----------|---------|---------------|
| **AKS Cluster** | Azure Kubernetes Service | Name: `aks-test`, RG: `rg-test`, Region: East US, K8s: 1.33.8, Node: Standard_D4ds_v5 |
| **ACR** | Azure Container Registry | Name: `pythonacrtest`, SKU: Basic |
| **OpenAI** | Azure OpenAI Service | Name: `test-ai-poc-nav`, Region: East US, Model: GPT-4.1, Deployment: `gpt-4.1`, API Version: `2024-02-15-preview` |
| **Service Principal** | Azure AD | ID: `e5dbfafb-e40e-4e3d-837f-11b6d21c32a4`, Name: `github-actions-sp` |

### 4.2 Kubernetes Resources

| Resource Type | Name | Namespace | Purpose |
|---------------|------|-----------|---------|
| Deployment | `ai-devops-assistant` | `ai-devops-assistant` | Runs the application pod |
| Service | `ai-devops-assistant` | `ai-devops-assistant` | LoadBalancer exposing port 80 → 8000 |
| ServiceAccount | `ai-devops-assistant` | `ai-devops-assistant` | Identity for K8s API access |
| ClusterRole | `ai-devops-assistant-reader` | cluster-wide | Read-only access to pods, logs, events |
| ClusterRoleBinding | `ai-devops-assistant-reader` | cluster-wide | Binds SA to ClusterRole |
| Secret | `ai-devops-assistant-secret` | `ai-devops-assistant` | Stores AZURE_OPENAI_KEY |

### 4.3 Network Configuration

```
Internet → Azure Load Balancer (External IP: 4.236.236.2)
  → Service (port 80) → Pod (port 8000) → FastAPI/Uvicorn
```

### 4.4 RBAC Permissions

The application requires **read-only** access across all namespaces:

```yaml
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "events", "namespaces"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list"]
```

**Security Note**: No write permissions are granted. The application can only read cluster state, never modify it.

---

## 5. Implementation Details

### 5.1 Module: `monitor.py` — PodMonitor

**Purpose**: Real-time detection of pod failures using the Kubernetes Watch API.

**Class: `PodMonitor`**

| Method | Description |
|--------|-------------|
| `__init__()` | Loads K8s config (in-cluster or local), initializes API client |
| `watch_pods()` | Main loop: streams pod events, detects failures, triggers analysis |
| `check_pod_health(pod)` | Inspects container statuses for failure states |
| `get_pod_events(pod, ns)` | Fetches last 20 K8s events for a specific pod |
| `get_pod_logs(pod, ns)` | Fetches last 30 log lines (current + previous container) |
| `describe_pod(pod, ns)` | Builds pod description (images, node, phase, states) |
| `analyze_incident(incident)` | Sends collected context to Azure OpenAI in background thread |
| `scan_all_pods()` | One-time scan of all pods (manual trigger) |
| `start()` | Starts background daemon thread for continuous watching |

**Failure Detection Logic:**

```python
FAILURE_STATES = {
    "ImagePullBackOff",          # Image pull failed, backing off
    "ErrImagePull",              # Initial image pull failure
    "CrashLoopBackOff",          # Container keeps crashing
    "OOMKilled",                 # Out of memory
    "CreateContainerConfigError", # Bad config (missing secret, etc.)
    "InvalidImageName",           # Malformed image reference
    "RunContainerError",          # Container failed to start
    "Error"                       # Generic error
}
```

**Deduplication Strategy:**
- Tracks `{namespace}/{pod_name}/{reason}` as a unique key
- Same key is suppressed for **10 minutes** after first detection
- Prevents alert fatigue from pods stuck in BackOff loops

**Threading Model:**
```
Main Thread: FastAPI/Uvicorn HTTP server
  │
  └── Daemon Thread: watch_pods() loop
        │
        └── Worker Thread (per incident): analyze_incident()
              └── Azure OpenAI API call (~10-15 seconds)
```

### 5.2 Module: `ai_assistant.py` — AIIncidentAssistant

**Purpose**: Interface with Azure OpenAI GPT-4.1 for intelligent log analysis.

**System Prompt Design:**
```
Role: Senior DevOps/SRE incident analysis expert
Input: K8s pod failure context (description + events + logs)
Output: Structured JSON with specific fields
```

**Required Output Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `severity` | string | `HIGH`, `MEDIUM`, or `LOW` |
| `root_cause` | string | Clear explanation of what went wrong |
| `category` | string | `INFRASTRUCTURE`, `BUILD`, `TEST`, `DEPLOYMENT`, `CONFIGURATION`, `NETWORK`, `SECURITY` |
| `fix_steps` | array[string] | Ordered list of human-readable fix steps |
| `commands` | array[string] | Ready-to-run CLI commands |
| `prevention` | string | How to prevent this in the future |
| `estimated_fix_time` | string | Human-readable time estimate |
| `confidence` | float | 0.0 to 1.0 confidence score |

**Error Handling:**
- JSON parsing failures return a fallback response with the raw AI text
- API timeout/errors are caught and logged without crashing the monitor
- Rate limiting is handled gracefully

### 5.3 Module: `app.py` — FastAPI Application

**Purpose**: HTTP server providing REST API and web dashboard.

**Startup Sequence:**
1. Create `AIIncidentAssistant` instance (loads OpenAI config from env)
2. Create `PodMonitor` instance (connects to K8s API)
3. Call `monitor.start()` → spawns background watch thread
4. FastAPI begins serving HTTP requests on port 8000

**API Endpoints:**

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/` | `ui()` | Serves `static/index.html` |
| GET | `/health` | `health()` | Returns status + monitoring state + incident count |
| GET | `/incidents` | `get_incidents()` | Returns all detected incidents with AI analysis |
| POST | `/scan` | `scan_now()` | Triggers immediate full-cluster scan |
| POST | `/analyze` | `analyze()` | Manual log analysis |
| POST | `/analyze/github-format` | `analyze_github()` | Manual analysis + GitHub markdown |

**Health Check Response:**
```json
{
  "status": "healthy",
  "service": "ai-devops-incident-assistant",
  "version": "2.0.0",
  "monitoring": true,
  "incidents_count": 3
}
```

### 5.4 Frontend: `index.html`

**Purpose**: Single-page web dashboard with two tabs.

**Tab 1: 🔴 Live Monitor**
- Stats bar: HIGH / MEDIUM / LOW / TOTAL incident counts
- "Scan All Pods Now" button → `POST /scan`
- Auto-refresh: `setInterval(refreshIncidents, 10000)` → `GET /incidents`
- Expandable incident cards with full AI analysis
- Color-coded severity badges

**Tab 2: 📋 Manual Analysis**
- Text area for pasting logs
- Sample error chips (pre-filled examples)
- "Analyze Failure" → `POST /analyze`
- "GitHub Format" → `POST /analyze/github-format`
- Results panel with severity, fix steps, commands

**Auto-Refresh Behavior:**
```
Page Load → startAutoRefresh()
  → refreshIncidents() immediately
  → setInterval(refreshIncidents, 10000)  // every 10 seconds

Switch to Manual tab → stopAutoRefresh()
Switch to Monitor tab → startAutoRefresh()
```

### 5.5 Helm Chart

**Chart Structure:**
```
helm-chart/
├── Chart.yaml          # name: ai-devops-assistant, version: 0.1.0
├── values.yaml         # Configurable: image, service type, env vars, resources
└── templates/
    ├── _helpers.tpl    # name, fullname, labels, selectorLabels
    ├── deployment.yaml # Pod spec with serviceAccount, env, probes, resources
    ├── service.yaml    # LoadBalancer service
    └── rbac.yaml       # ServiceAccount + ClusterRole + ClusterRoleBinding
```

**Key Configuration (values.yaml):**

```yaml
image:
  repository: pythonacrtest.azurecr.io/ai-devops-assistant
  tag: "v2"
  pullPolicy: Always

service:
  type: LoadBalancer    # External IP for browser access
  port: 80
  targetPort: 8000

env:
  AZURE_OPENAI_ENDPOINT: "https://test-ai-poc-nav.openai.azure.com/"
  AZURE_OPENAI_DEPLOYMENT: "gpt-4.1"
  AZURE_OPENAI_API_VERSION: "2024-02-15-preview"

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi
```

**Health Probes:**
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## 6. CI/CD Implementation

### 6.1 Pipeline 1: Build & Deploy (`ai-devops-ci-cd.yml`)

**Trigger**: Push to `main` branch with changes in `ai-devops-poc/**`

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ git push     │────►│ az acr build │────►│ helm upgrade│
│ to main      │     │ (cloud build)│     │ --install   │
└─────────────┘     └──────────────┘     └─────────────┘
```

**Steps:**

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `az login` | Authenticate with Azure using Service Principal |
| 2 | `az acr build` | Build Docker image in cloud, push to ACR |
| 3 | `az aks get-credentials` | Get kubeconfig for AKS cluster |
| 4 | `kubectl create namespace` | Ensure namespace exists |
| 5 | `kubectl create secret` | Create/update OpenAI key secret |
| 6 | `helm upgrade --install` | Deploy or update the application |

**Secrets Required:**

| GitHub Secret | Description |
|---------------|-------------|
| `AZURE_CREDENTIALS` | Service Principal JSON for `az login` |
| `AZURE_OPENAI_KEY` | Azure OpenAI API key |

### 6.2 Pipeline 2: AI Incident Analysis (`ai-incident-analysis.yml`)

**Trigger**: When Pipeline 1 completes with **failure** status

```
┌──────────────┐     ┌─────────────────┐     ┌───────────────┐
│ CI/CD fails  │────►│ Download logs   │────►│ Azure OpenAI  │
│              │     │ via GitHub API  │     │ analysis      │
└──────────────┘     └─────────────────┘     └──────┬────────┘
                                                     │
                                              ┌──────▼────────┐
                                              │ Create GitHub │
                                              │ Issue with AI │
                                              │ diagnosis     │
                                              └───────────────┘
```

**Output**: Automatically creates a GitHub Issue labeled `ai-analysis, incident` with:
- Severity rating
- Root cause analysis
- Fix steps and commands
- Prevention recommendations

---

## 7. Deployment Procedure

### 7.1 Prerequisites Checklist

- [ ] Azure CLI installed and authenticated (`az login`)
- [ ] kubectl configured for AKS (`az aks get-credentials`)
- [ ] Helm v3 installed
- [ ] ACR access configured (AKS → ACR integration)
- [ ] Azure OpenAI API key available

### 7.2 Manual Deployment Steps

```bash
# Step 1: Build container image
az acr build --registry pythonacrtest \
  --image ai-devops-assistant:v2 \
  ai-devops-poc/src/

# Step 2: Create namespace
kubectl create namespace ai-devops-assistant \
  --dry-run=client -o yaml | kubectl apply -f -

# Step 3: Create secret for Azure OpenAI key
kubectl create secret generic ai-devops-assistant-secret \
  --namespace ai-devops-assistant \
  --from-literal=AZURE_OPENAI_KEY=<your-key> \
  --dry-run=client -o yaml | kubectl apply -f -

# Step 4: Deploy with Helm
helm upgrade --install ai-devops-assistant \
  ai-devops-poc/helm-chart/ \
  --namespace ai-devops-assistant \
  --set image.tag=v2 \
  --wait --timeout 120s

# Step 5: Verify deployment
kubectl get pods -n ai-devops-assistant
kubectl get svc -n ai-devops-assistant
kubectl logs -n ai-devops-assistant deployment/ai-devops-assistant --tail=20
```

### 7.3 Rollback Procedure

```bash
# View Helm history
helm history ai-devops-assistant -n ai-devops-assistant

# Rollback to previous version
helm rollback ai-devops-assistant <revision> -n ai-devops-assistant

# Or rollback to last working version
helm rollback ai-devops-assistant 0 -n ai-devops-assistant
```

---

## 8. Testing

### 8.1 Test Cases

| # | Test Case | Steps | Expected Result | Status |
|---|-----------|-------|-----------------|--------|
| 1 | Health check | `curl http://4.236.236.2/health` | Returns JSON with `status: healthy` | ✅ Pass |
| 2 | Dashboard loads | Open `http://4.236.236.2` in browser | Dashboard renders with Live Monitor tab | ✅ Pass |
| 3 | ImagePullBackOff detection | Deploy pod with fake image | Incident appears on dashboard in ~15-20s | ✅ Pass |
| 4 | AI analysis quality | Trigger known error | AI returns correct root cause + relevant fix commands | ✅ Pass |
| 5 | Manual analysis | Paste logs in Manual tab | Returns structured diagnosis | ✅ Pass |
| 6 | GitHub format | Click "GitHub Format" | Returns valid markdown | ✅ Pass |
| 7 | Scan all pods | Click "Scan All Pods Now" | Finds existing failing pods | ✅ Pass |
| 8 | Auto-refresh | Wait 10 seconds on Live Monitor | Dashboard updates automatically | ✅ Pass |
| 9 | Deduplication | Same pod fails repeatedly | Only 1 alert per 10 minutes | ✅ Pass |
| 10 | Helm upgrade | Upgrade chart with new image tag | Zero-downtime rolling update | ✅ Pass |

### 8.2 Test Commands

```bash
# Test 1: ImagePullBackOff
kubectl run test-broken --image=pythonacrtest.azurecr.io/fake:nope -n default
# Wait 15-20 seconds, check dashboard
kubectl delete pod test-broken -n default

# Test 2: CrashLoopBackOff
kubectl run test-crash --image=python:3.11-slim -n default \
  -- python -c "raise Exception('crash!')"
kubectl delete pod test-crash -n default

# Test 3: API test
curl -X POST http://4.236.236.2/analyze \
  -H "Content-Type: application/json" \
  -d '{"logs":"Error: ImagePullBackOff for container myapp"}'

# Test 4: Scan
curl -X POST http://4.236.236.2/scan
```

---

## 9. Security Considerations

| Aspect | Implementation |
|--------|---------------|
| **API Key Storage** | Stored as Kubernetes Secret, mounted as env var (not in code) |
| **RBAC** | Minimal read-only ClusterRole (no write/delete permissions) |
| **Network** | LoadBalancer exposes only port 80 (no SSH, no debug ports) |
| **Container** | Runs as non-root (Python slim base), no privileged mode |
| **Secrets in CI/CD** | Stored in GitHub Secrets, never logged |
| **AI Data** | Pod logs sent to Azure OpenAI (within Azure tenant, not third-party) |

### 9.1 Production Recommendations

- [ ] Add authentication to the dashboard (e.g., Azure AD OAuth / basic auth)
- [ ] Use Azure Private Endpoint for OpenAI (avoid public internet)
- [ ] Switch to Internal LoadBalancer or Ingress with TLS
- [ ] Add NetworkPolicy to restrict pod communication
- [ ] Enable Azure Key Vault for secret management (instead of K8s secrets)
- [ ] Add HTTPS/TLS termination via Ingress Controller

---

## 10. Monitoring & Observability

### 10.1 Application Health

```bash
# Health endpoint
curl http://4.236.236.2/health

# Response includes:
# - monitoring: true/false (is the watcher running?)
# - incidents_count: number of detected incidents
```

### 10.2 Kubernetes Monitoring

```bash
# Pod status
kubectl get pods -n ai-devops-assistant

# Pod logs (real-time)
kubectl logs -f -n ai-devops-assistant deployment/ai-devops-assistant

# Resource usage
kubectl top pods -n ai-devops-assistant
```

### 10.3 Key Log Messages

| Log Message | Meaning |
|------------|---------|
| `🚀 Starting pod watcher...` | Monitor thread started |
| `🚨 ALERT: ns/pod → Reason` | New failure detected |
| `🔬 Sending to AI for analysis: ns/pod` | Calling Azure OpenAI |
| `✅ AI analysis complete for pod: severity=X` | Analysis successful |
| `❌ AI analysis failed for pod: error` | OpenAI call failed |
| `Watch disconnected. Reconnecting in 5s...` | Watch stream interrupted (auto-recovers) |

---

## 11. Limitations & Known Issues

| # | Issue | Impact | Mitigation |
|---|-------|--------|------------|
| 1 | In-memory incident storage | Incidents lost on pod restart | Acceptable for POC; production would use persistent DB |
| 2 | No authentication on dashboard | Anyone with IP can access | Add auth for production deployment |
| 3 | Azure OpenAI rate limits | May slow down during mass failures | Deduplication limits calls; add retry with backoff |
| 4 | Single replica | No HA | Scale to 2+ replicas with shared storage for production |
| 5 | Pylance warning locally | `kubernetes` not installed on dev machine | Install locally or ignore (runs in container) |

---

## 12. Future Enhancements

| Priority | Enhancement | Description |
|----------|-------------|-------------|
| P1 | **Slack/Teams Integration** | Send AI analysis to Slack/Teams channels on detection |
| P1 | **Persistent Storage** | Store incidents in Azure CosmosDB or PostgreSQL |
| P2 | **Auto-Remediation** | Optionally auto-apply fix commands (with approval) |
| P2 | **PagerDuty/OpsGenie** | Integrate with incident management platforms |
| P2 | **Multi-Cluster** | Monitor multiple AKS clusters from one dashboard |
| P3 | **Prometheus Metrics** | Export incident metrics for Grafana dashboards |
| P3 | **Historical Analysis** | Track incident trends over time |
| P3 | **Webhook Alerts** | HTTP webhooks for custom integrations |

---

## 13. Appendix

### A. Environment Variables

| Variable | Description | Source |
|----------|-------------|--------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | Helm values.yaml |
| `AZURE_OPENAI_KEY` | Azure OpenAI API key | Kubernetes Secret |
| `AZURE_OPENAI_DEPLOYMENT` | Model deployment name (`gpt-4.1`) | Helm values.yaml |
| `AZURE_OPENAI_API_VERSION` | API version (`2024-02-15-preview`) | Helm values.yaml |

### B. Docker Image Details

| Property | Value |
|----------|-------|
| Base Image | `python:3.11-slim` |
| Image Name | `pythonacrtest.azurecr.io/ai-devops-assistant` |
| Current Tag | `v2` |
| Exposed Port | `8000` |
| Entrypoint | `uvicorn app:app --host 0.0.0.0 --port 8000` |
| Image Size | ~250MB |

### C. Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.115.0 | Web framework |
| uvicorn | 0.30.0 | ASGI server |
| openai | 1.37.0 | Azure OpenAI SDK |
| pydantic | 2.8.0 | Data validation |
| httpx | 0.27.0 | HTTP client (pinned for openai compat) |
| kubernetes | 29.0.0 | Kubernetes Python client |

### D. GitHub Repository Structure

```
github.com/naveenbabu01/flux-naveen
├── ai-devops-poc/          ← This POC
├── ai-chatbot-api/         ← POC 1: AI Chatbot API
├── k8s-troubleshooter/     ← POC 2: K8s Troubleshooter
├── .github/workflows/
│   ├── ci-cd.yaml                  ← POC 1 CI/CD
│   ├── ai-devops-ci-cd.yml        ← POC 3 CI/CD
│   └── ai-incident-analysis.yml   ← POC 3 Failure Analysis
├── flux-clusters/
└── bb-app-source/
```

---

**Document End**

*Last Updated: May 4, 2026 | Version 2.0 | Author: Naveen Babu*
