#!/usr/bin/env python3
"""
Azure DevOps MCP Server — Production
=====================================
Author  : Naveen Babu Mummadi
Purpose : Production MCP server deployed on AKS with Managed Identity,
          Key Vault secrets, and HTTP/SSE transport for team access.

Transport modes:
    STDIO : python src/server.py --transport stdio   (local Claude Desktop)
    HTTP  : python src/server.py --transport http     (AKS deployment, team use)
"""

import asyncio
import argparse
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tools.aks_tools import AKSTools
from tools.github_tools import GitHubTools
from tools.azure_monitor import AzureMonitorTools
from tools.cost_tools import CostTools
from tools.jira_tools import JiraTools
from utils.config import Config
from utils.keyvault import KeyVaultManager
from utils.logger import setup_logger

# ─── Logging ────────────────────────────────────────────────────────────────
logger = setup_logger("mcp-server-prod")

# ─── MCP Server Instance ─────────────────────────────────────────────────────
server = Server("azure-devops-mcp-prod")


def initialize_tools(cfg: Config):
    """Initialize all tool classes with config (secrets loaded from Key Vault)."""
    aks_tools = AKSTools(cfg)
    github_tools = GitHubTools(cfg)
    monitor_tools = AzureMonitorTools(cfg)
    cost_tools = CostTools(cfg)
    jira_tools = JiraTools(cfg)
    return aks_tools, github_tools, monitor_tools, cost_tools, jira_tools


def load_config() -> Config:
    """Load config and populate secrets from Azure Key Vault."""
    cfg = Config()

    # Load secrets from Key Vault (uses Managed Identity on AKS)
    if cfg.key_vault_name:
        logger.info(f"Loading secrets from Key Vault: {cfg.key_vault_name}")
        kv = KeyVaultManager(cfg.key_vault_name)
        secrets = kv.load_all_secrets()
        cfg.github_token = secrets.get("github_token", "")
        cfg.jira_api_token = secrets.get("jira_api_token", "")
        cfg.app_insights_api_key = secrets.get("app_insights_api_key", "")
    else:
        # Fallback to env vars for local dev
        import os
        logger.info("No KEY_VAULT_NAME set — using environment variables for secrets")
        cfg.github_token = os.getenv("GITHUB_TOKEN", "")
        cfg.jira_api_token = os.getenv("JIRA_API_TOKEN", "")
        cfg.app_insights_api_key = os.getenv("APP_INSIGHTS_API_KEY", "")

    return cfg


# ─── Initialize ──────────────────────────────────────────────────────────────
cfg = load_config()
aks_tools, github_tools, monitor_tools, cost_tools, jira_tools = initialize_tools(cfg)


