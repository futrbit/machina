import re
import sqlite3
from pathlib import Path
from collections import Counter

DB = Path("data/intelligence/sector_metrics.sqlite3")

# Common identifiers and date-like strings that should not become metrics.
ARXIV_ID = re.compile(r"\b\d{4}\.\d{4,5}(?:v\d+)?\b", re.I)
YEAR_ONLY = re.compile(r"^(?:19\d{2}|20\d{2}|21\d{2})$")
PURE_NUMBER = re.compile(r"^[+-]?\d[\d,]*(?:\.\d+)?$")
BAD_SUFFIX = re.compile(r"\d(?:v\d+|[a-z])$", re.I)

METRIC_TERMS = [
    "flight time", "flight endurance", "battery life", "battery capacity",
    "maximum speed", "max speed", "cruise speed", "payload", "flight range",
    "charging time", "cost per flight", "drone show", "swarm",
    "reach", "cycle time", "repeatability", "positioning accuracy",
    "operating hours", "runtime", "energy consumption", "power consumption",
    "cost per task", "operational design domain", "operating conditions",
    "human intervention", "disengagement", "miles driven", "test distance",
    "safety assessment", "crash rate", "regulatory approval",
    "deployment location", "benchmark", "evaluation", "mmlu", "swe-bench",
    "gpqa", "leaderboard", "latency", "tokens per second", "throughput",
    "time to first token", "inference speed", "inference cost",
    "context window", "context length", "multimodal", "gpu",
    "hardware requirements", "inference energy",
]

def assess(row):
    value = (row["value_text"] or "").strip()
    context = (row["evidence_context"] or "").strip()
    combined = f"{row['title'] or ''} {context}"
    reasons = []

    if not value:
        return "REJECT", "empty value"

    # Reject values that appear to be fragments of identifiers.
    if ARXIV_ID.search(value) or BAD_SUFFIX.search(value):
        return "REJECT", "identifier-like value"

    if re.search(r"\b(?:arxiv|doi|isbn|figure|fig\.|table|section)\b", context, re.I):
        if ARXIV_ID.search(context) or re.search(r"\b(?:figure|fig\.|table|section)\s*\d", context, re.I):
            return "REJECT", "paper identifier or reference"

    # Exclude bare years unless the context makes the year itself a measurement,
    # which this first-pass pipeline does not currently support.
    if YEAR_ONLY.fullmatch(value):
        return "REJECT", "bare year"

    # Values should be a clean numeric token with an optional plausible unit.
    if not re.match(
        r"^[+-]?\d[\d,]*(?:\.\d+)?\s*(?:%|percent|ms|µs|"
        r"seconds?|secs?|minutes?|mins?|hours?|hrs?|"
        r"km/h|mph|m/s|kilometres?|kilometers?|miles?|metres?|meters?|"
        r"kg|grams?|g|kW|watts?|W|kWh|Wh|mAh|Ah|volts?|V|"
        r"GB|TB|MB|USD|GBP|EUR|dollars?|points?|"
        r"tokens?\s*(?:/\s*(?:second|sec|s)|per\s+second))?$",
        value, re.I
    ):
        return "REJECT", "malformed numeric value or unit"

    # Keep numbers only when a technical metric term occurs close to the number
    # in the evidence excerpt, not merely somewhere in a long paper summary.
    position = context.lower().find(value.lower())
    if position >= 0:
        left = context[max(0, position - 85):position].lower()
        right = context[position + len(value):position + len(value) + 85].lower()
        nearby = left + " " + right
    else:
        nearby = context.lower()

    matched = [term for term in METRIC_TERMS if term in nearby]
    if not matched:
        return "REVIEW", "metric term not close enough to value"

    # A clean number with nearby metric language is still source-reported,
    # not independently verified. Human review is required.
    return "REVIEW", "plausible candidate; confirm meaning, unit and conditions"

def main():
    if not DB.exists():
        raise SystemExit(f"Database not found: {DB}")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    con.execute("""
        CREATE TABLE IF NOT EXISTS metric_candidate_quality (
            candidate_id INTEGER PRIMARY KEY,
            quality_status TEXT NOT NULL,
            quality_reason TEXT NOT NULL
        )
    """)
    con.execute("DELETE FROM metric_candidate_quality")

    rows = con.execute("""
        SELECT id, value_text, evidence_context, title, sector, metric_category
        FROM metric_candidates
    """).fetchall()

    counts = Counter()
    by_category = Counter()

    for row in rows:
        status, reason = assess(row)
        con.execute("""
            INSERT INTO metric_candidate_quality
            (candidate_id, quality_status, quality_reason)
            VALUES (?, ?, ?)
        """, (row["id"], status, reason))
        counts[status] += 1
        by_category[(row["sector"], row["metric_category"], status)] += 1

    con.commit()

    print(f"Candidates assessed: {len(rows):,}")
    print(f"Rejected as obvious junk: {counts['REJECT']:,}")
    print(f"Needs evidence review: {counts['REVIEW']:,}")
    print("\nCounts by sector, metric and status:")
    for (sector, metric, status), count in sorted(by_category.items()):
        print(f"  {sector} | {metric} | {status}: {count}")

    print("\nSample plausible candidates for manual review:")
    for row in con.execute("""
        SELECT m.sector, m.metric_category, m.value_text, m.title,
               m.evidence_context, m.source_url, q.quality_reason
        FROM metric_candidates m
        JOIN metric_candidate_quality q ON q.candidate_id = m.id
        WHERE q.quality_status = 'REVIEW'
        ORDER BY m.sector, m.metric_category
        LIMIT 20
    """):
        print(f"\n[{row['sector']} / {row['metric_category']}] {row['value_text']}")
        print(f"Title: {row['title']}")
        print(f"Context: {row['evidence_context']}")
        print(f"Source: {row['source_url']}")
        print(f"Status: {row['quality_reason']}")

    print("\nQuality labels are provisional; REVIEW does not mean verified.")
    con.close()

if __name__ == "__main__":
    main()
