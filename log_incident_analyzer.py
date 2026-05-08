#!/usr/bin/env python3
"""
log_incident_analyzer.py
────────────────────────
Reads an unstructured technical log file and uses the Claude API to produce
a structured incident summary as JSON.

Usage
-----
    # Analyze the bundled sample log
    python log_incident_analyzer.py

    # Analyze your own log file
    python log_incident_analyzer.py --log path/to/your.log

    # Save the JSON summary to a file
    python log_incident_analyzer.py --log path/to/your.log --output summary.json

Requirements
------------
    pip install anthropic

    Set your API key:
        export ANTHROPIC_API_KEY="sk-ant-..."
"""

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime

import anthropic

# ──────────────────────────────────────────────
# Sample log bundled with the script
# ──────────────────────────────────────────────
SAMPLE_LOG = """
2024-03-15 02:11:43 INFO  [auth-service]     User login attempt: user_id=8821
2024-03-15 02:11:44 INFO  [auth-service]     Login successful: user_id=8821
2024-03-15 02:14:05 WARN  [db-primary]       Replication lag increasing: lag=1.2s replica=db-replica-02
2024-03-15 02:14:18 WARN  [db-primary]       Replication lag increasing: lag=3.7s replica=db-replica-02
2024-03-15 02:14:33 ERROR [db-primary]       Replication lag critical: lag=12.4s replica=db-replica-02
2024-03-15 02:14:33 ERROR [db-replica-02]    Cannot apply WAL segment: segment=000000010000003700000042 error="disk full"
2024-03-15 02:14:34 ERROR [db-replica-02]    Disk usage 100%: mount=/var/lib/postgresql used=500GB total=500GB
2024-03-15 02:14:35 WARN  [api-gateway]      Elevated error rate detected: 5xx_rate=4.2% threshold=2%
2024-03-15 02:14:40 ERROR [order-service]    DB query timeout after 30s: query=SELECT_orders user_id=9901
2024-03-15 02:14:40 ERROR [order-service]    DB query timeout after 30s: query=SELECT_orders user_id=4452
2024-03-15 02:14:41 ERROR [payment-service]  Failed to record transaction: tx_id=TXN-20240315-88821 error="connection pool exhausted"
2024-03-15 02:14:42 ERROR [payment-service]  Failed to record transaction: tx_id=TXN-20240315-88822 error="connection pool exhausted"
2024-03-15 02:14:45 WARN  [api-gateway]      Elevated error rate detected: 5xx_rate=18.7% threshold=2%
2024-03-15 02:14:50 ERROR [alert-manager]    PagerDuty alert fired: incident=INC-2024-0315-001 severity=P1
2024-03-15 02:16:12 INFO  [ops-oncall]       Engineer paged: responder=jane.doe@example.com
2024-03-15 02:18:30 INFO  [ops-oncall]       Incident acknowledged by jane.doe@example.com
2024-03-15 02:22:05 INFO  [db-replica-02]    Disk cleanup initiated: target_free=50GB
2024-03-15 02:24:11 INFO  [db-replica-02]    Disk cleanup complete: freed=55GB usage=89%
2024-03-15 02:24:15 INFO  [db-primary]       Replication lag normalizing: lag=8.1s replica=db-replica-02
2024-03-15 02:26:44 INFO  [db-primary]       Replication lag normal: lag=0.3s replica=db-replica-02
2024-03-15 02:26:50 INFO  [api-gateway]      Error rate back to normal: 5xx_rate=0.8%
2024-03-15 02:26:52 INFO  [order-service]    DB queries resuming normally
2024-03-15 02:27:00 INFO  [payment-service]  Connection pool recovered
2024-03-15 02:27:05 INFO  [alert-manager]    PagerDuty incident resolved: incident=INC-2024-0315-001
"""

# ──────────────────────────────────────────────
# Prompt
# ──────────────────────────────────────────────
SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert site-reliability engineer specialising in incident analysis.
    Analyse the log file the user provides and return ONLY a JSON object — no markdown,
    no explanation, just the raw JSON.

    The JSON must conform exactly to this schema:

    {
      "incident_id":        string | null,
      "title":              string,
      "severity":           "P1" | "P2" | "P3" | "P4" | "unknown",
      "status":             "resolved" | "ongoing" | "unknown",
      "timeline": {
        "detection_time":   ISO-8601 string | null,
        "acknowledgement_time": ISO-8601 string | null,
        "resolution_time":  ISO-8601 string | null,
        "total_duration_minutes": number | null
      },
      "root_cause":         string,
      "affected_services":  [string],
      "impact_summary":     string,
      "key_events": [
        { "timestamp": ISO-8601 string, "event": string }
      ],
      "remediation_steps":  [string],
      "recommendations":    [string]
    }

    Rules:
    - All timestamps must be ISO-8601 (e.g. "2024-03-15T02:14:33").
    - Derive severity from PagerDuty alerts or, if absent, from the blast radius.
    - key_events should capture only the most important 5–10 turning-point log lines.
    - recommendations should be actionable prevention measures for the future.
    - Return valid JSON only. Do not wrap in code fences.
