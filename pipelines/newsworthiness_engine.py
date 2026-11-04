import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
DATA = ROOT / "data" / "deep_research"

INDEX_FILE = DATA / "specialist_local_index.json"
EVIDENCE_FILE = DATA / "evidence_adjudicated.json"
OUTPUT_FILE = DATA / "newsworthy_intelligence.json"
AUDIT_FILE = DATA / "newsworthiness_audit.json"

TITLE_FIELDS = ["title", "headline", "story_title", "event_title"]
SUMMARY_FIELDS = ["summary", "description", "abstract", "content", "text", "body", "claim", "finding", "details"]
URL_FIELDS = ["url", "source_url", "link", "article_url"]
SOURCE_FIELDS = ["source", "source_name", "publisher", "outlet", "publication", "domain"]
DATE_FIELDS = ["published_at", "published", "publication_date", "date", "created_at"]

IMPACT_SIGNALS = {
    "major_contract": (18, [
        r"\bcontract worth\b",
        r"\bawarded.{0,50}\bcontract\b",
        r"\bsecures?.{0,35}\bcontract\b",
        r"\bcontract valued at\b",
    ]),
    "acquisition_or_merger": (16, [
        r"\bacquires?\s+[a-z0-9]",
        r"\bagreement to acquire\b",
        r"\bacquired\s+(?:the|company|business|assets|division|startup|firm)\b",
        r"\bacquisition of\b",
        r"\bmerger between\b",
        r"\bmerges? with\b",
        r"\btakeover of\b",
    ]),
    "funding_or_finance": (15, [
        r"\braises?\s+(?:\$|£|)",
        r"\bfunding round\b",
        r"\bseries [a-f]\b",
        r"\bventure capital\b",
        r"\bvaluation of\b",
        r"\binvestment of\s+(?:\$|£|)",
    ]),
    "government_or_policy_action": (12, [
        r"\bgovernment (?:approves|approved|orders|ordered|bans|banned)\b",
        r"\bregulator (?:approves|approved|orders|ordered|bans|banned)\b",
        r"\bnew regulation\b",
        r"\bpolicy change\b",
        r"\blegislation\b",
        r"\bexecutive order\b",
        r"\bdefence department\b",
        r"\bdepartment of defense\b",
    ]),
    "legal_or_regulatory": (12, [
        r"\blawsuit filed\b",
        r"\bsued by\b",
        r"\bsettlement worth\b",
        r"\bfined\s+(?:\$|£|)",
        r"\bantitrust\b",
        r"\bregulatory investigation\b",
        r"\bcharges filed\b",
    ]),
    "business_change": (8, [
        r"\blayoffs?\b",
        r"\bjob cuts?\b",
        r"\bceo resigns?\b",
        r"\bcompany shuts down\b",
        r"\bfiles for bankruptcy\b",
        r"\bexpands? into\b",
        r"\bproduction halted\b",
    ]),
    "product_or_deployment": (6, [
        r"\blaunches?\b",
        r"\brolls out\b",
        r"\bdeployed\b",
        r"\benters? production\b",
        r"\bcommercially available\b",
        r"\bfirst customer\b",
    ]),
    "research_contribution": (8, [
        r"\bintroduces? a new\b",
        r"\bproposes? a new\b",
        r"\bpresents? a new\b",
        r"\bdemonstrates? that\b",
        r"\bexperiment(?:s|al)? show\b",
        r"\boutperforms?\b",
        r"\bstate.of.the.art\b",
        r"\bbenchmark results\b",
        r"\bnew method\b",
        r"\bnew framework\b",
        r"\bnew architecture\b",
    ]),
    "security_or_failure": (10, [
        r"\bdata breach\b",
        r"\bsecurity vulnerability\b",
        r"\bcritical vulnerability\b",
        r"\bservice outage\b",
        r"\bsystem failure\b",
        r"\brecall(?:s|ed)?\b",
        r"\bexploited in the wild\b",
    ]),
}

FIGURE_PATTERN = re.compile(
    r"(?:[$£]\s?\d[\d,.]*\s?(?:billion|million|bn|m)?"
    r"|\b\d+(?:\.\d+)?\s?%)",
    re.IGNORECASE,
)


def first_value(record, fields):
    for field in fields:
        value = record.get(field)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return ""


def normalise(value):
    value = str(value or "").lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_records(value, origin, results):
    if isinstance(value, list):
        for item in value:
            extract_records(item, origin, results)
        return

    if not isinstance(value, dict):
        return

    title = first_value(value, TITLE_FIELDS)
    summary = first_value(value, SUMMARY_FIELDS)
    url = first_value(value, URL_FIELDS)

    if title and (summary or url):
        results.append({
            "title": title,
            "summary": summary,
            "url": url,
            "source": first_value(value, SOURCE_FIELDS),
            "date": first_value(value, DATE_FIELDS),
            "record_id": first_value(value, ["record_id", "id", "evidence_id"]),
            "specialist": first_value(value, ["specialist", "specialist_name", "category", "team"]),
            "input_file": origin,
        })

    for child in value.values():
        if isinstance(child, (dict, list)):
            extract_records(child, origin, results)


