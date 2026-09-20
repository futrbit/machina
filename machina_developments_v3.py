from pathlib import Path
from datetime import datetime
import json
import re
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

BASE = Path(__file__).parent
REWRITTEN_DIR = BASE / "data" / "rewritten"
INTEL_DIR = BASE / "data" / "intelligence"

CLUSTERS_FILE = INTEL_DIR / "developments_v3.json"

MODEL_NAME = "all-MiniLM-L6-v2"

# Semantic similarity required.
SIMILARITY_THRESHOLD = 0.72

# Articles further apart than this cannot belong
# to the same individual development.
MAX_DAYS_APART = 21

# A development must have at least 2 articles.
MIN_ARTICLES = 2

# Very broad clusters are suspicious.
MAX_CLUSTER_SIZE = 25


def parse_date(value):
    if not value:
        return None

    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))

    if not match:
        return None

    try:
        return datetime.strptime(
            match.group(),
            "%Y-%m-%d"
        )
    except Exception:
        return None


def source_from_url(url):
    match = re.search(
        r"https?://(?:www\.)?([^/]+)",
        str(url or "")
    )

    return match.group(1).lower() if match else "unknown"


def clean_text(value):
    value = str(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def load_articles():

    articles = []

    for fp in REWRITTEN_DIR.glob("*.json"):

        try:
            data = json.loads(
                fp.read_text(encoding="utf-8")
            )
        except Exception:
            continue

        title = clean_text(data.get("title"))

        if not title:
            continue

        body = clean_text(
            data.get("rewritten")
            or data.get("text")
            or ""
        )

        articles.append({
            "id": data.get("id", fp.stem),
            "title": title,
            "body": body[:1600],
            "published": data.get("published", ""),
            "date": parse_date(data.get("published")),
            "url": data.get("url", ""),
            "source": source_from_url(data.get("url")),
        })

    return articles


def build_document(article):

    # Title is repeated deliberately so the actual development
    # named in the headline dominates generic article language.

    return (
        f"HEADLINE: {article['title']} "
        f"HEADLINE: {article['title']} "
        f"ARTICLE: {article['body']}"
    )


class UnionFind:

    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):

        while self.parent[x] != x:
            self.parent[x] = self.parent[
                self.parent[x]
            ]
            x = self.parent[x]

        return x

    def union(self, a, b):

        a = self.find(a)
        b = self.find(b)

        if a != b:
            self.parent[b] = a


def title_similarity(a, b):

    words_a = set(
        re.findall(
            r"[a-z0-9]{3,}",
            a.lower()
        )
    )

    words_b = set(
        re.findall(
            r"[a-z0-9]{3,}",
            b.lower()
        )
    )

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b

    return len(intersection) / len(union)


def main():

    INTEL_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    articles = load_articles()

    print(f"Articles loaded: {len(articles)}")
    print()

    model = SentenceTransformer(
        MODEL_NAME
    )

    documents = [
        build_document(article)
        for article in articles
    ]

    print("Creating semantic embeddings...")

    embeddings = model.encode(
        documents,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    print()
    print("Calculating semantic similarity...")

    similarities = cosine_similarity(
        embeddings
    )

    uf = UnionFind(
        len(articles)
    )

    accepted_edges = 0

    # --------------------------------------------------------
    # BUILD DEVELOPMENT GRAPH
    # --------------------------------------------------------

    for i in range(len(articles)):

        for j in range(i + 1, len(articles)):

            a = articles[i]
            b = articles[j]

            score = float(
                similarities[i, j]
            )

            if score < SIMILARITY_THRESHOLD:
                continue

            # Date proximity.
            if a["date"] and b["date"]:

                days = abs(
                    (a["date"] - b["date"]).days
                )

                if days > MAX_DAYS_APART:
                    continue

            # Prevent generic semantic similarity from
            # joining completely unrelated headlines.
            title_score = title_similarity(
                a["title"],
                b["title"]
            )

            # Strong semantic match can stand alone.
            # Otherwise require some headline overlap.
            if score < 0.78 and title_score < 0.08:
                continue

            uf.union(i, j)

            accepted_edges += 1

    print(
        f"Development connections accepted: "
        f"{accepted_edges}"
    )

    # --------------------------------------------------------
    # BUILD GROUPS
    # --------------------------------------------------------

    groups = {}

    for i in range(len(articles)):

        root = uf.find(i)

        groups.setdefault(
            root,
            []
        ).append(i)

    developments = []

    for members in groups.values():

        if len(members) < MIN_ARTICLES:
            continue

        # Reject giant generic clusters.
        if len(members) > MAX_CLUSTER_SIZE:
            continue

        cluster = [
            articles[i]
            for i in members
        ]

        dates = [
            article["date"]
            for article in cluster
            if article["date"]
        ]

        sources = sorted({
            article["source"]
            for article in cluster
        })

        # ----------------------------------------------------
        # INTERNAL COHERENCE
        # ----------------------------------------------------

        scores = []

        for x in range(len(members)):

            for y in range(x + 1, len(members)):

                scores.append(
                    float(
                        similarities[
                            members[x],
                            members[y]
                        ]
                    )
                )

        coherence = (
            sum(scores) / len(scores)
            if scores
            else 0
        )

        # ----------------------------------------------------
        # ANCHOR ARTICLE
        # ----------------------------------------------------

        ordered = sorted(
            cluster,
            key=lambda article:
                article["date"]
                or datetime.max
        )

        anchor = ordered[0]

        developments.append({
            "title": anchor["title"],

            "article_count": len(cluster),

            "source_count": len(sources),

            "sources": sources,

            "first_seen": (
                min(dates).isoformat()
                if dates
                else None
            ),

            "last_seen": (
                max(dates).isoformat()
                if dates
                else None
            ),

            "date_span_days": (
                (max(dates) - min(dates)).days
                if len(dates) > 1
                else 0
            ),

            "coherence": round(
                coherence,
                4
            ),

            "articles": [
                {
                    "id": article["id"],
                    "title": article["title"],
                    "published": article["published"],
                    "source": article["source"],
                    "url": article["url"],
                }
                for article in cluster
            ],
        })

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    developments.sort(
        key=lambda item: (
            item["source_count"],
            item["article_count"],
            item["coherence"]
        ),
        reverse=True
    )

    for index, development in enumerate(
        developments,
        start=1
    ):
        development["id"] = (
            f"development_{index:04d}"
        )
        development["rank"] = index

    output = {
        "generated_at": datetime.now().isoformat(),

        "model": MODEL_NAME,

        "settings": {
            "similarity_threshold":
                SIMILARITY_THRESHOLD,

            "max_days_apart":
                MAX_DAYS_APART,

            "max_cluster_size":
                MAX_CLUSTER_SIZE,
        },

        "article_count":
            len(articles),

        "development_count":
            len(developments),

        "developments":
            developments,
    }

    CLUSTERS_FILE.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print()
    print("=" * 72)
    print("MACHINA DEVELOPMENT DETECTOR V3")
    print("=" * 72)

    for index, development in enumerate(
        developments[:30],
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{development['title'][:78]} | "
            f"articles={development['article_count']} | "
            f"sources={development['source_count']} | "
            f"coherence={development['coherence']:.2f} | "
            f"span={development['date_span_days']}d"
        )

    print()
    print(
        f"Developments detected: "
        f"{len(developments)}"
    )

    print()
    print(
        f"Saved: {CLUSTERS_FILE}"
    )


if __name__ == "__main__":
    main()
