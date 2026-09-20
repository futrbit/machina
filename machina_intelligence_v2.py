"""
MACHINA INTELLIGENCE V2

Corpus-backed technology intelligence engine.

This engine deliberately separates:

    ontology
        ↓
    concept measurement
        ↓
    signal measurement
        ↓
    machine-readable intelligence

No trend is invented.
All measurements come from the article corpus.
"""

from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import json
import math
import re

from machina_ontology import CONCEPT_FAMILIES


BASE_DIR = Path(__file__).parent
REWRITTEN_DIR = BASE_DIR / "data" / "rewritten"
OUTPUT_DIR = BASE_DIR / "data" / "intelligence"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# LOAD ARTICLES
# ------------------------------------------------------------

def load_articles():
    files = sorted(REWRITTEN_DIR.glob("*.json"))

    articles = []

    print(f"Found {len(files)} JSON files.")

    for fp in files:
        try:
            data = json.loads(
                fp.read_text(encoding="utf-8")
            )

            if isinstance(data, dict):
                articles.append(data)

        except Exception as exc:
            print(f"Could not read {fp.name}: {exc}")

    return articles


# ------------------------------------------------------------
# DATES
# ------------------------------------------------------------

def parse_date(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
    except Exception:
        return None


# ------------------------------------------------------------
# SOURCE
# ------------------------------------------------------------

def get_source(article):
    url = str(article.get("url", "") or "").strip()

    if "://" not in url:
        return ""

    domain = url.split("://", 1)[1].split("/", 1)[0]
    domain = domain.lower().replace("www.", "")

    return domain


# ------------------------------------------------------------
# TEXT NORMALISATION
# ------------------------------------------------------------

def normalise_text(text):
    text = str(text or "").lower()

    text = text.replace("’", "'")
    text = text.replace("–", "-")
    text = text.replace("—", "-")

    # Preserve useful hyphenated concepts while removing
    # punctuation that makes matching unreliable.
    text = re.sub(
        r"[^a-z0-9\s-]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ------------------------------------------------------------
# ALIAS MATCHING
# ------------------------------------------------------------

def compile_aliases():
    compiled = {}

    for concept_id, concept in CONCEPT_FAMILIES.items():

        aliases = []

        for alias in concept["aliases"]:
            cleaned = normalise_text(alias)

            if cleaned:
                aliases.append(cleaned)

        # Longest aliases first so:
        #
        # large language model
        #
        # is tested before:
        #
        # language model
        #
        aliases = sorted(
            set(aliases),
            key=lambda x: (
                len(x.split()),
                len(x)
            ),
            reverse=True
        )

        compiled[concept_id] = aliases

    return compiled


# ------------------------------------------------------------
# ARTICLE CONCEPT MATCHING
# ------------------------------------------------------------

def concept_matches(text, alias):
    """
    Word-boundary matching.

    Prevents:
        ai
    from matching:
        said
        rain
        train
    etc.
    """

    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(alias)
        + r"(?![a-z0-9])"
    )

    return re.search(pattern, text) is not None


def match_concepts(article, compiled_aliases):
    title = normalise_text(
        article.get("title", "")
    )

    body = normalise_text(
        article.get("text", "")
    )

    full_text = f"{title} {body}"

    matches = {}

    for concept_id, aliases in compiled_aliases.items():

        matched_aliases = []

        for alias in aliases:
            if concept_matches(full_text, alias):
                matched_aliases.append(alias)

        if matched_aliases:
            matches[concept_id] = matched_aliases

    return matches


# ------------------------------------------------------------
# BUILD CONCEPT CORPUS
# ------------------------------------------------------------

def build_concept_corpus(articles):
    compiled_aliases = compile_aliases()

    concepts = {}

    for concept_id, definition in CONCEPT_FAMILIES.items():

        concepts[concept_id] = {
            "id": concept_id,
            "label": definition["label"],
            "aliases": definition["aliases"],
            "article_ids": set(),
            "sources": set(),
            "categories": set(),
            "dates": [],
            "alias_counts": Counter(),
            "recent_article_ids": defaultdict(set),
        }

    article_matches = {}

    print()
    print("MATCHING ARTICLES TO CONCEPTS")
    print("-" * 70)

    for index, article in enumerate(articles, 1):

        article_id = str(
            article.get("id", "")
        ).strip()

        if not article_id:
            continue

        matches = match_concepts(
            article,
            compiled_aliases
        )

        article_matches[article_id] = matches

        source = get_source(article)

        category = str(
            article.get("category", "")
            or ""
        ).strip().lower()

        date = parse_date(
            article.get("published")
            or article.get("fetched")
        )

        for concept_id, aliases in matches.items():

            concept = concepts[concept_id]

            concept["article_ids"].add(
                article_id
            )

            if source:
                concept["sources"].add(source)

            if category:
                concept["categories"].add(category)

            if date:
                concept["dates"].append(date)

            for alias in aliases:
                concept["alias_counts"][alias] += 1

        if index % 100 == 0:
            print(
                f"Processed {index}/{len(articles)}"
            )

    return concepts, article_matches


# ------------------------------------------------------------
# PERIOD HELPERS
# ------------------------------------------------------------

def period_stats(
    article_dates,
    newest,
    days
):
    """
    Calculate activity in:
        recent window
        preceding equally-sized window
    """

    recent_start = newest.timestamp() - (
        days * 86400
    )

    previous_start = newest.timestamp() - (
        days * 2 * 86400
    )

    recent = 0
    previous = 0

    for dt in article_dates:

        timestamp = dt.timestamp()

        if timestamp >= recent_start:
            recent += 1

        elif timestamp >= previous_start:
            previous += 1

    if previous == 0:
        if recent > 0:
            growth = None
        else:
            growth = 0.0
    else:
        growth = (
            (recent - previous)
            / previous
        ) * 100

    return {
        "recent": recent,
        "previous": previous,
        "growth_percent": growth
    }


# ------------------------------------------------------------
# SOURCE DIVERSITY
# ------------------------------------------------------------

def source_diversity_score(source_count):
    """
    Saturating source-diversity measure.

    More independent sources increase confidence,
    but the score does not grow infinitely.
    """

    if source_count <= 0:
        return 0.0

    return round(
        min(
            100.0,
            100.0 * (
                1.0
                - math.exp(
                    -source_count / 5.0
                )
            )
        ),
        2
    )


# ------------------------------------------------------------
# MOMENTUM
# ------------------------------------------------------------

def calculate_momentum(stats):
    """
    Momentum combines:

      - recent growth
      - recent activity
      - source diversity

    This is a measurement of corpus movement,
    not a prediction of the future.
    """

    growth = stats["30_day"]["growth_percent"]

    if growth is None:
        growth_component = 100.0
    else:
        growth_component = max(
            0.0,
            min(
                100.0,
                50.0 + growth / 2.0
            )
        )

    activity_component = min(
        100.0,
        stats["30_day"]["recent"] * 5.0
    )

    diversity_component = source_diversity_score(
        stats["source_count"]
    )

    momentum = (
        growth_component * 0.50
        + activity_component * 0.25
        + diversity_component * 0.25
    )

    return round(
        min(100.0, max(0.0, momentum)),
        2
    )


# ------------------------------------------------------------
# SIGNAL LABEL
# ------------------------------------------------------------

def signal_state(stats):
    growth = stats["30_day"]["growth_percent"]

    recent = stats["30_day"]["recent"]
    previous = stats["30_day"]["previous"]

    if recent == 0:
        return "quiet"

    if previous == 0 and recent >= 3:
        return "emerging"

    if growth is not None:

        if growth >= 100:
            return "accelerating"

        if growth >= 25:
            return "rising"

        if growth <= -50:
            return "falling"

    if recent >= previous:
        return "persistent"

    return "stable"


# ------------------------------------------------------------
# BUILD SIGNALS
# ------------------------------------------------------------

def build_signals(
    articles,
    concepts
):

    dated_articles = []

    article_lookup = {}

    for article in articles:

        article_id = str(
            article.get("id", "")
        ).strip()

        date = parse_date(
            article.get("published")
            or article.get("fetched")
        )

        if not article_id or not date:
            continue

        article_lookup[article_id] = article

        dated_articles.append(
            (article_id, date)
        )

    if not dated_articles:
        return []

    newest = max(
        date
        for _, date in dated_articles
    )

    signals = []

    for concept_id, concept in concepts.items():

        article_ids = concept["article_ids"]

        if not article_ids:
            continue

        dates = []

        sources = set()
        categories = set()

        evidence = []

        for article_id in article_ids:

            article = article_lookup.get(
                article_id
            )

            if not article:
                continue

            date = parse_date(
                article.get("published")
                or article.get("fetched")
            )

            if date:
                dates.append(date)

            source = get_source(article)

            if source:
                sources.add(source)

            category = str(
                article.get("category", "")
                or ""
            ).strip().lower()

            if category:
                categories.add(category)

            evidence.append({
                "id": article_id,
                "title": article.get(
                    "title",
                    ""
                ),
                "date": (
                    date.isoformat()
                    if date
                    else None
                ),
                "source": source,
                "url": article.get(
                    "url",
                    ""
                )
            })

        if not dates:
            continue

        stats = {}

        for days in (7, 14, 30, 90):

            stats[f"{days}_day"] = period_stats(
                dates,
                newest,
                days
            )

        stats["source_count"] = len(sources)
        stats["category_count"] = len(categories)

        momentum = calculate_momentum(
            stats
        )

        state = signal_state(
            stats
        )

        # Most recent evidence first.
        evidence.sort(
            key=lambda x: (
                x["date"] or ""
            ),
            reverse=True
        )

        signal = {
            "id": concept_id,
            "name": concept["label"],
            "state": state,

            "article_count": len(
                article_ids
            ),

            "source_count": len(
                sources
            ),

            "category_count": len(
                categories
            ),

            "sources": sorted(
                sources
            ),

            "categories": sorted(
                categories
            ),

            "aliases_detected": [
                {
                    "alias": alias,
                    "matches": count
                }
                for alias, count
                in concept["alias_counts"].most_common()
            ],

            "activity": stats,

            "momentum": momentum,

            "evidence": evidence[:10]
        }

        signals.append(signal)

    signals.sort(
        key=lambda x: (
            x["momentum"],
            x["article_count"],
            x["source_count"]
        ),
        reverse=True
    )

    for index, signal in enumerate(
        signals,
        1
    ):
        signal["rank"] = index

    return signals, newest


# ------------------------------------------------------------
# SAVE
# ------------------------------------------------------------

def save_json(filename, data):

    path = OUTPUT_DIR / filename

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(
        f"Saved: {path}"
    )


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    print()
    print("=" * 70)
    print("MACHINA INTELLIGENCE V2")
    print("=" * 70)

    articles = load_articles()

    print(
        f"Articles loaded: {len(articles)}"
    )

    if not articles:
        print("No articles found.")
        return

    print()
    print("[1/3] Building concept corpus...")

    concepts, article_matches = (
        build_concept_corpus(
            articles
        )
    )

    print()
    print("[2/3] Measuring signals...")

    result = build_signals(
        articles,
        concepts
    )

    signals, newest = result

    print()
    print("[3/3] Saving intelligence...")

    concept_output = []

    for concept_id, concept in concepts.items():

        if not concept["article_ids"]:
            continue

        concept_output.append({
            "id": concept_id,
            "name": concept["label"],
            "aliases": concept["aliases"],
            "article_count": len(
                concept["article_ids"]
            ),
            "source_count": len(
                concept["sources"]
            ),
            "category_count": len(
                concept["categories"]
            )
        })

    concept_output.sort(
        key=lambda x: (
            x["article_count"],
            x["source_count"]
        ),
        reverse=True
    )

    save_json(
        "concepts_v2.json",
        {
            "generated": datetime.now(
                timezone.utc
            ).isoformat(),

            "corpus": {
                "articles": len(articles),
                "newest": newest.isoformat(),
                "concepts": len(
                    concept_output
                )
            },

            "concepts": concept_output
        }
    )

    save_json(
        "signals_v2.json",
        {
            "generated": datetime.now(
                timezone.utc
            ).isoformat(),

            "corpus": {
                "articles": len(articles),
                "newest": newest.isoformat(),
                "sources": len({
                    get_source(a)
                    for a in articles
                    if get_source(a)
                }),
                "categories": len({
                    str(
                        a.get("category", "")
                    ).strip().lower()
                    for a in articles
                    if a.get("category")
                })
            },

            "signals": signals
        }
    )

    print()
    print("=" * 70)
    print("TOP MACHINA SIGNALS")
    print("=" * 70)

    for signal in signals[:20]:

        growth = signal["activity"][
            "30_day"
        ]["growth_percent"]

        if growth is None:
            growth_text = "NEW"
        else:
            growth_text = (
                f"{growth:+.1f}%"
            )

        print(
            f"{signal['rank']:02}. "
            f"{signal['name']} "
            f"| articles={signal['article_count']} "
            f"| sources={signal['source_count']} "
            f"| 30d={growth_text} "
            f"| momentum={signal['momentum']:.1f} "
            f"| {signal['state']}"
        )

    print()
    print("MACHINA INTELLIGENCE V2 COMPLETE")


if __name__ == "__main__":
    main()
