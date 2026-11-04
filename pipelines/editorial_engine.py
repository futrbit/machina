import json
import re
from pathlib import Path
from collections import Counter


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "deep_research"

BRIEFS_FILE = DATA_DIR / "machina_intelligence_briefs.json"
EVIDENCE_FILE = DATA_DIR / "evidence_adjudicated.json"
ENTITY_FILE = DATA_DIR / "machina_entity_intelligence.json"
REPORT_FILE = DATA_DIR / "investigative_report.json"

OUTPUT_FILE = DATA_DIR / "editorial_queue.json"


# ============================================================
# EDITORIAL AGENTS
# ============================================================

EDITORIAL_AGENTS = {
    "FUTURIST": {
        "role": "Trajectory and future capability",
        "focus": [
            "future capability",
            "trajectory",
            "second-order effects",
            "what happens next",
            "technical evolution",
            "industry transformation",
        ],
    },
    "AUDITOR": {
        "role": "Evidence, verification and uncertainty",
        "focus": [
            "demonstrated facts",
            "source quality",
            "claims versus evidence",
            "contradictions",
            "limitations",
            "uncertainty",
        ],
    },
    "STRATEGIST": {
        "role": "Market, policy and strategic consequences",
        "focus": [
            "competition",
            "capital",
            "procurement",
            "government",
            "regulation",
            "strategic consequences",
        ],
    },
}


# ============================================================
# KNOWN COMPANIES
# ============================================================

KNOWN_COMPANIES = [
    "OpenAI",
    "Anthropic",
    "Google",
    "Google DeepMind",
    "Microsoft",
    "Meta",
    "xAI",
    "Mistral",
    "DeepSeek",
    "NVIDIA",
    "AMD",
    "Intel",
    "TSMC",
    "ASML",
    "Apple",
    "Amazon",
    "Tesla",
    "Anduril",
    "Palantir",
    "Shield AI",
    "Skydio",
    "DJI",
    "Figure AI",
    "Agility Robotics",
    "1X",
    "Apptronik",
    "Boston Dynamics",
    "Physical Intelligence",
    "Waymo",
    "Aurora",
    "Zoox",
    "Wayve",
    "SpaceX",
    "Rocket Lab",
    "ICEYE",
    "True Anomaly",
    "CrowdStrike",
    "Palo Alto Networks",
    "Wiz",
    "Lockheed Martin",
    "Northrop Grumman",
    "BAE Systems",
    "Rheinmetall",
    "Thales",
    "Saab",
    "DroneShield",
    "Dedrone",
    "Epirus",
    "Quantum Systems",
    "TEKEVER",
    "Zipline",
    "Uber",
]


# ============================================================
# KNOWN ORGANISATIONS
# ============================================================

KNOWN_ORGANISATIONS = [
    "DARPA",
    "DIU",
    "US Department of Defense",
    "Department of Defense",
    "UK Ministry of Defence",
    "Ministry of Defence",
    "Dstl",
    "DASA",
    "NATO",
    "NATO DIANA",
    "SBIR",
]


# ============================================================
# EDITORIAL THEMES
# ============================================================

