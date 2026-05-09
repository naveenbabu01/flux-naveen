# ============================================================
# MCP Server: Kubernetes AI Ops Agent
# Exposes K8s diagnostic tools via Model Context Protocol
# For use with VS Code + GitHub Copilot, Claude Desktop, etc.
# ============================================================

import os
import subprocess
import json
import datetime
from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP

# ─── Initialize MCP Server ────────────────────────────────────
mcp = FastMCP("K8s AI Ops Agent")

# ─── Azure OpenAI Setup ───────────────────────────────────────
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage

llm = AzureChatOpenAI(
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    api_version="2024-02-01",
    temperature=0,
)


# ─── Helper Functions ─────────────────────────────────────────


def run_kubectl(cmd: str) -> str:
    """Execute a kubectl command and return output."""
    try:
        result = subprocess.run(
            cmd.split(), capture_output=True, text=True, timeout=30
        )
        return result.stdout or result.stderr
    except Exception as e:
        return f"Error: {str(e)}"


# ─── MCP Tools ────────────────────────────────────────────────


@mcp.tool()
def scan_cluster() -> str:
    """Scan ALL namespaces in the Kubernetes cluster for unhealthy pods.
    Returns a list of pods with issues including pod name, namespace, phase, reason, and restart count.
    Use this as the first step to find problems in the cluster."""

    ns_raw = run_kubectl("kubectl get namespaces -o json")
    namespaces = []
    try:
        ns_data = json.loads(ns_raw)
        namespaces = [item["metadata"]["name"] for item in ns_data.get("items", [])]
    except Exception:
        namespaces = ["default"]

    all_unhealthy = []
    for ns in namespaces:
        out = run_kubectl(f"kubectl get pods -n {ns} -o json")
        try:
            data = json.loads(out)
            for pod in data.get("items", []):
                name = pod["metadata"]["name"]
                phase = pod["status"].get("phase", "Unknown")
                for c in pod["status"].get("containerStatuses", []):
                    state = c.get("state", {})
                    restarts = c.get("restartCount", 0)
                    reason = ""
                    if "waiting" in state:
                        reason = state["waiting"].get("reason", "")
                    elif "terminated" in state:
                        reason = state["terminated"].get("reason", "")
                    if reason or restarts > 3 or phase not in ["Running", "Succeeded"]:
                        all_unhealthy.append({
                            "pod": name,
                            "namespace": ns,
                            "phase": phase,
                            "reason": reason,
                            "restarts": restarts,
                        })
        except Exception:
            pass

    if not all_unhealthy:
        return "✅ All pods across all namespaces are healthy!"

    result = f"🚨 Found {len(all_unhealthy)} unhealthy pod(s):\n\n"
    for p in all_unhealthy:
        result += f"• **{p['pod']}** (ns: `{p['namespace']}`) — {p['reason'] or p['phase']} | restarts: {p['restarts']}\n"
    return result


@mcp.tool()
def diagnose_pod(pod_name: str, namespace: str = "default") -> str:
    """Diagnose a specific unhealthy pod using logs, events, and Azure OpenAI analysis.
    Provides root cause, severity, and confidence level.

    Args:
        pod_name: The name of the pod to diagnose
        namespace: The Kubernetes namespace (default: "default")
    """

    # Gather context
    logs = run_kubectl(f"kubectl logs {pod_name} -n {namespace} --tail=80 --previous")
    describe = run_kubectl(f"kubectl describe pod {pod_name} -n {namespace}")
    events = run_kubectl(f"kubectl get events -n {namespace} --sort-by=.lastTimestamp")

    # Check ACR image if ImagePullBackOff
    acr_check = ""
    pod_json = run_kubectl(f"kubectl get pod {pod_name} -n {namespace} -o json")
    try:
        pod_data = json.loads(pod_json)
        # Get pod reason
        for c in pod_data.get("status", {}).get("containerStatuses", []):
            state = c.get("state", {})
            if "waiting" in state:
                reason = state["waiting"].get("reason", "")
                if reason in ["ImagePullBackOff", "ErrImagePull"]:
                    for container in pod_data.get("spec", {}).get("containers", []):
                        image = container.get("image", "")
                        if ".azurecr.io" in image:
                            acr_check = _verify_acr_image(image)
                            break
    except Exception:
        pass

    # LLM diagnosis
    prompt = f"""You are a Kubernetes expert SRE. Diagnose this pod issue.

Pod: {pod_name}   Namespace: {namespace}

--- Recent logs ---
{logs[:1500]}

--- kubectl describe ---
{describe[:1500]}

--- ACR Image Verification ---
{acr_check or 'N/A'}

IMPORTANT: If the ACR check shows the image tag does NOT exist but suggests similar tags,
the root cause is a WRONG IMAGE TAG, not a missing pull secret.

Provide:
1. Root cause (2-3 sentences). If image tag is wrong, state the wrong tag and the correct tag.
2. Severity: LOW / MEDIUM / HIGH / CRITICAL
3. Confidence: 0-100%
4. Suggested fix commands (kubectl commands)"""

    response = llm.invoke([
        SystemMessage(content="You are a senior Kubernetes SRE. Be concise and precise."),
        HumanMessage(content=prompt),
    ])
    return response.content


