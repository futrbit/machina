from pathlib import Path
from datetime import datetime
import json
from collections import defaultdict

BASE = Path(__file__).parent
INTEL_DIR = BASE / "data" / "intelligence"

SIGNALS_FILE = INTEL_DIR / "signals_v2.json"
DEVELOPMENTS_FILE = INTEL_DIR / "development_intelligence.json"
OUTPUT_FILE = INTEL_DIR / "article_analysis_v2.json"


def load_json(path):

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def add_concept(mapping, article_id, concept):

    if not article_id:
        return

    mapping[article_id].append(concept)


def main():

    print("Loading intelligence...")

    signals_data = load_json(
        SIGNALS_FILE
    )

    developments_data = load_json(
        DEVELOPMENTS_FILE
    )

    # --------------------------------------------------------
    # ARTICLE -> CONCEPTS / SIGNALS
    # --------------------------------------------------------

    article_concepts = defaultdict(list)

    signals = (
        signals_data.get("signals")
        or signals_data.get("concepts")
        or []
    )

    print(
        f"Signals loaded: {len(signals)}"
    )

    for signal in signals:

        concept_id = signal.get(
            "id",
            ""
        )

        concept_name = (
            signal.get("name")
            or signal.get("label")
            or concept_id
        )

        state = signal.get(
            "state",
            "unknown"
        )

        momentum = signal.get(
            "momentum"
        )

        activity = signal.get(
            "activity",
            {}
        )

        evidence = signal.get(
            "evidence",
            []
        )

        for item in evidence:

            article_id = (
                item.get("article_id")
                or item.get("id")
            )

            if not article_id:
                continue

            article_concepts[
                article_id
            ].append({
                "id": concept_id,
                "name": concept_name,
                "state": state,
                "momentum": momentum,
                "activity": activity,
            })

    # --------------------------------------------------------
    # ARTICLE -> DEVELOPMENTS
    # --------------------------------------------------------

    article_developments = defaultdict(list)

    developments = (
        developments_data.get(
            "developments",
            []
        )
    )

    print(
        f"Developments loaded: "
        f"{len(developments)}"
    )

    for development in developments:

        development_id = development.get(
            "id"
        )

        development_title = development.get(
            "title",
            ""
        )

        for article in development.get(
            "articles",
            []
        ):

            article_id = article.get(
                "id"
            )

            if not article_id:
                continue

            article_developments[
                article_id
            ].append({
                "id": development_id,
                "title": development_title,
                "article_count":
                    development.get(
                        "article_count",
                        0
                    ),
                "source_count":
                    development.get(
                        "source_count",
                        0
                    ),
                "sources":
                    development.get(
                        "sources",
                        []
                    ),
                "first_seen":
                    development.get(
                        "first_seen"
                    ),
                "last_seen":
                    development.get(
                        "last_seen"
                    ),
                "date_span_days":
                    development.get(
                        "date_span_days",
                        0
                    ),
                "coherence":
                    development.get(
                        "coherence",
                        0
                    ),
                "evidence_type":
                    development.get(
                        "evidence_type"
                    ),
                "state":
                    development.get(
                        "state"
                    ),
            })

    # --------------------------------------------------------
    # BUILD ARTICLE MAP
    # --------------------------------------------------------

    article_ids = (
        set(article_concepts)
        |
        set(article_developments)
    )

    results = {}

    for article_id in article_ids:

        concepts = article_concepts.get(
            article_id,
            []
        )

        developments_for_article = (
            article_developments.get(
                article_id,
                []
            )
        )

        # Remove duplicate concepts.
        unique_concepts = {}

        for concept in concepts:

            unique_concepts[
                concept["id"]
            ] = concept

        concepts = list(
            unique_concepts.values()
        )

        # Remove duplicate developments.
        unique_developments = {}

        for development in (
            developments_for_article
        ):

            unique_developments[
                development["id"]
            ] = development

        developments_for_article = list(
            unique_developments.values()
        )

        # ----------------------------------------------------
        # EVIDENCE SUMMARY
        # ----------------------------------------------------

        evidence = {
            "concept_count":
                len(concepts),

            "development_count":
                len(
                    developments_for_article
                ),

            "source_count": 0,

            "article_count": 1,
        }

        # Add measured source coverage from tracked signals.
        for concept in concepts:
            activity = concept.get("activity", {})
            source_count = activity.get("source_count", 0)

            evidence["source_count"] = max(
                evidence["source_count"],
                source_count
            )


        if developments_for_article:

            source_set = set()

            article_counts = []

            for development in (
                developments_for_article
            ):

                source_set.update(
                    development.get(
                        "sources",
                        []
                    )
                )

                article_counts.append(
                    development.get(
                        "article_count",
                        0
                    )
                )

            evidence["source_count"] = len(
                source_set
            )

            evidence["article_count"] = (
                max(article_counts)
                if article_counts
                else 0
            )

        # ----------------------------------------------------
        # ARTICLE ANALYSIS PAYLOAD
        # ----------------------------------------------------

        results[article_id] = {

            "article_id":
                article_id,

            "generated_at":
                datetime.now().isoformat(),

            "machina_analysis": {

                "concepts":
                    concepts,

                "developments":
                    developments_for_article,

                "evidence":
                    evidence,
            },
        }

    output = {

        "generated_at":
            datetime.now().isoformat(),

        "article_count":
            len(results),

        "articles":
            results,
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("MACHINA ARTICLE INTELLIGENCE MAP")
    print("=" * 72)

    print(
        f"Articles with intelligence: "
        f"{len(results)}"
    )

    concept_links = sum(
        len(
            item["machina_analysis"][
                "concepts"
            ]
        )
        for item in results.values()
    )

    development_links = sum(
        len(
            item["machina_analysis"][
                "developments"
            ]
        )
        for item in results.values()
    )

    print(
        f"Concept links: "
        f"{concept_links}"
    )

    print(
        f"Development links: "
        f"{development_links}"
    )

    print()
    print("SAMPLE ARTICLE MAPPINGS")
    print("-" * 72)

    shown = 0

    for article_id, item in results.items():

        analysis = item[
            "machina_analysis"
        ]

        if (
            not analysis["concepts"]
            and not analysis["developments"]
        ):
            continue

        print()
        print(
            f"ARTICLE: {article_id}"
        )

        if analysis["concepts"]:

            print(
                "CONCEPTS:"
            )

            for concept in analysis[
                "concepts"
            ][:5]:

                print(
                    f"  - "
                    f"{concept['name']} "
                    f"[{concept['state']}]"
                )

        if analysis["developments"]:

            print(
                "DEVELOPMENTS:"
            )

            for development in analysis[
                "developments"
            ][:3]:

                print(
                    f"  - "
                    f"{development['title'][:75]}"
                )

        shown += 1

        if shown >= 5:
            break

    print()
    print(
        f"Saved: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
