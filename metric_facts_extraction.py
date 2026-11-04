import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "intelligence" / "deep_raw_index.sqlite3"
TARGET = ROOT / "data" / "intelligence" / "sector_metrics.sqlite3"

# Each pattern requires a number to be explicitly associated with a metric.
# This is conservative: it will miss some valid facts rather than guess.
RULES = {
    "drones": [
        ("Flight endurance", r"(?:flight time|flight endurance|flight duration)\s*(?:of|is|was|:|=|up to|approximately|about)?\s*(\d+(?:\.\d+)?)\s*(seconds?|minutes?|mins?|hours?|hrs?)"),
        ("Payload capacity", r"(?:payload capacity|payload)\s*(?:of|is|was|:|=|up to|approximately|about)?\s*(\d+(?:\.\d+)?)\s*(kg|kilograms?|grams?|g)\b"),
        ("Maximum speed", r"(?:maximum speed|max(?:imum)? velocity|cruise speed)\s*(?:of|is|was|:|=|up to|approximately|about)?\s*(\d+(?:\.\d+)?)\s*(km/h|m/s|mph)\b"),
        ("Flight range", r"(?:flight range|operating range|range)\s*(?:of|is|was|:|=|up to|approximately|about)?\s*(\d+(?:\.\d+)?)\s*(km|kilometres?|kilometers?|miles?)\b"),
    ],
    "robotics": [
        ("Payload capacity", r"(?:payload capacity|payload|load capacity)\s*(?:of|is|was|:|=|up to|approximately|about)?\s*(\d+(?:\.\d+)?)\s*(kg|kilograms?|grams?)\b"),
        ("Reach", r"(?:robot reach|maximum reach|reach)\s*(?:of|is|was|:|=|up to|approximately|about)?\s*(\d+(?:\.\d+)?)\s*(mm|cm|m|metres?|meters?)\b"),
        ("Cycle time", r"(?:cycle time|cycle duration)\s*(?:of|is|was|:|=|approximately|about)?\s*(\d+(?:\.\d+)?)\s*(ms|milliseconds?|seconds?|s)\b"),
        ("Repeatability", r"(?:repeatability|positioning repeatability)\s*(?:of|is|was|:|=|approximately|about)?\s*(\d+(?:\.\d+)?)\s*(mm|micrometres?|micrometers?|µm)\b"),
    ],
    "autonomous": [
        ("Test distance", r"(?:tested|test|driven|covered)\s*(?:for|over|a distance of)?\s*(\d[\d,]*(?:\.\d+)?)\s*(miles?|kilometres?|kilometers?|km)\b"),
        ("Human interventions", r"(\d[\d,]*(?:\.\d+)?)\s*(?:human )?(?:interventions|disengagements)\b"),
        ("Safety incident rate", r"(?:incident rate|crash rate)\s*(?:of|is|was|:|=)?\s*(\d+(?:\.\d+)?)\s*(%|per million miles|per km|per kilometre|per kilometer)\b"),
    ],
    "ai": [
        ("Latency", r"(?:latency|time to first token)\s*(?:of|is|was|:|=|approximately|about)?\s*(\d+(?:\.\d+)?)\s*(milliseconds?|ms|seconds?|secs?)\b"),
        ("Inference throughput", r"(\d+(?:\.\d+)?)\s*(tokens?\s*(?:/|per)\s*(?:second|sec|s)|tokens per second)\b"),
        ("Context window", r"(?:context window|context length|context size)\s*(?:of|is|was|:|=|up to|approximately|about)?\s*(\d[\d,]*(?:\.\d+)?)\s*(tokens?|k tokens?|million tokens?)\b"),
        ("Benchmark score", r"(?:accuracy|pass@1|pass rate|benchmark score|success rate)\s*(?:of|was|is|:|=)?\s*(\d+(?:\.\d+)?)\s*(%)\b"),
        ("Model parameters", r"(\d+(?:\.\d+)?)\s*(billion|million|B|M)\s*(?:parameters|parameter|model parameters|parameters)\b"),
    ],
}

