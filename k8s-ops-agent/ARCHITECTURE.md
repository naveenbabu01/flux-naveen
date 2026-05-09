# 🏗️ K8s AI Ops Agent — Full Architecture & Request Flow

## 0. System Overview — Two Interfaces, One Cluster

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              AKS CLUSTER (aks-test / rg-test)                       │
│                              Node: 1x Standard_DS2_v2 │ K8s v1.33.8                │
│                                                                                     │
│   ┌─────────────────────────────────┐    ┌──────────────────────────────────────┐   │
│   │  INTERFACE 1: Streamlit Web UI  │    │  INTERFACE 2: VS Code + GitHub      │   │
│   │  (AI-Powered Diagnostics)       │    │  Copilot Chat (MCP Protocol)        │   │
│   │                                 │    │                                      │   │
│   │  namespace: k8s-ops-agent       │    │  namespace: aks-mcp                  │   │
│   │  image: k8s-ops-agent:v1        │    │  image: ghcr.io/azure/aks-mcp       │   │
│   │  port: 8501 (LoadBalancer)      │    │  port: 8000 (LoadBalancer)           │   │
│   │  IP: 48.206.107.252             │    │  IP: 20.232.246.193                  │   │
│   │                                 │    │                                      │   │
│   │  Features:                      │    │  Features:                           │   │
│   │  • Auto-scan all namespaces     │    │  • 13 kubectl/helm tools             │   │
│   │  • LangGraph AI pipeline       │    │  • Natural language K8s queries      │   │
│   │  • RAG with runbooks           │    │  • Read/Write access to cluster      │   │
│   │  • Human approval gate         │    │  • SSE transport for real-time       │   │
│   │  • Auto-fix with kubectl       │    │  • Integrated in VS Code sidebar    │   │
│   │  • LangSmith tracing           │    │                                      │   │
│   └─────────────────────────────────┘    └──────────────────────────────────────┘   │
│                                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │  MONITORED WORKLOADS: ai-chatbot-api, bb-app, demo-cronjob, default, ...   │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 0.1 End-to-End Request Flow — Both Interfaces

