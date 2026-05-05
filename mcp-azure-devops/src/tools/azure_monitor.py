"""
tools/azure_monitor.py
======================
Azure Monitor alerts + Application Insights query tools.
"""

import httpx
from datetime import datetime, timedelta, timezone
from azure.identity import ClientSecretCredential
from azure.mgmt.monitor import MonitorManagementClient
from utils.config import Config
from utils.logger import setup_logger

logger = setup_logger("azure-monitor-tools")


class AzureMonitorTools:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.credential = ClientSecretCredential(
            tenant_id=cfg.azure_tenant_id,
            client_id=cfg.azure_client_id,
            client_secret=cfg.azure_client_secret,
        )
        self.monitor_client = MonitorManagementClient(
            credential=self.credential,
            subscription_id=cfg.azure_subscription_id,
        )

    # ── get_alerts ────────────────────────────────────────────────────────

    async def get_alerts(self, resource_group: str, severity: str = None) -> dict:
        """Return active Azure Monitor alerts for a resource group."""
        try:
            alerts = self.monitor_client.alerts.get_all(
                resource_group_name=resource_group
            )
            result = []
            severity_map = {"Sev0": 0, "Sev1": 1, "Sev2": 2, "Sev3": 3, "Sev4": 4}
            target_sev = severity_map.get(severity) if severity else None

            for alert in alerts:
                props = alert.properties
                alert_sev = getattr(props, "severity", None)
                if target_sev is not None and alert_sev != target_sev:
                    continue
                result.append({
                    "name":          alert.name,
                    "severity":      f"Sev{alert_sev}" if alert_sev is not None else "Unknown",
                    "state":         getattr(props, "alert_state", "Unknown"),
                    "condition":     getattr(props, "condition", {}).get("allOf", [{}])[0]
                                     .get("metricName", "") if hasattr(props, "condition") else "",
                    "fired_at":      str(getattr(props, "last_modified_date_time", "")),
                    "description":   getattr(props, "description", ""),
                    "resource":      alert.id,
                })

            return {
                "resource_group":  resource_group,
                "total_alerts":    len(result),
                "severity_filter": severity,
                "alerts":          result,
            }
        except Exception as e:
            return {"error": str(e), "resource_group": resource_group}

    # ── get_app_insights_errors ───────────────────────────────────────────

    async def get_app_insights_errors(
        self, app_name: str, hours: int = 24, limit: int = 50
    ) -> dict:
        """Query Application Insights REST API for exceptions in the last N hours."""
        if not self.cfg.app_insights_app_id or not self.cfg.app_insights_api_key:
            return {
                "error": "APP_INSIGHTS_APP_ID and APP_INSIGHTS_API_KEY must be set in .env",
                "hint":  "Get these from: Azure Portal → App Insights → API Access"
            }

        query = f"""
exceptions
| where timestamp > ago({hours}h)
| summarize count() by type, outerMessage, cloud_RoleName
| order by count_ desc
| take {limit}
"""
        url = (
            f"https://api.applicationinsights.io/v1/apps/"
            f"{self.cfg.app_insights_app_id}/query"
        )
        headers = {"x-api-key": self.cfg.app_insights_api_key}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, headers=headers, json={"query": query})
                resp.raise_for_status()
                data = resp.json()

            tables = data.get("tables", [{}])
            rows   = tables[0].get("rows", []) if tables else []
            cols   = [c["name"] for c in tables[0].get("columns", [])] if tables else []

            errors = [dict(zip(cols, row)) for row in rows]
            return {
                "app_name":    app_name,
                "period_hours":hours,
                "error_types": len(errors),
                "errors":      errors,
            }
        except Exception as e:
            return {"error": str(e), "app_name": app_name}
