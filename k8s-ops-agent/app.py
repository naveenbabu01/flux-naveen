# ============================================================
# POC: Kubernetes AI Ops Agent with Human Approval Gate
# Stack: Azure OpenAI + LangChain + LangGraph + ChromaDB + LangSmith
# ============================================================

import os
import subprocess
import json
import datetime
from typing import TypedDict, Annotated, List, Literal
import operator

from dotenv import load_dotenv
load_dotenv()

# ─── 1. AZURE OPENAI ─────────────────────────────────────────
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

llm = AzureChatOpenAI(
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    api_version="2024-02-01",
    temperature=0,
)

embeddings = AzureOpenAIEmbeddings(
    azure_deployment=os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT"),
    api_version="2024-02-01",
)

# ─── 2. KUBECTL TOOLS ────────────────────────────────────────
from langchain.tools import tool


def run_kubectl(cmd: str) -> str:
    """Execute a kubectl command and return output."""
    try:
        result = subprocess.run(
            cmd.split(), capture_output=True, text=True, timeout=30
        )
        return result.stdout or result.stderr
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def get_unhealthy_pods(namespace: str = "default") -> str:
    """List all pods that are NOT in Running/Completed state."""
    out = run_kubectl(f"kubectl get pods -n {namespace} -o json")
    try:
        data = json.loads(out)
        issues = []
        for pod in data.get("items", []):
            name = pod["metadata"]["name"]
            ns = pod["metadata"]["namespace"]
            phase = pod["status"].get("phase", "Unknown")
            containers = pod["status"].get("containerStatuses", [])
            for c in containers:
                state = c.get("state", {})
                restarts = c.get("restartCount", 0)
                reason = ""
                if "waiting" in state:
                    reason = state["waiting"].get("reason", "")
                elif "terminated" in state:
                    reason = state["terminated"].get("reason", "")
                if reason or restarts > 3 or phase not in ["Running", "Succeeded"]:
                    issues.append({
                        "pod": name,
                        "namespace": ns,
                        "phase": phase,
                        "reason": reason,
                        "restarts": restarts,
                    })
        return json.dumps(issues, indent=2) if issues else "All pods healthy."
    except Exception:
        return out


@tool
def get_pod_logs(pod_name: str, namespace: str = "default", lines: int = 50) -> str:
    """Get the last N lines of logs from a pod."""
    return run_kubectl(
        f"kubectl logs {pod_name} -n {namespace} --tail={lines} --previous"
    )


@tool
def describe_pod(pod_name: str, namespace: str = "default") -> str:
    """Run kubectl describe pod to get events and resource details."""
    return run_kubectl(f"kubectl describe pod {pod_name} -n {namespace}")


@tool
def get_node_status() -> str:
    """Get all node statuses in the cluster."""
    return run_kubectl("kubectl get nodes -o wide")


@tool
def get_events(namespace: str = "default") -> str:
    """Get recent Kubernetes events sorted by timestamp."""
    return run_kubectl(
        f"kubectl get events -n {namespace} --sort-by=.lastTimestamp"
    )


@tool
def verify_acr_image(image_ref: str) -> str:
    """Verify if a container image exists in Azure Container Registry.
    Pass the full image reference like: pythonacrtest.azurecr.io/myapp:tag"""
    try:
        parts = image_ref.split("/", 1)
        registry = parts[0].replace(".azurecr.io", "")
        repo_tag = parts[1] if len(parts) > 1 else ""
        if ":" in repo_tag:
            repo, tag = repo_tag.rsplit(":", 1)
        else:
            repo, tag = repo_tag, "latest"

        # Try managed identity first (for AKS), then fall back to default az login
        login_result = subprocess.run(
            f"az account show",
            capture_output=True, text=True, timeout=10, shell=True
        )
        if login_result.returncode != 0:
            # Try managed identity login (works on AKS with pod identity / workload identity)
            subprocess.run(
                "az login --identity --allow-no-subscriptions",
                capture_output=True, text=True, timeout=30, shell=True
            )

        # List available tags
        result = subprocess.run(
            f"az acr repository show-tags --name {registry} --repository {repo} -o json",
            capture_output=True, text=True, timeout=30, shell=True
        )
        if result.returncode != 0:
            return f"Error checking ACR: {result.stderr}"
        import json as _json
        tags = _json.loads(result.stdout)
        if tag in tags:
            return f"✅ Image EXISTS: {image_ref}"
        else:
            # Check for partial matches
            similar = [t for t in tags if tag in t or t in tag]
            msg = f"❌ Image TAG NOT FOUND: '{tag}' does not exist in '{registry}/{repo}'.\n"
            msg += f"Available tags: {', '.join(tags[-10:])}\n"
            if similar:
                msg += f"Did you mean: {', '.join(similar)}?"
            return msg
    except Exception as e:
        return f"Error: {str(e)}"