THEME_KEYWORDS = {
    "AI / AGENTS": [
        "artificial intelligence",
        " ai ",
        "llm",
        "large language model",
        "language model",
        "agent",
        "agents",
        "foundation model",
        "generative ai",
        "machine learning",
        "reasoning model",
        "coding agent",
    ],

    "DEFENCE / AUTONOMY": [
        "defence",
        "defense",
        "military",
        "counter-uas",
        "counter uas",
        "drone",
        "uav",
        "missile",
        "weapon",
        "weapons",
        "air defence",
        "air defense",
        "autonomous weapon",
        "munition",
    ],

    "ROBOTICS": [
        "robot",
        "robotics",
        "humanoid",
        "dexterous",
        "embodied",
        "manipulation",
        "actuator",
        "locomotion",
        "warehouse robot",
    ],

    "CHIPS / COMPUTE": [
        "gpu",
        "chip",
        "chips",
        "semiconductor",
        "compute",
        "datacenter",
        "data center",
        "accelerator",
        "inference hardware",
        "training hardware",
        "tsmc",
        "asml",
    ],

    "SPACE / SATELLITES": [
        "space",
        "satellite",
        "satellites",
        "orbit",
        "orbital",
        "rocket",
        "launch",
        "earth observation",
        "synthetic aperture radar",
    ],

    "CYBER": [
        "cyber",
        "cybersecurity",
        "cyber security",
        "malware",
        "ransomware",
        "security platform",
        "identity security",
        "zero trust",
    ],

    "POLICY / GOVERNMENT": [
        "government",
        "ministry",
        "department of defense",
        "department of defence",
        "ministry of defence",
        "regulation",
        "regulatory",
        "policy",
        "nato",
        "procurement",
        "contract",
        "export control",
        "sanctions",
    ],

    "CAPITAL / MARKETS": [
        "funding",
        "investment",
        "investor",
        "valuation",
        "acquisition",
        "acquires",
        "revenue",
        "contract",
        "customers",
        "pricing",
        "market",
        "capital",
        "venture",
    ],

    "RESEARCH": [
        "arxiv",
        "research paper",
        "paper",
        "study",
        "benchmark",
        "dataset",
        "algorithm",
        "architecture",
    ],
}


# ============================================================
# HELPERS
# ============================================================

def load_json(path, default):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def normalise_text(value):
    if value is None:
        return ""

    if isinstance(value, list):
        return " ".join(str(x) for x in value)

    if isinstance(value, dict):
        return " ".join(str(x) for x in value.values())

    return str(value)


def clean_text(value):
    text = normalise_text(value)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_title(record):
    return clean_text(
        record.get("title")
        or record.get("headline")
        or ""
    )


def get_summary(record):
    return clean_text(
        record.get("summary")
        or record.get("description")
        or record.get("abstract")
        or ""
    )


def get_source(record):
    return clean_text(
        record.get("source")
        or record.get("source_name")
        or ""
    )


def get_source_type(record):
    return clean_text(
        record.get("source_type")
        or ""
    )


def get_url(record):
    return (
        record.get("url")
        or record.get("source_url")
        or ""
    )


def get_date(record):
    return (
        record.get("date")
        or record.get("published")
        or ""
    )


def get_record_id(record):
    return (
        record.get("record_id")
        or record.get("id")
    )


def entity_mentions(text, entities):
    text_lower = text.lower()
    found = []

    for entity in entities:
        pattern = (
            r"(?<![A-Za-z0-9])"
            + re.escape(entity.lower())
            + r"(?![A-Za-z0-9])"
        )

        if re.search(pattern, text_lower):
            found.append(entity)

    return found


# ============================================================
# THEME DETECTION
# ============================================================

def detect_themes(record):
    title = get_title(record)
    summary = get_summary(record)
    source = get_source(record)
    source_type = get_source_type(record)

    text = (
        " "
        + title.lower()
        + " "
        + summary.lower()
        + " "
        + source.lower()
        + " "
        + source_type.lower()
        + " "
    )

    scores = {}

    for theme, keywords in THEME_KEYWORDS.items():
        score = 0

        for keyword in keywords:
            keyword = keyword.lower()

            if keyword in text:
                if keyword in title.lower():
                    score += 4
                elif keyword in source.lower():
                    score += 3
                else:
                    score += 1

        if score:
            scores[theme] = score

    if not scores:
        return ["GENERAL"]

    ordered = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    return [theme for theme, score in ordered[:3]]


# ============================================================
# ENTITY DETECTION
# ============================================================

def detect_entities(record):
    title = get_title(record)
    summary = get_summary(record)
    source = get_source(record)

    text = " ".join([
        title,
        summary,
        source,
    ])

    companies = entity_mentions(
        text,
        KNOWN_COMPANIES,
    )

    organisations = entity_mentions(
        text,
        KNOWN_ORGANISATIONS,
    )

    return companies, organisations


# ============================================================
# SPECIALIST ROUTING
# ============================================================