```
╔═══════════════════════════════════════════════════════════════════════════════════════╗
║                        COMPLETE REQUEST FLOW DIAGRAM                                 ║
╠═══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                      ║
║  PATH A: VS Code Copilot Chat → AKS-MCP → Cluster                                  ║
║  ════════════════════════════════════════════                                        ║
║                                                                                      ║
║  Developer                VS Code               AKS-MCP Pod              AKS API     ║
║  (typing)                 Copilot                (aks-mcp ns)            Server       ║
║     │                        │                      │                      │          ║
║     │ "list failing pods"    │                      │                      │          ║
║     │───────────────────────▶│                      │                      │          ║
║     │                        │                      │                      │          ║
║     │                        │  SSE connect         │                      │          ║
║     │                        │  GET /sse            │                      │          ║
║     │                        │─────────────────────▶│                      │          ║
║     │                        │  event: endpoint     │                      │          ║
║     │                        │◀─────────────────────│                      │          ║
║     │                        │                      │                      │          ║
║     │                        │  tools/list          │                      │          ║
║     │                        │  POST /messages      │                      │          ║
║     │                        │─────────────────────▶│                      │          ║
║     │                        │  13 tools returned   │                      │          ║
║     │                        │◀─────────────────────│                      │          ║
║     │                        │                      │                      │          ║
║     │                        │  Copilot selects     │                      │          ║
║     │                        │  tool: kubectl_get   │                      │          ║
║     │                        │  args: "pods -A      │                      │          ║
║     │                        │   --field-selector   │                      │          ║
║     │                        │   status.phase!=     │                      │          ║
║     │                        │   Running"           │                      │          ║
║     │                        │─────────────────────▶│                      │          ║
║     │                        │                      │  kubectl get pods    │          ║
║     │                        │                      │─────────────────────▶│          ║
║     │                        │                      │  pod list JSON       │          ║
║     │                        │                      │◀─────────────────────│          ║
║     │                        │  tool result (JSON)  │                      │          ║
║     │                        │◀─────────────────────│                      │          ║
║     │                        │                      │                      │          ║
║     │  Formatted answer      │                      │                      │          ║
║     │  "Found 1 failing pod: │                      │                      │          ║
║     │   demo-cronjob in ns   │                      │                      │          ║
║     │   demo — ImagePull     │                      │                      │          ║
║     │   BackOff"             │                      │                      │          ║
║     │◀───────────────────────│                      │                      │          ║
║     │                        │                      │                      │          ║
║                                                                                      ║
║  PATH B: Browser → Streamlit → LangGraph → AI → Cluster                            ║
║  ═══════════════════════════════════════════════════════                             ║
║                                                                                      ║
║  SRE                  Streamlit Pod           LangGraph         Azure OpenAI         ║
║  (browser)           (k8s-ops-agent ns)       Pipeline          (gpt-4.1)            ║
║     │                      │                      │                  │               ║
║     │  Open UI             │                      │                  │               ║
║     │  48.206.107.252:8501 │                      │                  │               ║
║     │─────────────────────▶│                      │                  │               ║
║     │                      │                      │                  │               ║
║     │                      │  Auto-scan cluster   │                  │               ║
║     │                      │──┐ kubectl get ns    │                  │               ║
║     │                      │  │ kubectl get pods  │                  │               ║
║     │                      │  │ (per namespace)   │                  │               ║
║     │                      │◀─┘                   │                  │               ║
║     │                      │                      │                  │               ║
║     │  Dashboard: 3 sick   │                      │                  │               ║
║     │  pods found          │                      │                  │               ║
║     │◀─────────────────────│                      │                  │               ║
║     │                      │                      │                  │               ║
║     │  Click "Diagnose"    │                      │                  │               ║
║     │─────────────────────▶│                      │                  │               ║
║     │                      │  k8s_agent.stream()  │                  │               ║
║     │                      │─────────────────────▶│                  │               ║
║     │                      │                      │                  │               ║
║     │                      │                      │── detect ───────▶│  kubectl      ║
║     │                      │                      │── context ──────▶│  kubectl+ACR  ║
║     │                      │                      │── rag ──────────▶│  ChromaDB     ║
║     │                      │                      │── diagnose ─────▶│  LLM call ──▶ ║
║     │                      │                      │◀─── root cause ──│◀──────────── ║
║     │                      │                      │── propose ──────▶│  LLM call ──▶ ║
║     │                      │                      │◀─── fix cmds ────│◀──────────── ║
║     │                      │                      │                  │               ║
║     │                      │  ◀── INTERRUPT ──────│                  │               ║
║     │                      │◀─────────────────────│                  │               ║
║     │                      │                      │                  │               ║
║     │  Approval screen:    │                      │                  │               ║
║     │  "kubectl set image  │                      │                  │               ║
║     │   deploy/X ..."      │                      │                  │               ║
║     │  [✅ APPROVE]         │                      │                  │               ║
║     │◀─────────────────────│                      │                  │               ║
║     │                      │                      │                  │               ║
║     │  Click APPROVE       │                      │                  │               ║
║     │─────────────────────▶│                      │                  │               ║
║     │                      │  execute_commands    │                  │               ║
║     │                      │──┐ kubectl set image │                  │               ║
║     │                      │  │ ──────────────────┼──────────▶ AKS   ║               ║
║     │                      │  │ verify pod status │                  │               ║
║     │                      │  │ ──────────────────┼──────────▶ AKS   ║               ║
║     │                      │  │ send Slack notif. │                  │               ║
║     │                      │◀─┘                   │                  │               ║
║     │                      │                      │                  │               ║
║     │  Final Report:       │                      │                  │               ║
║     │  ✅ Pod now Running   │                      │                  │               ║
║     │  📋 Audit log saved   │                      │                  │               ║
║     │◀─────────────────────│                      │                  │               ║
║                                                                                      ║
╚═══════════════════════════════════════════════════════════════════════════════════════╝
```

