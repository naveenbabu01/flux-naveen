import logging
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from ai_assistant import AIIncidentAssistant
from monitor import PodMonitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI DevOps Incident Assistant", version="2.0.0")

assistant = AIIncidentAssistant()

# Start real-time pod monitor
monitor = PodMonitor()
monitor.start()


class AnalyzeRequest(BaseModel):
    logs: str
    pipeline_name: Optional[str] = "manual"
    build_id: Optional[str] = "0"


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "ai-devops-incident-assistant",
        "version": "2.0.0",
        "monitoring": monitor.monitoring,
        "incidents_count": len(monitor.incidents),
    }


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse("static/index.html")


@app.get("/incidents")
def get_incidents():
    """Get all auto-detected incidents with AI analysis."""
    return {"incidents": monitor.get_incidents()}


@app.post("/scan")
def scan_now():
    """Trigger immediate scan of all pods across all namespaces."""
    new_incidents = monitor.scan_all_pods()
    return {
        "message": f"Scan complete. Found {len(new_incidents)} new failing pods.",
        "new_incidents": [i.to_dict() for i in new_incidents],
        "total_incidents": len(monitor.incidents),
    }


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    try:
        result = assistant.analyze_failure(
            logs=request.logs,
            pipeline_name=request.pipeline_name,
            build_id=request.build_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/github-format")
def analyze_github(request: AnalyzeRequest):
    """Returns analysis formatted as GitHub PR comment markdown."""
    try:
        result = assistant.analyze_failure(
            logs=request.logs,
            pipeline_name=request.pipeline_name,
            build_id=request.build_id,
        )
        comment = assistant.format_github_comment(result)
        return {"markdown": comment, "analysis": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