# ─── 3. RAG — Kubernetes Runbook Knowledge Base ───────────────
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

RUNBOOKS = [
    Document(
        page_content="""CrashLoopBackOff: Pod keeps crashing and restarting.
Causes: Application error, missing ConfigMap/Secret, wrong command, OOM.
Fix steps:
1. kubectl logs <pod> --previous  — check crash reason
2. kubectl describe pod <pod>     — check events
3. If OOM: increase memory limits in deployment
4. If config missing: kubectl get configmap / secret
5. kubectl rollout restart deployment/<name>""",
        metadata={"issue": "CrashLoopBackOff"},
    ),
    Document(
        page_content="""OOMKilled: Pod killed because it exceeded memory limit.
Causes: Memory leak, under-provisioned limits.
Fix steps:
1. kubectl top pod <pod>  — check memory usage
2. Edit deployment: increase resources.limits.memory
3. kubectl set resources deployment/<name> --limits=memory=512Mi
4. kubectl rollout restart deployment/<name>
5. Consider HPA for auto-scaling""",
        metadata={"issue": "OOMKilled"},
    ),
    Document(
        page_content="""ImagePullBackOff / ErrImagePull: Cannot pull container image.
Causes: Wrong image name/tag, private registry without secret, image deleted.
Fix steps:
1. kubectl describe pod <pod>  — see exact image and error
2. Verify image exists in registry
3. If private: kubectl create secret docker-registry regcred ...
4. Patch deployment: kubectl patch deployment <name> -p '{"spec":...}'
5. kubectl rollout restart deployment/<name>""",
        metadata={"issue": "ImagePullBackOff"},
    ),
    Document(
        page_content="""Pending pod: Pod scheduled but not running.
Causes: Insufficient CPU/memory on nodes, NodeSelector mismatch, PVC unbound.
Fix steps:
1. kubectl describe pod <pod>  — check Events section
2. kubectl get nodes           — check node capacity
3. kubectl describe nodes      — check Allocatable vs Requests
4. If PVC issue: kubectl get pvc
5. kubectl scale deployment/<name> --replicas=1 to reduce pressure""",
        metadata={"issue": "Pending"},
    ),
    Document(
        page_content="""Node NotReady: A worker node is not available.
Causes: kubelet crash, disk pressure, network issue, node unreachable.
Fix steps:
1. kubectl describe node <node>  — check conditions
2. kubectl get events            — look for node events
3. SSH to node and check: systemctl status kubelet
4. kubectl drain <node> --ignore-daemonsets
5. kubectl cordon <node>  to prevent new scheduling""",
        metadata={"issue": "NodeNotReady"},
    ),
    Document(
        page_content="""High restart count: Pod restarting frequently (>5 times).
Causes: Liveness probe failing, application crashing on start, config errors.
Fix steps:
1. kubectl logs <pod> --previous  — last crash logs
2. kubectl describe pod <pod>     — check liveness probe config
3. Temporarily disable liveness probe to diagnose
4. Fix probe thresholds: initialDelaySeconds, failureThreshold
5. kubectl rollout restart deployment/<name>""",
        metadata={"issue": "HighRestarts"},
    ),
]

vectorstore = Chroma.from_documents(
    documents=RUNBOOKS,
    embedding=embeddings,
    collection_name="k8s_runbooks",
)
retriever = vectorstore.as_retriever(search_kwargs={"k": 2})


# ─── 4. LANGGRAPH STATE ───────────────────────────────────────
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