def score_record(record, copies=1):
    title = record["title"]
    summary = record["summary"]
    combined = (title + " " + summary).lower()

    score = 8
    reasons = ["Baseline for a titled record"]

    if len(summary) >= 300:
        score += 4
        reasons.append("Substantive description")
    elif len(summary) >= 100:
        score += 3
        reasons.append("Useful description")
    elif len(summary) >= 30:
        score += 1
        reasons.append("Brief description")

    if record["url"].startswith(("https://", "http://")):
        score += 2
        reasons.append("HTTP source URL present")

    if record["source"]:
        score += 2
        reasons.append("Publisher identified")

    impact_points = 0
    matched_categories = []

    for category, (weight, patterns) in IMPACT_SIGNALS.items():
        if any(re.search(pattern, combined) for pattern in patterns):
            impact_points += weight
            matched_categories.append(category)

    impact_points = min(40, impact_points)
    score += impact_points

    if matched_categories:
        reasons.append("Impact signals: " + ", ".join(matched_categories))

    if FIGURE_PATTERN.search(combined):
        score += 2
        reasons.append("Specific financial or percentage figure")

    date_text = record["date"]
    if date_text:
        try:
            parsed = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            age_days = (
                datetime.now(timezone.utc) -
                parsed.astimezone(timezone.utc)
            ).total_seconds() / 86400

            if 0 <= age_days <= 2:
                score += 6
                reasons.append("Published within 2 days")
            elif 2 < age_days <= 7:
                score += 4
                reasons.append("Published within 7 days")
            elif 7 < age_days <= 30:
                score += 2
                reasons.append("Published within 30 days")
            elif age_days < 0:
                reasons.append("Future-dated; no freshness bonus")

        except (ValueError, TypeError, OverflowError):
            pass

    if copies > 1:
        reasons.append("Duplicate title; no repetition bonus applied")

    score = min(100, max(0, score))
    tier = "HIGH" if score >= 42 else "MEDIUM" if score >= 28 else "LOW"
    return score, tier, reasons

def main():
    print("=" * 60)
    print("MACHINADAILY NEWSWORTHINESS ENGINE")
    print("=" * 60)

    for path in [INDEX_FILE, EVIDENCE_FILE]:
        if not path.is_file():
            raise FileNotFoundError("Required input missing: " + str(path))

    with INDEX_FILE.open("r", encoding="utf-8-sig") as handle:
        index_data = json.load(handle)

    with EVIDENCE_FILE.open("r", encoding="utf-8-sig") as handle:
        evidence_data = json.load(handle)

    extracted = []
    extract_records(index_data, INDEX_FILE.name, extracted)
    extract_records(evidence_data, EVIDENCE_FILE.name, extracted)

    if not extracted:
        raise ValueError(
            "No titled records found. The source JSON may use different field names."
        )

    grouped = {}
    counts = Counter()

    for record in extracted:
        key = normalise(record["title"])
        if not key:
            continue

        counts[key] += 1

        if key not in grouped:
            grouped[key] = record
        else:
            current = grouped[key]
            if len(record["summary"]) > len(current["summary"]):
                record["input_file"] = current["input_file"] + "; " + record["input_file"]
                grouped[key] = record
            else:
                current["input_file"] += "; " + record["input_file"]

    records = []

    for key, record in grouped.items():
        score, tier, reasons = score_record(record, counts[key])
        records.append({
            **record,
            "deduplication_key": key,
            "newsworthiness_score": score,
            "newsworthiness_tier": tier,
            "ranking_reasons": reasons,
        })

    records.sort(key=lambda item: item["newsworthiness_score"], reverse=True)

    for rank, record in enumerate(records, start=1):
        record["rank"] = rank

    now = datetime.now(timezone.utc).isoformat()
    tiers = Counter(item["newsworthiness_tier"] for item in records)

    output = {
        "engine": "MachinaDaily Newsworthiness Engine",
        "version": "1.0",
        "generated_at": now,
        "total_records": len(records),
        "scoring_note": "Heuristic ranking; scores do not prove accuracy or independent corroboration.",
        "records": records,
    }

    audit = {
        "engine": "MachinaDaily Newsworthiness Engine",
        "generated_at": now,
        "input_files": [str(INDEX_FILE), str(EVIDENCE_FILE)],
        "extracted_records": len(extracted),
        "unique_records": len(records),
        "duplicate_records_removed": len(extracted) - len(records),
        "tier_counts": dict(tiers),
        "top_stories": [
            {
                "rank": item["rank"],
                "title": item["title"],
                "score": item["newsworthiness_score"],
                "tier": item["newsworthiness_tier"],
            }
            for item in records[:20]
        ],
        "warnings": [
            "Scores are heuristic, not fact verification.",
            "Repeated titles do not prove independent corroboration.",
        ],
    }

    DATA.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, ensure_ascii=False)

    with AUDIT_FILE.open("w", encoding="utf-8") as handle:
        json.dump(audit, handle, indent=2, ensure_ascii=False)

    print("Input records:", len(extracted))
    print("Unique stories:", len(records))
    print("High priority:", tiers["HIGH"])
    print("Medium priority:", tiers["MEDIUM"])
    print("Low priority:", tiers["LOW"])
    print()
    print("Top stories:")
    for record in records[:10]:
        print(
            str(record["rank"]) + ". [" +
            str(record["newsworthiness_score"]) + "] " +
            record["title"][:110]
        )

    print()
    print("Wrote:", OUTPUT_FILE)
    print("Wrote:", AUDIT_FILE)
    print("ENGINE FINISHED")


if __name__ == "__main__":
    main()