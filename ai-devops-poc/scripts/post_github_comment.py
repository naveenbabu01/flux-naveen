#!/usr/bin/env python3
"""Post AI analysis as a GitHub PR comment."""

import argparse
import json
import os
import sys
import urllib.request


def post_comment(repo: str, pr_number: int, body: str, token: str):
    """Post a comment to a GitHub PR."""
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    data = json.dumps({"body": body}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        response = urllib.request.urlopen(req)
        result = json.loads(response.read().decode())
        print(f"✅ Comment posted: {result['html_url']}")
        return result
    except urllib.error.HTTPError as e:
        print(f"❌ Failed to post comment: {e.code} {e.read().decode()}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Post AI analysis to GitHub PR")
    parser.add_argument("--repo", type=str, required=True, help="GitHub repo (owner/name)")
    parser.add_argument("--pr", type=int, required=True, help="PR number")
    parser.add_argument("--comment-file", type=str, help="File containing the comment markdown")
    parser.add_argument("--comment", type=str, help="Comment text directly")
    parser.add_argument("--analysis-file", type=str, help="JSON analysis file to format")
    args = parser.parse_args()

    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ GH_TOKEN or GITHUB_TOKEN not set")
        sys.exit(1)

    if args.comment_file:
        with open(args.comment_file, "r") as f:
            body = f.read()
    elif args.comment:
        body = args.comment
    elif args.analysis_file:
        with open(args.analysis_file, "r") as f:
            analysis = json.load(f)
        # Import and format
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from ai_assistant import AIIncidentAssistant
        assistant = AIIncidentAssistant.__new__(AIIncidentAssistant)
        body = AIIncidentAssistant.format_github_comment(assistant, analysis)
    else:
        print("❌ Provide --comment-file, --comment, or --analysis-file")
        sys.exit(1)

    post_comment(args.repo, args.pr, body, token)


if __name__ == "__main__":
    main()