# ─── List All Available Tools ────────────────────────────────────────────────
@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return all tools this MCP server exposes."""
    return [
        # ── AKS Tools ──
        Tool(name="get_aks_pod_status",
             description="Get status of all pods in an AKS namespace.",
             inputSchema={"type": "object", "properties": {
                 "namespace": {"type": "string", "description": "K8s namespace"},
                 "deployment": {"type": "string", "description": "Filter by deployment (optional)"},
             }, "required": ["namespace"]}),
        Tool(name="restart_deployment",
             description="Perform rolling restart of an AKS deployment.",
             inputSchema={"type": "object", "properties": {
                 "deployment": {"type": "string"}, "namespace": {"type": "string"},
             }, "required": ["deployment", "namespace"]}),
        Tool(name="scale_deployment",
             description="Scale an AKS deployment to specified replicas.",
             inputSchema={"type": "object", "properties": {
                 "deployment": {"type": "string"}, "namespace": {"type": "string"},
                 "replicas": {"type": "integer", "description": "Target replicas (1-20)"},
             }, "required": ["deployment", "namespace", "replicas"]}),
        Tool(name="get_aks_events",
             description="Get recent Kubernetes warning events in a namespace.",
             inputSchema={"type": "object", "properties": {
                 "namespace": {"type": "string"}, "limit": {"type": "integer", "default": 20},
             }, "required": ["namespace"]}),
        Tool(name="get_pod_logs",
             description="Fetch recent logs from a specific pod.",
             inputSchema={"type": "object", "properties": {
                 "pod_name": {"type": "string"}, "namespace": {"type": "string"},
                 "tail_lines": {"type": "integer", "default": 100},
             }, "required": ["pod_name", "namespace"]}),

        # ── GitHub Actions Tools ──
        Tool(name="get_pipeline_status",
             description="Get status of recent GitHub Actions workflow runs.",
             inputSchema={"type": "object", "properties": {
                 "repo": {"type": "string", "description": "owner/repo"},
                 "workflow": {"type": "string"}, "limit": {"type": "integer", "default": 5},
             }, "required": ["repo"]}),
        Tool(name="get_pipeline_logs",
             description="Fetch logs from a GitHub Actions workflow run.",
             inputSchema={"type": "object", "properties": {
                 "repo": {"type": "string"}, "run_id": {"type": "string"},
             }, "required": ["repo", "run_id"]}),
        Tool(name="trigger_pipeline",
             description="Trigger a GitHub Actions workflow dispatch.",
             inputSchema={"type": "object", "properties": {
                 "repo": {"type": "string"}, "workflow": {"type": "string"},
                 "branch": {"type": "string", "default": "main"},
             }, "required": ["repo", "workflow"]}),
        Tool(name="get_failed_jobs",
             description="Get failed jobs from a GitHub Actions run.",
             inputSchema={"type": "object", "properties": {
                 "repo": {"type": "string"}, "run_id": {"type": "string"},
             }, "required": ["repo", "run_id"]}),

        # ── Azure Monitor Tools ──
        Tool(name="get_azure_alerts",
             description="Get active Azure Monitor alerts for a resource group.",
             inputSchema={"type": "object", "properties": {
                 "resource_group": {"type": "string"},
                 "severity": {"type": "string", "enum": ["Sev0", "Sev1", "Sev2", "Sev3", "Sev4"]},
             }, "required": ["resource_group"]}),
        Tool(name="get_app_insights_errors",
             description="Query App Insights for exceptions in last N hours.",
             inputSchema={"type": "object", "properties": {
                 "app_name": {"type": "string"}, "hours": {"type": "integer", "default": 24},
             }, "required": ["app_name"]}),

        # ── Cost Tools ──
        Tool(name="get_cost_report",
             description="Get Azure spend report for a subscription.",
             inputSchema={"type": "object", "properties": {
                 "subscription_id": {"type": "string"}, "days": {"type": "integer", "default": 7},
                 "resource_group": {"type": "string"},
             }, "required": ["subscription_id"]}),
        Tool(name="get_cost_anomalies",
             description="Detect unusual cost spikes in Azure.",
             inputSchema={"type": "object", "properties": {
                 "subscription_id": {"type": "string"},
                 "threshold_pct": {"type": "number", "default": 20},
             }, "required": ["subscription_id"]}),

        # ── Jira Tools ──
        Tool(name="create_incident_ticket",
             description="Create a Jira incident ticket.",
             inputSchema={"type": "object", "properties": {
                 "title": {"type": "string"}, "description": {"type": "string"},
                 "severity": {"type": "string", "enum": ["Critical", "High", "Medium", "Low"]},
                 "project_key": {"type": "string"}, "assignee": {"type": "string"},
             }, "required": ["title", "description", "severity", "project_key"]}),
        Tool(name="get_open_incidents",
             description="Get open incident tickets in a Jira project.",
             inputSchema={"type": "object", "properties": {
                 "project_key": {"type": "string"}, "limit": {"type": "integer", "default": 10},
             }, "required": ["project_key"]}),
    ]


# ─── Tool Call Handler ────────────────────────────────────────────────────────
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route incoming tool calls to the correct handler."""
    logger.info(f"Tool called: {name} | args: {arguments}")

    try:
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
        elif name == "get_pipeline_status":
            result = await github_tools.get_pipeline_status(**arguments)
        elif name == "get_pipeline_logs":
            result = await github_tools.get_pipeline_logs(**arguments)
        elif name == "trigger_pipeline":
            result = await github_tools.trigger_pipeline(**arguments)
        elif name == "get_failed_jobs":
            result = await github_tools.get_failed_jobs(**arguments)
        elif name == "get_azure_alerts":
            result = await monitor_tools.get_alerts(**arguments)
        elif name == "get_app_insights_errors":
            result = await monitor_tools.get_app_insights_errors(**arguments)
        elif name == "get_cost_report":
            result = await cost_tools.get_cost_report(**arguments)
        elif name == "get_cost_anomalies":
            result = await cost_tools.get_cost_anomalies(**arguments)
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


# ─── Health Check Endpoint (for K8s liveness/readiness probes) ────────────────
async def health_check(request):
    """Simple health check for Kubernetes probes."""
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "healthy", "server": "azure-devops-mcp-prod"})


# ─── Entry Point ─────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="MCP Azure DevOps Server (Production)")
    parser.add_argument("--transport", choices=["stdio", "http"], default=cfg.transport)
    parser.add_argument("--port", type=int, default=cfg.port)
    parser.add_argument("--host", default=cfg.host)
    args = parser.parse_args()

    if args.transport == "stdio":
        logger.info("Starting MCP server in STDIO mode (local Claude Desktop)")
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    else:
        logger.info(f"Starting MCP server in HTTP/SSE mode on {args.host}:{args.port}")
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        import uvicorn

        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await server.run(streams[0], streams[1], server.create_initialization_options())

        app = Starlette(
            routes=[
                Route("/health", health_check),
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ]
        )

        config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
        srv = uvicorn.Server(config)
        await srv.serve()


if __name__ == "__main__":
    asyncio.run(main())
