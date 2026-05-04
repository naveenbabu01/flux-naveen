import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from ai_assistant import AIIncidentAssistant

app = FastAPI(title="AI DevOps Incident Assistant", version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

assistant = AIIncidentAssistant()


class AnalyzeRequest(BaseModel):
    logs: str
    pipeline_name: Optional[str] = "manual"
    build_id: Optional[str] = "0"


class AnalyzeResponse(BaseModel):
    severity: str
    root_cause: str
    category: str
    fix_steps: list
    commands: list
    prevention: str
    estimated_fix_time: str
    confidence: float


@app.get("/health")
def health():
    return {"status": "healthy", "service": "ai-devops-assistant"}


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse("static/index.html")


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
