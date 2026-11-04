from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
SOURCE_DB = ROOT / "data" / "intelligence" / "deep_raw_index.sqlite3"
OUTPUT_DB = ROOT / "data" / "intelligence" / "sector_metrics.sqlite3"

SECTORS = {
    "drones": {
        "terms": ["drone", "uav", "quadrotor", "unmanned aerial", "aerial robot"],
        "metrics": {
            "Flight endurance and battery": [
                "flight time", "flight endurance", "battery life",
                "battery capacity", "energy density", "endurance"
            ],
            "Speed and operating envelope": [
                "maximum speed", "max speed", "cruise speed",
                "airspeed", "operating speed", "wind speed"
            ],
            "Payload and range": [
                "payload capacity", "payload", "flight range",
                "operating range"
            ],
            "Charging and operating cost": [
                "charging time", "charge time", "cost per flight",
                "operating cost"
            ],
            "Show fleets and synchronisation": [
                "drone show", "swarm", "synchronization",
                "synchronisation", "fleet size", "formation flight"
            ],
        },
    },
    "robotics": {
        "terms": ["robot", "robotics", "robotic arm", "manipulator", "humanoid"],
        "metrics": {
            "Payload and reach": ["payload", "reach", "load capacity", "workspace"],
            "Cycle time and repeatability": [
                "cycle time", "repeatability", "positioning accuracy",
                "precision", "throughput"
            ],
            "Operating hours and energy": [
                "operating hours", "runtime", "energy consumption",
                "power consumption", "battery life"
            ],
            "Purchase and task cost": [
                "purchase cost", "cost per task",
                "total cost of ownership", "unit cost"
            ],
        },
    },
    "autonomous": {
        "terms": [
            "autonomous vehicle", "autonomous system", "autonomous driving",
            "self-driving", "driverless", "adas", "autonomous robot",
            "autonomous drone"
        ],
        "metrics": {
            "Operating conditions": [
                "operational design domain", "operating conditions",
                "weather conditions", "operating envelope"
            ],
            "Interventions and test distance": [
                "human intervention", "disengagement", "miles driven",
                "kilometres driven", "kilometers driven", "test distance"
            ],
            "Safety and independent assessment": [
                "safety incident", "safety assessment",
                "independent assessment", "crash rate", "safety case"
            ],
            "Regulation and deployment": [
                "regulatory approval", "approved for deployment",
                "deployment location", "commercial deployment"
            ],
        },
    },
    "ai": {
        "terms": [
            "large language model", "llm", "generative ai",
            "foundation model", "ai model", "machine learning",
            "inference", "artificial intelligence"
        ],
        "metrics": {
            "Benchmarks and evaluation": [
                "benchmark", "evaluation", "mmlu", "swe-bench",
                "gpqa", "leaderboard", "accuracy score"
            ],
            "Latency and throughput": [
                "latency", "tokens per second", "throughput",
                "time to first token", "inference speed"
            ],
            "Token and inference cost": [
                "cost per million tokens", "inference cost",
                "input token price", "output token price"
            ],
            "Context and modalities": [
                "context window", "context length", "multimodal",
                "image input", "audio input", "video input"
            ],
            "Hardware and energy": [
                "gpu", "hardware requirements", "energy consumption",
                "power consumption", "inference energy"
            ],
        },
    },
}

# Numeric candidates are retained with their original text and units.
# Extraction does NOT certify that a figure is correct.
NUMBER_RE = re.compile(
    r"(?<![A-Za-z])"
    r"[-+]?\d[\d,]*(?:\.\d+)?"
    r"\s*(?:"
    r"%|percent|"
    r"milliseconds?|ms|microseconds?|µs|"
    r"seconds?|secs?|minutes?|mins?|hours?|hrs?|"
    r"kilometres?|kilometers?|miles?|metres?|meters?|"
    r"kilograms?|kg|grams?|g|"
    r"kilowatts?|kW|watts?|W|"
    r"kWh|Wh|mAh|Ah|volts?|V|"
    r"km/h|mph|m/s|"
    r"tokens?\s*/\s*(?:second|sec|s)|"
    r"tokens?\s+per\s+second|"
    r"GB|TB|MB|"
    r"USD|GBP|EUR|dollars?|"
    r"points?|"
    r")",
    re.IGNORECASE,
)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def has_term(text: str, term: str) -> bool:
    # Phrase-aware matching; avoid matching "AI" inside unrelated words.
    if term.isalpha() and len(term) <= 3:
        return re.search(r"\b" + re.escape(term) + r"\b", text, re.I) is not None
    return term.casefold() in text.casefold()


