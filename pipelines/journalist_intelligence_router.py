
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
DATA = ROOT / "data" / "deep_research"
INPUT_FILE = DATA / "newsworthy_intelligence.json"
OUTPUT_DIR = DATA / "journalist_feeds"

FEED_SIZE = 100

# Prefer fields explicitly named as publication dates.
# Generic "date" is retained but its meaning is not assumed.
DATE_FIELDS = (
    "published_at",
    "published",
    "publication_date",
    "date",
    "created_at",
    "updated_at",
    "timestamp",
    "indexed_at",
    "discovered_at",
    "first_seen",
)

JOURNALISTS = {
    "callum_reyes": {
        "name": "Callum Reyes",
        "role": "Wire Desk",
        "focus": [
            "breaking", "announced", "announcement", "launch",
            "launched", "revealed", "statement", "confirmed",
            "appointed", "resigned", "deal", "agreement",
            "incident", "milestone", "today", "urgent"
        ],
    },
    "tomas_vega": {
        "name": "Tomas Vega",
        "role": "Markets & Business",
        "focus": [
            "funding", "investment", "investor", "revenue",
            "profit", "loss", "acquisition", "acquired",
            "merger", "valuation", "contract", "customer",
            "commercial", "business", "startup", "company",
            "partnership", "billion", "million", "market"
        ],
    },
    "ingrid_sorensen": {
        "name": "Ingrid Sorensen",
        "role": "Policy Correspondent",
        "focus": [
            "government", "policy", "regulation", "regulatory",
            "legislation", "minister", "parliament", "law",
            "approved", "ban", "banned", "department",
            "public sector", "defence", "defense", "military",
            "national security", "consultation", "official"
        ],
    },
    "dev_okafor": {
        "name": "Dev Okafor",
        "role": "Product Correspondent",
        "focus": [
            "product", "launched", "launch", "release", "released",
            "feature", "platform", "application", "app",
            "tool", "service", "model", "capability",
            "available", "developer", "software", "update",
            "version", "integration", "user"
        ],
    },
    "ravi_chatterjee": {
        "name": "Ravi Chatterjee",
        "role": "Technical & Research Explainer",
        "focus": [
            "research", "paper", "study", "benchmark", "dataset",
            "evaluation", "experiment", "accuracy", "inference",
            "training", "model", "architecture", "algorithm",
            "technical", "scientific", "arxiv", "performance",
            "limitations", "methodology", "results", "findings"
        ],
    },
    "elena_vasquez": {
        "name": "Elena Vasquez",
        "role": "Drones & Uncrewed Systems",
        "focus": [
            "drone", "drones", "uav", "uncrewed", "unmanned",
            "counter-drone", "counter drone", "loitering munition",
            "autonomous weapon", "air defence", "air defense",
            "electronic warfare", "surveillance", "interceptor",
            "military aircraft", "flight test", "remote piloting"
        ],
    },
    "marcus_okafor": {
        "name": "Marcus Okafor",
        "role": "Robotics Correspondent",
        "focus": [
            "robot", "robotics", "humanoid", "manipulation",
            "embodied ai", "industrial automation", "robotic arm",
            "warehouse automation", "factory automation",
            "robot fleet", "actuator", "gripper", "locomotion",
            "robot deployment", "physical ai", "autonomous robot"
        ],
    },
    "kenji_nakamura": {
        "name": "Kenji Nakamura",
        "role": "Autonomous Vehicles Correspondent",
        "focus": [
            "autonomous vehicle", "self-driving", "self driving",
            "driverless", "robotaxi", "autonomous driving",
            "vehicle autonomy", "automotive", "adas",
            "advanced driver assistance", "waymo", "tesla",
            "mobility", "transport", "road test", "vehicle fleet",
            "autonomous truck", "automated driving"
        ],
    },
    "sofia_lindqvist": {
        "name": "Sofia Lindqvist",
        "role": "Industrial Systems & Infrastructure",
        "focus": [
            "industrial", "manufacturing", "production",
            "infrastructure", "supply chain", "factory",
            "power grid", "energy system", "industrial system",
            "semiconductor fabrication", "data centre",
            "data center", "logistics", "critical infrastructure",
            "automation", "industrial deployment", "capacity",
            "large-scale production", "resilience"
        ],
    },
}


