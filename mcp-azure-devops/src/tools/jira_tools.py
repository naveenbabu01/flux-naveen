"""
tools/jira_tools.py
===================
Jira Cloud REST API v3 — create and query incident tickets.
"""

import httpx
import base64
from datetime import datetime, timezone
from utils.config import Config
from utils.logger import setup_logger

logger = setup_logger("jira-tools")

SEVERITY_PRIORITY_MAP = {
    "Critical": "Highest",
    "High":     "High",
    "Medium":   "Medium",
    "Low":      "Low",
}


class JiraTools:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        token = base64.b64encode(
            f"{cfg.jira_email}:{cfg.jira_api_token}".encode()
        ).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
        self.base = cfg.jira_url.rstrip("/")

    async def _post(self, path: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base}/rest/api/3{path}",
                headers=self.headers,
                json=body
            )
            resp.raise_for_status()
            return resp.json()

    async def _get(self, path: str, params: dict = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base}/rest/api/3{path}",
                headers=self.headers,
                params=params
            )
            resp.raise_for_status()
            return resp.json()

    # ── create_incident ───────────────────────────────────────────────────

    async def create_incident(
        self,
        title:       str,
        description: str,
        severity:    str,
        project_key: str,
        assignee:    str = None,
    ) -> dict:
        """Create a Jira incident ticket with severity label and priority."""
        priority = SEVERITY_PRIORITY_MAP.get(severity, "Medium")
        now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        body = {
            "fields": {
                "project":   {"key": project_key},
                "summary":   f"[{severity.upper()}] {title}",
                "issuetype": {"name": "Bug"},
                "priority":  {"name": priority},
                "labels":    ["incident", "devops", f"severity-{severity.lower()}"],
                "description": {
                    "type":    "doc",
                    "version": 1,
                    "content": [
                        {
                            "type":    "paragraph",
                            "content": [{"type": "text", "text": description}]
                        },
                        {
                            "type":    "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"\n\nAuto-created by Azure DevOps MCP Server at {now_str}",
                                    "marks": [{"type": "em"}]
                                }
                            ]
                        }
                    ]
                }
            }
        }
        if assignee:
            body["fields"]["assignee"] = {"name": assignee}

        try:
            result = await self._post("/issue", body)
            ticket_key = result.get("key", "")
            return {
                "success":     True,
                "ticket_key":  ticket_key,
                "ticket_url":  f"{self.base}/browse/{ticket_key}",
                "project":     project_key,
                "severity":    severity,
                "priority":    priority,
                "message":     f"Incident ticket {ticket_key} created successfully.",
            }
        except httpx.HTTPStatusError as e:
            return {"success": False, "error": str(e), "response": e.response.text}

    # ── get_open_incidents ────────────────────────────────────────────────

    async def get_open_incidents(self, project_key: str, limit: int = 10) -> dict:
        """Query open incident tickets in a Jira project using JQL."""
        jql = (
            f'project = "{project_key}" '
            f'AND labels = "incident" '
            f'AND status NOT IN ("Done", "Resolved", "Closed") '
            f'ORDER BY priority ASC, created DESC'
        )
        try:
            data = await self._get(
                "/search",
                params={"jql": jql, "maxResults": limit, "fields": "summary,status,priority,labels,created,assignee"}
            )
            issues = data.get("issues", [])
            result = []
            for issue in issues:
                fields = issue.get("fields", {})
                result.append({
                    "key":        issue["key"],
                    "title":      fields.get("summary", ""),
                    "status":     fields.get("status", {}).get("name", ""),
                    "priority":   fields.get("priority", {}).get("name", ""),
                    "assignee":   (fields.get("assignee") or {}).get("displayName", "Unassigned"),
                    "created":    fields.get("created", ""),
                    "labels":     fields.get("labels", []),
                    "url":        f"{self.base}/browse/{issue['key']}",
                })
            return {
                "project":        project_key,
                "open_incidents": len(result),
                "issues":         result,
            }
        except Exception as e:
            return {"error": str(e), "project_key": project_key}