class K8sAgentState(TypedDict):
    messages: Annotated[List, operator.add]
    namespace: str
    unhealthy_pods: List[dict]
    current_pod: dict
    pod_logs: str
    pod_describe: str
    runbook_context: str
    acr_check: str
    diagnosis: str
    proposed_commands: List[dict]  # [{cmd, reason, risk}]
    approval_status: str  # "pending" | "approved" | "rejected"
    approved_commands: List[str]
    execution_results: List[dict]
    final_report: str
    audit_log: List[dict]


# ─── 5. NODE FUNCTIONS ────────────────────────────────────────


def detect_issues_node(state: K8sAgentState) -> K8sAgentState:
    """Scan cluster for unhealthy pods."""
    ns = state.get("namespace", "default")
    raw = get_unhealthy_pods.invoke({"namespace": ns})
    try:
        pods = json.loads(raw) if raw != "All pods healthy." else []
    except Exception:
        pods = []
    return {
        **state,
        "unhealthy_pods": pods,
        "messages": state["messages"]
        + [AIMessage(content=f"Detected {len(pods)} unhealthy pods in namespace '{ns}'.")],
    }


def fetch_context_node(state: K8sAgentState) -> K8sAgentState:
    """Fetch logs, describe, and events for the current pod."""
    pod = state.get("current_pod", {})
    name = pod.get("pod", "")
    ns = pod.get("namespace", "default")
    if not name:
        return state
    logs = get_pod_logs.invoke({"pod_name": name, "namespace": ns, "lines": 80})
    describe = describe_pod.invoke({"pod_name": name, "namespace": ns})
    _events = get_events.invoke({"namespace": ns})

    # If ImagePullBackOff, verify image exists in ACR
    acr_check = ""
    reason = pod.get("reason", "")
    if reason in ["ImagePullBackOff", "ErrImagePull", "ImagePullErr"]:
        # Get image from pod JSON (more reliable than regex on describe)
        pod_json = run_kubectl(f"kubectl get pod {name} -n {ns} -o json")
        try:
            pod_data = json.loads(pod_json)
            containers = pod_data.get("spec", {}).get("containers", [])
            for c in containers:
                image = c.get("image", "")
                if ".azurecr.io" in image:
                    acr_check = verify_acr_image.invoke({"image_ref": image})
                    print(f"[DEBUG] ACR CHECK RESULT: {acr_check}")
                    break
        except Exception as e:
            print(f"[DEBUG] ACR CHECK ERROR: {e}")
        if not acr_check:
            acr_check = "Could not extract ACR image reference from pod."

    return {
        **state,
        "pod_logs": logs[:3000],
        "pod_describe": describe[:3000],
        "acr_check": acr_check,
        "messages": state["messages"]
        + [AIMessage(content=f"Fetched context for pod '{name}'." + (f"\nACR check: {acr_check}" if acr_check else ""))],
    }


def rag_node(state: K8sAgentState) -> K8sAgentState:
    """Retrieve relevant runbook for this issue type."""
    pod = state.get("current_pod", {})
    reason = pod.get("reason", "") or pod.get("phase", "")
    docs = retriever.invoke(reason)
    context = "\n\n---\n\n".join([d.page_content for d in docs])
    return {**state, "runbook_context": context}


def diagnose_node(state: K8sAgentState) -> K8sAgentState:
    """Use Azure OpenAI to diagnose the pod issue."""
    pod = state.get("current_pod", {})
    prompt = f"""You are a Kubernetes expert SRE. Diagnose this pod issue and explain the root cause clearly.

Pod: {pod.get('pod')}   Namespace: {pod.get('namespace')}
Phase: {pod.get('phase')}   Reason: {pod.get('reason')}   Restarts: {pod.get('restarts')}

--- Recent logs ---
{state.get('pod_logs', 'N/A')[:1500]}

--- kubectl describe ---
{state.get('pod_describe', 'N/A')[:1500]}

--- Runbook context ---
{state.get('runbook_context', 'N/A')}

--- ACR Image Verification ---
{state.get('acr_check', 'N/A')}

IMPORTANT: If the ACR check shows the image tag does NOT exist but suggests similar tags,
the root cause is a WRONG IMAGE TAG, not a missing pull secret.

Provide:
1. Root cause (2-3 sentences). If image tag is wrong, state the wrong tag and the correct tag.
2. Severity: LOW / MEDIUM / HIGH / CRITICAL
3. Confidence: 0-100%"""

    response = llm.invoke([
        SystemMessage(content="You are a senior Kubernetes SRE. Be concise and precise."),
        HumanMessage(content=prompt),
    ])
    return {
        **state,
        "diagnosis": response.content,
        "messages": state["messages"] + [AIMessage(content=response.content)],
    }


