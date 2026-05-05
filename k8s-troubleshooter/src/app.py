import os
import subprocess
import json
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import AzureOpenAI
from typing import Optional, List

app = FastAPI(title="K8s Troubleshooter Bot", version="2.0.0")

app.mount("/static", StaticFiles(directory="static"), name="static")

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
)

DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1")

K8S_SYSTEM_PROMPT = """You are an expert Kubernetes troubleshooter and SRE engineer. 
When a user provides a Kubernetes error, log, or issue:

1. **Identify the Problem**: Clearly state what the error means
2. **Root Cause**: Explain the most likely root cause(s)
3. **Solution Steps**: Provide step-by-step kubectl commands to fix it
4. **Prevention**: Suggest how to prevent this in the future
5. **Severity**: Rate the severity (🟢 Low, 🟡 Medium, 🔴 Critical)

Format your response with clear headings and code blocks for commands.
Always provide working kubectl commands that can be copy-pasted.
If the user provides pod/deployment names, use them in your commands.
"""


class TroubleshootRequest(BaseModel):
    error: str
    namespace: Optional[str] = "default"
    resource_name: Optional[str] = None
    max_tokens: int = 1000


class TroubleshootResponse(BaseModel):
    error: str
    diagnosis: str
    model: str


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/", include_in_schema=False)
def serve_ui():
    return FileResponse("static/index.html")


