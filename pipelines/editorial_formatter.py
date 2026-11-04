import json
import re
from pathlib import Path
from datetime import datetime


# ============================================================
# MACHINA DAILY
# EDITORIAL INTELLIGENCE FORMATTER
#
# RAW INTELLIGENCE
#       ↓
# DEVELOPMENT INTELLIGENCE
#       ↓
# CLEAN EDITORIAL STORY CANDIDATES
#
# The journalists NEVER read the raw intelligence directly.
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

INTELLIGENCE_DIR = ROOT / "data" / "intelligence"
OUTPUT_DIR = ROOT / "data" / "editorial"

DEVELOPMENTS_FILE = INTELLIGENCE_DIR / "developments_v3.json"
DEVELOPMENT_INTELLIGENCE_FILE = (
    INTELLIGENCE_DIR / "development_intelligence.json"
)
ARTICLE_ANALYSIS_FILE = (
    INTELLIGENCE_DIR / "article_analysis_v2.json"
)
CONCEPTS_FILE = INTELLIGENCE_DIR / "concepts_v2.json"

OUTPUT_FILE = (
    OUTPUT_DIR / "editorial_story_candidates.json"
)


# ============================================================
# BASIC UTILITIES
# ============================================================

def load_json(path):
    if not path.exists():
        print(f"WARNING: Missing file: {path}")
        return {}

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()

    return str(value)


def truncate(text, length=1200):
    text = clean_text(text)

    if len(text) <= length:
        return text

    return text[:length].rstrip() + "..."


def as_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        return list(value.values())

    return [value]


def normalise_title(title):
    title = clean_text(title).lower()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    title = re.sub(r"\s+", " ", title)

    return title.strip()


def walk_dicts(value):
    """
    Recursively find dictionaries inside arbitrary JSON.
    """

    if isinstance(value, dict):

        yield value

        for child in value.values():
            yield from walk_dicts(child)

    elif isinstance(value, list):

        for child in value:
            yield from walk_dicts(child)


# ============================================================
# ARTICLE ANALYSIS INDEX
# ============================================================

def build_article_index(data):

    index = {}

    for record in walk_dicts(data):

        article_id = (
            record.get("id")
            or record.get("article_id")
            or record.get("articleId")
        )

        if not article_id:
            continue

        useful = {}

        for key in [
            "title",
            "headline",
            "summary",
            "description",
            "analysis",
            "content",
            "text",
            "key_points",
            "claims",
            "evidence",
            "findings",
            "context",
        ]:

            if key in record and record[key]:
                useful[key] = record[key]

        if useful:
            index[str(article_id)] = useful

    return index


# ============================================================
# ARTICLE ANALYSIS EXTRACTION
# ============================================================

def extract_analysis(record):

    if not isinstance(record, dict):
        return ""

    preferred = [
        "summary",
        "analysis",
        "findings",
        "description",
        "context",
        "content",
        "text",
    ]

    pieces = []

    for key in preferred:

        value = record.get(key)

        if isinstance(value, str) and value.strip():

            pieces.append(value)

        elif isinstance(value, list):

            for item in value:

                if isinstance(item, str):
                    pieces.append(item)

    if not pieces:
        return ""

    return truncate(
        " ".join(pieces),
        1400
    )


def extract_claims(record):

    if not isinstance(record, dict):
        return []

    claims = []

    for key in [
        "claims",
        "key_claims",
        "findings",
        "key_points",
    ]:

        value = record.get(key)

        if isinstance(value, list):

            for item in value:

                if isinstance(item, str):

                    text = clean_text(item)

                    if text:
                        claims.append(text)

                elif isinstance(item, dict):

                    text = (
                        item.get("claim")
                        or item.get("text")
                        or item.get("statement")
                    )

                    if text:
                        claims.append(
                            clean_text(text)
                        )

        elif isinstance(value, str):

            if value.strip():
                claims.append(
                    clean_text(value)
                )

    output = []
    seen = set()

    for claim in claims:

        key = claim.lower()

        if key not in seen:

            seen.add(key)
            output.append(claim)

    return output[:10]


# ============================================================
# STORY CLASSIFICATION
# ============================================================

