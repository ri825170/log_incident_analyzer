# Log Incident Analyzer

A Python CLI tool that reads an unstructured technical log file and uses the Claude API to produce a structured incident summary in JSON.

---

## Features

- Parses raw, noisy log files of any format
- Extracts incident metadata: ID, severity (P1–P4), status, and timeline
- Identifies root cause, affected services, and business impact
- Highlights the 5–10 most important turning-point events
- Outputs actionable remediation steps and future recommendations
- Prints a human-readable terminal report and optionally saves full JSON

---

## Requirements

- Python 3.8+
- An [Anthropic API key](https://console.anthropic.com/)

Install the only dependency:

```bash
pip install anthropic
```

---

## Setup

Export your API key as an environment variable:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## Usage

**Run with the bundled sample log**
```bash
python log_incident_analyzer.py
```

**Analyze your own log file**
```bash
python log_incident_analyzer.py --log /var/log/app.log
```

**Save the JSON summary to a file**
```bash
python log_incident_analyzer.py --log /var/log/app.log --output summary.json
```

### Arguments

| Argument | Description |
|---|---|
| `--log FILE` | Path to your log file. Omit to run against the bundled sample. |
| `--output FILE` | Optional path to write the JSON summary (e.g. `summary.json`). |

---

## Output

The tool prints a structured report to the terminal and, if `--output` is specified, writes the full JSON to disk.

**Terminal report example**
```
────────────────────────────────────────────────────────────
  INCIDENT SUMMARY
────────────────────────────────────────────────────────────
  ID       : INC-2024-0315-001
  Title    : Database Replica Disk Full Causing Service Degradation
  Severity : P1
  Status   : resolved

  Timeline
    Detected    : 2024-03-15T02:14:33
    Acked       : 2024-03-15T02:18:30
    Resolved    : 2024-03-15T02:27:05
    Duration    : 13 min

  Root Cause
    db-replica-02 ran out of disk space (500 GB, 100% used),
    halting WAL replication and exhausting DB connection pools
    across dependent services.

  Affected Services
    • db-primary
    • db-replica-02
    • api-gateway
    • order-service
    • payment-service

  ...
────────────────────────────────────────────────────────────
```

**JSON schema**

```json
{
  "incident_id":              "string | null",
  "title":                    "string",
  "severity":                 "P1 | P2 | P3 | P4 | unknown",
  "status":                   "resolved | ongoing | unknown",
  "timeline": {
    "detection_time":         "ISO-8601 | null",
    "acknowledgement_time":   "ISO-8601 | null",
    "resolution_time":        "ISO-8601 | null",
    "total_duration_minutes": "number  | null"
  },
  "root_cause":               "string",
  "affected_services":        ["string"],
  "impact_summary":           "string",
  "key_events": [
    { "timestamp": "ISO-8601", "event": "string" }
  ],
  "remediation_steps":        ["string"],
  "recommendations":          ["string"]
}
```

---

## How It Works

1. **Load** — reads the log file from disk (or uses the bundled sample).
2. **Prompt** — sends the raw log inside `<log>` tags to `claude-sonnet-4-20250514` with a strict system prompt that enforces the JSON schema above.
3. **Parse** — validates and parses the JSON response, stripping any accidental markdown fences.
4. **Display** — renders the summary as a readable terminal report.
5. **Save** — optionally writes the full JSON to the path given by `--output`.

---

## Project Structure

```
.
├── log_incident_analyzer.py   # Main script
└── README.md                  # This file
```

---

## License

MIT
