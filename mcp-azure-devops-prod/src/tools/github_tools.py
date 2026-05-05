"""
tools/github_tools.py — GitHub Actions operations (token from Key Vault).
"""

import httpx
from utils.config import Config
from utils.logger import setup_logger

logger = setup_logger("github-tools")


class GitHubTools:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.headers = {
            "Authorization": f"Bearer {cfg.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.base = cfg.github_api_url

    async def _get(self, path: str, params: dict = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self.base}{path}", headers=self.headers, params=params)
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, body: dict = None) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self.base}{path}", headers=self.headers, json=body or {})
            return resp

    async def get_pipeline_status(self, repo: str, workflow: str = None, limit: int = 5) -> dict:
        """Get recent workflow runs for a repo."""
        params = {"per_page": limit}
        if workflow:
            params["workflow_id"] = workflow
        data = await self._get(f"/repos/{repo}/actions/runs", params)
        runs = data.get("workflow_runs", [])
        result = [{
            "id": r["id"], "name": r["name"], "status": r["status"],
            "conclusion": r["conclusion"], "branch": r["head_branch"],
            "started_at": r["run_started_at"], "url": r["html_url"],
        } for r in runs[:limit]]
        return {"repo": repo, "total_runs": data.get("total_count", 0), "runs": result}

    async def get_pipeline_logs(self, repo: str, run_id: str) -> dict:
        """Get jobs and logs for a workflow run."""
        jobs_data = await self._get(f"/repos/{repo}/actions/runs/{run_id}/jobs")
        jobs = [{
            "name": j["name"], "status": j["status"], "conclusion": j["conclusion"],
            "steps": [{"name": s["name"], "conclusion": s["conclusion"]} for s in j.get("steps", [])]
        } for j in jobs_data.get("jobs", [])]
        return {"repo": repo, "run_id": run_id, "jobs": jobs}

    async def trigger_pipeline(self, repo: str, workflow: str, branch: str = "main", inputs: dict = None) -> dict:
        """Trigger a workflow_dispatch event."""
        resp = await self._post(
            f"/repos/{repo}/actions/workflows/{workflow}/dispatches",
            {"ref": branch, "inputs": inputs or {}}
        )
        if resp.status_code == 204:
            return {"success": True, "workflow": workflow, "branch": branch}
        return {"success": False, "status_code": resp.status_code, "error": resp.text}

    async def get_failed_jobs(self, repo: str, run_id: str) -> dict:
        """Return only the failed jobs for quick diagnosis."""
        jobs_data = await self._get(f"/repos/{repo}/actions/runs/{run_id}/jobs")
        failed = [{
            "job_name": j["name"], "failed_steps": [
                {"step": s["name"]} for s in j.get("steps", []) if s["conclusion"] == "failure"
            ]
        } for j in jobs_data.get("jobs", []) if j["conclusion"] == "failure"]
        return {"repo": repo, "run_id": run_id, "failed_jobs": failed}