def classify_story(title):

    text = clean_text(title).lower()

    if any(x in text for x in [
        "self-driving",
        "robotaxi",
        "autonomous vehicle",
        "autonomous driving",
        "autopilot",
        "electric aircraft",
        "autonomous trucking",
    ]):

        return "autonomous_mobility"

    if any(x in text for x in [
        "drone",
        "uav",
        "bvlos",
        "unmanned",
        "drone delivery",
        "drone show",
    ]):

        return "drones"

    if any(x in text for x in [
        "ai model",
        "language model",
        "reasoning model",
        "generative ai",
        "gemini",
        "chatgpt",
        "openai",
        "deepmind",
        "veo",
        "ai agent",
        "machine learning",
    ]):

        return "artificial_intelligence"

    if any(x in text for x in [
        "chip",
        "semiconductor",
        "processor",
        "gpu",
        "scale ai",
    ]):

        return "ai_infrastructure"

    if any(x in text for x in [
        "cyber",
        "security",
        "secure boot",
        "hack",
        "scam",
    ]):

        return "cybersecurity"

    if any(x in text for x in [
        "government",
        "regulation",
        "law",
        "rule",
        "fcc",
        "faa",
        "patent",
        "executive order",
    ]):

        return "policy_regulation"

    if any(x in text for x in [
        "investment",
        "invests",
        "billion",
        "million",
        "funding",
        "acquisition",
        "public",
        "spac",
        "contract",
        "partnership",
    ]):

        return "business_technology"

    return "technology"


# ============================================================
# LOW VALUE STORY DETECTION
# ============================================================

JUNK_TERMS = [

    "review",
    "hands-on review",
    "hands on review",
    "discount",
    "off",
    "where to buy",
    "stock live",
    "live build-up",
    "buy info",
    "deals",
    "sale",
    "best tv",
    "number one tv",
    "watch this weekend",
    "shows to watch",
    "weekend",
    "smartwatch",
    "product review",

]


def detect_junk(title):

    text = clean_text(title).lower()

    hits = []

    for term in JUNK_TERMS:

        if term in text:
            hits.append(term)

    return hits


# ============================================================
# EDITORIAL SCORE
# ============================================================

def editorial_score(
    confidence,
    source_count,
    article_count,
    coherence,
    junk_hits,
):

    score = 20

    score += (
        min(float(confidence or 0), 100)
        * 0.35
    )

    score += (
        min(int(source_count or 0), 5)
        * 4
    )

    score += (
        min(int(article_count or 0), 8)
        * 1.5
    )

    score += (
        float(coherence or 0)
        * 10
    )

    score -= len(junk_hits) * 25

    return round(
        max(0, min(100, score)),
        1
    )


# ============================================================
# TOPIC EXTRACTION
# ============================================================

def derive_topics(title, concepts):

    text = clean_text(title).lower()

    matches = []

    for concept in concepts:

        if not isinstance(concept, dict):
            continue

        name = (
            concept.get("name")
            or concept.get("concept")
            or concept.get("title")
        )

        if not name:
            continue

        name = clean_text(name)

        if name.lower() in text:
            matches.append(name)

    return matches[:8]


# ============================================================
# SOURCE ARTICLE EVIDENCE
# ============================================================

def build_source_articles(
    articles,
    article_index,
):

    output = []

    for article in as_list(articles):

        if not isinstance(article, dict):
            continue

        article_id = (
            article.get("id")
            or article.get("article_id")
        )

        title = clean_text(
            article.get("title")
            or article.get("headline")
        )

        source = clean_text(
            article.get("source")
            or article.get("domain")
        )

        published = clean_text(
            article.get("published")
            or article.get("date")
        )

        url = clean_text(
            article.get("url")
            or article.get("link")
        )

        analysis = ""
        claims = []

        if article_id:

            analysis_record = article_index.get(
                str(article_id),
                {}
            )

            analysis = extract_analysis(
                analysis_record
            )

            claims = extract_claims(
                analysis_record
            )

        output.append({

            "article_id": article_id,

            "title": title,

            "source": source,

            "published": published,

            "url": url,

            "analysis": analysis,

            "claims": claims,

        })

    return output


# ============================================================
# UNKNOWN AREAS
# ============================================================

def build_unknowns(
    source_count,
    confidence,
    article_count,
    source_articles,
):

    unknowns = []

    if source_count < 2:

        unknowns.append(
            "Independent source corroboration is limited "
            "in the supplied intelligence."
        )

    if confidence < 80:

        unknowns.append(
            "The intelligence confidence score is below 80, "
            "so some elements require caution."
        )

    if article_count < 3:

        unknowns.append(
            "The development is supported by a relatively "
            "small number of source articles."
        )

    has_analysis = any(
        article.get("analysis")
        for article in source_articles
    )

    if not has_analysis:

        unknowns.append(
            "The supplied intelligence contains source "
            "metadata but limited article-level analysis."
        )

    if not unknowns:

        unknowns.append(
            "Long-term consequences are not established "
            "by the supplied intelligence."
        )

    return unknowns


