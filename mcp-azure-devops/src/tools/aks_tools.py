"""
tools/aks_tools.py
==================
All AKS (Azure Kubernetes Service) operations.
Uses the official Kubernetes Python client + Azure Identity for authentication.
"""

from datetime import datetime, timezone
from kubernetes import client as k8s_client, config as k8s_config
from azure.identity import ClientSecretCredential
from azure.mgmt.containerservice import ContainerServiceClient
from utils.config import Config
from utils.logger import setup_logger

logger = setup_logger("aks-tools")


class AKSTools:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._k8s_ready = False
        self._init_azure_client()

    def _init_azure_client(self):
        """Initialise Azure SDK client for AKS cluster management."""
        try:
            self.credential = ClientSecretCredential(
                tenant_id=self.cfg.azure_tenant_id,
                client_id=self.cfg.azure_client_id,
                client_secret=self.cfg.azure_client_secret,
            )
            self.aks_client = ContainerServiceClient(
                credential=self.credential,
                subscription_id=self.cfg.azure_subscription_id,
            )
            logger.info("Azure AKS client initialised")
        except Exception as e:
            logger.error(f"Azure client init failed: {e}")

    def _ensure_k8s_config(self):
        """Load kubeconfig from AKS cluster credentials (runs once)."""
        if self._k8s_ready:
            return
        try:
            # Fetch kubeconfig from AKS API
            creds = self.aks_client.managed_clusters.list_cluster_user_credentials(
                resource_group_name=self.cfg.aks_resource_group,
                resource_name=self.cfg.aks_cluster_name,
            )
            import tempfile
            import os
            kubeconfig_data = creds.kubeconfigs[0].value
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")
            tmp.write(kubeconfig_data)
            tmp.close()
            k8s_config.load_kube_config(config_file=tmp.name)
            os.unlink(tmp.name)
            self._k8s_ready = True
            logger.info(f"Kubeconfig loaded for cluster: {self.cfg.aks_cluster_name}")
        except Exception as e:
            logger.warning(f"Could not load AKS kubeconfig ({e}) — trying local kubeconfig")
            try:
                k8s_config.load_kube_config()   # fallback to ~/.kube/config
                self._k8s_ready = True
            except Exception as e2:
                logger.error(f"Kubeconfig load failed: {e2}")

    # ── get_pod_status ──────────────────────────────────────────────────────

    async def get_pod_status(self, namespace: str, deployment: str = None) -> dict:
        """Return status of all pods (optionally filtered by deployment label)."""
        self._ensure_k8s_config()
        v1 = k8s_client.CoreV1Api()
        label_selector = f"app={deployment}" if deployment else None

        try:
            pods = v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector
            )
            result = []
            for pod in pods.items:
                # Calculate age
                created = pod.metadata.creation_timestamp
                age_secs = (datetime.now(timezone.utc) - created).seconds if created else 0
                age_str = f"{age_secs // 3600}h{(age_secs % 3600) // 60}m"

                # Count restarts across all containers
                restarts = sum(
                    cs.restart_count
                    for cs in (pod.status.container_statuses or [])
                )
                result.append({
                    "name":       pod.metadata.name,
                    "namespace":  namespace,
                    "status":     pod.status.phase,
                    "ready":      all(
                        cs.ready for cs in (pod.status.container_statuses or [])
                    ),
                    "restarts":   restarts,
                    "node":       pod.spec.node_name,
                    "age":        age_str,
                    "containers": [
                        {
                            "name":    cs.name,
                            "ready":   cs.ready,
                            "image":   cs.image,
                            "restarts":cs.restart_count,
                            "state":   list(cs.state.to_dict().keys())[0]
                                       if cs.state else "unknown",
                        }
                        for cs in (pod.status.container_statuses or [])
                    ]
                })

            summary = {
                "total":    len(result),
                "running":  sum(1 for p in result if p["status"] == "Running"),
                "failed":   sum(1 for p in result if p["status"] in ["Failed", "CrashLoopBackOff"]),
                "pending":  sum(1 for p in result if p["status"] == "Pending"),
                "pods":     result,
            }
            return summary

        except Exception as e:
            return {"error": str(e), "namespace": namespace}

    # ── restart_deployment ──────────────────────────────────────────────────

    async def restart_deployment(self, deployment: str, namespace: str) -> dict:
        """Rolling restart of a deployment — sets restart annotation on pod template."""
        self._ensure_k8s_config()
        apps_v1 = k8s_client.AppsV1Api()
        now = datetime.utcnow().isoformat() + "Z"
        patch = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": now
                        }
                    }
                }
            }
        }
        try:
            apps_v1.patch_namespaced_deployment(
                name=deployment,
                namespace=namespace,
                body=patch
            )
            logger.info(f"Restarted deployment {deployment} in {namespace}")
            return {
                "success":    True,
                "deployment": deployment,
                "namespace":  namespace,
                "restarted_at": now,
                "message":    f"Rolling restart triggered for '{deployment}'. "
                              f"Run get_aks_pod_status to monitor progress."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── scale_deployment ────────────────────────────────────────────────────

    async def scale_deployment(self, deployment: str, namespace: str, replicas: int) -> dict:
        """Scale a deployment to the specified replica count."""
        self._ensure_k8s_config()
        apps_v1 = k8s_client.AppsV1Api()
        patch = {"spec": {"replicas": replicas}}
        try:
            apps_v1.patch_namespaced_deployment_scale(
                name=deployment,
                namespace=namespace,
                body=patch
            )
            return {
                "success":    True,
                "deployment": deployment,
                "namespace":  namespace,
                "replicas":   replicas,
                "message":    f"Deployment '{deployment}' scaled to {replicas} replica(s)."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── get_events ──────────────────────────────────────────────────────────

    async def get_events(self, namespace: str, limit: int = 20) -> dict:
        """Return recent Kubernetes events — especially useful for Warning events."""
        self._ensure_k8s_config()
        v1 = k8s_client.CoreV1Api()
        try:
            events = v1.list_namespaced_event(
                namespace=namespace,
                limit=limit,
                field_selector="type=Warning"   # Only show warnings/errors
            )
            result = [
                {
                    "type":    e.type,
                    "reason":  e.reason,
                    "message": e.message,
                    "object":  f"{e.involved_object.kind}/{e.involved_object.name}",
                    "count":   e.count,
                    "time":    str(e.last_timestamp),
                }
                for e in events.items
            ]
            return {"namespace": namespace, "event_count": len(result), "events": result}
        except Exception as e:
            return {"error": str(e)}

    # ── get_pod_logs ────────────────────────────────────────────────────────

    async def get_pod_logs(self, pod_name: str, namespace: str, tail_lines: int = 100) -> dict:
        """Fetch the last N lines of logs from a pod."""
        self._ensure_k8s_config()
        v1 = k8s_client.CoreV1Api()
        try:
            logs = v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                tail_lines=tail_lines,
                timestamps=True
            )
            return {
                "pod_name":  pod_name,
                "namespace": namespace,
                "tail_lines":tail_lines,
                "logs":      logs
            }
        except Exception as e:
            return {"error": str(e), "pod_name": pod_name}