def propose_commands_node(state: K8sAgentState) -> K8sAgentState:
    """Generate kubectl fix commands with risk level for each."""
    pod = state.get("current_pod", {})
    ns = pod.get("namespace", "default")
    acr_info = state.get('acr_check', '')

    # Dynamically get deployment name and container info from the pod
    deploy_name = ""
    container_name = ""
    current_image = ""
    pod_name = pod.get("pod", "")
    if pod_name:
        pod_json = run_kubectl(f"kubectl get pod {pod_name} -n {ns} -o json")
        try:
            pod_data = json.loads(pod_json)
            # Get deployment name from owner references
            for owner in pod_data.get("metadata", {}).get("ownerReferences", []):
                if owner.get("kind") == "ReplicaSet":
                    rs_name = owner.get("name", "")
                    # Deployment name = ReplicaSet name minus the last hash
                    deploy_name = "-".join(rs_name.split("-")[:-1])
            # Get container name and image
            containers = pod_data.get("spec", {}).get("containers", [])
            if containers:
                container_name = containers[0].get("name", "")
                current_image = containers[0].get("image", "")
        except Exception:
            pass

    # Extract the correct tag and build the full correct image reference
    correct_tag_hint = ""
    correct_image_cmd = ""
    if "Did you mean:" in acr_info:
        import re
        meant = re.search(r'Did you mean:\s*(.+?)(?:\?|$)', acr_info)
        if meant and current_image and deploy_name:
            correct_tag = meant.group(1).strip()
            # Build correct image: replace wrong tag with correct one
            registry_repo = current_image.rsplit(":", 1)[0]  # e.g. pythonacrtest.azurecr.io/ai-chatbot-api
            correct_image = f"{registry_repo}:{correct_tag}"
            correct_tag_hint = f"\nWrong image: {current_image}\nCorrect image: {correct_image}"
            correct_image_cmd = f"\nEXACT FIX COMMAND (use this verbatim): kubectl set image deployment/{deploy_name} {container_name}={correct_image} -n {ns}"
    if "Available tags:" in acr_info and not correct_tag_hint:
        import re
        tags_match = re.search(r'Available tags:\s*(.+?)(?:\n|$)', acr_info)
        if tags_match:
            correct_tag_hint = f"\nAvailable tags in ACR: {tags_match.group(1).strip()}"

    prompt = f"""Based on this diagnosis, generate the exact kubectl commands to fix the issue.

Pod: {pod_name}   Namespace: {ns}
Deployment: {deploy_name}   Container: {container_name}
Current image: {current_image}
Diagnosis: {state.get('diagnosis')}

ACR Image Verification: {acr_info}
{correct_tag_hint}
{correct_image_cmd}

CRITICAL RULES:
- If an EXACT FIX COMMAND is provided above, use it VERBATIM as the first command. Do NOT modify it.
- Always include .azurecr.io in the registry URL (e.g. myregistry.azurecr.io/myrepo:tag).
- NEVER use placeholder values like <correct_tag>, <ACR_USERNAME>, <ACR_PASSWORD>, <EMAIL>. Use only REAL values.
- Use the REAL deployment name, container name, namespace, and image from the context above.

Return a JSON array only. Each item must have:
- "cmd": the exact kubectl command string
- "reason": why this command helps (1 sentence)
- "risk": "LOW" | "MEDIUM" | "HIGH"
- "order": execution order (1, 2, 3...)

Example:
[
  {{"cmd": "kubectl rollout restart deployment/myapp -n default", "reason": "Restarts pods with fresh config", "risk": "LOW", "order": 1}},
  {{"cmd": "kubectl delete pod myapp-xxxx -n default", "reason": "Force reschedule crashed pod", "risk": "MEDIUM", "order": 2}}
]

Return ONLY valid JSON."""

    response = llm.invoke([HumanMessage(content=prompt)])
    try:
        raw = response.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        commands = json.loads(raw)
    except Exception:
        commands = [
            {
                "cmd": f"kubectl describe pod {pod.get('pod')} -n {pod.get('namespace')}",
                "reason": "Investigate pod state",
                "risk": "LOW",
                "order": 1,
            }
        ]
    return {
        **state,
        "proposed_commands": sorted(commands, key=lambda x: x.get("order", 1)),
        "approval_status": "pending",
        "messages": state["messages"]
        + [AIMessage(content=f"Proposed {len(commands)} commands. Awaiting approval.")],
    }


