import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


BASE_DIR = Path(__file__).parent
REWRITTEN_DIR = BASE_DIR / "data" / "rewritten"
OUTPUT_DIR = BASE_DIR / "data" / "intelligence"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------
# LOAD ARTICLES
# ---------------------------------------------------------

def load_articles():

    articles = []

    for fp in sorted(REWRITTEN_DIR.glob("*.json")):

        try:
            article = json.loads(
                fp.read_text(encoding="utf-8")
            )

            articles.append(article)

        except Exception:
            continue

    return articles


# ---------------------------------------------------------
# TEXT NORMALISATION
# ---------------------------------------------------------

def clean_text(value):

    if not value:
        return ""

    value = str(value).lower()

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def article_text(article):

    title = clean_text(
        article.get("title", "")
    )

    text = clean_text(
        article.get("text", "")
    )

    rewritten = clean_text(
        article.get("rewritten", "")
    )

    # Title gets repeated so that it has greater influence
    # than generic article body language.
    return (
        title + " " +
        title + " " +
        rewritten + " " +
        text
    )


# ---------------------------------------------------------
# DATE / SOURCE HELPERS
# ---------------------------------------------------------

def parse_date(value):

    if not value:
        return None

    try:

        text = str(value).strip()

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(timezone.utc)

    except Exception:
        return None


def get_source(article):

    url = str(
        article.get("url", "")
    )

    match = re.search(
        r"https?://(?:www\.)?([^/]+)",
        url
    )

    if match:
        return match.group(1).lower()

    return "unknown"


# ---------------------------------------------------------
# UNION FIND
# ---------------------------------------------------------

class UnionFind:

    def __init__(self, size):

        self.parent = list(
            range(size)
        )

        self.rank = [0] * size


    def find(self, x):

        while self.parent[x] != x:

            self.parent[x] = (
                self.parent[
                    self.parent[x]
                ]
            )

            x = self.parent[x]

        return x


    def union(self, a, b):

        root_a = self.find(a)
        root_b = self.find(b)

        if root_a == root_b:
            return

        if self.rank[root_a] < self.rank[root_b]:

            self.parent[root_a] = root_b

        elif self.rank[root_a] > self.rank[root_b]:

            self.parent[root_b] = root_a

        else:

            self.parent[root_b] = root_a

            self.rank[root_a] += 1


# ---------------------------------------------------------
# CLUSTER ARTICLES
# ---------------------------------------------------------

def build_clusters(
    articles,
    similarity_threshold=0.48
):

    usable = []
    texts = []

    for article in articles:

        text = article_text(article)

        if not text:
            continue

        usable.append(article)
        texts.append(text)

    if not texts:
        return []

    print(
        f"Vectorising {len(texts)} articles..."
    )

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.90,
        sublinear_tf=True
    )

    matrix = vectorizer.fit_transform(
        texts
    )

    print(
        f"TF-IDF features: {matrix.shape[1]}"
    )

    similarities = cosine_similarity(
        matrix,
        dense_output=False
    )

    union_find = UnionFind(
        len(usable)
    )

    print(
        "Building similarity graph..."
    )

    rows, cols = similarities.nonzero()

    edge_count = 0

    for row, col in zip(rows, cols):

        if row >= col:
            continue

        score = float(
            similarities[row, col]
        )

        if score >= similarity_threshold:

            union_find.union(
                row,
                col
            )

            edge_count += 1

    print(
        f"Similarity edges accepted: {edge_count}"
    )

    groups = {}

    for index in range(len(usable)):

        root = union_find.find(index)

        groups.setdefault(
            root,
            []
        ).append(index)

    clusters = []

    cluster_number = 1

    for indexes in groups.values():

        # A single article isn't a development cluster.
        # Keep it out of the cluster dataset.
        if len(indexes) < 2:
            continue

        cluster_articles = [
            usable[i]
            for i in indexes
        ]

        # -------------------------------------------------
        # REPRESENTATIVE ARTICLE
        # -------------------------------------------------

        representative = max(
            cluster_articles,
            key=lambda article: len(
                str(article.get("title", ""))
            )
        )

        titles = [
            str(
                article.get(
                    "title",
                    ""
                )
            ).strip()
            for article in cluster_articles
        ]

        sources = sorted(
            set(
                get_source(article)
                for article in cluster_articles
            )
        )

        dates = []

        for article in cluster_articles:

            dt = parse_date(
                article.get("published")
                or article.get("fetched")
            )

            if dt:
                dates.append(dt)

        dates.sort()

        first_date = (
            dates[0].isoformat()
            if dates
            else None
        )

        latest_date = (
            dates[-1].isoformat()
            if dates
            else None
        )

        # -------------------------------------------------
        # ARTICLE IDS
        # -------------------------------------------------

        article_ids = []

        for article in cluster_articles:

            article_id = (
                article.get("id")
                or article.get("article_id")
            )

            if article_id:
                article_ids.append(
                    str(article_id)
                )

        cluster = {

            "id": (
                f"development_{cluster_number:04d}"
            ),

            "title": str(
                representative.get(
                    "title",
                    ""
                )
            ).strip(),

            "article_count": len(
                cluster_articles
            ),

            "source_count": len(
                sources
            ),

            "sources": sources,

            "first_seen": first_date,

            "last_seen": latest_date,

            "date_span_days": (
                (
                    dates[-1] - dates[0]
                ).total_seconds() / 86400
                if len(dates) >= 2
                else 0.0
            ),

            "titles": titles[:25],

            "article_ids": article_ids[:50]
        }

        clusters.append(
            cluster
        )

        cluster_number += 1

    # Strongest / largest developments first.
    clusters.sort(
        key=lambda cluster: (
            cluster["article_count"],
            cluster["source_count"],
            cluster["date_span_days"]
        ),
        reverse=True
    )

    return clusters


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print("=" * 70)
    print("MACHINA DEVELOPMENT CLUSTER ENGINE V2")
    print("=" * 70)

    articles = load_articles()

    print(
        f"Articles loaded: {len(articles)}"
    )

    clusters = build_clusters(
        articles
    )

    output = {

        "version": 2,

        "article_count": len(
            articles
        ),

        "cluster_count": len(
            clusters
        ),

        "similarity_threshold": 0.48,

        "clusters": clusters
    }

    output_file = (
        OUTPUT_DIR
        / "clusters_v2.json"
    )

    output_file.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print()
    print(
        "TOP DEVELOPMENT CLUSTERS"
    )

    print("=" * 70)

    for index, cluster in enumerate(
        clusters[:30],
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{cluster['title'][:90]} | "
            f"articles={cluster['article_count']} | "
            f"sources={cluster['source_count']} | "
            f"span={cluster['date_span_days']:.1f}d"
        )

    print()
    print(
        f"Development clusters: "
        f"{len(clusters)}"
    )

    print(
        f"Saved: {output_file}"
    )

    print()
    print(
        "MACHINA DEVELOPMENT CLUSTER ENGINE V2 COMPLETE"
    )


if __name__ == "__main__":
    main()
