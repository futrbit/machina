import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from itertools import combinations
from machina_ontology import CONCEPT_FAMILIES


BASE_DIR = Path(__file__).parent
REWRITTEN_DIR = BASE_DIR / "data" / "rewritten"
OUTPUT_DIR = BASE_DIR / "data" / "intelligence"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_articles():
    articles = []

    for fp in sorted(REWRITTEN_DIR.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            articles.append(data)
        except Exception:
            continue

    return articles


def normalise_text(value):
    if not value:
        return ""

    value = str(value).lower()

    value = re.sub(r"\s+", " ", value)

    return value


def compile_aliases():
    compiled = {}

    for concept_id, concept in CONCEPT_FAMILIES.items():
        aliases = concept.get("aliases", [])

        compiled[concept_id] = []

        for alias in aliases:
            alias = normalise_text(alias).strip()

            if not alias:
                continue

            escaped = re.escape(alias)

            # Word boundaries prevent things such as "ai"
            # matching inside unrelated words.
            pattern = re.compile(
                rf"(?<!\w){escaped}(?!\w)",
                re.IGNORECASE
            )

            compiled[concept_id].append(
                (alias, pattern)
            )

    return compiled


def article_text(article):
    parts = [
        article.get("title", ""),
        article.get("text", ""),
        article.get("rewritten", "")
    ]

    return normalise_text(" ".join(parts))


def match_article_concepts(text, compiled):
    matched = set()

    for concept_id, aliases in compiled.items():

        for alias, pattern in aliases:

            if pattern.search(text):
                matched.add(concept_id)
                break

    return matched


def build_relationships(articles):

    compiled = compile_aliases()

    pair_article_ids = defaultdict(list)
    concept_article_ids = defaultdict(list)
    concept_counts = Counter()

    article_concepts = {}

    for article in articles:

        article_id = str(
            article.get("id")
            or article.get("article_id")
            or ""
        )

        if not article_id:
            continue

        text = article_text(article)

        if not text:
            continue

        concepts = match_article_concepts(
            text,
            compiled
        )

        if not concepts:
            continue

        article_concepts[article_id] = concepts

        for concept_id in concepts:
            concept_counts[concept_id] += 1
            concept_article_ids[concept_id].append(
                article_id
            )

        # Only create each pair once per article.
        for left, right in combinations(
            sorted(concepts),
            2
        ):
            pair_article_ids[(left, right)].append(
                article_id
            )

    relationships = []

    for (left, right), article_ids in pair_article_ids.items():

        shared_articles = len(article_ids)

        left_total = concept_counts[left]
        right_total = concept_counts[right]

        if left_total == 0 or right_total == 0:
            continue

        # Jaccard-style overlap:
        # shared / total unique articles containing either concept.
        union_count = (
            left_total
            + right_total
            - shared_articles
        )

        overlap = (
            shared_articles / union_count
            if union_count
            else 0.0
        )

        # A simple co-occurrence strength.
        # This rewards repeated evidence while preventing
        # enormous concepts from automatically dominating.
        strength = (
            shared_articles
            / max(1, min(left_total, right_total))
        ) * 100

        relationships.append({
            "from": left,
            "to": right,
            "shared_article_count": shared_articles,
            "from_article_count": left_total,
            "to_article_count": right_total,
            "overlap_percent": round(overlap * 100, 2),
            "strength": round(strength, 2),
            "article_ids": article_ids[:25]
        })

    relationships.sort(
        key=lambda x: (
            x["shared_article_count"],
            x["overlap_percent"],
            x["strength"]
        ),
        reverse=True
    )

    return relationships, article_concepts


def build_concept_network(relationships):

    network = {}

    for concept_id in CONCEPT_FAMILIES:

        connections = []

        for relationship in relationships:

            if relationship["from"] == concept_id:
                other = relationship["to"]

            elif relationship["to"] == concept_id:
                other = relationship["from"]

            else:
                continue

            connections.append({
                "concept": other,
                "shared_article_count":
                    relationship["shared_article_count"],
                "overlap_percent":
                    relationship["overlap_percent"],
                "strength":
                    relationship["strength"]
            })

        connections.sort(
            key=lambda x: (
                x["shared_article_count"],
                x["overlap_percent"]
            ),
            reverse=True
        )

        network[concept_id] = connections[:10]

    return network


def main():

    print("=" * 70)
    print("MACHINA RELATIONSHIP ENGINE V2")
    print("=" * 70)

    articles = load_articles()

    print(f"Articles loaded: {len(articles)}")

    relationships, article_concepts = build_relationships(
        articles
    )

    network = build_concept_network(
        relationships
    )

    output = {
        "version": 2,
        "article_count": len(articles),
        "relationship_count": len(relationships),
        "relationships": relationships,
        "network": network
    }

    output_file = OUTPUT_DIR / "relationships_v2.json"

    output_file.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print()
    print("TOP CONCEPT RELATIONSHIPS")
    print("=" * 70)

    for index, relationship in enumerate(
        relationships[:25],
        start=1
    ):

        left = CONCEPT_FAMILIES[
            relationship["from"]
        ]["label"]

        right = CONCEPT_FAMILIES[
            relationship["to"]
        ]["label"]

        print(
            f"{index:02d}. "
            f"{left} <-> {right} | "
            f"shared={relationship['shared_article_count']} | "
            f"overlap={relationship['overlap_percent']}%"
        )

    print()
    print(
        f"Relationships saved: {output_file}"
    )

    print()
    print("MACHINA RELATIONSHIP ENGINE V2 COMPLETE")


if __name__ == "__main__":
    main()