---

## 0.2 AKS-MCP: 13 Available Tools

| # | Tool | Description |
|---|------|-------------|
| 1 | `kubectl_get` | Get K8s resources (pods, deployments, services, etc.) |
| 2 | `kubectl_describe` | Describe K8s resources in detail |
| 3 | `kubectl_logs` | Fetch container logs |
| 4 | `kubectl_api_resources` | List available API resources |
| 5 | `kubectl_top` | Show resource usage (CPU/memory) |
| 6 | `kubectl_auth` | Check RBAC permissions |
| 7 | `kubectl_create` | Create K8s resources |
| 8 | `kubectl_apply` | Apply manifests |
| 9 | `kubectl_delete` | Delete resources |
| 10 | `kubectl_scale` | Scale deployments |
| 11 | `kubectl_patch` | Patch resources |
| 12 | `helm_list` | List Helm releases |
| 13 | `helm_get` | Get Helm release details |

---

## 0.3 Network Topology

```
                    INTERNET
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
   ┌────────────┐ ┌─────────┐ ┌─────────────┐
   │ Browser    │ │ VS Code │ │ LangSmith   │
   │ (SRE)     │ │ Copilot │ │ API         │
   └─────┬──────┘ └────┬────┘ └──────▲──────┘
         │              │             │ traces (HTTPS)
         │              │             │
    ┌────┼──────────────┼─────────────┼─────────────────────┐
    │    │    AKS LoadBalancers       │                      │
    │    │              │             │                      │
    │    ▼              ▼             │                      │
    │ ┌──────────┐ ┌──────────┐      │                      │
    │ │ :8501    │ │ :8000    │      │                      │
    │ │Streamlit │ │ AKS-MCP  │      │                      │
    │ │ Service  │ │ Service  │      │                      │
    │ └────┬─────┘ └────┬─────┘      │                      │
    │      │            │            │                      │
    │      ▼            ▼            │                      │
    │ ┌──────────┐ ┌──────────┐      │                      │
    │ │Streamlit │ │ AKS-MCP  │      │                      │
    │ │  Pod     │ │  Pod     │      │                      │
    │ │          │ │          │      │                      │
    │ │ LangGraph│ │ kubectl  │      │                      │
    │ │ ChromaDB │ │ helm     │      │                      │
    │ │ kubectl  │ │ az SDK   │      │                      │
    │ └──┬──┬────┘ └────┬─────┘      │                      │
    │    │  │           │            │                      │
    │    │  │     ┌─────┘            │                      │
    │    │  │     │                  │                      │
    │    ▼  ▼     ▼                  │                      │
    │  ┌──────────────────┐         │                      │
    │  │  K8s API Server  │         │                      │
    │  │  (kube-apiserver)│         │                      │
    │  └──────────────────┘         │                      │
    │        AKS Cluster            │                      │
    └───────────────────────────────┼──────────────────────┘
                                    │
                          ┌─────────┴──────────┐
                          │                    │
                          ▼                    ▼
                   ┌────────────┐      ┌──────────────┐
                   │Azure OpenAI│      │  Azure ACR   │
                   │ gpt-4.1   │      │pythonacrtest │
                   │ ada-002   │      │              │
                   └────────────┘      └──────────────┘
```

---