def route_specialists(record, themes):
    title = get_title(record)
    summary = get_summary(record)

    text = (
        title
        + " "
        + summary
        + " "
        + " ".join(themes)
    ).lower()

    alpha_terms = [
        "ai",
        "agent",
        "model",
        "robot",
        "robotics",
        "drone",
        "autonomy",
        "chip",
        "gpu",
        "compute",
        "satellite",
        "radar",
        "lidar",
        "sensor",
        "rocket",
        "semiconductor",
        "software",
        "hardware",
    ]

    beta_terms = [
        "funding",
        "investment",
        "investor",
        "valuation",
        "revenue",
        "customer",
        "customers",
        "contract",
        "procurement",
        "acquisition",
        "market",
        "pricing",
        "capital",
        "production",
        "manufacturing",
        "partnership",
    ]

    gamma_terms = [
        "government",
        "defence",
        "defense",
        "military",
        "nato",
        "regulation",
        "policy",
        "sanctions",
        "export",
        "ministry",
        "department",
        "procurement",
        "national security",
        "strategic",
    ]

    specialists = []

    if any(term in text for term in alpha_terms):
        specialists.append("ALPHA")

    if any(term in text for term in beta_terms):
        specialists.append("BETA")

    if any(term in text for term in gamma_terms):
        specialists.append("GAMMA")

    if not specialists:
        specialists.append("general")

    return specialists


# ============================================================
# CANDIDATE SCORING
# ============================================================

def score_candidate(record, themes, companies):
    title = get_title(record)
    summary = get_summary(record)
    source_type = get_source_type(record).lower()

    text = (
        title
        + " "
        + summary
    ).lower()

    score = 0

    development_terms = [
        "launch",
        "launched",
        "announced",
        "contract",
        "awarded",
        "wins",
        "won",
        "funding",
        "partners",
        "partnership",
        "production",
        "deployment",
        "deploy",
        "acquisition",
        "breakthrough",
        "new model",
        "new system",
        "demonstrates",
        "delivers",
        "introduces",
        "unveils",
    ]

    for term in development_terms:
        if term in text:
            score += 1

    if source_type == "company":
        score += 2
    elif source_type == "government":
        score += 3
    elif source_type == "research":
        score += 2
    elif source_type == "podcast":
        score += 2

    if re.search(
        r"\b\d+(\.\d+)?\s?(million|billion|£|\$|€|%)\b",
        text,
    ):
        score += 2

    if len(summary) > 400:
        score += 2
    elif len(summary) > 200:
        score += 1

    if len(companies) >= 2:
        score += 2

    if len(themes) >= 2:
        score += 1

    if len(title) < 20:
        score -= 2

    if len(summary) < 80:
        score -= 1

    return score


# ============================================================
# EVIDENCE STATUS
# ============================================================

def evidence_status(record_id, evidence_data):
    if not evidence_data:
        return "UNVERIFIED"

    possible = []

    if isinstance(evidence_data, list):
        possible = evidence_data

    elif isinstance(evidence_data, dict):
        for key in [
            "records",
            "results",
            "assessments",
            "items",
        ]:
            value = evidence_data.get(key)

            if isinstance(value, list):
                possible.extend(value)

    statuses = []

    for item in possible:
        if not isinstance(item, dict):
            continue

        item_id = (
            item.get("record_id")
            or item.get("id")
        )

        if str(item_id) != str(record_id):
            continue

        status = (
            item.get("status")
            or item.get("evidence_status")
        )

        if status:
            statuses.append(
                str(status).upper()
            )

    if not statuses:
        return "UNVERIFIED"

    priority = [
        "CONTRADICTED",
        "PARTIALLY_SUPPORTED",
        "SUPPORTED",
        "UNKNOWN",
        "UNVERIFIED",
    ]

    for status in priority:
        if status in statuses:
            return status

    return statuses[0]


# ============================================================
# BUILD EDITORIAL CANDIDATES
# ============================================================