""").strip()


# ──────────────────────────────────────────────
# Core function
# ──────────────────────────────────────────────
def analyze_log(log_text: str, client: anthropic.Anthropic) -> dict:
    """Send log_text to Claude and return the parsed incident summary dict."""

    print("⏳  Sending log to Claude for analysis …")

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Please analyse the following log file and return the structured "
                    "incident summary JSON.\n\n"
                    f"<log>\n{log_text}\n</log>"
                ),
            }
        ],
    )

    raw = message.content[0].text.strip()

    # Strip accidental markdown fences just in case
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()

    return json.loads(raw)


# ──────────────────────────────────────────────
# Pretty-print helper
# ──────────────────────────────────────────────
def print_summary(summary: dict) -> None:
    SEP = "─" * 60

    def fmt(val):
        return val if val is not None else "N/A"

    print(f"\n{SEP}")
    print(f"  INCIDENT SUMMARY")
    print(SEP)
    print(f"  ID       : {fmt(summary.get('incident_id'))}")
    print(f"  Title    : {fmt(summary.get('title'))}")
    print(f"  Severity : {fmt(summary.get('severity'))}")
    print(f"  Status   : {fmt(summary.get('status'))}")

    tl = summary.get("timeline", {})
    print(f"\n  Timeline")
    print(f"    Detected    : {fmt(tl.get('detection_time'))}")
    print(f"    Acked       : {fmt(tl.get('acknowledgement_time'))}")
    print(f"    Resolved    : {fmt(tl.get('resolution_time'))}")
    dur = tl.get("total_duration_minutes")
    print(f"    Duration    : {f'{dur} min' if dur else 'N/A'}")

    print(f"\n  Root Cause")
    for line in textwrap.wrap(summary.get("root_cause", "N/A"), width=56):
        print(f"    {line}")

    print(f"\n  Affected Services")
    for svc in summary.get("affected_services", []):
        print(f"    • {svc}")

    print(f"\n  Impact")
    for line in textwrap.wrap(summary.get("impact_summary", "N/A"), width=56):
        print(f"    {line}")

    print(f"\n  Key Events")
    for ev in summary.get("key_events", []):
        ts = ev.get("timestamp", "")
        evt = ev.get("event", "")
        print(f"    [{ts}]")
        for line in textwrap.wrap(evt, width=54):
            print(f"      {line}")

    print(f"\n  Remediation Steps")
    for i, step in enumerate(summary.get("remediation_steps", []), 1):
        for line in textwrap.wrap(f"{i}. {step}", width=56):
            print(f"    {line}")

    print(f"\n  Recommendations")
    for i, rec in enumerate(summary.get("recommendations", []), 1):
        for line in textwrap.wrap(f"{i}. {rec}", width=56):
            print(f"    {line}")

    print(SEP + "\n")


# ──────────────────────────────────────────────
# CLI entry-point
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Analyse a technical log file and produce a structured incident summary."
    )
    parser.add_argument(
        "--log",
        metavar="FILE",
        help="Path to the log file. Omit to use the bundled sample log.",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Optional path to write the JSON summary (e.g. summary.json).",
    )
    args = parser.parse_args()

    # ── Load log ──────────────────────────────
    if args.log:
        if not os.path.isfile(args.log):
            print(f"Error: file not found: {args.log}", file=sys.stderr)
            sys.exit(1)
        with open(args.log, "r", encoding="utf-8") as fh:
            log_text = fh.read()
        print(f"📄  Loaded log: {args.log} ({len(log_text):,} chars)")
    else:
        log_text = SAMPLE_LOG
        print("📄  Using bundled sample log (pass --log <file> to use your own)")

    # ── API key ───────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "Error: ANTHROPIC_API_KEY environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # ── Analyse ───────────────────────────────
    try:
        summary = analyze_log(log_text, client)
    except json.JSONDecodeError as exc:
        print(f"Error: Claude returned invalid JSON — {exc}", file=sys.stderr)
        sys.exit(1)
    except anthropic.APIError as exc:
        print(f"Error: Anthropic API error — {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Display ───────────────────────────────
    print_summary(summary)

    # ── Save ──────────────────────────────────
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"✅  JSON summary written to: {args.output}")
    else:
        print("💡  Tip: pass --output summary.json to save the full JSON.\n")
        print("Full JSON:\n")
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