# ============================================================
# BUILD ONE CANDIDATE
# ============================================================

def build_candidate(
    development,
    development_intel,
    article_index,
    concepts,
):

    development_id = (
        development_intel.get("id")
        or development.get("id")
    )

    title = clean_text(
        development.get("title")
        or development_intel.get("title")
    )

    if not title:
        return None

    article_count = int(
        development_intel.get("article_count")
        or development.get("article_count")
        or 0
    )

    source_count = int(
        development_intel.get("source_count")
        or development.get("source_count")
        or 0
    )

    sources = (
        development_intel.get("sources")
        or development.get("sources")
        or []
    )

    sources = [
        clean_text(x)
        for x in as_list(sources)
        if clean_text(x)
    ]

    confidence = float(
        development_intel.get("confidence")
        or development.get("confidence")
        or 0
    )

    intelligence = (
        development_intel.get(
            "intelligence",
            {}
        )
    )

    coherence = float(
        development_intel.get("coherence")
        or development.get("coherence")
        or intelligence.get(
            "semantic_coherence",
            0
        )
        or 0
    )

    evidence_type = clean_text(
        development_intel.get(
            "evidence_type"
        )
        or development.get(
            "evidence_type"
        )
    )

    first_seen = clean_text(
        development_intel.get(
            "first_seen"
        )
        or development.get(
            "first_seen"
        )
    )

    last_seen = clean_text(
        development_intel.get(
            "last_seen"
        )
        or development.get(
            "last_seen"
        )
    )

    date_span_days = (
        development_intel.get(
            "date_span_days"
        )
        or development.get(
            "date_span_days"
        )
        or 0
    )

    articles = (
        development_intel.get(
            "articles"
        )
        or development.get(
            "articles"
        )
        or []
    )

    source_articles = build_source_articles(
        articles,
        article_index,
    )

    all_claims = []

    for article in source_articles:

        all_claims.extend(
            article.get(
                "claims",
                []
            )
        )

    unique_claims = []
    seen_claims = set()

    for claim in all_claims:

        key = claim.lower()

        if key not in seen_claims:

            seen_claims.add(key)
            unique_claims.append(claim)

    junk_hits = detect_junk(title)

    score = editorial_score(
        confidence,
        source_count,
        article_count,
        coherence,
        junk_hits,
    )

    story_type = classify_story(
        title
    )

    topics = derive_topics(
        title,
        concepts,
    )

    if story_type not in topics:
        topics.insert(
            0,
            story_type
        )

    known_facts = []

    for article in source_articles:

        line = article["title"]

        if article["source"]:
            line += (
                f" [{article['source']}]"
            )

        if article["published"]:
            line += (
                f" ({article['published']})"
            )

        known_facts.append(line)

    why_now = (
        f"This development was first seen on "
        f"{first_seen or 'an unknown date'} "
        f"and most recently appears in the "
        f"intelligence on "
        f"{last_seen or 'an unknown date'}."
    )

    if date_span_days:

        why_now += (
            f" The observed development spans "
            f"{date_span_days} days."
        )

    if source_count:

        why_now += (
            f" It is represented by "
            f"{source_count} source domain(s)."
        )

    unknowns = build_unknowns(
        source_count,
        confidence,
        article_count,
        source_articles,
    )

    status = "candidate"

    if score < 40:
        status = "weak"

    if junk_hits:
        status = "filtered"

    return {

        "story_id": (
            f"story_"
            f"{str(development_id).replace('development_', '')}"
        ),

        "development_id": development_id,

        "headline": title,

        "what_changed": title,

        "why_now": why_now,

        "story_type": story_type,

        "topics": topics,

        "evidence_strength": (
            evidence_type
            or (
                "multi-source"
                if source_count >= 2
                else "single-source"
            )
        ),

        "confidence": confidence,

        "editorial_score": score,

        "article_count": article_count,

        "source_count": source_count,

        "sources": sources,

        "first_seen": first_seen,

        "last_seen": last_seen,

        "date_span_days": date_span_days,

        "known_facts": known_facts,

        "claims": unique_claims[:15],

        "unknowns": unknowns,

        "source_articles": source_articles,

        "filter_hits": junk_hits,

        "editorial_status": status,

    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "MACHINA DAILY — "
        "EDITORIAL INTELLIGENCE FORMATTER"
    )
    print("=" * 70)
    print()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    developments_data = load_json(
        DEVELOPMENTS_FILE
    )

    development_intel_data = load_json(
        DEVELOPMENT_INTELLIGENCE_FILE
    )

    article_analysis_data = load_json(
        ARTICLE_ANALYSIS_FILE
    )

    concepts_data = load_json(
        CONCEPTS_FILE
    )

    developments = as_list(
        developments_data.get(
            "developments",
            []
        )
    )

    development_intelligence = as_list(
        development_intel_data.get(
            "developments",
            []
        )
    )

    concepts = as_list(
        concepts_data.get(
            "concepts",
            []
        )
    )

    print(
        f"Developments loaded: "
        f"{len(developments)}"
    )

    print(
        f"Development intelligence: "
        f"{len(development_intelligence)}"
    )

    print(
        f"Concepts loaded: "
        f"{len(concepts)}"
    )

    article_index = build_article_index(
        article_analysis_data
    )

    print(
        f"Article analysis records: "
        f"{len(article_index)}"
    )

    print()

    # --------------------------------------------------------
    # DEVELOPMENT INDEX
    # --------------------------------------------------------

    development_map = {}

    for development in developments:

        if not isinstance(
            development,
            dict
        ):
            continue

        development_id = (
            development.get("id")
        )

        if development_id:

            development_map[
                str(development_id)
            ] = development

        title_key = normalise_title(
            development.get(
                "title",
                ""
            )
        )

        if title_key:

            development_map[
                title_key
            ] = development

    # --------------------------------------------------------
    # BUILD CANDIDATES
    # --------------------------------------------------------

    candidates = []

    for intel in development_intelligence:

        if not isinstance(
            intel,
            dict
        ):
            continue

        development_id = intel.get(
            "id"
        )

        development = (
            development_map.get(
                str(development_id),
                {}
            )
        )

        if not development:

            title_key = normalise_title(
                intel.get(
                    "title",
                    ""
                )
            )

            development = (
                development_map.get(
                    title_key,
                    {}
                )
            )

        candidate = build_candidate(
            development,
            intel,
            article_index,
            concepts,
        )

        if candidate:
            candidates.append(
                candidate
            )

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    candidates.sort(
        key=lambda x:
        x["editorial_score"],
        reverse=True,
    )

    active = [
        x for x in candidates
        if x["editorial_status"]
        == "candidate"
    ]

    filtered = [
        x for x in candidates
        if x["editorial_status"]
        == "filtered"
    ]

    weak = [
        x for x in candidates
        if x["editorial_status"]
        == "weak"
    ]

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    output = {

        "generated_at":
            datetime.utcnow().isoformat()
            + "Z",

        "pipeline":
            "editorial_formatter",

        "version":
            "1.0",

        "purpose": (
            "Clean editorial intelligence layer "
            "between the Machina Daily research "
            "system and journalist agents."
        ),

        "stats": {

            "developments_processed":
                len(candidates),

            "editorial_candidates":
                len(active),

            "filtered":
                len(filtered),

            "weak":
                len(weak),

        },

        "story_candidates":
            active,

        "filtered_stories":
            filtered,

        "weak_stories":
            weak,

    }

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("EDITORIAL FORMAT COMPLETE")
    print("=" * 70)
    print()

    print(
        f"Total processed:      "
        f"{len(candidates)}"
    )

    print(
        f"Editorial candidates: "
        f"{len(active)}"
    )

    print(
        f"Filtered:              "
        f"{len(filtered)}"
    )

    print(
        f"Weak:                  "
        f"{len(weak)}"
    )

    print()
    print("TOP EDITORIAL CANDIDATES")
    print("-" * 70)

    for number, candidate in enumerate(
        active[:15],
        start=1
    ):

        print(
            f"{number:02d}. "
            f"{candidate['headline']}"
        )

        print(
            f"    Score: "
            f"{candidate['editorial_score']} | "
            f"Confidence: "
            f"{candidate['confidence']} | "
            f"Sources: "
            f"{candidate['source_count']}"
        )

    print()
    print("OUTPUT:")
    print(OUTPUT_FILE)
    print()


if __name__ == "__main__":
    main()