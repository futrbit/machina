from pathlib import Path
from datetime import datetime
import json

BASE = Path(__file__).parent
INTEL_DIR = BASE / "data" / "intelligence"

INPUT = INTEL_DIR / "developments_v3.json"
OUTPUT = INTEL_DIR / "development_intelligence.json"


def classify(development):

    articles = development["article_count"]
    sources = development["source_count"]
    span = development["date_span_days"]
    coherence = development["coherence"]

    # Evidence quality
    if sources >= 2 and articles >= 3:
        evidence = "multi-source"

    elif sources >= 2:
        evidence = "cross-source"

    else:
        evidence = "single-source"

    # Activity state
    if span <= 1 and articles >= 3:
        state = "emerging"

    elif span <= 7 and articles >= 3:
        state = "active"

    elif span <= 21:
        state = "persistent"

    else:
        state = "long-running"

    # Confidence is descriptive, based only on measurable evidence.
    confidence = 0

    confidence += min(40, articles * 8)
    confidence += min(30, sources * 15)
    confidence += min(20, coherence * 20)

    if span >= 1:
        confidence += 10

    confidence = min(
        100,
        round(confidence)
    )

    return {
        "evidence_type": evidence,
        "state": state,
        "confidence": confidence,
    }


def main():

    data = json.loads(
        INPUT.read_text(
            encoding="utf-8"
        )
    )

    developments = []

    for development in data["developments"]:

        classification = classify(
            development
        )

        enriched = {
            **development,
            **classification,

            "intelligence": {
                "articles": development["article_count"],
                "sources": development["source_count"],
                "date_span_days": development["date_span_days"],
                "semantic_coherence": development["coherence"],
            },
        }

        developments.append(
            enriched
        )

    result = {
        "generated_at":
            datetime.now().isoformat(),

        "development_count":
            len(developments),

        "developments":
            developments,
    }

    OUTPUT.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print()
    print("=" * 72)
    print("MACHINA DEVELOPMENT INTELLIGENCE")
    print("=" * 72)

    for index, development in enumerate(
        developments[:30],
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{development['title'][:70]} | "
            f"{development['evidence_type']} | "
            f"{development['state']} | "
            f"confidence={development['confidence']}"
        )

    print()
    print(
        f"Developments enriched: "
        f"{len(developments)}"
    )

    print(
        f"Saved: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
