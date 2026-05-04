#!/usr/bin/env python3
"""Analyze CI/CD pipeline failure logs using Azure OpenAI."""

import argparse
import json
import os
import sys

from ai_assistant import AIIncidentAssistant


def main():
    parser = argparse.ArgumentParser(description="AI Pipeline Failure Analyzer")
    parser.add_argument("--log", type=str, help="Failure log text")
    parser.add_argument("--log-file", type=str, help="Path to log file")
    parser.add_argument("--pipeline", type=str, default="unknown", help="Pipeline name")
    parser.add_argument("--build-id", type=str, default="0", help="Build ID")
    parser.add_argument("--output", type=str, default="console", choices=["console", "json", "github"],
                        help="Output format")
    parser.add_argument("--output-file", type=str, help="Write result to file")
    args = parser.parse_args()

    # Get logs
    if args.log:
        logs = args.log
    elif args.log_file:
        with open(args.log_file, "r") as f:
            logs = f.read()
    elif not sys.stdin.isatty():
        logs = sys.stdin.read()
    else:
        print("❌ No logs provided. Use --log, --log-file, or pipe via stdin")
        sys.exit(1)

    print(f"🔬 Analyzing failure for pipeline: {args.pipeline} (build: {args.build_id})")
    print(f"📝 Log length: {len(logs)} characters")
    print("⏳ Sending to Azure OpenAI for analysis...\n")

    assistant = AIIncidentAssistant()
    analysis = assistant.analyze_failure(
        logs=logs,
        pipeline_name=args.pipeline,
        build_id=args.build_id,
    )

    if args.output == "json":
        result = json.dumps(analysis, indent=2)
        print(result)
    elif args.output == "github":
        comment = assistant.format_github_comment(analysis)
        print(comment)
    else:
        # Console output
        severity_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(
            analysis.get("severity", ""), "⚪"
        )
        print(f"{'='*60}")
        print(f"{severity_emoji} Severity: {analysis.get('severity', 'UNKNOWN')}")
        print(f"📁 Category: {analysis.get('category', 'UNKNOWN')}")
        print(f"⏱️  Fix Time: {analysis.get('estimated_fix_time', 'Unknown')}")
        print(f"🎯 Confidence: {analysis.get('confidence', 'N/A')}")
        print(f"{'='*60}")
        print(f"\n🔍 ROOT CAUSE:\n{analysis.get('root_cause', 'Unknown')}")
        print(f"\n🛠️  FIX STEPS:")
        for i, step in enumerate(analysis.get("fix_steps", []), 1):
            print(f"  {i}. {step}")
        if analysis.get("commands"):
            print(f"\n💻 COMMANDS:")
            for cmd in analysis["commands"]:
                print(f"  $ {cmd}")
        print(f"\n🛡️  PREVENTION:\n{analysis.get('prevention', 'N/A')}")

    # Write to file if specified
    if args.output_file:
        with open(args.output_file, "w") as f:
            if args.output == "github":
                f.write(assistant.format_github_comment(analysis))
            else:
                json.dump(analysis, f, indent=2)
        print(f"\n✅ Result saved to {args.output_file}")


if __name__ == "__main__":
    main()