def build_candidates(
    briefs,
    evidence_data,
    entity_data,
):
    candidates = []

    for record in briefs:
        if not isinstance(record, dict):
            continue

        record_id = get_record_id(record)

        if not record_id:
            continue

        title = get_title(record)

        if not title:
            continue

        summary = get_summary(record)

        companies, organisations = detect_entities(
            record
        )

        themes = detect_themes(record)

        specialists = route_specialists(
            record,
            themes,
        )

        score = score_candidate(
            record,
            themes,
            companies,
        )

        status = evidence_status(
            record_id,
            evidence_data,
        )

        candidate = {
            "id": record_id,
            "title": title,
            "summary": summary,
            "url": get_url(record),
            "source_name": get_source(record),
            "source_type": get_source_type(record),
            "published": get_date(record),

            "sectors": record.get(
                "sectors",
                [],
            ),

            "companies": companies,
            "organisations": organisations,

            "themes": themes,
            "specialists": specialists,

            "evidence_status": status,

            "editorial_score": score,
        }

        candidates.append(candidate)

    candidates.sort(
        key=lambda item: item["editorial_score"],
        reverse=True,
    )

    return candidates


# ============================================================
# DIVERSITY SELECTION
# ============================================================

def diversity_bonus(
    candidate,
    selected_themes,
    selected_companies,
):
    bonus = 0

    themes = candidate["themes"]
    companies = candidate["companies"]

    new_themes = [
        theme
        for theme in themes
        if selected_themes[theme] == 0
    ]

    bonus += min(
        len(new_themes) * 4,
        8,
    )

    new_companies = [
        company
        for company in companies
        if selected_companies[company] == 0
    ]

    bonus += min(
        len(new_companies) * 2,
        4,
    )

    return bonus


def selection_penalty(
    candidate,
    selected_companies,
    selected_themes,
):
    penalty = 0

    companies = candidate["companies"]
    themes = candidate["themes"]

    repeated_company_count = sum(
        1
        for company in companies
        if selected_companies[company] >= 1
    )

    if repeated_company_count:
        penalty += (
            repeated_company_count * 5
        )

    repeated_theme_count = sum(
        1
        for theme in themes
        if selected_themes[theme] >= 2
    )

    if repeated_theme_count:
        penalty += (
            repeated_theme_count * 2
        )

    return penalty