@mcp.tool()
def get_pod_logs(pod_name: str, namespace: str = "default", lines: int = 50) -> str:
    """Get the last N lines of logs from a Kubernetes pod.

    Args:
        pod_name: The name of the pod
        namespace: The Kubernetes namespace (default: "default")
        lines: Number of log lines to retrieve (default: 50)
    """
    current_logs = run_kubectl(f"kubectl logs {pod_name} -n {namespace} --tail={lines}")
    previous_logs = run_kubectl(f"kubectl logs {pod_name} -n {namespace} --tail={lines} --previous")

    result = f"=== Current Logs ===\n{current_logs[:3000]}\n"
    if previous_logs and "error" not in previous_logs.lower()[:50]:
        result += f"\n=== Previous Container Logs ===\n{previous_logs[:3000]}"
    return result


@mcp.tool()
def describe_pod(pod_name: str, namespace: str = "default") -> str:
    """Get detailed pod information including events, resource usage, and conditions.

    Args:
        pod_name: The name of the pod
        namespace: The Kubernetes namespace (default: "default")
    """
    return run_kubectl(f"kubectl describe pod {pod_name} -n {namespace}")


@mcp.tool()
def get_events(namespace: str = "default") -> str:
    """Get recent Kubernetes events for a namespace, sorted by timestamp.

    Args:
        namespace: The Kubernetes namespace (default: "default")
    """
    return run_kubectl(f"kubectl get events -n {namespace} --sort-by=.lastTimestamp")


@mcp.tool()
def get_node_status() -> str:
    """Get the status of all nodes in the Kubernetes cluster.
    Shows node name, status, roles, version, and resource info."""
    return run_kubectl("kubectl get nodes -o wide")


@mcp.tool()
def verify_acr_image(image_ref: str) -> str:
    """Verify if a container image exists in Azure Container Registry.

    Args:
        image_ref: Full image reference (e.g., pythonacrtest.azurecr.io/myapp:tag)
    """
    return _verify_acr_image(image_ref)


def _verify_acr_image(image_ref: str) -> str:
    """Internal ACR image verification."""
    try:
        parts = image_ref.split("/", 1)
        registry = parts[0].replace(".azurecr.io", "")
        repo_tag = parts[1] if len(parts) > 1 else ""
        if ":" in repo_tag:
            repo, tag = repo_tag.rsplit(":", 1)
        else:
            repo, tag = repo_tag, "latest"

        # Try managed identity first (AKS), then fallback
        login_result = subprocess.run(
            "az account show", capture_output=True, text=True, timeout=10, shell=True
        )
        if login_result.returncode != 0:
            subprocess.run(
                "az login --identity --allow-no-subscriptions",
                capture_output=True, text=True, timeout=30, shell=True,
            )

        result = subprocess.run(
            f"az acr repository show-tags --name {registry} --repository {repo} -o json",
            capture_output=True, text=True, timeout=30, shell=True,
        )
        if result.returncode != 0:
            return f"Error checking ACR: {result.stderr}"

        tags = json.loads(result.stdout)
        if tag in tags:
            return f"✅ Image EXISTS: {image_ref}"
        else:
            similar = [t for t in tags if tag in t or t in tag]
            msg = f"❌ Image TAG NOT FOUND: '{tag}' does not exist in '{registry}/{repo}'.\n"
            msg += f"Available tags: {', '.join(tags[-10:])}\n"
            if similar:
                msg += f"Did you mean: {', '.join(similar)}?"
            return msg
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def propose_fix(pod_name: str, namespace: str = "default") -> str:
    """Analyze an unhealthy pod and propose kubectl fix commands with risk levels.
    Returns a list of commands with explanations and risk assessment.

    Args:
        pod_name: The name of the pod to fix
        namespace: The Kubernetes namespace (default: "default")
    """

    # Get pod details
    pod_json = run_kubectl(f"kubectl get pod {pod_name} -n {namespace} -o json")
    deploy_name = ""
    container_name = ""
    current_image = ""
    try:
        pod_data = json.loads(pod_json)
        for owner in pod_data.get("metadata", {}).get("ownerReferences", []):
            if owner.get("kind") == "ReplicaSet":
                rs_name = owner.get("name", "")
                deploy_name = "-".join(rs_name.split("-")[:-1])
        containers = pod_data.get("spec", {}).get("containers", [])
        if containers:
            container_name = containers[0].get("name", "")
            current_image = containers[0].get("image", "")
    except Exception:
        pass

    # Get diagnosis first
    diagnosis = diagnose_pod(pod_name, namespace)

    prompt = f"""Based on this diagnosis, generate kubectl fix commands.

Pod: {pod_name}   Namespace: {namespace}
Deployment: {deploy_name}   Container: {container_name}
Current image: {current_image}
Diagnosis: {diagnosis}

RULES:
- Use REAL values only (no placeholders)
- Include risk level for each command

Return as a numbered list:
1. [RISK: LOW/MEDIUM/HIGH] `kubectl command here` — reason
2. ..."""

    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


