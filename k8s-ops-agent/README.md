# Kubernetes AI Ops Agent

> POC: Autonomous K8s troubleshooting with human approval gate

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Streamlit  │────▶│  LangGraph   │────▶│   kubectl   │
│     UI      │◀────│  State Graph │◀────│   cluster   │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌───────────┐ ┌──────────┐ ┌──────────┐
       │Azure OpenAI│ │ ChromaDB │ │LangSmith │
       │  (GPT-4o)  │ │  (RAG)   │ │ (Traces) │
       └───────────┘ └──────────┘ └──────────┘
```

## Flow

1. **Detect** — Scans cluster for unhealthy pods
2. **Context** — Fetches logs, describe, events for troubled pod
3. **RAG** — Retrieves matching runbook from ChromaDB
4. **Diagnose** — Azure OpenAI analyzes root cause
5. **Propose** — Generates kubectl fix commands with risk levels
6. **⏸ HUMAN APPROVAL GATE** — Operator reviews & cherry-picks commands
7. **Execute** — Runs only approved commands
8. **Report** — Verifies fix, posts to Slack, logs audit trail

## Prerequisites

- Python 3.10+
- Access to a Kubernetes cluster (`kubectl` configured)
- Azure OpenAI resource with GPT-4o and text-embedding-ada-002 deployed
- (Optional) Slack bot token for notifications
- (Optional) LangSmith API key for tracing

## Quick Start

```bash
# 1. Clone and enter directory
cd k8s-ops-agent

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env
# Edit .env with your Azure OpenAI keys

# 5. Verify kubectl access
kubectl get nodes

# 6. Run the agent
streamlit run app.py
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_API_KEY` | ✅ | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | ✅ | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | ✅ | GPT-4o deployment name |
| `AZURE_OPENAI_EMBED_DEPLOYMENT` | ✅ | Embedding model deployment name |
| `LANGCHAIN_API_KEY` | ❌ | LangSmith tracing key |
| `LANGCHAIN_TRACING_V2` | ❌ | Set `true` to enable tracing |
| `LANGCHAIN_PROJECT` | ❌ | LangSmith project name |
| `SLACK_BOT_TOKEN` | ❌ | Slack bot token for alerts |
| `SLACK_CHANNEL` | ❌ | Slack channel for notifications |

## Safety Features

- **Interrupt gate**: LangGraph pauses before any execution
- **Risk labeling**: Each command tagged LOW / MEDIUM / HIGH
- **Cherry-pick**: Operator selects which commands to run
- **Audit log**: Every action timestamped and logged
- **Slack alerts**: Optional notification on fix completion
