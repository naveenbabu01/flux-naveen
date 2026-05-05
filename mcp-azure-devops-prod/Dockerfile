FROM python:3.11-slim

LABEL maintainer="Naveen Babu Mummadi"
LABEL description="MCP Azure DevOps Server — Production (AKS + Managed Identity)"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV TRANSPORT=http
ENV PORT=8000

# Non-root user
RUN useradd -m mcpuser
USER mcpuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "src/server.py", "--transport", "http", "--port", "8000"]