SECTOR_TERMS = {
    "drones": ["drone", "uav", "quadrotor", "unmanned aerial"],
    "robotics": ["robot", "robotics", "robotic arm", "manipulator", "humanoid"],
    "autonomous": ["autonomous vehicle", "autonomous driving", "self-driving",
                   "driverless", "autonomous system", "disengagement"],
    "ai": ["large language model", "llm", "generative ai", "foundation model",
           "machine learning", "artificial intelligence", "inference"],
}

def main():
    if not SOURCE.exists():
        raise SystemExit(f"Source database missing: {SOURCE}")
    if not TARGET.exists():
        raise SystemExit(f"Metrics database missing: {TARGET}. Run metric_extraction.py first.")

    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    papers = src.execute("""
        SELECT paper_id, title, summary, sectors, source_name, url, published
        FROM papers
    """).fetchall()
    src.close()

    out = sqlite3.connect(TARGET)
    out.execute("""
        CREATE TABLE IF NOT EXISTS metric_facts (
            id INTEGER PRIMARY KEY,
            source_paper_id TEXT NOT NULL,
            sector TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            value TEXT NOT NULL,
            unit TEXT NOT NULL,
            evidence_sentence TEXT NOT NULL,
            title TEXT,
            source_name TEXT,
            published TEXT,
            source_url TEXT,
            status TEXT NOT NULL,
            extraction_rule TEXT NOT NULL,
            extracted_at TEXT NOT NULL,
            UNIQUE(source_paper_id, sector, metric_name, value, unit, evidence_sentence)
        )
    """)
    out.execute("DELETE FROM metric_facts")

    timestamp = datetime.now(timezone.utc).isoformat()
    inserted = 0

    for paper in papers:
        title = paper["title"] or ""
        summary = paper["summary"] or ""
        sector_text = (paper["sectors"] or "").lower()
        combined = f"{title}. {summary}"
        combined_lower = combined.lower()

        # Keep sentence context reasonably intact. Avoid splitting on decimal points.
        sentences = re.split(r"(?<=[!?])\s+|(?<!\d)\.(?!\d)\s+|\n+", combined)
        for sector, rules in RULES.items():
            if not (
                sector in sector_text
                or any(term in combined_lower for term in SECTOR_TERMS[sector])
            ):
                continue

            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                for metric_name, pattern in rules:
                    for match in re.finditer(pattern, sentence, re.IGNORECASE):
                        groups = match.groups()
                        value = groups[0].replace(",", "")
                        unit = groups[1].strip() if len(groups) > 1 else ""

                        # Do not show generic bare years as measurements.
                        if re.fullmatch(r"(?:19|20|21)\d{2}", value):
                            continue

                        out.execute("""
                            INSERT OR IGNORE INTO metric_facts (
                                source_paper_id, sector, metric_name, value, unit,
                                evidence_sentence, title, source_name, published,
                                source_url, status, extraction_rule, extracted_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            paper["paper_id"], sector, metric_name, value, unit,
                            sentence, title, paper["source_name"],
                            paper["published"], paper["url"],
                            "SOURCE_REPORTED_UNVERIFIED",
                            "explicit metric-label and numeric-unit pattern",
                            timestamp,
                        ))
                        inserted += out.execute("SELECT changes()").fetchone()[0]

    out.commit()

    print("Indexed records scanned:", f"{len(papers):,}")
    print("New metric facts stored:", f"{inserted:,}")
    print("Output table: metric_facts")
    print("Status: SOURCE_REPORTED_UNVERIFIED")
    print("\nFacts by sector and metric:")
    for row in out.execute("""
        SELECT sector, metric_name, COUNT(*)
        FROM metric_facts
        GROUP BY sector, metric_name
        ORDER BY sector, metric_name
    """):
        print(f"  {row[0]} | {row[1]}: {row[2]}")

    print("\nSample extracted facts:")
    for row in out.execute("""
        SELECT sector, metric_name, value, unit, evidence_sentence, title, source_url
        FROM metric_facts
        ORDER BY sector, metric_name
        LIMIT 15
    """):
        print(f"\n[{row[0]} / {row[1]}] {row[2]} {row[3]}")
        print("Evidence:", row[4])
        print("Title:", row[5])
        print("Source:", row[6])

    out.close()

if __name__ == "__main__":
    main()
