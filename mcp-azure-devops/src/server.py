#!/usr/bin/env python3
"""
Azure DevOps MCP Server
=======================
Author  : Naveen Babu Mummadi
Purpose : MCP server exposing AKS, GitHub Actions, Azure Monitor,
          Cost Management, and Jira tools to any MCP-compatible AI model.

Run:
    python src/server.py
    # or via uvicorn for HTTP transport:
    uvicorn src.server:app --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tools.aks_tools       import AKSTools
from tools.github_tools    import GitHubTools
from tools.azure_monitor   import AzureMonitorTools
from tools.cost_tools      import CostTools
from tools.jira_tools      import JiraTools
from utils.config          import Config
from utils.logger          import setup_logger

# ─── Logging ────────────────────────────────────────────────────────────────
logger = setup_logger("mcp-azure-devops")

# ─── MCP Server Instance ─────────────────────────────────────────────────────
server = Server("azure-devops-mcp")

# ─── Tool Registry ───────────────────────────────────────────────────────────
cfg          = Config()
aks_tools    = AKSTools(cfg)
github_tools = GitHubTools(cfg)
monitor_tools= AzureMonitorTools(cfg)
cost_tools   = CostTools(cfg)
jira_tools   = JiraTools(cfg)


# ─── List All Available Tools ────────────────────────────────────────────────
@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return all tools this MCP server exposes to the AI model."""
    return [
        # ── AKS Tools ──────────────────────────────────────────────
        Tool(
            name="get_aks_pod_status",
            description="Get status of all pods in an AKS namespace. Returns pod name, status, restarts, age.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace":   {"type": "string", "description": "K8s namespace (e.g. production, staging)"},
                    "deployment":  {"type": "string", "description": "Filter by deployment name (optional)"},
                },
                "required": ["namespace"]
            }
        ),
        Tool(
            name="restart_deployment",
            description="Perform a rolling restart of an AKS deployment (equivalent to kubectl rollout restart).",
            inputSchema={
                "type": "object",
                "properties": {
                    "deployment": {"type": "string", "description": "Deployment name"},
                    "namespace":  {"type": "string", "description": "K8s namespace"},
                },
                "required": ["deployment", "namespace"]
            }
        ),
        Tool(
            name="scale_deployment",
            description="Scale an AKS deployment to a specified number of replicas.",
            inputSchema={
                "type": "object",
                "properties": {
                    "deployment": {"type": "string"},
                    "namespace":  {"type": "string"},
                    "replicas":   {"type": "integer", "description": "Target replica count (1-20)"},
                },
                "required": ["deployment", "namespace", "replicas"]
            }
        ),
        Tool(
            name="get_aks_events",
            description="Get recent Kubernetes events in a namespace — useful for diagnosing failures.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "limit":     {"type": "integer", "default": 20},
                },
                "required": ["namespace"]
            }
        ),
        Tool(
            name="get_pod_logs",
            description="Fetch recent logs from a specific pod in AKS.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pod_name":  {"type": "string"},
                    "namespace": {"type": "string"},
                    "tail_lines":{"type": "integer", "default": 100},
                },
                "required": ["pod_name", "namespace"]
            }
        ),

        # ── GitHub Actions Tools ───────────────────────────────────
        Tool(
            name="get_pipeline_status",
            description="Get the status of recent GitHub Actions workflow runs for a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo":     {"type": "string", "description": "owner/repo format e.g. naveen/myapp"},
                    "workflow": {"type": "string", "description": "Workflow filename e.g. ci-cd.yml (optional)"},
                    "limit":    {"type": "integer", "default": 5},
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="get_pipeline_logs",
            description="Fetch logs from a specific GitHub Actions workflow run.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo":   {"type": "string"},
                    "run_id": {"type": "string", "description": "Workflow run ID"},
                },
                "required": ["repo", "run_id"]
            }
        ),
        Tool(
            name="trigger_pipeline",
            description="Manually trigger a GitHub Actions workflow dispatch event.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo":     {"type": "string"},
                    "workflow": {"type": "string", "description": "Workflow filename e.g. deploy.yml"},
                    "branch":   {"type": "string", "default": "main"},
                    "inputs":   {"type": "object", "description": "Optional workflow_dispatch inputs"},
                },
                "required": ["repo", "workflow"]
            }
        ),
        Tool(
            name="get_failed_jobs",
            description="Get details of failed jobs in a GitHub Actions run including step-by-step breakdown.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo":   {"type": "string"},
                    "run_id": {"type": "string"},
                },
                "required": ["repo", "run_id"]
            }
        ),

        # ── Azure Monitor Tools ────────────────────────────────────
        Tool(
            name="get_azure_alerts",
            description="Get active Azure Monitor alerts for a resource group, filtered by severity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_group": {"type": "string"},
                    "severity":       {"type": "string", "enum": ["Sev0","Sev1","Sev2","Sev3","Sev4"], "description": "Sev0=Critical"},
                },
                "required": ["resource_group"]
            }
        ),
        Tool(
            name="get_app_insights_errors",
            description="Query Application Insights for exceptions and errors in the last N hours.",
            inputSchema={
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Application Insights resource name"},
                    "hours":    {"type": "integer", "default": 24},
                    "limit":    {"type": "integer", "default": 50},
                },
                "required": ["app_name"]
            }
        ),

        # ── Cost Tools ─────────────────────────────────────────────
        Tool(
            name="get_cost_report",
            description="Get Azure spend report for a subscription over the last N days, grouped by service.",
            inputSchema={
                "type": "object",
                "properties": {
                    "subscription_id": {"type": "string"},
                    "days":            {"type": "integer", "default": 7},
                    "resource_group":  {"type": "string", "description": "Optional filter by resource group"},
                },
                "required": ["subscription_id"]
            }
        ),
        Tool(
            name="get_cost_anomalies",
            description="Detect unusual cost spikes in an Azure subscription compared to previous period.",
            inputSchema={
                "type": "object",
                "properties": {
                    "subscription_id": {"type": "string"},
                    "threshold_pct":   {"type": "number", "default": 20, "description": "Alert if spend increases by this % or more"},
                },
                "required": ["subscription_id"]
            }
        ),

        # ── Jira Tools ─────────────────────────────────────────────
        Tool(
            name="create_incident_ticket",
            description="Create a Jira incident ticket with severity, description, and assignee.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title":       {"type": "string"},
                    "description": {"type": "string"},
                    "severity":    {"type": "string", "enum": ["Critical","High","Medium","Low"]},
                    "project_key": {"type": "string", "description": "Jira project key e.g. OPS"},
                    "assignee":    {"type": "string", "description": "Jira username (optional)"},
                },
                "required": ["title", "description", "severity", "project_key"]
            }
        ),
        Tool(
            name="get_open_incidents",
            description="Get all open incident tickets in a Jira project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_key": {"type": "string"},
                    "limit":       {"type": "integer", "default": 10},
                },
                "required": ["project_key"]
            }
        ),
    ]


