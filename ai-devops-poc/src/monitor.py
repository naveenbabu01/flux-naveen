"""
AKS Pod Health Monitor
Watches for failing pods (ImagePullBackOff, CrashLoopBackOff, OOMKilled, etc.)
Collects K8s events/logs and sends to Azure OpenAI for analysis.
"""
import os
import json
import time
import logging
import threading
from datetime import datetime, timezone
from kubernetes import client, config, watch
from ai_assistant import AIIncidentAssistant

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Failure states to watch for
FAILURE_STATES = {
    "ImagePullBackOff", "ErrImagePull", "CrashLoopBackOff",
    "OOMKilled", "Error", "CreateContainerConfigError",
    "InvalidImageName", "RunContainerError"
}

class Incident:
    def __init__(self, pod_name, namespace, reason, message, events_text):
        self.id = f"{namespace}/{pod_name}/{int(time.time())}"
        self.pod_name = pod_name
        self.namespace = namespace
        self.reason = reason
        self.message = message
        self.events_text = events_text
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.ai_analysis = None
        self.status = "detected"  # detected -> analyzing -> resolved

    def to_dict(self):
        return {
            "id": self.id,
            "pod_name": self.pod_name,
            "namespace": self.namespace,
            "reason": self.reason,
            "message": self.message,
            "events_text": self.events_text,
            "timestamp": self.timestamp,
            "ai_analysis": self.ai_analysis,
            "status": self.status
        }