def normalise(text):
    text = str(text or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_specialist(record):
    value = str(record.get("specialist", "")).lower()
    source = str(record.get("source", "")).lower()
    combined = value + " " + source

    if any(word in combined for word in [
        "alpha", "technical intelligence"
    ]):
        return "ALPHA"

    if any(word in combined for word in [
        "beta", "capital intelligence", "market intelligence"
    ]):
        return "BETA"

    if any(word in combined for word in [
        "gamma", "policy intelligence", "strategic intelligence"
    ]):
        return "GAMMA"

    return "UNCLASSIFIED"


def parse_source_date(record, now):
    """
    Parse a source-provided date without pretending that a generic
    date or indexing timestamp is definitely a publication date.

    Returns normalized metadata. The original record fields are
    never modified by this function.
    """
    raw_value = None
    field_used = None

    for field in DATE_FIELDS:
        value = record.get(field)

        if value is not None and str(value).strip():
            raw_value = value
            field_used = field
            break

    if raw_value is None:
        return {
            "source_date_field": None,
            "source_date_utc": None,
            "source_date_status": "missing",
            "source_date_semantics": "unknown",
            "source_date_age_days": None,
            "freshness_score": 0,
        }

    # Convert Unix timestamps when supplied as numbers.
    try:
        if isinstance(raw_value, (int, float)):
            parsed = datetime.fromtimestamp(
                raw_value, tz=timezone.utc
            )
        else:
            text = str(raw_value).strip()

            # Support ISO timestamps ending in Z.
            if text.endswith(("Z", "z")):
                text = text[:-1] + "+00:00"

            parsed = datetime.fromisoformat(text)

        # Naive timestamps have no explicit timezone.
        # Assume UTC for consistent comparison, and disclose this.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
            timezone_assumed = True
        else:
            parsed = parsed.astimezone(timezone.utc)
            timezone_assumed = False

    except (ValueError, TypeError, OverflowError, OSError):
        return {
            "source_date_field": field_used,
            "source_date_utc": None,
            "source_date_status": "invalid",
            "source_date_semantics": "unverified",
            "source_date_age_days": None,
            "freshness_score": 0,
        }

    age_seconds = (now - parsed).total_seconds()
    age_days = round(age_seconds / 86400, 2)

    if age_seconds < 0:
        status = "future"
        freshness = -5
    else:
        status = (
            "parsed_naive_assumed_utc"
            if timezone_assumed
            else "parsed"
        )

        if age_days <= 2:
            freshness = 18
        elif age_days <= 7:
            freshness = 12
        elif age_days <= 30:
            freshness = 6
        elif age_days <= 90:
            freshness = 2
        elif age_days <= 180:
            freshness = -4
        else:
            freshness = -10

    if field_used in (
        "published_at", "published", "publication_date"
    ):
        semantics = "publication_field_name"
    elif field_used in ("created_at", "updated_at"):
        semantics = "record_creation_or_update"
    elif field_used in ("indexed_at", "discovered_at", "first_seen"):
        semantics = "discovery_or_indexing"
    else:
        semantics = "generic_date_meaning_unverified"

    return {
        "source_date_field": field_used,
        "source_date_utc": parsed.isoformat(),
        "source_date_status": status,
        "source_date_semantics": semantics,
        "source_date_age_days": age_days,
        "freshness_score": freshness,
    }


def rank_for_journalist(record, journalist, now):
    title = str(record.get("title", ""))
    summary = str(record.get("summary", ""))
    text = normalise(title + " " + summary)

    matched = []

    for term in journalist["focus"]:
        pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
        if re.search(pattern, text):
            matched.append(term)

    try:
        news_score = int(record.get("newsworthiness_score", 0))
    except (ValueError, TypeError, OverflowError):
        news_score = 0

    specialist = get_specialist(record)
    specialist_bonus = 0

    if (
        journalist["role"] == "Technical & Research Explainer"
        and specialist == "ALPHA"
    ):
        specialist_bonus = 4
    elif (
        journalist["role"] == "Markets & Business"
        and specialist == "BETA"
    ):
        specialist_bonus = 4
    elif (
        journalist["role"] == "Policy Correspondent"
        and specialist == "GAMMA"
    ):
        specialist_bonus = 4

    desk_relevance = min(40, len(matched) * 5)
    date_info = parse_source_date(record, now)

    ranking_score = (
        news_score
        + desk_relevance
        + specialist_bonus
        + date_info["freshness_score"]
    )

    result = dict(record)

    # Keep the original date and original newsworthiness score.
    # Add separate fields for the router's interpretation.
    result.update(date_info)
    result["desk_relevance_score"] = desk_relevance
    result["specialist_bonus"] = specialist_bonus
    result["base_newsworthiness_score"] = news_score
    result["journalist_relevance_score"] = ranking_score
    result["ranking_score"] = ranking_score
    result["matched_focus_terms"] = matched
    result["specialist_group"] = specialist

    result["routing_note"] = (
        "Matched desk focus: " + ", ".join(matched[:8])
        if matched
        else "General candidate; no exact desk-focus term matched"
    )

    return result


def main():
    print("=" * 64)
    print("MACHINADAILY - JOURNALIST INTELLIGENCE ROUTER")
    print("=" * 64)

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            "Newsworthiness output not found: "
            + str(INPUT_FILE)
            + ". Run newsworthiness_engine.py first."
        )

    with INPUT_FILE.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)

    if isinstance(data, dict):
        records = data.get("records", [])
    elif isinstance(data, list):
        records = data
    else:
        records = []

    if not isinstance(records, list) or not records:
        raise ValueError(
            "The newsworthiness file contains no records."
        )

    # One consistent clock for all nine feeds in this run.
    now = datetime.now(timezone.utc)
    generated_at = now.isoformat()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {
        "generated_at": generated_at,
        "input_file": str(INPUT_FILE),
        "input_record_count": len(records),
        "feed_size": FEED_SIZE,
        "date_policy": {
            "ranking_uses_source_dates": True,
            "original_date_fields_preserved": True,
            "naive_timestamps_assumed_utc": True,
            "missing_dates_receive_no_freshness_bonus": True,
            "future_dates_are_flagged": True,
            "date_semantics_are_not_assumed": True,
        },
        "freshness_scoring": {
            "0_to_2_days": 18,
            "3_to_7_days": 12,
            "8_to_30_days": 6,
            "31_to_90_days": 2,
            "91_to_180_days": -4,
            "over_180_days": -10,
            "missing_or_invalid": 0,
            "future": -5,
        },
        "routing_method": (
            "Desk keyword relevance + source newsworthiness score "
            "+ specialist bonus + date freshness score. "
            "Candidate ranking is not a factual verdict. "
            "Date meaning depends on the source field."
        ),
        "journalists": {},
    }

    print("Stories available:", len(records))
    print("Feed generation time (UTC):", generated_at)
    print("Building nine desk feeds...\n")

    for journalist_id, journalist in JOURNALISTS.items():
        ranked = [
            rank_for_journalist(record, journalist, now)
            for record in records
            if isinstance(record, dict)
        ]

        ranked.sort(
            key=lambda item: (
                item["ranking_score"],
                item["desk_relevance_score"],
                item["freshness_score"],
                item.get("base_newsworthiness_score", 0),
                item.get("source_date_utc") or "",
                str(item.get("record_id", "")),
            ),
            reverse=True,
        )

        selected = ranked[:FEED_SIZE]
        filename = journalist_id + ".json"
        output_path = OUTPUT_DIR / filename

        status_counts = {}
        for item in selected:
            status = item["source_date_status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        feed = {
            "journalist_id": journalist_id,
            "journalist_name": journalist["name"],
            "desk": journalist["role"],
            "generated_at": generated_at,
            "input_record_count": len(records),
            "candidate_count": len(selected),
            "focus_terms": journalist["focus"],
            "date_status_counts": status_counts,
            "selection_note": (
                "Candidates are ranked for this desk. "
                "Check source evidence and date semantics before "
                "making factual claims. Older stories can remain "
                "eligible when their relevance and significance "
                "justify further investigation."
            ),
            "stories": selected,
        }

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(feed, handle, indent=2, ensure_ascii=False)

        matched_count = sum(
            1 for item in selected if item["matched_focus_terms"]
        )

        recent_count = sum(
            1 for item in selected
            if item["source_date_age_days"] is not None
            and 0 <= item["source_date_age_days"] <= 7
        )

        manifest["journalists"][journalist_id] = {
            "name": journalist["name"],
            "desk": journalist["role"],
            "file": str(output_path),
            "candidate_count": len(selected),
            "candidates_with_focus_matches": matched_count,
            "candidates_dated_within_7_days": recent_count,
            "date_status_counts": status_counts,
            "top_story": (
                selected[0].get("title") if selected else None
            ),
            "top_story_date_status": (
                selected[0].get("source_date_status")
                if selected else None
            ),
        }

        print(
            journalist["name"],
            "|", journalist["role"],
            "| candidates:", len(selected),
            "| focus matches:", matched_count,
            "| dated within 7 days:", recent_count,
            "| missing/invalid dates:",
            status_counts.get("missing", 0)
            + status_counts.get("invalid", 0),
        )

    manifest_path = OUTPUT_DIR / "manifest.json"

    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)

    print("\nFEEDS WRITTEN TO:", OUTPUT_DIR)
    print("MANIFEST:", manifest_path)
    print("ROUTER FINISHED")


if __name__ == "__main__":
    main()