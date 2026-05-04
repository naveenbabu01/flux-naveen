import os
import json
from openai import AzureOpenAI
from datetime import datetime


class AIIncidentAssistant:
    """Azure OpenAI-powered DevOps Incident Assistant."""

    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        )
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")

        self.system_prompt = """You are an expert DevOps/SRE AI assistant specializing in CI/CD pipeline failures, 
Kubernetes troubleshooting, and cloud infrastructure issues.

When analyzing a pipeline failure, provide your response in this EXACT JSON format:
{
    "severity": "HIGH|MEDIUM|LOW",
    "root_cause": "Clear description of what went wrong",
    "category": "BUILD|TEST|DEPLOY|INFRA|CONFIG|SECURITY",
    "affected_components": ["list", "of", "affected", "components"],
    "fix_steps": [
        "Step 1: ...",
        "Step 2: ...",
        "Step 3: ..."
    ],
    "commands": [
        "actual shell/kubectl commands to fix the issue"
    ],
    "prevention": "How to prevent this in the future",
    "estimated_fix_time": "e.g., 5 minutes, 30 minutes",
    "confidence": 0.95
}

Rules:
- Always provide working, copy-paste ready commands
- Be specific with file paths, container names, namespace references
- Include kubectl, docker, helm, az CLI commands as needed
- Rate severity based on production impact
- If logs show multiple issues, address the root cause first
"""

    def analyze_failure(self, logs: str, pipeline_name: str = "", build_id: str = "", context: dict = None) -> dict:
        """Analyze pipeline failure logs and return structured diagnosis."""

        user_prompt = f"""Analyze this CI/CD pipeline failure:

**Pipeline:** {pipeline_name}
**Build ID:** {build_id}
**Timestamp:** {datetime.utcnow().isoformat()}Z

**Failure Logs:**
```
{logs[-3000:]}
```
"""
        if context:
            user_prompt += f"\n**Additional Context:**\n{json.dumps(context, indent=2)}"

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=1500,
                temperature=0.1,  # Low temp for consistent, factual analysis
            )

            content = response.choices[0].message.content

            # Try to parse as JSON
            try:
                # Extract JSON from potential markdown code block
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                analysis = json.loads(content)
            except (json.JSONDecodeError, IndexError):
                analysis = {
                    "severity": "MEDIUM",
                    "root_cause": content,
                    "category": "UNKNOWN",
                    "affected_components": [],
                    "fix_steps": [content],
                    "commands": [],
                    "prevention": "Review the full analysis above",
                    "estimated_fix_time": "Unknown",
                    "confidence": 0.5,
                }

            # Add metadata
            analysis["pipeline_name"] = pipeline_name
            analysis["build_id"] = build_id
            analysis["analyzed_at"] = datetime.utcnow().isoformat() + "Z"
            analysis["model"] = self.deployment
            analysis["tokens_used"] = response.usage.total_tokens

            return analysis

        except Exception as e:
            return {
                "severity": "HIGH",
                "root_cause": f"AI analysis failed: {str(e)}",
                "category": "UNKNOWN",
                "fix_steps": ["Check Azure OpenAI connectivity", "Verify API key"],
                "commands": [],
                "error": str(e),
            }

    def format_github_comment(self, analysis: dict) -> str:
        """Format analysis as a GitHub PR comment with markdown."""

        severity_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(
            analysis.get("severity", "MEDIUM"), "⚪"
        )

        comment = f"""## 🤖 AI DevOps Incident Analysis

{severity_emoji} **Severity:** {analysis.get('severity', 'UNKNOWN')}
📁 **Category:** {analysis.get('category', 'UNKNOWN')}
⏱️ **Est. Fix Time:** {analysis.get('estimated_fix_time', 'Unknown')}
🎯 **Confidence:** {analysis.get('confidence', 'N/A')}

---

### 🔍 Root Cause
{analysis.get('root_cause', 'Unable to determine')}

### 🛠️ Fix Steps
"""
        for i, step in enumerate(analysis.get("fix_steps", []), 1):
            comment += f"{i}. {step}\n"

        if analysis.get("commands"):
            comment += "\n### 💻 Commands to Fix\n```bash\n"
            for cmd in analysis["commands"]:
                comment += f"{cmd}\n"
            comment += "```\n"

        comment += f"""
### 🛡️ Prevention
{analysis.get('prevention', 'N/A')}

### 📊 Affected Components
{', '.join(analysis.get('affected_components', ['N/A']))}

---
<sub>🤖 Analyzed by AI DevOps Assistant | Pipeline: {analysis.get('pipeline_name', 'N/A')} | Build: {analysis.get('build_id', 'N/A')} | {analysis.get('analyzed_at', '')}</sub>
"""
        return comment