def init_output(connection: sqlite3.Connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS metric_candidates (
            id INTEGER PRIMARY KEY,
            source_paper_id TEXT NOT NULL,
            sector TEXT NOT NULL,
            metric_category TEXT NOT NULL,
            value_text TEXT NOT NULL,
            evidence_context TEXT NOT NULL,
            title TEXT,
            source_name TEXT,
            published TEXT,
            source_url TEXT,
            evidence_status TEXT NOT NULL,
            extraction_method TEXT NOT NULL,
            extracted_at TEXT NOT NULL
        )
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_metric_sector
        ON metric_candidates(sector, metric_category)
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_metric_source
        ON metric_candidates(source_paper_id)
    """)
    connection.commit()


def main() -> None:
    if not SOURCE_DB.exists():
        raise SystemExit(f"Source index not found: {SOURCE_DB}")

    # Source index is opened read-only.
    source = sqlite3.connect(
        f"file:{SOURCE_DB.as_posix()}?mode=ro", uri=True, timeout=15
    )
    source.row_factory = sqlite3.Row

    columns = {
        row["name"] for row in
        source.execute("PRAGMA table_info(papers)").fetchall()
    }
    required = {
        "paper_id", "title", "summary", "sectors",
        "source_name", "url", "published"
    }
    if not required.issubset(columns):
        source.close()
        raise SystemExit(
            "Unexpected papers schema. Missing: " +
            ", ".join(sorted(required - columns))
        )

    records = source.execute("""
        SELECT paper_id, title, summary, sectors, source_name, url, published
        FROM papers
    """).fetchall()
    source.close()

    output = sqlite3.connect(OUTPUT_DB)
    init_output(output)

    # Rebuild candidates from the current index on each run.
    # The original source index is never modified.
    output.execute("DELETE FROM metric_candidates")

    extracted_at = datetime.now(timezone.utc).isoformat()
    insert_rows = []
    seen = set()

    for record in records:
        title = record["title"] or ""
        summary = record["summary"] or ""
        sectors_text = record["sectors"] or ""
        searchable = " ".join((title, summary, sectors_text)).casefold()

        for sector_key, profile in SECTORS.items():
            sector_match = (
                any(has_term(searchable, t) for t in profile["terms"])
                or sector_key in sectors_text.casefold()
            )
            if not sector_match:
                continue

            # Summaries can be abstracts, excerpts or short descriptions.
            # Only extract a candidate when a metric term and a number occur
            # together in the same text segment.
            text = title + ". " + summary
            for segment in SENTENCE_SPLIT_RE.split(text):
                segment = segment.strip()
                if not segment or not NUMBER_RE.search(segment):
                    continue

                for metric_name, terms in profile["metrics"].items():
                    matched_terms = [t for t in terms if has_term(segment, t)]
                    if not matched_terms:
                        continue

                    for number in NUMBER_RE.finditer(segment):
                        value = number.group(0).strip()
                        context_start = max(0, number.start() - 150)
                        context_end = min(len(segment), number.end() + 150)
                        context = segment[context_start:context_end].strip()

                        # Prevent duplicate candidates for the same source,
                        # category, value and evidence excerpt.
                        identity = (
                            record["paper_id"], sector_key, metric_name,
                            value, context
                        )
                        if identity in seen:
                            continue
                        seen.add(identity)

                        insert_rows.append((
                            record["paper_id"], sector_key, metric_name,
                            value, context, title, record["source_name"],
                            record["published"], record["url"],
                            "SOURCE_REPORTED_UNVERIFIED",
                            "keyword-context numeric extraction",
                            extracted_at,
                        ))

    output.executemany("""
        INSERT INTO metric_candidates (
            source_paper_id, sector, metric_category, value_text,
            evidence_context, title, source_name, published, source_url,
            evidence_status, extraction_method, extracted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, insert_rows)
    output.commit()

    print(f"Source records scanned: {len(records):,}")
    print(f"Numeric evidence candidates: {len(insert_rows):,}")
    print(f"Separate output database: {OUTPUT_DB}")
    print("Original research index: read-only; unchanged.")
    print("\nCandidates by sector and metric:")
    for row in output.execute("""
        SELECT sector, metric_category, COUNT(*) AS candidates
        FROM metric_candidates
        GROUP BY sector, metric_category
        ORDER BY sector, metric_category
    """):
        print(f"  {row[0]} | {row[1]}: {row[2]}")

    print("\nSample candidates for manual validation:")
    for row in output.execute("""
        SELECT sector, metric_category, value_text, title, source_url
        FROM metric_candidates
        ORDER BY id DESC LIMIT 12
    """):
        print(f"\n[{row[0]} / {row[1]}] {row[2]}")
        print(f"  {row[3] or 'Untitled'}")
        print(f"  {row[4] or 'No source URL'}")

    output.close()


if __name__ == "__main__":
    main()