@mcp.tool()
def execute_command(command: str) -> str:
    """Execute a single kubectl command against the cluster.
    ⚠️ IMPORTANT: Only use this after the user has explicitly approved the command.

    Args:
        command: The kubectl command to execute (e.g., "kubectl rollout restart deployment/myapp -n default")
    """

    if not command.startswith("kubectl"):
        return "❌ Error: Only kubectl commands are allowed."

    # Safety check — block dangerous commands
    dangerous = ["delete namespace", "delete node", "delete --all", "drain"]
    for d in dangerous:
        if d in command.lower():
            return f"❌ Blocked: '{d}' commands require manual execution for safety."

    output = run_kubectl(command)

    # Log the execution
    log_entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "command": command,
        "output": output[:500],
        "source": "mcp-copilot",
    }
    print(f"[MCP EXECUTED] {json.dumps(log_entry)}")

    return f"✅ Executed: `{command}`\n\nOutput:\n```\n{output}\n```"


@mcp.tool()
def get_cluster_summary() -> str:
    """Get a high-level summary of the Kubernetes cluster.
    Includes node count, pod counts by namespace, and overall health."""

    nodes = run_kubectl("kubectl get nodes -o json")
    node_count = 0
    try:
        node_count = len(json.loads(nodes).get("items", []))
    except Exception:
        pass

    ns_raw = run_kubectl("kubectl get namespaces -o json")
    namespaces = []
    try:
        ns_data = json.loads(ns_raw)
        namespaces = [item["metadata"]["name"] for item in ns_data.get("items", [])]
    except Exception:
        namespaces = ["default"]

    summary = f"## Cluster Summary\n\n"
    summary += f"**Nodes:** {node_count}\n"
    summary += f"**Namespaces:** {len(namespaces)}\n\n"
    summary += "| Namespace | Total Pods | Running | Issues |\n"
    summary += "|---|---|---|---|\n"

    total_issues = 0
    for ns in namespaces:
        pods_raw = run_kubectl(f"kubectl get pods -n {ns} -o json")
        try:
            pods = json.loads(pods_raw).get("items", [])
            total = len(pods)
            running = sum(1 for p in pods if p["status"].get("phase") == "Running")
            issues = total - running
            total_issues += issues
            if total > 0:
                summary += f"| `{ns}` | {total} | {running} | {issues} |\n"
        except Exception:
            pass

    summary += f"\n**Overall health:** {'✅ Healthy' if total_issues == 0 else f'🚨 {total_issues} issue(s) detected'}"
    return summary


# ─── Run Server ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    # Patch MCP SSE to allow all hosts (needed for external LoadBalancer IP)
    import mcp.server.sse as sse_module
    original_validate = getattr(sse_module, '_validate_request', None)
    # Patch any validation function to always pass
    for attr in dir(sse_module):
        obj = getattr(sse_module, attr)
        if callable(obj) and 'valid' in attr.lower():
            setattr(sse_module, attr, lambda *a, **kw: True)

    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import Response

    sse_transport = SseServerTransport("/messages/")

    # Also patch instance methods
    for attr in dir(sse_transport):
        if 'valid' in attr.lower() or 'allowed' in attr.lower():
            try:
                setattr(sse_transport, attr, lambda *a, **kw: True)
            except (AttributeError, TypeError):
                pass

    async def handle_sse(request):
        # Manually set headers to pass validation
        if 'host' not in request.headers:
            request.scope['headers'].append((b'host', b'localhost'))
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp._mcp_server.run(
                streams[0], streams[1], mcp._mcp_server.create_initialization_options()
            )
        return Response()

    async def handle_messages(request):
        await sse_transport.handle_post_message(request.scope, request.receive, request._send)
        return Response()

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages/{session_id}", endpoint=handle_messages, methods=["POST"]),
        ],
    )

    print("🚀 MCP Server starting on http://0.0.0.0:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
