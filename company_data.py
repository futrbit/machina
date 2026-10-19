
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any
from flask import Blueprint, jsonify, send_from_directory


ROOT = Path(__file__).resolve().parent
INTELLIGENCE_DIR = ROOT / "data" / "intelligence"
RAW_DIR = ROOT / "data" / "raw"
FRONTEND_DIR = ROOT / "frontend"

ATLAS_FILE = INTELLIGENCE_DIR / "company_atlas.json"
ANALYSIS_FILE = INTELLIGENCE_DIR / "company_atlas_analysis.json"
VERIFIED_FILE = INTELLIGENCE_DIR / "company_atlas_verified_profiles.json"

company_data_bp = Blueprint("company_data", __name__)


def read_json(path: Path, default: Any = None) -> Any:
    """Read JSON with a fallback for legacy Windows-encoded evidence."""
    if not path.exists():
        return default

    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with path.open("r", encoding=encoding) as file:
                return json.load(file)
        except UnicodeDecodeError:
            continue
        except (OSError, json.JSONDecodeError):
            return default

    return default

def normalise_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None or value == "":
        return []
    return [value]


def clean_text(value: Any, limit: int = 4000) -> str:
    if isinstance(value, str):
        return value.strip()[:limit]
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def clean_urls(*groups: Any, limit: int = 15) -> list[str]:
    result = []
    seen = set()

    for group in groups:
        for item in as_list(group):
            if not isinstance(item, str):
                continue
            url = item.strip()
            if not url.startswith(("https://", "http://")):
                continue
            if url not in seen:
                seen.add(url)
                result.append(url)
            if len(result) >= limit:
                return result

    return result


def parse_date(value: Any) -> datetime | None:
    """Parse common ISO and email/RFC-style timestamps into UTC."""
    if not isinstance(value, str) or not value.strip():
        return None

    value = value.strip()

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def evidence_path(value: Any) -> Path | None:
    """Resolve atlas evidence paths safely within this project."""
    if not isinstance(value, str) or not value.strip():
        return None

    relative = Path(value.replace("\\", "/"))

    if relative.is_absolute():
        try:
            resolved = relative.resolve()
            resolved.relative_to(ROOT.resolve())
            return resolved
        except (ValueError, OSError):
            return None

    try:
        resolved = (ROOT / relative).resolve()
        resolved.relative_to(ROOT.resolve())
        return resolved
    except (ValueError, OSError):
        return None


def entity_class(name: str, identity: Any, description: str) -> str:
    """Cautious classification based on explicit wording, not guesswork."""
    text = f"{name} {clean_text(identity)} {description}".casefold()

    product_terms = (
        "subsidiary", "division of", "business unit of",
        "product of", "product line", "brand of",
        "department of", "research division", "operating division",
    )
    if any(term in text for term in product_terms):
        return "product_or_division"

    organisation_terms = (
        "nonprofit", "non-profit", "charity", "foundation",
        "government agency", "public body", "university",
        "research institute", "research organisation",
        "research organization", "consortium",
    )
    if any(term in text for term in organisation_terms):
        return "other_or_organisation"

    return "unclassified"


def number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
        if match:
            try:
                return float(match.group())
            except ValueError:
                return None
    return None


def assessment_for(
    name: str,
    analyst: dict,
    verified: dict,
    atlas_record: dict,
) -> tuple[str, str]:
    status = clean_text(verified.get("status")).casefold()

    if status in ("probable", "needs_review"):
        return status, clean_text(verified.get("status_reason"))

    analyst_status = clean_text(
        analyst.get("source_verification_status")
    ).casefold()

    if "review" in analyst_status:
        return "needs_review", "Analyst assessment flags this record for review."

    atlas_status = clean_text(atlas_record.get("assessment_status")).casefold()
    if "review" in atlas_status:
        return "needs_review", "Atlas assessment flags this record for review."

    return "unassessed", "No matching verification status was available."


def make_company(
    record: dict,
    analyst: dict,
    verified: dict,
) -> dict:
    name = clean_text(record.get("name"), 300) or "Unnamed record"
    description = clean_text(record.get("description"), 2000)

    if not description:
        descriptions = record.get("additional_descriptions", [])
        if isinstance(descriptions, list):
            description = next(
                (clean_text(item, 2000) for item in descriptions if clean_text(item)),
                "",
            )

    if not description:
        description = "No description is available in the company atlas."

    evidence_files = [
        item for item in as_list(record.get("evidence_files"))
        if isinstance(item, str) and item.strip()
    ]

    facts = as_list(analyst.get("evidence_based_facts"))
    technology = as_list(analyst.get("technology_and_capabilities"))
    gaps = as_list(analyst.get("evidence_gaps"))

    impact = analyst.get("potential_world_impact")
    if not impact:
        impact = record.get("world_impact", "")

    status, reason = assessment_for(name, analyst, verified, record)
    identity = clean_text(analyst.get("identity_assessment"), 3000)

    urls = clean_urls(
        record.get("source_urls"),
        analyst.get("source_urls"),
        verified.get("source_urls"),
    )

    explicit_sector = (
        record.get("sector")
        or analyst.get("sector")
        or verified.get("sector")
    )
    sector = clean_text(explicit_sector, 120) or "Unclassified"

    return {
        "id": normalise_name(name) or f"record{abs(hash(name))}",
        "name": name,
        "description": description,
        "mentions": max(0, int(number_or_none(record.get("evidence_count")) or 0)),
        "evidence_files_count": len(set(evidence_files)),
        "evidence_files": list(dict.fromkeys(evidence_files)),
        "sector": sector,
        "entity_type": entity_class(name, identity, description),
        "verification_status": status,
        "verification_reason": reason,
        "verification_limits": clean_text(verified.get("verification_limits"), 3000),
        "confidence": number_or_none(analyst.get("overall_confidence")),
        "assessment_status": clean_text(
            analyst.get("source_verification_status")
            or record.get("assessment_status")
            or "Unassessed"
        ),
        "identity_assessment": identity,
        "facts": facts[:20],
        "technology": technology[:20],
        "impact": impact,
        "gaps": gaps[:20],
        "urls": urls,
        "has_dated_evidence": False,
        "recent_mentions": 0,
        "timeline": [],
    }