def execute_commands_node(state: K8sAgentState) -> K8sAgentState:
    """Execute only the approved commands."""
    approved = state.get("approved_commands", [])
    results = []
    audit = state.get("audit_log", [])

    for cmd in approved:
        output = run_kubectl(cmd)
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "command": cmd,
            "output": output[:500],
            "status": "executed",
        }
        results.append(entry)
        audit.append(entry)
        print(f"[EXECUTED] {cmd}\n{output[:200]}")

    return {
        **state,
        "execution_results": results,
        "audit_log": audit,
        "messages": state["messages"]
        + [AIMessage(content=f"Executed {len(results)} approved commands.")],
    }


def verify_and_report_node(state: K8sAgentState) -> K8sAgentState:
    """Re-check pod status and generate summary report."""
    import time

    time.sleep(5)  # wait for K8s to reconcile

    pod = state.get("current_pod", {})
    name = pod.get("pod", "")
    ns = pod.get("namespace", "default")
    post_status = run_kubectl(f"kubectl get pod {name} -n {ns}")

    report = f"""
=== K8s AI Ops Agent Report ===
Pod:       {name}
Namespace: {ns}
Issue:     {pod.get('reason')} (restarts: {pod.get('restarts')})

Diagnosis:
{state.get('diagnosis')}

Commands executed:
{chr(10).join(['  ' + r['command'] for r in state.get('execution_results', [])])}

Post-fix pod status:
{post_status}

Approval status: {state.get('approval_status')}
Timestamp: {datetime.datetime.utcnow().isoformat()}
"""

    _send_slack(report)

    return {
        **state,
        "final_report": report,
        "messages": state["messages"] + [AIMessage(content=report)],
    }


def skip_node(state: K8sAgentState) -> K8sAgentState:
    """Handle rejection — log and continue."""
    pod = state.get("current_pod", {})
    audit = state.get("audit_log", [])
    audit.append(
        {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "pod": pod.get("pod"),
            "status": "rejected_by_operator",
            "commands": [c["cmd"] for c in state.get("proposed_commands", [])],
        }
    )
    return {
        **state,
        "audit_log": audit,
        "final_report": f"Operator rejected fix for pod: {pod.get('pod')}",
        "messages": state["messages"]
        + [AIMessage(content="Operator rejected. Skipping fix.")],
    }


def _send_slack(message: str):
    """Post report to Slack (optional)."""
    token = os.getenv("SLACK_BOT_TOKEN")
    channel = os.getenv("SLACK_CHANNEL", "#k8s-alerts")
    if not token:
        return
    try:
        from slack_sdk import WebClient

        WebClient(token=token).chat_postMessage(
            channel=channel, text=f"```{message[:2900]}```"
        )
    except Exception as e:
        print(f"Slack error: {e}")


# ─── 6. ROUTER FUNCTIONS ─────────────────────────────────────


def approval_router(state: K8sAgentState) -> Literal["execute", "skip"]:
    status = state.get("approval_status", "pending")
    return "execute" if status == "approved" else "skip"


# ─── 7. BUILD LANGGRAPH ───────────────────────────────────────
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()

graph = StateGraph(K8sAgentState)

graph.add_node("detect", detect_issues_node)
graph.add_node("context", fetch_context_node)
graph.add_node("rag", rag_node)
graph.add_node("diagnose", diagnose_node)
graph.add_node("propose", propose_commands_node)
graph.add_node("execute", execute_commands_node)
graph.add_node("skip", skip_node)
graph.add_node("report", verify_and_report_node)

graph.set_entry_point("detect")
graph.add_edge("detect", "context")
graph.add_edge("context", "rag")
graph.add_edge("rag", "diagnose")
graph.add_edge("diagnose", "propose")

# INTERRUPT HERE — waits for human approval
graph.add_conditional_edges(
    "propose",
    approval_router,
    {"execute": "execute", "skip": "skip"},
)
graph.add_edge("execute", "report")
graph.add_edge("skip", "report")
graph.add_edge("report", END)