# ─── Tool Call Handler ────────────────────────────────────────────────────────
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route incoming tool calls to the correct handler."""
    logger.info(f"Tool called: {name} | args: {arguments}")

    try:
        # ── AKS ──────────────────────────────────────────────────
        if name == "get_aks_pod_status":
            result = await aks_tools.get_pod_status(**arguments)
        elif name == "restart_deployment":
            result = await aks_tools.restart_deployment(**arguments)
        elif name == "scale_deployment":
            result = await aks_tools.scale_deployment(**arguments)
        elif name == "get_aks_events":
            result = await aks_tools.get_events(**arguments)
        elif name == "get_pod_logs":
            result = await aks_tools.get_pod_logs(**arguments)

        # ── GitHub Actions ────────────────────────────────────────
        elif name == "get_pipeline_status":
            result = await github_tools.get_pipeline_status(**arguments)
        elif name == "get_pipeline_logs":
            result = await github_tools.get_pipeline_logs(**arguments)
        elif name == "trigger_pipeline":
            result = await github_tools.trigger_pipeline(**arguments)
        elif name == "get_failed_jobs":
            result = await github_tools.get_failed_jobs(**arguments)

        # ── Azure Monitor ─────────────────────────────────────────
        elif name == "get_azure_alerts":
            result = await monitor_tools.get_alerts(**arguments)
        elif name == "get_app_insights_errors":
            result = await monitor_tools.get_app_insights_errors(**arguments)

        # ── Cost ──────────────────────────────────────────────────
        elif name == "get_cost_report":
            result = await cost_tools.get_cost_report(**arguments)
        elif name == "get_cost_anomalies":
            result = await cost_tools.get_cost_anomalies(**arguments)

        # ── Jira ──────────────────────────────────────────────────
        elif name == "create_incident_ticket":
            result = await jira_tools.create_incident(**arguments)
        elif name == "get_open_incidents":
            result = await jira_tools.get_open_incidents(**arguments)

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=str(result))]

    except Exception as e:
        logger.error(f"Tool {name} failed: {e}", exc_info=True)
        return [TextContent(type="text", text=f"Error executing {name}: {str(e)}")]


# ─── Entry Point ─────────────────────────────────────────────────────────────
async def main():
    logger.info("Starting Azure DevOps MCP Server...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
