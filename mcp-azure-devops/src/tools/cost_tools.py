"""
tools/cost_tools.py
===================
Azure Cost Management — spend reports and anomaly detection.
"""

from datetime import datetime, timedelta
from azure.identity import ClientSecretCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    QueryDefinition, QueryTimePeriod, QueryDataset,
    QueryAggregation, QueryGrouping, TimeframeType
)
from utils.config import Config
from utils.logger import setup_logger

logger = setup_logger("cost-tools")


class CostTools:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.credential = ClientSecretCredential(
            tenant_id=cfg.azure_tenant_id,
            client_id=cfg.azure_client_id,
            client_secret=cfg.azure_client_secret,
        )
        self.cost_client = CostManagementClient(credential=self.credential)

    def _build_query(self, days: int) -> QueryDefinition:
        end_date   = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        return QueryDefinition(
            type="ActualCost",
            timeframe=TimeframeType.CUSTOM,
            time_period=QueryTimePeriod(
                from_property=start_date,
                to=end_date
            ),
            dataset=QueryDataset(
                granularity="Daily",
                aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
                grouping=[QueryGrouping(type="Dimension", name="ServiceName")]
            )
        )

    # ── get_cost_report ───────────────────────────────────────────────────

    async def get_cost_report(
        self, subscription_id: str, days: int = 7, resource_group: str = None
    ) -> dict:
        """Return Azure spend grouped by service for the past N days."""
        scope = f"/subscriptions/{subscription_id}"
        if resource_group:
            scope += f"/resourceGroups/{resource_group}"

        try:
            result = self.cost_client.query.usage(
                scope=scope,
                parameters=self._build_query(days)
            )
            # Parse columns
            cols = [c.name for c in result.columns] if result.columns else []
            rows = result.rows or []
            data = [dict(zip(cols, row)) for row in rows]

            # Aggregate by service
            by_service: dict = {}
            for row in data:
                svc   = row.get("ServiceName", "Unknown")
                cost  = float(row.get("Cost", 0))
                by_service[svc] = round(by_service.get(svc, 0) + cost, 2)

            sorted_services = sorted(by_service.items(), key=lambda x: x[1], reverse=True)
            total = round(sum(by_service.values()), 2)

            return {
                "subscription_id": subscription_id,
                "resource_group":  resource_group,
                "period_days":     days,
                "total_usd":       total,
                "currency":        "USD",
                "top_services":    [
                    {"service": svc, "cost_usd": cost, "pct": round(cost/total*100, 1) if total else 0}
                    for svc, cost in sorted_services[:15]
                ],
            }
        except Exception as e:
            return {"error": str(e), "hint": "Ensure Cost Management Reader role on subscription"}

    # ── get_cost_anomalies ───────────────────────────────────────────────

    async def get_cost_anomalies(
        self, subscription_id: str, threshold_pct: float = 20
    ) -> dict:
        """Compare current 7-day spend vs previous 7-day to detect spikes."""
        scope = f"/subscriptions/{subscription_id}"
        try:
            current_raw  = self.cost_client.query.usage(scope=scope, parameters=self._build_query(7))
            previous_raw = self.cost_client.query.usage(scope=scope, parameters=self._build_query(14))

            def total(result):
                cols = [c.name for c in result.columns] if result.columns else []
                return sum(float(dict(zip(cols, r)).get("Cost", 0)) for r in (result.rows or []))

            current  = round(total(current_raw) / 2, 2)    # last 7 days
            previous = round(total(previous_raw) / 2, 2)   # prev 7 days (approx)
            change   = round((current - previous) / previous * 100, 1) if previous else 0

            anomalies = []
            if abs(change) >= threshold_pct:
                anomalies.append({
                    "type":       "TotalSpend",
                    "change_pct": change,
                    "current":    current,
                    "previous":   previous,
                    "severity":   "High" if abs(change) >= 50 else "Medium",
                })

            return {
                "subscription_id":      subscription_id,
                "current_7d_usd":       current,
                "previous_7d_usd":      previous,
                "change_pct":           change,
                "threshold_pct":        threshold_pct,
                "anomaly_detected":     len(anomalies) > 0,
                "anomalies":            anomalies,
                "recommendation":       (
                    f"Spend increased {change}% vs prior period. "
                    "Review Azure Advisor and check for untagged resources."
                ) if change >= threshold_pct else "Spend within normal range.",
            }
        except Exception as e:
            return {"error": str(e)}
