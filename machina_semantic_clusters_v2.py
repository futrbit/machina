from pathlib import Path
import json
import re
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


BASE = Path(__file__).parent
REWRITTEN_DIR = BASE / "data" / "rewritten"
OUT_DIR = BASE / "data" / "intelligence"
OUT_FILE = OUT_DIR / "semantic_clusters_v2.json"

# ------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------

MODEL_NAME = "all-MiniLM-L6-v2"

# Articles must be semantically similar enough to connect.
SIMILARITY_THRESHOLD = 0.68

# Prevent ancient articles about the same broad subject
# from becoming one giant "development".
MAX_DAYS_APART = 45

# Only keep clusters with at least this many articles.
MIN_CLUSTER_SIZE = 2


# ------------------------------------------------------------
# LOAD ARTICLES
# ------------------------------------------------------------

def load_articles():
    articles = []

    for fp in sorted(REWRITTEN_DIR.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        title = str(data.get("title", "")).strip()
        rewritten = str(data.get("rewritten", "")).strip()
        text = str(data.get("text", "")).strip()

        if not title:
            continue

        published = str(data.get("published", "")).strip()

        articles.append({
            "id": data.get("id", fp.stem),
            "title": title,
            "rewritten": rewritten,
            "text": text,
            "published": published,
            "url": data.get("url", ""),
        })

    return articles


# ------------------------------------------------------------
# NORMALISE DATE
# ------------------------------------------------------------

def parse_date(value):
    if not value:
        return None

    value = str(value).strip()

    # ISO date/time
    match = re.match(r"^(\\d{4}-\\d{2}-\\d{2})", value)

    if not match:
        return None

    from datetime import datetime

    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d")
    except Exception:
        return None


# ------------------------------------------------------------
# SOURCE
# ------------------------------------------------------------

def source_from_url(url):
    if not url:
        return "unknown"

    match = re.search(r"https?://(?:www\\.)?([^/]+)", url)

    if not match:
        return "unknown"

    return match.group(1).lower()


# ------------------------------------------------------------
# BUILD SEMANTIC DOCUMENT
# ------------------------------------------------------------

def build_document(article):
    title = article["title"]

    rewritten = article["rewritten"]
    text = article["text"]

    # Keep the title highly influential.
    body = rewritten if rewritten else text

    # Strip HTML-ish noise.
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\\s+", " ", body).strip()

    # We don't need the entire article.
    body = body[:1800]

    return (
        f"TITLE: {title}\\n"
        f"TITLE: {title}\\n"
        f"ARTICLE: {body}"
    )


# ------------------------------------------------------------
# UNION-FIND
# ------------------------------------------------------------

class UnionFind:

    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra = self.find(a)
        rb = self.find(b)

        if ra == rb:
            return

        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    articles = load_articles()

    print(f"Articles loaded: {len(articles)}")

    if not articles:
        print("No articles found.")
        return

    documents = [
        build_document(article)
        for article in articles
    ]

    print()
    print(f"Loading semantic model: {MODEL_NAME}")

    model = SentenceTransformer(MODEL_NAME)

    print("Creating semantic embeddings...")

    embeddings = model.encode(
        documents,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True
    )

    print()
    print(f"Embeddings created: {len(embeddings)}")
    print("Calculating semantic similarity...")

    similarity = cosine_similarity(embeddings)

    dates = [
        parse_date(article["published"])
        for article in articles
    ]

    uf = UnionFind(len(articles))

    edges = 0

    for i in range(len(articles)):

        for j in range(i + 1, len(articles)):

            score = float(similarity[i, j])

            if score < SIMILARITY_THRESHOLD:
                continue

            # Date constraint.
            if dates[i] and dates[j]:

                difference = abs(
                    (dates[i] - dates[j]).days
                )

                if difference > MAX_DAYS_APART:
                    continue

            uf.union(i, j)
            edges += 1

    print(f"Semantic edges accepted: {edges}")

    # --------------------------------------------------------
    # BUILD CLUSTERS
    # --------------------------------------------------------

    groups = {}

    for index in range(len(articles)):

        root = uf.find(index)

        groups.setdefault(root, []).append(index)

    clusters = []

    for members in groups.values():

        if len(members) < MIN_CLUSTER_SIZE:
            continue

        cluster_articles = [
            articles[i]
            for i in members
        ]

        cluster_dates = [
            dates[i]
            for i in members
            if dates[i]
        ]

        sources = sorted({
            source_from_url(article["url"])
            for article in cluster_articles
            if article["url"]
        })

        titles = [
            article["title"]
            for article in cluster_articles
        ]

        # Pick the earliest article as the cluster anchor.
        ordered = sorted(
            cluster_articles,
            key=lambda article: (
                parse_date(article["published"])
                or __import__("datetime").datetime.max
            )
        )

        anchor = ordered[0]

        # Average internal similarity.
        if len(members) > 1:

            internal_scores = []

            for x in range(len(members)):

                for y in range(x + 1, len(members)):

                    internal_scores.append(
                        float(
                            similarity[
                                members[x],
                                members[y]
                            ]
                        )
                    )

            coherence = (
                sum(internal_scores) /
                len(internal_scores)
            )

        else:
            coherence = 0.0

        clusters.append({
            "id": f"development_{len(clusters) + 1:04d}",

            "title": anchor["title"],

            "article_count": len(cluster_articles),

            "source_count": len(sources),

            "sources": sources,

            "first_seen": (
                min(cluster_dates).isoformat()
                if cluster_dates
                else None
            ),

            "last_seen": (
                max(cluster_dates).isoformat()
                if cluster_dates
                else None
            ),

            "date_span_days": (
                (max(cluster_dates) - min(cluster_dates)).days
                if len(cluster_dates) > 1
                else 0
            ),

            "coherence": round(coherence, 4),

            "titles": titles,

            "article_ids": [
                article["id"]
                for article in cluster_articles
            ],

            "articles": [
                {
                    "id": article["id"],
                    "title": article["title"],
                    "published": article["published"],
                    "source": source_from_url(article["url"]),
                    "url": article["url"],
                }
                for article in cluster_articles
            ],
        })

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    clusters.sort(
        key=lambda cluster: (
            cluster["article_count"],
            cluster["source_count"],
            cluster["coherence"],
        ),
        reverse=True
    )

    # Re-number after sorting.
    for index, cluster in enumerate(clusters, start=1):
        cluster["rank"] = index
        cluster["id"] = f"development_{index:04d}"

    result = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),

        "model": MODEL_NAME,

        "settings": {
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "max_days_apart": MAX_DAYS_APART,
            "min_cluster_size": MIN_CLUSTER_SIZE,
        },

        "article_count": len(articles),

        "cluster_count": len(clusters),

        "clusters": clusters,
    }

    OUT_FILE.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print()
    print("=" * 70)
    print("TOP SEMANTIC DEVELOPMENT CLUSTERS")
    print("=" * 70)

    for index, cluster in enumerate(clusters[:25], start=1):

        print(
            f"{index:02d}. "
            f"{cluster['title'][:85]} | "
            f"articles={cluster['article_count']} | "
            f"sources={cluster['source_count']} | "
            f"coherence={cluster['coherence']:.2f} | "
            f"span={cluster['date_span_days']}d"
        )

    print()
    print(f"Development clusters: {len(clusters)}")
    print(f"Saved: {OUT_FILE}")


if __name__ == "__main__":
    main()
