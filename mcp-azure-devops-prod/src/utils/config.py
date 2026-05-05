"""
utils/config.py — Production config with Key Vault + DefaultAzureCredential.
No hardcoded secrets. All sensitive values come from Azure Key Vault.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """
    Non-sensitive values come from environment variables / ConfigMap.
    Sensitive values (tokens, secrets) are loaded from Azure Key Vault at runtime.
    """

    # ── Azure (non-sensitive — from ConfigMap/env) ────────────────
    azure_subscription_id: str = os.getenv("AZURE_SUBSCRIPTION_ID", "")
    azure_tenant_id: str = os.getenv("AZURE_TENANT_ID", "")

    # ── AKS ───────────────────────────────────────────────────────
    aks_resource_group: str = os.getenv("AKS_RESOURCE_GROUP", "")
    aks_cluster_name: str = os.getenv("AKS_CLUSTER_NAME", "")

    # ── Key Vault ─────────────────────────────────────────────────
    key_vault_name: str = os.getenv("KEY_VAULT_NAME", "")

    # ── Server ────────────────────────────────────────────────────
    transport: str = os.getenv("TRANSPORT", "http")  # "http" or "stdio"
    port: int = int(os.getenv("PORT", "8000"))
    host: str = os.getenv("HOST", "0.0.0.0")

    # ── GitHub (non-sensitive) ────────────────────────────────────
    github_api_url: str = os.getenv("GITHUB_API_URL", "https://api.github.com")

    # ── Azure Monitor / App Insights (non-sensitive IDs) ──────────
    app_insights_app_id: str = os.getenv("APP_INSIGHTS_APP_ID", "")
    log_analytics_workspace: str = os.getenv("LOG_ANALYTICS_WORKSPACE_ID", "")

    # ── Jira (non-sensitive) ──────────────────────────────────────
    jira_url: str = os.getenv("JIRA_URL", "")
    jira_email: str = os.getenv("JIRA_EMAIL", "")
    jira_default_project: str = os.getenv("JIRA_DEFAULT_PROJECT", "OPS")

    # ── Secrets (populated from Key Vault at runtime) ─────────────
    github_token: str = ""
    jira_api_token: str = ""
    app_insights_api_key: str = ""

    # These are NOT needed when using DefaultAzureCredential
    # (Managed Identity handles Azure auth automatically)
    azure_client_id: str = ""
    azure_client_secret: str = ""
