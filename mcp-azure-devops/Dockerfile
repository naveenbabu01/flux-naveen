FROM python:3.11-slim

LABEL maintainer="Naveen Babu Mummadi <mummadinaveen777@gmail.com>"
LABEL description="Azure DevOps MCP Server — AKS + GitHub Actions + Monitor + Cost + Jira"

WORKDIR /app

# Install OS dependencies (needed by azure-identity for some auth flows)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/

# Ensure Python can find modules in src/
ENV PYTHONPATH=/app/src

# Non-root user for security
RUN useradd -m mcpuser
USER mcpuser

# MCP stdio mode — no exposed port needed for Claude Desktop
# For HTTP mode: uvicorn src.server:app --host 0.0.0.0 --port 8000
CMD ["python", "src/server.py"]
