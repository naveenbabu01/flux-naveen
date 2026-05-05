"""
utils/config.py — Centralised config loaded from environment variables.
Copy .env.example to .env and fill in your values.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    # ── Azure credentials ─────────────────────────────────────────
    azure_subscription_id:  str = os.getenv("AZURE_SUBSCRIPTION_ID", "")
    azure_tenant_id:        str = os.getenv("AZURE_TENANT_ID", "")
    azure_client_id:        str = os.getenv("AZURE_CLIENT_ID", "")
    azure_client_secret:    str = os.getenv("AZURE_CLIENT_SECRET", "")

    # ── AKS ───────────────────────────────────────────────────────
    aks_resource_group:     str = os.getenv("AKS_RESOURCE_GROUP", "")
    aks_cluster_name:       str = os.getenv("AKS_CLUSTER_NAME", "")

    # ── GitHub ────────────────────────────────────────────────────
    github_token:           str = os.getenv("GITHUB_TOKEN", "")
    github_api_url:         str = os.getenv("GITHUB_API_URL", "https://api.github.com")

    # ── Azure Monitor / App Insights ──────────────────────────────
    app_insights_app_id:    str = os.getenv("APP_INSIGHTS_APP_ID", "")
    app_insights_api_key:   str = os.getenv("APP_INSIGHTS_API_KEY", "")
    log_analytics_workspace:str = os.getenv("LOG_ANALYTICS_WORKSPACE_ID", "")

    # ── Jira ──────────────────────────────────────────────────────
    jira_url:               str = os.getenv("JIRA_URL", "")
    jira_email:             str = os.getenv("JIRA_EMAIL", "")
    jira_api_token:         str = os.getenv("JIRA_API_TOKEN", "")
    jira_default_project:   str = os.getenv("JIRA_DEFAULT_PROJECT", "OPS")

    def validate(self):
        """Raise if critical credentials are missing."""
        required = {
            "AZURE_SUBSCRIPTION_ID": self.azure_subscription_id,
            "AZURE_TENANT_ID":       self.azure_tenant_id,
            "AZURE_CLIENT_ID":       self.azure_client_id,
            "AZURE_CLIENT_SECRET":   self.azure_client_secret,
            "GITHUB_TOKEN":          self.github_token,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Copy .env.example to .env and fill in your values."
            )
        return True