@app.post("/troubleshoot", response_model=TroubleshootResponse)
def troubleshoot(request: TroubleshootRequest):
    try:
        context = f"Error/Issue: {request.error}"
        if request.namespace:
            context += f"\nNamespace: {request.namespace}"
        if request.resource_name:
            context += f"\nResource: {request.resource_name}"

        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": K8S_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            max_tokens=request.max_tokens,
        )
        return TroubleshootResponse(
            error=request.error,
            diagnosis=response.choices[0].message.content,
            model=DEPLOYMENT_NAME,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────── LIVE CLUSTER ANALYSIS ────────────────────

def run_kubectl(cmd: str) -> str:
    """Run a kubectl command and return output."""
    try:
        result = subprocess.run(
            cmd.split(), capture_output=True, text=True, timeout=15
        )
        return result.stdout if result.returncode == 0 else result.stderr
    except Exception as e:
        return f"Error running kubectl: {str(e)}"


class PodIssue(BaseModel):
    pod_name: str
    namespace: str
    status: str
    restarts: int
    reason: str
    logs: str = ""


class ClusterScanResponse(BaseModel):
    total_pods: int
    healthy_pods: int
    unhealthy_pods: int
    issues: List[dict]
    ai_diagnosis: str = ""
    model: str = ""


@app.get("/scan")
def scan_cluster():
    """Scan ALL namespaces for unhealthy pods and return AI diagnosis."""
    try:
        # Get all pods across all namespaces
        pod_output = run_kubectl("kubectl get pods --all-namespaces -o json")
        if "Error" in pod_output or not pod_output.strip():
            raise HTTPException(status_code=500, detail=f"kubectl error: {pod_output}")

        pods_data = json.loads(pod_output)
        all_pods = pods_data.get("items", [])

        total = len(all_pods)
        issues = []

        for pod in all_pods:
            name = pod["metadata"]["name"]
            ns = pod["metadata"]["namespace"]
            phase = pod["status"].get("phase", "Unknown")

            # Check container statuses
            container_statuses = pod["status"].get("containerStatuses", [])
            for cs in container_statuses:
                restarts = cs.get("restartCount", 0)
                ready = cs.get("ready", False)
                state = cs.get("state", {})

                # Detect issues
                waiting = state.get("waiting", {})
                reason = waiting.get("reason", "")

                if reason in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull",
                              "CreateContainerConfigError", "OOMKilled", "RunContainerError"]:
                    # Get last 20 lines of logs
                    logs = run_kubectl(f"kubectl logs {name} -n {ns} --tail=20")
                    issues.append({
                        "pod_name": name,
                        "namespace": ns,
                        "status": reason,
                        "restarts": restarts,
                        "reason": waiting.get("message", reason),
                        "logs": logs[:500]  # limit log size
                    })
                elif not ready and phase == "Running" and restarts > 3:
                    logs = run_kubectl(f"kubectl logs {name} -n {ns} --tail=20")
                    issues.append({
                        "pod_name": name,
                        "namespace": ns,
                        "status": "Unhealthy (high restarts)",
                        "restarts": restarts,
                        "reason": f"Pod has restarted {restarts} times",
                        "logs": logs[:500]
                    })

            # Check for Pending pods
            if phase == "Pending":
                conditions = pod["status"].get("conditions", [])
                reason_msg = ""
                for c in conditions:
                    if c.get("status") == "False":
                        reason_msg = c.get("message", "Unknown reason")
                        break
                issues.append({
                    "pod_name": name,
                    "namespace": ns,
                    "status": "Pending",
                    "restarts": 0,
                    "reason": reason_msg or "Pod stuck in Pending",
                    "logs": ""
                })

        healthy = total - len(issues)

        # If there are issues, get AI diagnosis
        ai_diagnosis = ""
        model = ""
        if issues:
            issues_summary = "\n".join([
                f"- Pod: {i['pod_name']} | Namespace: {i['namespace']} | "
                f"Status: {i['status']} | Restarts: {i['restarts']} | "
                f"Reason: {i['reason']}\n  Logs: {i['logs'][:200]}"
                for i in issues[:10]  # limit to 10 issues
            ])

            prompt = f"""Analyze these Kubernetes cluster issues and provide fixes for each:

{issues_summary}

For each issue, provide:
1. What's wrong
2. The fix (kubectl commands)
3. Priority (🔴 Critical / 🟡 Medium / 🟢 Low)
"""
            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": K8S_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
            )
            ai_diagnosis = response.choices[0].message.content
            model = DEPLOYMENT_NAME

        return ClusterScanResponse(
            total_pods=total,
            healthy_pods=healthy,
            unhealthy_pods=len(issues),
            issues=issues,
            ai_diagnosis=ai_diagnosis,
            model=model,
        )
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse kubectl output")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scan/{namespace}")
def scan_namespace(namespace: str):
    """Scan a specific namespace for unhealthy pods."""
    try:
        pod_output = run_kubectl(f"kubectl get pods -n {namespace} -o json")
        pods_data = json.loads(pod_output)
        all_pods = pods_data.get("items", [])

        issues = []
        for pod in all_pods:
            name = pod["metadata"]["name"]
            phase = pod["status"].get("phase", "Unknown")
            container_statuses = pod["status"].get("containerStatuses", [])

            for cs in container_statuses:
                restarts = cs.get("restartCount", 0)
                ready = cs.get("ready", False)
                waiting = cs.get("state", {}).get("waiting", {})
                reason = waiting.get("reason", "")

                if reason or (not ready and restarts > 0):
                    logs = run_kubectl(f"kubectl logs {name} -n {namespace} --tail=20")
                    issues.append({
                        "pod_name": name,
                        "namespace": namespace,
                        "status": reason or phase,
                        "restarts": restarts,
                        "reason": waiting.get("message", reason or "Not ready"),
                        "logs": logs[:500]
                    })

        # AI diagnosis
        ai_diagnosis = ""
        if issues:
            issues_text = "\n".join([
                f"- {i['pod_name']}: {i['status']} (restarts: {i['restarts']}) - {i['reason']}\n  Logs: {i['logs'][:200]}"
                for i in issues
            ])
            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": K8S_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Namespace: {namespace}\n\n{issues_text}"},
                ],
                max_tokens=1000,
            )
            ai_diagnosis = response.choices[0].message.content

        return {
            "namespace": namespace,
            "total_pods": len(all_pods),
            "unhealthy_pods": len(issues),
            "issues": issues,
            "ai_diagnosis": ai_diagnosis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