## 1. Streamlit App — High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OPERATOR / SRE (Browser)                            │
│                        http://48.206.107.252:8501                            │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │  Streamlit UI
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        STREAMLIT APPLICATION LAYER                          │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │  Auto-Scan   │  │  Dashboard   │  │   Approval   │  │    Report     │   │
│  │  (All NS)    │  │  (Pod List)  │  │   (Review)   │  │   (Results)   │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └───────────────┘   │
│         │                 │                  │                               │
│         ▼                 ▼                  ▼                               │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │              st.session_state (In-Memory State Manager)            │     │
│  │  phase | all_unhealthy | state | selected_pod | last_scan          │     │
│  └──────────────────────────┬──────────────────────────────────────────┘    │
└─────────────────────────────┼──────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       LANGGRAPH ORCHESTRATION LAYER                         │
│                                                                             │
│  ┌────────┐   ┌─────────┐   ┌─────┐   ┌──────────┐   ┌─────────┐         │
│  │ detect │──▶│ context │──▶│ rag │──▶│ diagnose │──▶│ propose │         │
│  └────────┘   └─────────┘   └─────┘   └──────────┘   └────┬────┘         │
│                                                             │               │
│                                              ┌──────────────┤               │
│                                              │  HUMAN GATE  │               │
│                                              │  (INTERRUPT)  │               │
│                                              ▼              ▼               │
│                                        ┌─────────┐   ┌──────┐              │
│                                        │ execute │   │ skip │              │
│                                        └────┬────┘   └──┬───┘              │
│                                             │           │                   │
│                                             ▼           ▼                   │
│                                        ┌─────────────────┐                  │
│                                        │     report      │                  │
│                                        └─────────────────┘                  │
│                                                                             │
│  State: K8sAgentState (TypedDict)          Checkpointer: MemorySaver        │
└──────────┬──────────────┬──────────────┬────────────────────────────────────┘
           │              │              │
           ▼              ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│   KUBECTL    │  │  AZURE       │  │   CHROMADB        │
│   (subprocess│  │  OPENAI      │  │   (Vector Store)  │
│    calls)    │  │  (LLM +      │  │                   │
│              │  │   Embeddings)│  │  6 Runbook Docs   │
└──────┬───────┘  └──────┬───────┘  └──────────────────┘
       │                 │
       ▼                 ▼