class PodMonitor:
    def __init__(self):
        # Load K8s config (in-cluster when running in AKS)
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster K8s config")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("Loaded local kubeconfig")

        self.v1 = client.CoreV1Api()
        self.ai = AIIncidentAssistant()
        self.incidents = []  # Store last 50 incidents
        self.seen_pods = {}  # Track already-alerted pods to avoid duplicates
        self.monitoring = False
        self._lock = threading.Lock()

    def get_pod_events(self, pod_name: str, namespace: str) -> str:
        """Get K8s events for a specific pod."""
        try:
            events = self.v1.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={pod_name}"
            )
            lines = []
            for e in sorted(events.items, key=lambda x: x.last_timestamp or x.event_time or datetime.min.replace(tzinfo=timezone.utc)):
                ts = e.last_timestamp or e.event_time or "unknown"
                lines.append(f"[{ts}] {e.type}: {e.reason} - {e.message}")
            return "\n".join(lines[-20:]) if lines else "No events found"
        except Exception as ex:
            return f"Error fetching events: {ex}"

    def get_pod_logs(self, pod_name: str, namespace: str) -> str:
        """Get recent logs from the pod (if any)."""
        try:
            logs = self.v1.read_namespaced_pod_log(
                name=pod_name, namespace=namespace,
                tail_lines=30, previous=True
            )
            return logs if logs else "No logs available"
        except Exception:
            try:
                logs = self.v1.read_namespaced_pod_log(
                    name=pod_name, namespace=namespace, tail_lines=30
                )
                return logs if logs else "No logs available"
            except Exception:
                return "Unable to retrieve pod logs (container may not have started)"

    def describe_pod(self, pod_name: str, namespace: str) -> str:
        """Get key pod details similar to kubectl describe."""
        try:
            pod = self.v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            lines = [
                f"Pod: {pod_name}",
                f"Namespace: {namespace}",
                f"Node: {pod.spec.node_name or 'Pending'}",
                f"Phase: {pod.status.phase}",
                f"Images: {', '.join(c.image for c in pod.spec.containers)}",
            ]
            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    lines.append(f"Container '{cs.name}': ready={cs.ready}, restarts={cs.restart_count}")
                    if cs.state.waiting:
                        lines.append(f"  State: Waiting - {cs.state.waiting.reason}: {cs.state.waiting.message or ''}")
                    elif cs.state.terminated:
                        lines.append(f"  State: Terminated - {cs.state.terminated.reason}: exit_code={cs.state.terminated.exit_code}")
            if pod.status.conditions:
                for cond in pod.status.conditions:
                    if cond.status != "True":
                        lines.append(f"Condition {cond.type}: {cond.status} - {cond.message or ''}")
            return "\n".join(lines)
        except Exception as ex:
            return f"Error describing pod: {ex}"

    def analyze_incident(self, incident: Incident):
        """Send collected data to Azure OpenAI for analysis."""
        incident.status = "analyzing"
        full_context = f"""=== POD FAILURE DETECTED ===
Pod: {incident.pod_name}
Namespace: {incident.namespace}
Failure Reason: {incident.reason}
Message: {incident.message}
Time: {incident.timestamp}

=== POD DESCRIPTION ===
{self.describe_pod(incident.pod_name, incident.namespace)}

=== KUBERNETES EVENTS ===
{incident.events_text}

=== POD LOGS ===
{self.get_pod_logs(incident.pod_name, incident.namespace)}
"""
        logger.info(f"🔬 Sending to AI for analysis: {incident.namespace}/{incident.pod_name}")
        try:
            analysis = self.ai.analyze_failure(
                logs=full_context,
                pipeline_name=f"aks-pod-{incident.namespace}",
                build_id=incident.pod_name
            )
            incident.ai_analysis = analysis
            incident.status = "analyzed"
            logger.info(f"✅ AI analysis complete for {incident.pod_name}: severity={analysis.get('severity', '?')}")
        except Exception as ex:
            incident.ai_analysis = {"root_cause": f"AI analysis failed: {ex}", "severity": "UNKNOWN"}
            incident.status = "error"
            logger.error(f"❌ AI analysis failed for {incident.pod_name}: {ex}")

    def check_pod_health(self, pod) -> tuple:
        """Check if a pod is in a failure state. Returns (is_failing, reason, message)."""
        if not pod.status.container_statuses:
            return False, None, None

        for cs in pod.status.container_statuses:
            if cs.state.waiting and cs.state.waiting.reason in FAILURE_STATES:
                return True, cs.state.waiting.reason, cs.state.waiting.message or ""
            if cs.state.terminated and cs.state.terminated.reason in FAILURE_STATES:
                return True, cs.state.terminated.reason, f"exit_code={cs.state.terminated.exit_code}"
            # Check for OOMKilled in last_state
            if cs.last_state and cs.last_state.terminated:
                if cs.last_state.terminated.reason == "OOMKilled":
                    return True, "OOMKilled", f"Container was OOM killed, restarts={cs.restart_count}"
        return False, None, None

    def scan_all_pods(self) -> list:
        """One-time scan of all pods across all namespaces."""
        new_incidents = []
        try:
            pods = self.v1.list_pod_for_all_namespaces()
            for pod in pods.items:
                # Skip system namespaces
                if pod.metadata.namespace in ("kube-system", "kube-node-lease", "kube-public"):
                    continue

                is_failing, reason, message = self.check_pod_health(pod)
                if is_failing:
                    pod_key = f"{pod.metadata.namespace}/{pod.metadata.name}/{reason}"
                    if pod_key not in self.seen_pods:
                        self.seen_pods[pod_key] = time.time()
                        events = self.get_pod_events(pod.metadata.name, pod.metadata.namespace)
                        incident = Incident(pod.metadata.name, pod.metadata.namespace, reason, message, events)
                        self.analyze_incident(incident)
                        with self._lock:
                            self.incidents.append(incident)
                            if len(self.incidents) > 50:
                                self.incidents = self.incidents[-50:]
                        new_incidents.append(incident)
        except Exception as ex:
            logger.error(f"Error scanning pods: {ex}")
        return new_incidents

    def watch_pods(self):
        """Continuously watch for pod events."""
        self.monitoring = True
        logger.info("🚀 Starting pod watcher...")
        while self.monitoring:
            try:
                w = watch.Watch()
                for event in w.stream(self.v1.list_pod_for_all_namespaces, timeout_seconds=300):
                    if not self.monitoring:
                        break
                    pod = event['object']
                    event_type = event['type']

                    if pod.metadata.namespace in ("kube-system", "kube-node-lease", "kube-public"):
                        continue

                    is_failing, reason, message = self.check_pod_health(pod)
                    if is_failing and event_type in ("MODIFIED", "ADDED"):
                        pod_key = f"{pod.metadata.namespace}/{pod.metadata.name}/{reason}"
                        # Deduplicate: only alert once per pod+reason per 10 minutes
                        now = time.time()
                        if pod_key in self.seen_pods and (now - self.seen_pods[pod_key]) < 600:
                            continue

                        self.seen_pods[pod_key] = now
                        logger.info(f"🚨 ALERT: {pod.metadata.namespace}/{pod.metadata.name} → {reason}")

                        events = self.get_pod_events(pod.metadata.name, pod.metadata.namespace)
                        incident = Incident(pod.metadata.name, pod.metadata.namespace, reason, message, events)

                        # Run AI analysis in a thread to not block the watcher
                        thread = threading.Thread(target=self.analyze_incident, args=(incident,))
                        thread.start()

                        with self._lock:
                            self.incidents.append(incident)
                            if len(self.incidents) > 50:
                                self.incidents = self.incidents[-50:]

            except Exception as ex:
                logger.warning(f"Watch disconnected: {ex}. Reconnecting in 5s...")
                time.sleep(5)

    def get_incidents(self) -> list:
        with self._lock:
            return [i.to_dict() for i in reversed(self.incidents)]

    def start(self):
        """Start background monitoring."""
        thread = threading.Thread(target=self.watch_pods, daemon=True)
        thread.start()
        logger.info("✅ Background pod monitor started")

    def stop(self):
        self.monitoring = False