k8s_agent = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["execute"],  # LangGraph pauses here for approval
)


# ─── 8. STREAMLIT UI ─────────────────────────────────────────
import streamlit as st

RISK_COLOR = {"LOW": "green", "MEDIUM": "orange", "HIGH": "red", "CRITICAL": "red"}


def scan_all_namespaces() -> list:
    """Scan ALL namespaces for unhealthy pods automatically."""
    # Get all namespaces
    ns_raw = run_kubectl("kubectl get namespaces -o json")
    namespaces = []
    try:
        ns_data = json.loads(ns_raw)
        namespaces = [item["metadata"]["name"] for item in ns_data.get("items", [])]
    except Exception:
        namespaces = ["default"]

    all_unhealthy = []
    for ns in namespaces:
        raw = get_unhealthy_pods.invoke({"namespace": ns})
        try:
            pods = json.loads(raw) if raw != "All pods healthy." else []
            all_unhealthy.extend(pods)
        except Exception:
            pass
    return all_unhealthy


def run_ui():
    st.set_page_config(
        page_title="K8s AI Ops Agent", page_icon="☸️", layout="wide"
    )
    st.title("☸️ Kubernetes AI Ops Agent")
    st.caption(
        "Powered by Azure OpenAI + LangGraph | Auto-scans all namespaces for unhealthy pods"
    )

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = "k8s-session-1"
        st.session_state.state = None
        st.session_state.phase = "idle"
        st.session_state.all_unhealthy = []
        st.session_state.last_scan = None
        st.session_state.config = {
            "configurable": {"thread_id": st.session_state.thread_id}
        }

    # ── Auto-scan on first load ──
    if st.session_state.phase == "idle" and st.session_state.last_scan is None:
        with st.spinner("🔍 Auto-scanning all namespaces for unhealthy pods..."):
            st.session_state.all_unhealthy = scan_all_namespaces()
            st.session_state.last_scan = datetime.datetime.utcnow().isoformat()
            st.session_state.phase = "dashboard"
        st.rerun()

    # ── Sidebar ──
    with st.sidebar:
        st.markdown("### ⚙️ Controls")
        if st.button("🔄 Rescan Cluster", type="primary"):
            with st.spinner("Scanning all namespaces..."):
                st.session_state.all_unhealthy = scan_all_namespaces()
                st.session_state.last_scan = datetime.datetime.utcnow().isoformat()
                st.session_state.phase = "dashboard"
                st.session_state.state = None
            st.rerun()

        if st.session_state.last_scan:
            st.caption(f"Last scan: {st.session_state.last_scan}")

        st.markdown("---")
        total = len(st.session_state.all_unhealthy)
        if total > 0:
            st.error(f"🚨 {total} unhealthy pod(s)")
        else:
            st.success("✅ Cluster healthy")

        # Group by namespace
        ns_counts = {}
        for p in st.session_state.all_unhealthy:
            ns = p.get("namespace", "unknown")
            ns_counts[ns] = ns_counts.get(ns, 0) + 1
        if ns_counts:
            st.markdown("**By namespace:**")
            for ns, count in sorted(ns_counts.items()):
                st.markdown(f"- `{ns}`: {count} pod(s)")

    # ── Main area ──
    pods = st.session_state.all_unhealthy

    if st.session_state.phase == "dashboard":
        if not pods:
            st.success("✅ All pods across all namespaces are healthy!")
        else:
            st.error(f"🚨 Found {len(pods)} unhealthy pod(s) across the cluster")
            st.markdown("---")

            for i, pod_data in enumerate(pods):
                reason = pod_data.get("reason", "Unknown")
                phase = pod_data.get("phase", "Unknown")
                restarts = pod_data.get("restarts", 0)
                ns = pod_data.get("namespace", "")
                name = pod_data.get("pod", "")

                severity_icon = "🔴" if reason in ["CrashLoopBackOff", "OOMKilled", "ImagePullBackOff", "ErrImagePull"] else "🟡"

                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1, 2])
                    c1.markdown(f"{severity_icon} **{name}**")
                    c2.caption(f"ns: `{ns}`")
                    c3.caption(f"Reason: `{reason}`")
                    c4.caption(f"↻ {restarts}")
                    with c5:
                        if st.button("🩺 Diagnose", key=f"diag_{i}"):
                            st.session_state.phase = "diagnosing"
                            st.session_state.selected_pod = pod_data
                            # Build state and run diagnosis pipeline
                            initial_state: K8sAgentState = {
                                "messages": [],
                                "namespace": ns,
                                "unhealthy_pods": pods,
                                "current_pod": pod_data,
                                "pod_logs": "",
                                "pod_describe": "",
                                "runbook_context": "",
                                "acr_check": "",
                                "diagnosis": "",
                                "proposed_commands": [],
                                "approval_status": "pending",
                                "approved_commands": [],
                                "execution_results": [],
                                "final_report": "",
                                "audit_log": [],
                            }
                            with st.spinner(f"Diagnosing `{name}` with Azure OpenAI..."):
                                for event in k8s_agent.stream(
                                    initial_state,
                                    config={"configurable": {"thread_id": f"k8s-{name}"}},
                                    stream_mode="values",
                                ):
                                    st.session_state.state = event
                            st.session_state.phase = "approval"
                            st.rerun()
                st.divider()

    elif st.session_state.phase == "approval" and st.session_state.state:
        state = st.session_state.state
        pod = state.get("current_pod", {})
        st.markdown(f"### 🩺 Diagnosing: `{pod.get('pod')}` in `{pod.get('namespace')}`")

        st.markdown("### 🔬 Diagnosis")
        st.info(state.get("diagnosis", ""))

        if state.get("acr_check"):
            st.markdown("### 🐳 ACR Image Check")
            st.code(state.get("acr_check"))

        st.markdown("### 🛠️ Proposed kubectl commands")
        st.warning(
            "⚠️ Review carefully before approving. These commands will run against your live cluster."
        )

        commands = state.get("proposed_commands", [])
        approved_list = []

        for i, cmd_obj in enumerate(commands):
            risk = cmd_obj.get("risk", "LOW")
            color = RISK_COLOR.get(risk, "gray")
            with st.container():
                st.markdown(
                    f"**Command {i+1}** &nbsp; :{color}[Risk: {risk}]"
                )
                st.code(cmd_obj["cmd"], language="bash")
                st.caption(cmd_obj.get("reason", ""))
                if st.checkbox(
                    f"Include command {i+1}",
                    value=(risk == "LOW"),
                    key=f"cmd_{i}",
                ):
                    approved_list.append(cmd_obj["cmd"])
            st.divider()

        col_a, col_r, col_back = st.columns(3)

        with col_a:
            if st.button(
                "✅ APPROVE & EXECUTE",
                type="primary",
                disabled=len(approved_list) == 0,
            ):
                final_state = {
                    **state,
                    "approval_status": "approved",
                    "approved_commands": approved_list,
                }
                with st.spinner("Executing approved commands..."):
                    final_state = execute_commands_node(final_state)
                    final_state = verify_and_report_node(final_state)
                    st.session_state.state = final_state
                st.session_state.phase = "done"
                st.rerun()

        with col_r:
            if st.button("❌ REJECT ALL", type="secondary"):
                final_state = {
                    **state,
                    "approval_status": "rejected",
                    "approved_commands": [],
                }
                final_state = skip_node(final_state)
                st.session_state.state = final_state
                st.session_state.phase = "done"
                st.rerun()

        with col_back:
            if st.button("⬅️ Back to dashboard"):
                st.session_state.phase = "dashboard"
                st.session_state.state = None
                st.rerun()

    elif st.session_state.phase == "done" and st.session_state.state:
        state = st.session_state.state
        status = state.get("approval_status")
        if status == "approved":
            st.success("✅ Commands executed successfully!")
            st.markdown("### Execution results")
            for r in state.get("execution_results", []):
                with st.expander(r["command"]):
                    st.code(r["output"])
        elif status == "rejected":
            st.warning("Commands were rejected. No changes made to cluster.")

        st.markdown("### 📋 Final report")
        st.text(state.get("final_report", ""))

        st.markdown("### 📜 Audit log")
        st.json(state.get("audit_log", []))

        if st.button("🔄 Back to dashboard"):
            st.session_state.phase = "dashboard"
            st.session_state.state = None
            st.rerun()


if __name__ == "__main__":
    run_ui()
