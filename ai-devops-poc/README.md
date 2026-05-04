# 🤖 AI DevOps Incident Assistant - POC Documentation

## Real-Time AKS Pod Monitoring with Azure OpenAI-Powered Incident Analysis

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [How It Works](#how-it-works)
4. [Tech Stack](#tech-stack)
5. [Project Structure](#project-structure)
6. [Components Deep Dive](#components-deep-dive)
7. [Deployment Architecture](#deployment-architecture)
8. [API Reference](#api-reference)
9. [CI/CD Pipelines](#cicd-pipelines)
10. [Setup & Deployment Guide](#setup--deployment-guide)
11. [Testing](#testing)
12. [Screenshots / UI](#ui-overview)
13. [Azure Resources](#azure-resources)

---

## 🎯 Overview

**Problem Statement:**
When Kubernetes pods fail (ImagePullBackOff, CrashLoopBackOff, OOMKilled, etc.), DevOps engineers must manually:
1. Run `kubectl describe pod` to see events
2. Run `kubectl logs` to check container logs
3. Search documentation/StackOverflow for the root cause
4. Figure out the fix commands
5. Apply the fix

This process can take **15-30 minutes** per incident, especially for junior engineers.

**Solution:**
An AI-powered incident assistant that runs inside AKS and:
- **Automatically detects** failing pods in real-time using the Kubernetes Watch API
- **Collects context** (pod description, K8s events, container logs)
- **Sends everything to Azure OpenAI GPT-4.1** for analysis
- **Displays AI-powered diagnosis** on a live web dashboard with:
  - Root cause analysis
  - Severity rating (HIGH / MEDIUM / LOW)
  - Step-by-step fix instructions
  - Ready-to-run CLI commands
  - Prevention recommendations

**Time to diagnosis: ~15-20 seconds** (from pod failure to AI analysis on screen)

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Azure Kubernetes Service (AKS)                │
│                    Cluster: aks-test (rg-test)                   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Namespace: ai-devops-assistant                            │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────────────┐  │  │
│  │  │  Pod: ai-devops-assistant                            │  │  │
│  │  │                                                      │  │  │
│  │  │  ┌────────────────┐  ┌───────────────────────────┐   │  │  │
│  │  │  │  FastAPI App   │  │  PodMonitor (Background)  │   │  │  │
│  │  │  │  Port 8000     │  │  Kubernetes Watch API     │   │  │  │
│  │  │  │                │  │                           │   │  │  │
│  │  │  │  /incidents    │  │  Watches ALL namespaces   │   │  │  │
│  │  │  │  /scan         │  │  Detects pod failures     │   │  │  │
│  │  │  │  /analyze      │  │  Collects events + logs   │   │  │  │
│  │  │  │  / (Dashboard) │  │  Calls Azure OpenAI       │   │  │  │
│  │  │  └────────────────┘  └───────────────────────────┘   │  │  │
│  │  └──────────────────────────────┬───────────────────────┘  │  │
│  │                                 │                          │  │
│  │  ServiceAccount + ClusterRole (read-only pod/event access) │  │
│  │  Service: LoadBalancer (External IP: 4.236.236.2)          │  │
│  │  Secret: AZURE_OPENAI_KEY                                  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─────────────┐  ┌──────────────────┐  ┌───────────────────┐   │
│  │  default     │  │  ai-chatbot      │  │  k8s-troubleshooter│  │
│  │  (monitored) │  │  (monitored)     │  │  (monitored)      │  │
│  └─────────────┘  └──────────────────┘  └───────────────────┘   │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 │ Azure OpenAI API Call
                                 ▼
                  ┌──────────────────────────────┐
                  │  Azure OpenAI Service         │
                  │  Resource: test-ai-poc-nav    │
                  │  Model: GPT-4.1               │
                  │  Region: East US              │
                  └──────────────────────────────┘
```

---

## ⚙️ How It Works

### Flow 1: Automatic Real-Time Detection

```
Step 1: Pod fails (e.g., bad image tag pushed)
         │
Step 2: Kubernetes Watch API streams the event to PodMonitor
        (monitor.py runs as a background thread inside the pod)
         │
Step 3: PodMonitor detects failure state:
        - ImagePullBackOff, ErrImagePull
        - CrashLoopBackOff
        - OOMKilled
        - CreateContainerConfigError
        - RunContainerError
         │
Step 4: Collects full context:
        ├── Pod description (images, node, phase, container states)
        ├── Kubernetes events (last 20 events for the pod)
        └── Pod logs (last 30 lines, including previous container)
         │
Step 5: Sends ALL context to Azure OpenAI GPT-4.1 (in background thread)
        System prompt: "You are a Senior DevOps/SRE incident analysis expert..."
         │
Step 6: GPT-4.1 returns structured JSON:
        {
          "severity": "HIGH",
          "root_cause": "Image does not exist in ACR...",
          "category": "INFRASTRUCTURE",
          "fix_steps": ["Verify image tag", "Check ACR repo", ...],
          "commands": ["az acr repository show-tags ...", ...],
          "prevention": "Use image tag validation in CI pipeline",
          "estimated_fix_time": "10 minutes",
          "confidence": 0.95
        }
         │
Step 7: Incident stored in memory, dashboard auto-refreshes every 10 seconds
         │
Step 8: DevOps engineer sees the incident with full AI diagnosis on the dashboard
```

**Total time: Pod failure → AI diagnosis on screen = ~15-20 seconds**

### Flow 2: Manual Log Analysis

```
DevOps engineer pastes any CI/CD logs into the Manual Analysis tab
  → POST /analyze → Azure OpenAI GPT-4.1 → Returns diagnosis
  → Also available: POST /analyze/github-format → GitHub PR comment markdown
```

### Flow 3: Automated CI/CD Failure Analysis (GitHub Actions)

```
CI/CD pipeline fails → ai-incident-analysis.yml triggers
  → Downloads failure logs from GitHub API
  → Runs analyze_failure.py → Calls Azure OpenAI
  → Creates GitHub Issue with AI analysis (labeled: ai-analysis, incident)
```

---

## 🛠️ Tech Stack

| Component | Technology | Version |
|-----------|------------|---------|
| **AI Engine** | Azure OpenAI GPT-4.1 | 2024-02-15-preview |
| **Backend** | Python FastAPI | 0.115.0 |
| **K8s Client** | kubernetes (Python) | 29.0.0 |
| **HTTP Client** | httpx | 0.27.0 |
| **OpenAI SDK** | openai | 1.37.0 |
| **ASGI Server** | uvicorn | 0.30.0 |
| **Container** | Python 3.11-slim | - |
| **Orchestration** | Azure Kubernetes Service | 1.33.8 |
| **Registry** | Azure Container Registry | pythonacrtest |
| **Package Manager** | Helm | v3 |
| **CI/CD** | GitHub Actions | - |
| **Frontend** | Vanilla HTML/CSS/JS | - |

---

## 📁 Project Structure

```
ai-devops-poc/
├── src/
│   ├── app.py                    # FastAPI application (main entry point)
│   ├── ai_assistant.py           # Azure OpenAI integration for log analysis
│   ├── monitor.py                # Real-time K8s pod health monitor
│   ├── requirements.txt          # Python dependencies
│   ├── Dockerfile                # Container image definition
│   └── static/
│       └── index.html            # Web dashboard (Live Monitor + Manual Analysis)
│
├── helm-chart/
│   ├── Chart.yaml                # Helm chart metadata
│   ├── values.yaml               # Configurable values (image, service, env)
│   └── templates/
│       ├── _helpers.tpl           # Template helper functions
│       ├── deployment.yaml        # K8s Deployment with ServiceAccount
│       ├── service.yaml           # K8s Service (LoadBalancer)
│       └── rbac.yaml              # ServiceAccount + ClusterRole + Binding
│
├── scripts/
│   ├── analyze_failure.py         # CLI tool: analyze log files with AI
│   └── post_github_comment.py     # CLI tool: post AI analysis to GitHub PR
│
└── README.md                      # This documentation

.github/workflows/
├── ai-devops-ci-cd.yml            # Build & deploy pipeline
└── ai-incident-analysis.yml       # Auto-analyze CI/CD failures with AI
```

---

## 🔍 Components Deep Dive

### 1. `monitor.py` — PodMonitor

The core component that enables real-time detection.

**Key Features:**
- Uses `kubernetes.watch.Watch()` to stream pod events from all namespaces
- Runs as a **background daemon thread** (doesn't block the FastAPI server)
- **Deduplication**: Same pod+reason is only alerted once per 10 minutes
- **Thread-safe**: Uses `threading.Lock` for incident list access
- AI analysis runs in **separate threads** to not block the watcher
- Skips system namespaces: `kube-system`, `kube-node-lease`, `kube-public`
- Stores last 50 incidents in memory
- Loads `incluster_config` when running in AKS, falls back to `kubeconfig` locally

**Failure States Detected:**
| State | Description |
|-------|-------------|
| `ImagePullBackOff` | Image pull failed, backing off |
| `ErrImagePull` | Initial image pull failure |
| `CrashLoopBackOff` | Container keeps crashing and restarting |
| `OOMKilled` | Container killed due to memory limit |
| `CreateContainerConfigError` | Bad container config (missing secret, etc.) |
| `InvalidImageName` | Malformed image reference |
| `RunContainerError` | Container failed to start |
| `Error` | Generic error state |

**Data Collected Per Incident:**
1. **Pod Description**: Name, namespace, node, phase, images, container states, conditions
2. **K8s Events**: Last 20 events for the pod (filtered by `involvedObject.name`)
3. **Pod Logs**: Last 30 lines (tries current container, falls back to previous)

### 2. `ai_assistant.py` — AIIncidentAssistant

Interfaces with Azure OpenAI GPT-4.1.

**System Prompt** instructs the model to act as a Senior DevOps/SRE expert and return structured JSON with:
- `root_cause`: Clear explanation of what went wrong
- `severity`: HIGH / MEDIUM / LOW
- `category`: INFRASTRUCTURE / BUILD / TEST / DEPLOYMENT / CONFIGURATION / NETWORK / SECURITY
- `fix_steps[]`: Ordered list of human-readable fix steps
- `commands[]`: Ready-to-run CLI commands (kubectl, az, helm, etc.)
- `prevention`: How to prevent this in the future
- `estimated_fix_time`: Human-readable time estimate
- `confidence`: 0.0 to 1.0

### 3. `app.py` — FastAPI Application

The web server that ties everything together.

**Startup**: Creates `PodMonitor` instance and starts background watching thread.

### 4. `index.html` — Web Dashboard

Two-tab UI:
- **🔴 Live Monitor**: Auto-refreshes every 10 seconds, shows severity counters, expandable incident cards with full AI analysis
- **📋 Manual Analysis**: Paste any logs, get AI diagnosis, export as GitHub markdown

### 5. RBAC (`rbac.yaml`)

```yaml
ClusterRole: ai-devops-assistant-reader
  Rules:
    - pods, pods/log, events, namespaces: get, list, watch
    - deployments, replicasets: get, list
```

This gives the pod **read-only access** across all namespaces — no write permissions.

---

## 🌐 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the web dashboard |
| `GET` | `/health` | Health check (used by K8s liveness/readiness probes) |
| `GET` | `/incidents` | Returns all auto-detected incidents with AI analysis |
| `POST` | `/scan` | Triggers immediate scan of all pods across all namespaces |
| `POST` | `/analyze` | Manual log analysis via Azure OpenAI |
| `POST` | `/analyze/github-format` | Manual analysis + GitHub markdown output |

### Example: POST /analyze

**Request:**
```json
{
  "logs": "Error: ImagePullBackOff for container myapp...",
  "pipeline_name": "my-pipeline",
  "build_id": "42"
}
```

**Response:**
```json
{
  "severity": "HIGH",
  "root_cause": "The image 'myapp:v5' does not exist in the container registry...",
  "category": "INFRASTRUCTURE",
  "fix_steps": [
    "Verify the image tag exists in ACR",
    "Check for typos in the image reference",
    "Ensure ACR authentication is configured"
  ],
  "commands": [
    "az acr repository show-tags --name pythonacrtest --repository myapp",
    "kubectl set image deployment/myapp myapp=pythonacrtest.azurecr.io/myapp:v4"
  ],
  "prevention": "Add image tag validation step in CI pipeline before deployment",
  "estimated_fix_time": "10 minutes",
  "confidence": 0.95
}
```

### Example: GET /incidents

**Response:**
```json
{
  "incidents": [
    {
      "id": "default/test-broken-pod/1714830000",
      "pod_name": "test-broken-pod",
      "namespace": "default",
      "reason": "ImagePullBackOff",
      "message": "Back-off pulling image pythonacrtest.azurecr.io/fake:v99",
      "events_text": "[2026-05-04T15:30:01Z] Warning: Failed to pull image...",
      "timestamp": "2026-05-04T15:30:05+00:00",
      "status": "analyzed",
      "ai_analysis": {
        "severity": "HIGH",
        "root_cause": "Image 'fake:v99' does not exist in ACR...",
        "category": "INFRASTRUCTURE",
        "fix_steps": ["..."],
        "commands": ["..."],
        "prevention": "...",
        "estimated_fix_time": "10 minutes",
        "confidence": 0.95
      }
    }
  ]
}
```

---

## 🚀 CI/CD Pipelines

### Pipeline 1: `ai-devops-ci-cd.yml` — Build & Deploy

**Trigger:** Push to `main` branch (path: `ai-devops-poc/**`)

```
Steps:
  1. Azure Login (Service Principal)
  2. az acr build → Build & push image to ACR
  3. az aks get-credentials → Get AKS kubeconfig
  4. kubectl create secret → Create OpenAI key secret
  5. helm upgrade --install → Deploy to AKS
```

### Pipeline 2: `ai-incident-analysis.yml` — Auto-Analyze Failures

**Trigger:** When `ai-devops-ci-cd.yml` workflow **fails**

```
Steps:
  1. Download failed workflow logs via GitHub API
  2. Install Python + openai SDK
  3. Run analyze_failure.py → Call Azure OpenAI
  4. Create GitHub Issue with AI analysis
     Labels: ai-analysis, incident
```

---

## 📦 Setup & Deployment Guide

### Prerequisites

- Azure subscription with:
  - Azure OpenAI Service (GPT-4.1 deployed)
  - Azure Kubernetes Service (AKS)
  - Azure Container Registry (ACR)
- `kubectl` configured for AKS
- `helm` v3 installed
- `az` CLI logged in

### Step 1: Build the Container Image

```bash
az acr build --registry pythonacrtest \
  --image ai-devops-assistant:v2 \
  ai-devops-poc/src/
```

### Step 2: Create Namespace and Secret

```bash
kubectl create namespace ai-devops-assistant

kubectl create secret generic ai-devops-assistant-secret \
  --namespace ai-devops-assistant \
  --from-literal=AZURE_OPENAI_KEY=<your-key>
```

### Step 3: Deploy with Helm

```bash
helm upgrade --install ai-devops-assistant \
  ai-devops-poc/helm-chart/ \
  --namespace ai-devops-assistant \
  --set image.tag=v2 \
  --wait --timeout 120s
```

### Step 4: Verify

```bash
kubectl get pods -n ai-devops-assistant
kubectl get svc -n ai-devops-assistant   # Note the EXTERNAL-IP
```

### Step 5: Access Dashboard

Open `http://<EXTERNAL-IP>` in your browser.

---

## 🧪 Testing

### Test 1: Trigger ImagePullBackOff

```bash
# Create a pod with a non-existent image
kubectl run test-broken-pod \
  --image=pythonacrtest.azurecr.io/fake-image:doesnotexist \
  --namespace=default

# Watch the dashboard — incident should appear in ~15-20 seconds

# Clean up
kubectl delete pod test-broken-pod --namespace=default
```

### Test 2: Trigger CrashLoopBackOff

```bash
kubectl run test-crash-pod \
  --image=python:3.11-slim \
  --namespace=default \
  -- python -c "raise Exception('App crashed!')"

# Clean up
kubectl delete pod test-crash-pod --namespace=default
```

### Test 3: Manual Analysis

1. Open `http://<EXTERNAL-IP>`
2. Switch to "📋 Manual Analysis" tab
3. Click any sample error chip (e.g., 🔴 ImagePullBackOff)
4. Click "🔬 Analyze Failure"
5. View the AI diagnosis

### Test 4: API Test

```bash
curl -X POST http://<EXTERNAL-IP>/analyze \
  -H "Content-Type: application/json" \
  -d '{"logs": "Error: ImagePullBackOff for container myapp"}'
```

---

## 🖥️ UI Overview

### Live Monitor Tab
- **Stats Bar**: Real-time count of HIGH / MEDIUM / LOW / TOTAL incidents
- **Scan Now Button**: Trigger immediate full-cluster scan
- **Auto-Refresh**: Polls `/incidents` every 10 seconds
- **Incident Cards**: Click to expand full AI analysis
  - Severity badge (color-coded)
  - Failure reason badge
  - Pod name, namespace, timestamp
  - Root cause, fix steps, CLI commands, prevention tips
  - Raw K8s events

### Manual Analysis Tab
- **Text Area**: Paste any CI/CD or K8s failure logs
- **Sample Chips**: Pre-filled examples (ImagePullBackOff, OOM, RBAC, Helm Timeout)
- **Analyze Button**: Send to Azure OpenAI for diagnosis
- **GitHub Format Button**: Get markdown formatted for GitHub PR/Issue comments
- **Results Panel**: Severity, category, fix time, confidence, root cause, steps, commands

---

## ☁️ Azure Resources

| Resource | Name | Resource Group | Region |
|----------|------|----------------|--------|
| **Azure OpenAI** | test-ai-poc-nav | rg-test | East US |
| **AKS Cluster** | aks-test | rg-test | East US |
| **ACR** | pythonacrtest | rg-test | East US |
| **OpenAI Model** | GPT-4.1 (gpt-4.1) | - | East US |

### Kubernetes Resources

| Resource | Name | Namespace |
|----------|------|-----------|
| **Deployment** | ai-devops-assistant | ai-devops-assistant |
| **Service** | ai-devops-assistant (LoadBalancer) | ai-devops-assistant |
| **ServiceAccount** | ai-devops-assistant | ai-devops-assistant |
| **ClusterRole** | ai-devops-assistant-reader | cluster-wide |
| **ClusterRoleBinding** | ai-devops-assistant-reader | cluster-wide |
| **Secret** | ai-devops-assistant-secret | ai-devops-assistant |

### External Access

| Service | URL |
|---------|-----|
| **Dashboard** | http://4.236.236.2 |
| **Health Check** | http://4.236.236.2/health |
| **API Docs** | http://4.236.236.2/docs |
| **GitHub Repo** | https://github.com/naveenbabu01/flux-naveen |

---

## 👤 Author

**Naveen Babu** — DevOps Engineer
- GitHub: [naveenbabu01](https://github.com/naveenbabu01)
- Repository: [flux-naveen](https://github.com/naveenbabu01/flux-naveen)

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2026-05-04 | Initial release: Manual log analysis + web UI |
| v2 | 2026-05-04 | Added real-time AKS pod monitoring with Kubernetes Watch API, RBAC, live dashboard |
