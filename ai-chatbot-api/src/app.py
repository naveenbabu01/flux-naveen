import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import AzureOpenAI

app = FastAPI(title="AI Chatbot API", version="1.0.0")

# Serve static files (Chat UI)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Azure OpenAI Configuration (set via environment variables)
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
)

DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")


class ChatRequest(BaseModel):
    question: str
    max_tokens: int = 500


class ChatResponse(BaseModel):
    question: str
    answer: str
    model: str


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/", include_in_schema=False)
def serve_chat_ui():
    return FileResponse("static/index.html")


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": request.question},
            ],
            max_tokens=request.max_tokens,
        )
        return ChatResponse(
            question=request.question,
            answer=response.choices[0].message.content,
            model=DEPLOYMENT_NAME,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