@lru_cache(maxsize=1)
def load_company_data() -> dict:
    """Build the map payload from the current on-disk intelligence data."""
    atlas = read_json(ATLAS_FILE)
    analyses_file = read_json(ANALYSIS_FILE, {})
    verified_file = read_json(VERIFIED_FILE, {})

    if not isinstance(atlas, dict):
        raise RuntimeError(f"Company atlas is missing or unreadable: {ATLAS_FILE}")

    atlas_records = atlas.get("companies", [])
    if not isinstance(atlas_records, list):
        raise RuntimeError("The company atlas 'companies' field is not a list.")

    analysis_records = analyses_file.get("analyses", []) if isinstance(analyses_file, dict) else []
    verified_records = verified_file.get("profiles", []) if isinstance(verified_file, dict) else []

    analyst_by_name = {}
    for item in analysis_records:
        if isinstance(item, dict):
            key = normalise_name(item.get("company_name") or item.get("source_company_name"))
            if key:
                analyst_by_name[key] = item

    verified_by_name = {}
    for item in verified_records:
        if isinstance(item, dict):
            key = normalise_name(item.get("name"))
            if key:
                verified_by_name[key] = item

    companies = []
    used_ids = set()

    for record in atlas_records:
        if not isinstance(record, dict):
            continue

        name = clean_text(record.get("name"), 300)
        key = normalise_name(name)
        analyst = analyst_by_name.get(key, {})
        verified = verified_by_name.get(key, {})
        company = make_company(record, analyst, verified)

        # Ensure ids are unique even when different names normalise identically.
        base_id = company["id"]
        if base_id in used_ids:
            suffix = 2
            while f"{base_id}-{suffix}" in used_ids:
                suffix += 1
            company["id"] = f"{base_id}-{suffix}"
        used_ids.add(company["id"])

        companies.append(company)

    owners_by_file = defaultdict(list)
    company_by_id = {item["id"]: item for item in companies}

    for company in companies:
        for evidence in company["evidence_files"]:
            path = evidence_path(evidence)
            if path is None:
                continue
            key = str(path)
            if company["id"] not in owners_by_file[key]:
                owners_by_file[key].append(company["id"])

    today = datetime.now(timezone.utc).date()
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    timeline_counts = defaultdict(Counter)
    recent_counts = Counter()
    link_counts = Counter()
    sources_read = 0
    sources_with_publication_dates = 0

    for path_string, owners in owners_by_file.items():
        source_path = Path(path_string)
        source = read_json(source_path)

        if not isinstance(source, dict):
            continue

        sources_read += 1
        published = parse_date(source.get("published"))

        if published is not None:
            sources_with_publication_dates += 1
            day = published.date().isoformat()

            for company_id in owners:
                timeline_counts[company_id][day] += 1
                if published >= recent_cutoff and published.date() <= today:
                    recent_counts[company_id] += 1

        # These links mean only that two atlas records reference the same
        # source file. They do NOT establish a partnership or business tie.
        if 2 <= len(owners) <= 30:
            for left, right in combinations(sorted(owners), 2):
                link_counts[(left, right)] += 1

    for company in companies:
        counts = timeline_counts.get(company["id"], Counter())
        company["timeline"] = [
            {"date": day, "mentions": count}
            for day, count in sorted(counts.items())
        ]
        company["has_dated_evidence"] = bool(company["timeline"])
        company["recent_mentions"] = recent_counts.get(company["id"], 0)

    links = [
        {
            "source": source,
            "target": target,
            "weight": weight,
        }
        for (source, target), weight in sorted(
            link_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        if weight >= 2
    ][:800]

    return {
        "companies": companies,
        "links": links,
        "timeline": [],
        "meta": {
            "company_records": len(companies),
            "analyst_assessments": len(analysis_records),
            "verified_profiles": len(verified_records),
            "atlas_generated_at": clean_text(atlas.get("generated_at")),
            "evidence_sources_read": sources_read,
            "sources_with_publication_dates": sources_with_publication_dates,
            "timeline_note": (
                "Timeline and recent-mention counts use publication dates found "
                "in raw evidence files. Sources without a parseable publication "
                "date are excluded from the timeline. Shared-source links indicate "
                "co-mention in evidence files, not a verified business relationship."
            ),
        },
    }


@company_data_bp.get("/company-data")
def company_data_page():
    return send_from_directory(FRONTEND_DIR, "company-data.html")


@company_data_bp.get("/company-data/api/map")
def company_data_map():
    try:
        return jsonify(load_company_data())
    except Exception as exc:
        return jsonify({
            "error": "Unable to build the Company Data view.",
            "detail": str(exc),
        }), 500


@company_data_bp.get("/company-data/api/company/<company_id>")
def company_data_company(company_id: str):
    try:
        data = load_company_data()
        for company in data["companies"]:
            if company["id"] == company_id:
                # Do not send the complete evidence-file list for one profile.
                profile = dict(company)
                profile.pop("evidence_files", None)
                return jsonify(profile)

        return jsonify({"error": "Company record not found"}), 404
    except Exception as exc:
        return jsonify({
            "error": "Unable to load the company profile.",
            "detail": str(exc),
        }), 500
