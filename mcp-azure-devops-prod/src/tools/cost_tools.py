"""
tools/cost_tools.py — Azure Cost Management using DefaultAzureCredential.
"""

from azure.identity import DefaultAzureCredential
from azure.mgmt.costmanagement import CostManagementClient
from utils.config import Config
from utils.logger import setup_logger

logger = setup_logger("cost-tools")


class CostTools:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.credential = DefaultAzureCredential()
        self.client = CostManagementClient(credential=self.credential)

    async def get_cost_report(self, subscription_id: str, days: int = 7, resource_group: str = None) -> dict:
        """Get Azure spend report grouped by service."""
        from datetime import datetime, timedelta, timezone
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        scope = f"/subscriptions/{subscription_id}"
        if resource_group:
            scope += f"/resourceGroups/{resource_group}"

        try:
            query = {
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {"from": start.isoformat(), "to": end.isoformat()},
                "dataset": {
                    "granularity": "Daily",
                    "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                    "grouping": [{"type": "Dimension", "name": "ServiceName"}],
                }
            }
            result = self.client.query.usage(scope=scope, parameters=query)
            rows = result.rows if hasattr(result, "rows") else []
            costs = [{"service": r[1], "cost": round(r[0], 2), "currency": r[2]} for r in rows] if rows else []
            total = sum(c["cost"] for c in costs)
            return {"subscription_id": subscription_id, "days": days, "total_cost": round(total, 2), "by_service": costs}
        except Exception as e:
            return {"error": str(e)}

    async def get_cost_anomalies(self, subscription_id: str, threshold_pct: float = 20) -> dict:
        """Detect cost spikes compared to previous period."""
        current = await self.get_cost_report(subscription_id, days=7)
        previous = await self.get_cost_report(subscription_id, days=14)

        if "error" in current or "error" in previous:
            return {"error": "Could not fetch cost data for comparison"}

        current_cost = current.get("total_cost", 0)
        prev_cost = max(previous.get("total_cost", 0) - current_cost, 0.01)
        change_pct = ((current_cost - prev_cost) / prev_cost) * 100

        anomaly = change_pct >= threshold_pct
        return {
            "subscription_id": subscription_id,
            "current_7d_cost": current_cost,
            "previous_7d_cost": round(prev_cost, 2),
            "change_percent": round(change_pct, 1),
            "threshold_pct": threshold_pct,
            "anomaly_detected": anomaly,
            "status": "⚠️ ANOMALY" if anomaly else "✅ Normal",
        }