def select_diverse_investigations(
    candidates,
    target_count=5,
):
    if not candidates:
        return []

    remaining = list(candidates)

    selected = []

    selected_companies = Counter()
    selected_themes = Counter()
    selected_sources = Counter()

    while remaining and len(selected) < target_count:

        best = None
        best_value = None

        for candidate in remaining:

            base = candidate[
                "editorial_score"
            ]

            diversity = diversity_bonus(
                candidate,
                selected_themes,
                selected_companies,
            )

            penalty = selection_penalty(
                candidate,
                selected_companies,
                selected_themes,
            )

            source_name = candidate[
                "source_name"
            ]

            source_penalty = 0

            if (
                source_name
                and selected_sources[source_name] >= 2
            ):
                source_penalty = 3

            value = (
                base * 3
                + diversity
                - penalty
                - source_penalty
            )

            if len(selected) >= 3:

                unique_theme_count = len([
                    theme
                    for theme in candidate["themes"]
                    if selected_themes[theme] == 0
                ])

                if unique_theme_count:
                    value += 5

            if (
                best_value is None
                or value > best_value
            ):
                best_value = value
                best = candidate

        if best is None:
            break

        selected.append(best)
        remaining.remove(best)

        for company in best["companies"]:
            selected_companies[company] += 1

        for theme in best["themes"]:
            selected_themes[theme] += 1

        if best["source_name"]:
            selected_sources[
                best["source_name"]
            ] += 1

    return selected


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("MACHINA DAILY EDITORIAL ENGINE")
    print("=" * 70)

    briefs_data = load_json(
        BRIEFS_FILE,
        {},
    )

    evidence_data = load_json(
        EVIDENCE_FILE,
        {},
    )

    entity_data = load_json(
        ENTITY_FILE,
        {},
    )

    report_data = load_json(
        REPORT_FILE,
        {},
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # machina_intelligence_briefs.json contains:
    #
    # {
    #     "generated_at": "...",
    #     "architecture": {...},
    #     "statistics": {...},
    #     "briefs": [...]
    # }
    #
    # --------------------------------------------------------

    if isinstance(
        briefs_data,
        dict,
    ):
        briefs = briefs_data.get(
            "briefs",
            [],
        )
    else:
        briefs = briefs_data

    print()
    print(
        f"Research briefs loaded: {len(briefs)}"
    )

    candidates = build_candidates(
        briefs,
        evidence_data,
        entity_data,
    )

    print(
        f"Editorial candidates:   {len(candidates)}"
    )

    # --------------------------------------------------------
    # Preserve the broader candidate queue.
    # --------------------------------------------------------

    editorial_queue = candidates[:25]

    # --------------------------------------------------------
    # Select a small, diverse editorial board.
    # --------------------------------------------------------

    selected = select_diverse_investigations(
        candidates,
        target_count=5,
    )

    output = {
        "generated_by": "machina editorial engine",

        "openai_api_calls": 0,

        "editorial_agents": EDITORIAL_AGENTS,

        "research_briefs_scanned": len(
            briefs
        ),

        "editorial_candidates": len(
            candidates
        ),

        "editorial_queue_size": len(
            editorial_queue
        ),

        "editorial_queue": editorial_queue,

        "selected_investigations": selected,

        "selection_policy": {
            "target_investigations": 5,

            "purpose": (
                "Create a diverse editorial board "
                "before API-powered synthesis."
            ),

            "max_company_domination": 1,

            "diversity_dimensions": [
                "theme",
                "company",
                "source",
                "specialist",
            ],
        },
    }

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # ========================================================
    # REPORT
    # ========================================================

    print()
    print("=" * 70)
    print("TOP EDITORIAL CANDIDATES")
    print("=" * 70)

    for index, item in enumerate(
        editorial_queue[:15],
        1,
    ):

        companies = (
            ", ".join(
                item["companies"]
            )
            or "None detected"
        )

        specialists = ", ".join(
            item["specialists"]
        )

        print()
        print(
            f"{index:2}. "
            f"[{item['editorial_score']:2}] "
            f"{item['title']}"
        )

        print(
            f"    Companies: {companies}"
        )

        print(
            f"    Source: {item['source_name']}"
        )

        print(
            f"    Specialists: {specialists}"
        )

    print()
    print("=" * 70)
    print("EDITORIAL SELECTION")
    print("=" * 70)

    if not selected:
        print()
        print(
            "WARNING: No investigations "
            "were selected."
        )

    for index, item in enumerate(
        selected,
        1,
    ):

        companies = (
            ", ".join(
                item["companies"]
            )
            or "None detected"
        )

        themes = (
            ", ".join(
                item["themes"]
            )
            or "GENERAL"
        )

        specialists = ", ".join(
            item["specialists"]
        )

        print()
        print(
            f"{index}. "
            f"[{item['editorial_score']:2}] "
            f"{item['title']}"
        )

        print(
            f"   Themes:      {themes}"
        )

        print(
            f"   Companies:   {companies}"
        )

        print(
            f"   Specialists: {specialists}"
        )

        print(
            f"   Source:      {item['source_name']}"
        )

        print(
            f"   Evidence:    "
            f"{item['evidence_status']}"
        )

    # ========================================================
    # DIVERSITY CHECK
    # ========================================================

    print()
    print("=" * 70)
    print("DIVERSITY CHECK")
    print("=" * 70)

    theme_counts = Counter()
    company_counts = Counter()
    source_counts = Counter()

    for item in selected:

        for theme in item["themes"]:
            theme_counts[theme] += 1

        for company in item["companies"]:
            company_counts[company] += 1

        if item["source_name"]:
            source_counts[
                item["source_name"]
            ] += 1

    print()
    print("Themes:")

    for theme, count in (
        theme_counts.most_common()
    ):
        print(
            f"  {theme}: {count}"
        )

    print()
    print("Companies:")

    for company, count in (
        company_counts.most_common()
    ):
        print(
            f"  {company}: {count}"
        )

    print()
    print("Sources:")

    for source, count in (
        source_counts.most_common()
    ):
        print(
            f"  {source}: {count}"
        )

    # ========================================================
    # AGENTS
    # ========================================================

    print()
    print("=" * 70)
    print("EDITORIAL AGENTS")
    print("=" * 70)

    for name, config in (
        EDITORIAL_AGENTS.items()
    ):
        print(
            f"  {name}: "
            f"{config['role']}"
        )

    print()
    print("OpenAI API calls: 0")

    print()
    print("Saved to:")
    print(OUTPUT_FILE)

    print()
    print("=" * 70)
    print("EDITORIAL ENGINE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()