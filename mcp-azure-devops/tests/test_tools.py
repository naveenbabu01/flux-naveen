"""
tests/test_tools.py
===================
Unit tests for MCP tools using mocked Azure/GitHub responses.
Run: pytest tests/ -v
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.utils.config import Config


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_config():
    cfg = Config()
    cfg.azure_subscription_id  = "test-sub"
    cfg.azure_tenant_id        = "test-tenant"
    cfg.azure_client_id        = "test-client"
    cfg.azure_client_secret    = "test-secret"
    cfg.aks_resource_group     = "test-rg"
    cfg.aks_cluster_name       = "test-cluster"
    cfg.github_token           = "ghp_test"
    cfg.jira_url               = "https://test.atlassian.net"
    cfg.jira_email             = "test@test.com"
    cfg.jira_api_token         = "test-token"
    return cfg


# ─── GitHub Tools Tests ───────────────────────────────────────────────────────

class TestGitHubTools:
    @pytest.mark.asyncio
    async def test_get_pipeline_status_success(self, mock_config):
        """Should parse GitHub API response into clean summary."""
        from src.tools.github_tools import GitHubTools

        mock_response = {
            "total_count": 2,
            "workflow_runs": [
                {
                    "id": 12345,
                    "name": "CI/CD Pipeline",
                    "path": ".github/workflows/ci-cd.yml",
                    "status": "completed",
                    "conclusion": "success",
                    "head_branch": "main",
                    "head_sha": "abc12345def",
                    "head_commit": {"message": "feat: add AI assistant"},
                    "triggering_actor": {"login": "naveen"},
                    "run_started_at": "2026-05-01T10:00:00Z",
                    "updated_at":     "2026-05-01T10:05:00Z",
                    "html_url": "https://github.com/naveen/myapp/actions/runs/12345",
                }
            ]
        }

        tools = GitHubTools(mock_config)
        with patch.object(tools, "_get", return_value=mock_response):
            result = await tools.get_pipeline_status("naveen/myapp", limit=5)

        assert result["repo"] == "naveen/myapp"
        assert result["success"] == 1
        assert result["failure"] == 0
        assert len(result["runs"]) == 1
        assert result["runs"][0]["conclusion"] == "success"

    @pytest.mark.asyncio
    async def test_trigger_pipeline_success(self, mock_config):
        from src.tools.github_tools import GitHubTools

        mock_resp = MagicMock()
        mock_resp.status_code = 204

        tools = GitHubTools(mock_config)
        with patch.object(tools, "_post", return_value=mock_resp):
            result = await tools.trigger_pipeline("naveen/myapp", "deploy.yml", "main")

        assert result["success"] is True
        assert result["workflow"] == "deploy.yml"

    @pytest.mark.asyncio
    async def test_get_failed_jobs(self, mock_config):
        from src.tools.github_tools import GitHubTools

        mock_response = {
            "jobs": [
                {
                    "id": 1,
                    "name": "deploy-to-aks",
                    "status": "completed",
                    "conclusion": "failure",
                    "started_at": "2026-05-01T10:00:00Z",
                    "html_url": "https://github.com/naveen/myapp/runs/1",
                    "steps": [
                        {"name": "Helm deploy", "conclusion": "failure",  "number": 3},
                        {"name": "Checkout",    "conclusion": "success",  "number": 1},
                    ]
                }
            ]
        }
        tools = GitHubTools(mock_config)
        with patch.object(tools, "_get", return_value=mock_response):
            result = await tools.get_failed_jobs("naveen/myapp", "99999")

        assert result["failed_count"] == 1
        assert result["failed_jobs"][0]["job_name"] == "deploy-to-aks"
        assert len(result["failed_jobs"][0]["failed_steps"]) == 1


# ─── Jira Tools Tests ─────────────────────────────────────────────────────────

class TestJiraTools:
    @pytest.mark.asyncio
    async def test_create_incident_success(self, mock_config):
        from src.tools.jira_tools import JiraTools

        mock_response = {"key": "OPS-42", "id": "10001"}

        tools = JiraTools(mock_config)
        with patch.object(tools, "_post", return_value=mock_response):
            result = await tools.create_incident(
                title="AKS pod crash loop in production",
                description="3 pods in production namespace are in CrashLoopBackOff",
                severity="Critical",
                project_key="OPS",
            )

        assert result["success"] is True
        assert result["ticket_key"] == "OPS-42"
        assert "OPS-42" in result["ticket_url"]

    @pytest.mark.asyncio
    async def test_get_open_incidents(self, mock_config):
        from src.tools.jira_tools import JiraTools

        mock_response = {
            "issues": [
                {
                    "key": "OPS-40",
                    "fields": {
                        "summary":  "[CRITICAL] DB connection timeout",
                        "status":   {"name": "In Progress"},
                        "priority": {"name": "Highest"},
                        "assignee": {"displayName": "Naveen"},
                        "labels":   ["incident"],
                        "created":  "2026-05-01T08:00:00Z",
                    }
                }
            ]
        }
        tools = JiraTools(mock_config)
        with patch.object(tools, "_get", return_value=mock_response):
            result = await tools.get_open_incidents("OPS")

        assert result["open_incidents"] == 1
        assert result["issues"][0]["key"] == "OPS-40"


# ─── Config Tests ─────────────────────────────────────────────────────────────

class TestConfig:
    def test_validate_raises_on_missing(self):
        cfg = Config()
        cfg.azure_subscription_id = ""
        cfg.github_token = ""
        with pytest.raises(EnvironmentError) as exc_info:
            cfg.validate()
        assert "AZURE_SUBSCRIPTION_ID" in str(exc_info.value)

    def test_validate_passes_with_all_fields(self, mock_config):
        assert mock_config.validate() is True
