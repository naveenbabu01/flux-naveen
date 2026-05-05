"""
tools/github_tools.py
=====================
GitHub Actions workflow operations via GitHub REST API v2022-11-28.
"""

import httpx
from utils.config import Config
from utils.logger import setup_logger

logger = setup_logger("github-tools")


class GitHubTools:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.headers = {
            "Authorization":        f"Bearer {cfg.github_token}",
            "Accept":               "application/vnd.github+json",
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

    # ── get_pipeline_status ────────────────────────────────────────────────

    async def get_pipeline_status(self, repo: str, workflow: str = None, limit: int = 5) -> dict:
        """Get recent workflow runs for a repo, optionally filtered by workflow file."""
        path = f"/repos/{repo}/actions/runs"
        params = {"per_page": limit}
        if workflow:
            params["workflow_id"] = workflow

        data = await self._get(path, params)
        runs = data.get("workflow_runs", [])

        result = []
        for run in runs[:limit]:
            result.append({
                "id":           run["id"],
                "name":         run["name"],
                "workflow":     run.get("path", "").split("/")[-1],
                "status":       run["status"],
                "conclusion":   run["conclusion"],
                "branch":       run["head_branch"],
                "commit_sha":   run["head_sha"][:8],
                "commit_msg":   run.get("head_commit", {}).get("message", "")[:80],
                "triggered_by": run.get("triggering_actor", {}).get("login", ""),
                "started_at":   run["run_started_at"],
                "duration_sec": None,   # computed below
                "url":          run["html_url"],
            })
            # Compute duration if completed
            if run.get("updated_at") and run.get("run_started_at"):
                from datetime import datetime
                fmt = "%Y-%m-%dT%H:%M:%SZ"
                try:
                    start = datetime.strptime(run["run_started_at"], fmt)
                    end   = datetime.strptime(run["updated_at"], fmt)
                    result[-1]["duration_sec"] = int((end - start).total_seconds())
                except Exception:
                    pass

        summary = {
            "repo":       repo,
            "total_runs": data.get("total_count", 0),
            "shown":      len(result),
            "success":    sum(1 for r in result if r["conclusion"] == "success"),
            "failure":    sum(1 for r in result if r["conclusion"] == "failure"),
            "runs":       result,
        }
        return summary

    # ── get_pipeline_logs ─────────────────────────────────────────────────

    async def get_pipeline_logs(self, repo: str, run_id: str) -> dict:
        """Download and return logs for a workflow run (truncated to last 6000 chars)."""
        # First get the jobs list
        jobs_data = await self._get(f"/repos/{repo}/actions/runs/{run_id}/jobs")
        jobs = jobs_data.get("jobs", [])

        jobs_summary = []
        for job in jobs:
            steps = [
                {
                    "name":       s["name"],
                    "status":     s["status"],
                    "conclusion": s["conclusion"],
                    "number":     s["number"],
                }
                for s in job.get("steps", [])
            ]
            jobs_summary.append({
                "job_id":    job["id"],
                "name":      job["name"],
                "status":    job["status"],
                "conclusion":job["conclusion"],
                "started_at":job["started_at"],
                "steps":     steps,
            })

        # Attempt log download
        log_text = "Log download requires appropriate GitHub token permissions."
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                resp = await client.get(
                    f"{self.base}/repos/{repo}/actions/runs/{run_id}/logs",
                    headers=self.headers
                )
                if resp.status_code == 200:
                    log_text = resp.text[-6000:]   # last 6000 chars
        except Exception as e:
            log_text = f"Could not download logs: {e}"

        return {
            "repo":     repo,
            "run_id":   run_id,
            "jobs":     jobs_summary,
            "logs":     log_text,
        }

    # ── trigger_pipeline ──────────────────────────────────────────────────

    async def trigger_pipeline(
        self, repo: str, workflow: str, branch: str = "main", inputs: dict = None
    ) -> dict:
        """Trigger a workflow_dispatch event to manually start a pipeline."""
        body = {"ref": branch, "inputs": inputs or {}}
        resp = await self._post(f"/repos/{repo}/actions/workflows/{workflow}/dispatches", body)
        if resp.status_code == 204:
            return {
                "success":  True,
                "repo":     repo,
                "workflow": workflow,
                "branch":   branch,
                "message":  f"Workflow '{workflow}' triggered on branch '{branch}'. "
                            f"Check GitHub Actions for progress."
            }
        return {
            "success": False,
            "status_code": resp.status_code,
            "error": resp.text
        }

    # ── get_failed_jobs ───────────────────────────────────────────────────

    async def get_failed_jobs(self, repo: str, run_id: str) -> dict:
        """Return only the failed jobs and their failed steps for quick diagnosis."""
        jobs_data = await self._get(f"/repos/{repo}/actions/runs/{run_id}/jobs")
        failed = []
        for job in jobs_data.get("jobs", []):
            if job["conclusion"] == "failure":
                failed_steps = [
                    {
                        "step":       s["name"],
                        "number":     s["number"],
                        "conclusion": s["conclusion"],
                    }
                    for s in job.get("steps", [])
                    if s["conclusion"] == "failure"
                ]
                failed.append({
                    "job_name":    job["name"],
                    "job_id":      job["id"],
                    "conclusion":  job["conclusion"],
                    "failed_steps":failed_steps,
                    "logs_url":    job["html_url"],
                })
        return {
            "repo":         repo,
            "run_id":       run_id,
            "failed_count": len(failed),
            "failed_jobs":  failed,
        }