┌──────────────┐  ┌──────────────────────────────────────┐
│  AKS CLUSTER │  │  EXTERNAL SERVICES                   │
│  (aks-test)  │  │                                      │
│              │  │  ┌────────────┐  ┌────────────────┐  │
│  Namespaces  │  │  │ LangSmith  │  │  Slack (opt.)  │  │
│  Pods/Deploy │  │  │ (Tracing)  │  │  (#k8s-alerts) │  │
│  Events/Logs │  │  └────────────┘  └────────────────┘  │
└──────────────┘  └──────────────────────────────────────┘
```

---

## 2. Streamlit Data Flow — End to End

```
BROWSER                    STREAMLIT                LANGGRAPH               EXTERNAL
  │                           │                        │                       │
  │   Open 48.206.107.252     │                        │                       │
  │──────────────────────────▶│                        │                       │
  │                           │                        │                       │
  │                           │  Auto-scan trigger     │                       │
  │                           │───┐                    │                       │
  │                           │   │ scan_all_namespaces()                      │
  │                           │   │                    │                       │
  │                           │   │  kubectl get ns    │                       │
  │                           │   │────────────────────┼──────▶ AKS           │
  │                           │   │  [ns1,ns2,ns3...]  │◀──────               │
  │                           │   │                    │                       │
  │                           │   │  For each NS:      │                       │
  │                           │   │  kubectl get pods  │                       │
  │                           │   │────────────────────┼──────▶ AKS           │
  │                           │   │  [unhealthy pods]  │◀──────               │
  │                           │◀──┘                    │                       │
  │                           │                        │                       │
  │  Dashboard (pod list)     │                        │                       │
  │◀──────────────────────────│                        │                       │
  │                           │                        │                       │
  │  Click "🩺 Diagnose"      │                        │                       │
  │──────────────────────────▶│                        │                       │
  │                           │  k8s_agent.stream()    │                       │
  │                           │───────────────────────▶│                       │
  │                           │                        │                       │
  │                           │                     ┌──┤  detect_issues_node   │
  │                           │                     │  │  kubectl get pods -o json
  │                           │                     │  │──────────────────▶ AKS│
  │                           │                     │  │◀──────────────────    │
  │                           │                     └──┤                       │
  │                           │                     ┌──┤  fetch_context_node   │
  │                           │                     │  │  kubectl logs         │
  │                           │                     │  │  kubectl describe     │
  │                           │                     │  │  kubectl get events   │
  │                           │                     │  │──────────────────▶ AKS│
  │                           │                     │  │◀──────────────────    │
  │                           │                     │  │                       │
  │                           │                     │  │  If ImagePullBackOff: │
  │                           │                     │  │  az acr show-tags     │
  │                           │                     │  │──────────────────▶ ACR│
  │                           │                     │  │◀──────────────────    │
  │                           │                     └──┤                       │
  │                           │                     ┌──┤  rag_node             │
  │                           │                     │  │  retriever.invoke()   │
  │                           │                     │  │──────▶ ChromaDB       │
  │                           │                     │  │◀──────                │
  │                           │                     └──┤                       │
  │                           │                     ┌──┤  diagnose_node        │
  │                           │                     │  │  llm.invoke()         │
  │                           │                     │  │────────────────▶ Azure│
  │                           │                     │  │                OpenAI │
  │                           │  ◄──── TRACING ────▶│  │─ ─ ─ ─ ─ ─ ─▶LangSmith
  │                           │                     │  │◀────────────────      │
  │                           │                     └──┤                       │
  │                           │                     ┌──┤  propose_commands_node│
  │                           │                     │  │  kubectl get pod -o json
  │                           │                     │  │──────────────────▶ AKS│
  │                           │                     │  │◀──────────────────    │
  │                           │                     │  │  llm.invoke()         │
  │                           │                     │  │────────────────▶ Azure│
  │                           │                     │  │◀────────────────OpenAI│
  │                           │                     └──┤                       │
  │                           │                        │                       │
  │                           │  ◀── INTERRUPT ────────│                       │
  │                           │◀───────────────────────│                       │
  │                           │                        │                       │
  │  Approval UI (commands)   │                        │                       │
  │◀──────────────────────────│                        │                       │
  │                           │                        │                       │
  │  Click "✅ APPROVE"        │                        │                       │
  │──────────────────────────▶│                        │                       │
  │                           │  execute_commands_node │                       │
  │                           │───┐                    │                       │
  │                           │   │ run_kubectl(cmd)   │                       │
  │                           │   │────────────────────┼──────▶ AKS           │
  │                           │   │◀───────────────────┼──────                │
  │                           │◀──┘                    │                       │
  │                           │  verify_and_report     │                       │
  │                           │───┐                    │                       │
  │                           │   │ sleep(5)           │                       │
  │                           │   │ kubectl get pod    │                       │
  │                           │   │────────────────────┼──────▶ AKS           │
  │                           │   │◀───────────────────┼──────                │
  │                           │   │ _send_slack()      │                       │
  │                           │   │────────────────────┼──────▶ Slack         │
  │                           │◀──┘                    │                       │
  │                           │                        │                       │
  │  Final Report + Audit Log │                        │                       │
  │◀──────────────────────────│                        │                       │
```

---

## 3. LangGraph State Machine (Detailed)

```
                    ┌─────────────────┐
                    │   Entry Point   │
                    └────────┬────────┘
                             │
                             ▼
                   ┌──────────────────┐
                   │  detect_issues   │  Scans namespace for unhealthy pods
                   │  ─────────────   │  Tool: get_unhealthy_pods()
                   │  Output: list of │  kubectl get pods -n <ns> -o json
                   │  {pod, ns, phase,│  Parses containerStatuses for
                   │   reason,restarts│  waiting/terminated states
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  fetch_context   │  Gathers diagnostic data
                   │  ─────────────   │
                   │  • kubectl logs  │  Last 80 lines (--previous)
                   │  • kubectl desc  │  Events, resources, conditions
                   │  • kubectl events│  Namespace events
                   │  • ACR verify    │  If ImagePullBackOff:
                   │    (conditional) │    az acr show-tags
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │    rag_node      │  Retrieves runbook knowledge
                   │  ─────────────   │
                   │  ChromaDB search │  retriever.invoke(reason)
                   │  Returns top-2   │  Matches: CrashLoopBackOff,
                   │  runbook docs    │  OOMKilled, ImagePullBackOff,
                   │                  │  Pending, NodeNotReady, etc.
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │   diagnose_node  │  LLM-powered root cause analysis
                   │  ─────────────   │
                   │  Input:          │  Azure OpenAI (gpt-4.1)
                   │  • Pod info      │
                   │  • Logs          │  Output:
                   │  • Describe      │  1. Root cause (2-3 sentences)
                   │  • Runbook       │  2. Severity: LOW/MED/HIGH/CRIT
                   │  • ACR check     │  3. Confidence: 0-100%
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  propose_commands│  LLM generates fix commands
                   │  ─────────────   │
                   │  Dynamic resolve:│  Azure OpenAI (gpt-4.1)
                   │  • Deployment    │
                   │    (ownerRefs →  │  Output: JSON array
                   │     ReplicaSet → │  [{cmd, reason, risk, order}]
                   │     Deployment)  │
                   │  • Container name│  If ACR tag wrong:
                   │  • Current image │  Builds EXACT FIX COMMAND
                   └────────┬─────────┘
                            │
               ┌────────────┴────────────┐
               │    🚨 HUMAN APPROVAL    │
               │    GATE (INTERRUPT)      │
               │                          │
               │  Streamlit shows:        │
               │  • Diagnosis             │
               │  • Proposed commands     │
               │  • Risk levels           │
               │  • Checkboxes per cmd    │
               │                          │
               │  [✅ APPROVE] [❌ REJECT] │
               └────┬──────────────┬──────┘
                    │              │
          approved  │              │  rejected
                    ▼              ▼
           ┌──────────────┐  ┌──────────┐
           │   execute    │  │   skip   │
           │  ──────────  │  │  ──────  │
           │  Runs each   │  │  Logs    │
           │  approved cmd│  │  rejection│
           │  via kubectl │  │  to audit│
           │  + audit log │  │  log     │
           └──────┬───────┘  └────┬─────┘
                  │               │
                  ▼               ▼
           ┌──────────────────────────┐
           │   verify_and_report      │
           │  ─────────────────       │
           │  1. Wait 5s for K8s      │
           │  2. Re-check pod status  │
           │  3. Generate report      │
           │  4. Send to Slack (opt.) │
           └──────────┬───────────────┘
                      │
                      ▼
                   ┌──────┐
                   │  END │
                   └──────┘
```

---

## 4. LangSmith Tracing Flow

```
┌─────────────────────────────────────────────────────────┐
│                    Your App (app.py)                     │
│                                                         │
│  load_dotenv() loads:                                   │
│    LANGCHAIN_TRACING_V2=true                            │
│    LANGCHAIN_API_KEY=lsv2_pt_...                        │
│    LANGCHAIN_PROJECT=k8s-ops-agent                      │
│                                                         │
│  LangChain SDK detects these env vars at import time    │
│  and installs a global tracing callback automatically.  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Every LangChain operation is intercepted:       │   │
│  │                                                  │   │
│  │  llm.invoke()         ──▶ TracerCallback         │   │
│  │  embeddings.embed()   ──▶ TracerCallback         │   │
│  │  retriever.invoke()   ──▶ TracerCallback         │   │
│  │  k8s_agent.stream()   ──▶ TracerCallback         │   │
│  │  @tool functions      ──▶ TracerCallback         │   │
│  └──────────────────────────┬───────────────────────┘   │
│                             │                            │
└─────────────────────────────┼────────────────────────────┘
                              │  HTTPS POST (async, non-blocking)
                              │  Payload: {run_id, inputs, outputs,
                              │            tokens, latency, errors}
                              ▼
                ┌─────────────────────────────┐
                │   https://api.smith.        │
                │   langchain.com             │
                │                             │
                │   Project: k8s-ops-agent    │
                │                             │
                │   ┌───────────────────────┐ │
                │   │  Trace: k8s-agent     │ │
                │   │  ├─ detect (tool)     │ │
                │   │  ├─ context (tool)    │ │
                │   │  │  ├─ get_pod_logs   │ │
                │   │  │  ├─ describe_pod   │ │
                │   │  │  └─ verify_acr     │ │
                │   │  ├─ rag (retriever)   │ │
                │   │  │  └─ ChromaDB query │ │
                │   │  ├─ diagnose (LLM)    │ │
                │   │  │  └─ AzureOpenAI    │ │
                │   │  │    tokens: 1.2k in │ │
                │   │  │    tokens: 300 out │ │
                │   │  │    latency: 2.3s   │ │
                │   │  └─ propose (LLM)     │ │
                │   │     └─ AzureOpenAI    │ │
                │   │       tokens: 800 in  │ │
                │   │       tokens: 200 out │ │
                │   │       latency: 1.8s   │ │
                │   └───────────────────────┘ │
                └─────────────────────────────┘

View at: https://smith.langchain.com/o/<org>/projects/p/<project>
```

---

## 5. Component Interaction Map

```
┌──────────────────────────────────────────────────────────────────┐
│                        TECHNOLOGY STACK                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────────────┐  │
│  │  Streamlit   │     │  LangGraph   │     │  Azure OpenAI    │  │
│  │  (UI Layer)  │◀───▶│  (Agent      │◀───▶│  (LLM Engine)    │  │
│  │              │     │   Orchestra- │     │                  │  │
│  │  • Dashboard │     │   tion)      │     │  • gpt-4.1       │  │
│  │  • Approval  │     │              │     │  • text-embed-   │  │
│  │  • Reports   │     │  • StateGraph│     │    ada-002       │  │
│  │  • Audit Log │     │  • MemorySvr │     │                  │  │
│  └─────────────┘     │  • Interrupt  │     └──────────────────┘  │
│                       └──────┬───────┘                            │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐              │
│         │                    │                    │              │
│         ▼                    ▼                    ▼              │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────────────┐  │
│  │  kubectl     │     │  ChromaDB    │     │  LangSmith       │  │
│  │  (K8s CLI)   │     │  (Vector DB) │     │  (Observability) │  │
│  │              │     │              │     │                  │  │
│  │  • get pods  │     │  6 Runbook   │     │  • Traces        │  │
│  │  • logs      │     │  Documents   │     │  • Token usage   │  │
│  │  • describe  │     │  embedded    │     │  • Latency       │  │
│  │  • events    │     │  with ada-002│     │  • I/O logging   │  │
│  │  • set image │     │              │     │                  │  │
│  └──────┬──────┘     └──────────────┘     └──────────────────┘  │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────────────┐  │
│  │  AKS Cluster│     │  Azure ACR   │     │  Slack (opt.)    │  │
│  │  (aks-test)  │     │  (pythonacrtest)│  │  (#k8s-alerts)  │  │
│  │              │     │              │     │                  │  │
│  │  Namespaces: │     │  Repos:      │     │  Receives final  │  │
│  │  • ai-chatbot│     │  • ai-chatbot│     │  report after    │  │
│  │  • default   │     │    -api      │     │  execution       │  │
│  │  • kube-sys  │     │  Tags: v1,v2,│     │                  │  │
│  │              │     │  v3, sha...  │     │                  │  │
│  └─────────────┘     └──────────────┘     └──────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. Streamlit UI State Machine

```
                    ┌────────┐
                    │  idle  │  (Initial load)
                    └───┬────┘
                        │  Auto-trigger (last_scan is None)
                        │  scan_all_namespaces()
                        ▼
                  ┌───────────┐
           ┌─────│ dashboard  │◀─────────────────────────────┐
           │     │            │                               │
           │     │ Shows all  │                               │
           │     │ unhealthy  │  "Back to dashboard"          │
           │     │ pods across│  or "Rescan Cluster"          │
           │     │ all NS     │                               │
           │     └───────────┘                                │
           │          │                                       │
           │          │ Click "🩺 Diagnose" on a pod           │
           │          ▼                                       │
           │   ┌──────────────┐                               │
           │   │  diagnosing  │  (transient — runs pipeline)  │
           │   │              │  LangGraph: detect → context  │
           │   │  spinner...  │  → rag → diagnose → propose   │
           │   └──────┬───────┘                               │
           │          │                                       │
           │          ▼                                       │
           │   ┌──────────────┐                               │
           │   │   approval   │                               │
           │   │              │                               │
           │   │ • Diagnosis  │                               │
           │   │ • ACR check  │                               │
           │   │ • Commands   │                               │
           │   │ • Risk level │                               │
           │   │ • Checkboxes │                               │
           │   └──┬───┬───┬───┘                               │
           │      │   │   │                                   │
           │  ┌───┘   │   └───┐                               │
           │  │       │       │                                │
           │  ▼       │       ▼                                │
           │ ✅       │      ❌                                │
           │APPROVE   │    REJECT    ⬅️ Back                   │
           │  │       │      │        │                        │
           │  │       │      │        └────────────────────────┘
           │  ▼       │      ▼
           │ execute  │    skip_node
           │ _commands│    (audit log)
           │ _node    │      │
           │  │       │      │
           │  ▼       │      │
           │ verify_  │      │
           │ and_     │      │
           │ report   │      │
           │  │       │      │
           │  ▼       ▼      ▼
           │  ┌──────────────┐
           │  │     done     │
           │  │              │
           │  │ • Results    │
           │  │ • Report     │──── "Back to dashboard" ───────┘
           │  │ • Audit log  │
           │  └──────────────┘
           │
           │  "Rescan Cluster" (sidebar)
           └──▶ scan_all_namespaces() → dashboard
```

---

## 7. Key Design Decisions

| Decision | Why |
|---|---|
| **LangGraph (not plain LangChain)** | Provides state machine with interrupt/resume for human approval gate |
| **ChromaDB (in-memory)** | Lightweight vector DB for 6 runbook docs — no external DB needed |
| **subprocess for kubectl** | Direct CLI calls — works with any kubeconfig, no K8s Python client dependency |
| **shell=True for az CLI** | Windows compatibility — `az` is `az.cmd`, needs shell resolution |
| **Direct node calls for approve/reject** | Avoids re-streaming full graph which resets `approval_status` to "pending" |
| **ownerReferences for deployment name** | Dynamic resolution: Pod → ReplicaSet → Deployment (no hardcoding) |
| **LangSmith via env vars** | Zero-code integration — just set `LANGCHAIN_TRACING_V2=true` |
| **scan_all_namespaces()** | Auto-discovery across entire cluster, not manual namespace entry |

---

## 8. Deployment Summary

| Component | Namespace | Image | Service IP | Port |
|-----------|-----------|-------|------------|------|
| Streamlit AI Agent | `k8s-ops-agent` | `pythonacrtest.azurecr.io/k8s-ops-agent:v1` | `48.206.107.252` | 8501 |
| AKS-MCP Server | `aks-mcp` | `ghcr.io/azure/aks-mcp:latest` | `20.232.246.193` | 8000 |

### Helm Releases
```
NAME            NAMESPACE       CHART
k8s-ops-agent   k8s-ops-agent   k8s-ops-agent-0.1.0
aks-mcp         aks-mcp         aks-mcp (official Azure chart)
```

### VS Code MCP Configuration (`.vscode/mcp.json`)
```json
{
  "servers": {
    "aks-mcp": {
      "type": "sse",
      "url": "http://20.232.246.193:8000/sse"
    }
  }
}
```
