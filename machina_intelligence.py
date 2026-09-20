from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse
import json
import math
import re

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ============================================================
# MACHINA INTELLIGENCE ENGINE
# ============================================================

BASE_DIR = Path(__file__).parent
REWRITTEN_DIR = BASE_DIR / "data" / "rewritten"
OUTPUT_DIR = BASE_DIR / "data" / "intelligence"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

STOP_WORDS = {
    "about", "after", "again", "against", "almost", "also",
    "although", "among", "another", "around", "because",
    "before", "being", "between", "could", "during", "each",
    "from", "further", "have", "having", "here", "into",
    "itself", "more", "most", "other", "over", "same",
    "some", "such", "than", "that", "their", "there",
    "these", "they", "this", "those", "through", "under",
    "very", "what", "when", "where", "which", "while",
    "with", "would", "your", "will", "were", "been",
    "said", "says", "news", "today", "new", "latest",
    "read", "article", "report", "reports", "according",
    "could", "would", "might", "first", "just", "like",
    "using", "used", "use", "one", "two", "three",
    "make", "makes", "made", "many", "much", "even",
    "still", "however", "including", "year", "years",
    "time", "way", "people", "thing", "things"
}


GENERIC_ENTITY_WORDS = {
    "The", "This", "That", "These", "Those", "New",
    "News", "Today", "Report", "Reports", "Company",
    "Companies", "Technology", "Technologies", "System",
    "Systems", "Model", "Models", "Product", "Products",
    "Future", "World", "Team", "Project", "Research"
}


# ------------------------------------------------------------
# Loading
# ------------------------------------------------------------

def load_articles():
    articles = []
    seen = set()

    files = sorted(REWRITTEN_DIR.glob("*.json"))

    print(f"Found {len(files)} JSON files.")

    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))

            article_id = data.get("id")

            if not article_id or article_id in seen:
                continue

            seen.add(article_id)

            text = str(data.get("text") or "")
            rewritten = str(data.get("rewritten") or "")

            # Intelligence works primarily from the original cleaned
            # article text. Rewritten text is retained for reference.
            combined = f"{data.get('title', '')} {text}"

            articles.append({
                "id": article_id,
                "url": data.get("url", ""),
                "title": str(data.get("title") or "").strip(),
                "category": str(data.get("category") or "unknown").strip().lower(),
                "authors": data.get("authors") or [],
                "published": data.get("published"),
                "fetched": data.get("fetched"),
                "text": text,
                "rewritten": rewritten,
                "combined": combined
            })

        except Exception as exc:
            print(f"Could not load {fp.name}: {exc}")

    return articles


# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------

def clean_text(text):
    text = re.sub(r"<[^>]+>", " ", str(text))
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def domain_from_url(url):
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def parse_date(value):
    try:
        if not value:
            return pd.NaT

        dt = pd.to_datetime(value, errors="coerce", utc=True)

        if pd.isna(dt):
            return pd.NaT

        return dt

    except Exception:
        return pd.NaT


def safe_float(value):
    try:
        value = float(value)
        if math.isfinite(value):
            return value
    except Exception:
        pass

    return 0.0


# ------------------------------------------------------------
# Keywords
# ------------------------------------------------------------

def extract_keywords(articles, top_n=60):
    texts = [
        clean_text(
            f"{article['title']} {article['text']}"
        )
        for article in articles
    ]

    if not any(texts):
        return []

    vectorizer = TfidfVectorizer(
        stop_words=list(STOP_WORDS),
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.75,
        max_features=2500,
        sublinear_tf=True
    )

    matrix = vectorizer.fit_transform(texts)

    scores = matrix.sum(axis=0).A1
    terms = vectorizer.get_feature_names_out()

    ranked = sorted(
        zip(terms, scores),
        key=lambda x: x[1],
        reverse=True
    )

    results = []

    for term, score in ranked[:top_n]:
        results.append({
            "keyword": term,
            "score": round(safe_float(score), 5)
        })

    return results


# ------------------------------------------------------------
# Keyword growth
# ------------------------------------------------------------

def keyword_growth(articles, top_n=40):
    dated = []

    for article in articles:
        dt = parse_date(article["published"])

        if not pd.isna(dt):
            dated.append((article, dt))

    if len(dated) < 10:
        return []

    dates = [x[1] for x in dated]
    newest = max(dates)

    # Recent = 45 days
    # Previous = 45-90 days
    recent_start = newest - pd.Timedelta(days=45)
    previous_start = newest - pd.Timedelta(days=90)

    recent = [
        article for article, dt in dated
        if dt >= recent_start
    ]

    previous = [
        article for article, dt in dated
        if previous_start <= dt < recent_start
    ]

    if not recent:
        return []

    def counts(group):
        counter = Counter()

        for article in group:
            words = re.findall(
                r"\b[a-zA-Z][a-zA-Z0-9\-]{3,}\b",
                clean_text(
                    f"{article['title']} {article['text']}"
                ).lower()
            )

            for word in words:
                if word not in STOP_WORDS:
                    counter[word] += 1

        return counter

    recent_counts = counts(recent)
    previous_counts = counts(previous)

    results = []

    for word, recent_count in recent_counts.items():

        if recent_count < 2:
            continue

        previous_count = previous_counts.get(word, 0)

        recent_rate = recent_count / max(len(recent), 1)
        previous_rate = previous_count / max(len(previous), 1)

        if previous_rate == 0:
            growth = 5.0
        else:
            growth = recent_rate / previous_rate

        results.append({
            "keyword": word,
            "recent_articles": recent_count,
            "previous_articles": previous_count,
            "growth": round(min(growth, 99.0), 3)
        })

    results.sort(
        key=lambda x: (
            x["growth"],
            x["recent_articles"]
        ),
        reverse=True
    )

    return results[:top_n]


# ------------------------------------------------------------
# Entity extraction
# ------------------------------------------------------------

def extract_entities(articles, top_n=100):
    """
    Lightweight entity extraction.

    We intentionally avoid requiring a spaCy model here.
    Capitalised multi-word phrases are useful signals in
    technology journalism and give us a reliable baseline.
    """

    counts = Counter()
    article_map = defaultdict(set)

    pattern = re.compile(
        r"\b(?:[A-Z][A-Za-z0-9&.\-]+"
        r"(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,3})\b"
    )

    for article in articles:

        source_text = (
            f"{article['title']} "
            f"{article['text'][:10000]}"
        )

        matches = pattern.findall(source_text)

        local = set()

        for match in matches:

            entity = re.sub(
                r"\s+",
                " ",
                match
            ).strip()

            words = entity.split()

            if not entity:
                continue

            if entity in GENERIC_ENTITY_WORDS:
                continue

            if len(entity) < 3:
                continue

            if len(words) == 1:
                if entity.lower() in STOP_WORDS:
                    continue

                # Ignore ordinary sentence-start words
                if len(entity) < 4:
                    continue

            # Avoid giant sentence fragments
            if len(entity) > 60:
                continue

            local.add(entity)

        for entity in local:
            counts[entity] += 1
            article_map[entity].add(article["id"])

    results = []

    for entity, count in counts.most_common(top_n):

        if count < 2:
            continue

        results.append({
            "entity": entity,
            "article_count": count,
            "article_ids": list(article_map[entity])[:50]
        })

    return results


# ------------------------------------------------------------
# Categories
# ------------------------------------------------------------

def category_analysis(articles):
    counter = Counter(
        article["category"]
        for article in articles
        if article["category"]
    )

    return [
        {
            "category": category,
            "articles": count
        }
        for category, count in counter.most_common()
    ]


# ------------------------------------------------------------
# Sources
# ------------------------------------------------------------

def source_analysis(articles):
    source_articles = defaultdict(list)

    for article in articles:
        domain = domain_from_url(article["url"])

        if domain:
            source_articles[domain].append(article["id"])

    results = []

    for domain, ids in sorted(
        source_articles.items(),
        key=lambda x: len(x[1]),
        reverse=True
    ):
        results.append({
            "source": domain,
            "articles": len(ids)
        })

    return results


# ------------------------------------------------------------
# Topic discovery
# ------------------------------------------------------------

def discover_topics(articles, max_topics=18):
    """
    Discover clean technology concepts from the article corpus.

    Related phrases are grouped into broader concepts so that
    minor wording differences do not become separate signals.
    """

    import re
    from collections import Counter, defaultdict

    STOP_WORDS = {
        "the", "and", "for", "with", "from", "that", "this", "these",
        "those", "into", "over", "after", "before", "about", "under",
        "between", "through", "during", "while", "where", "when",
        "which", "their", "there", "they", "them", "than", "then",
        "have", "has", "had", "been", "being", "were", "was", "are",
        "is", "be", "can", "could", "would", "should", "will",
        "may", "might", "must", "not", "but", "you", "your", "our",
        "its", "his", "her", "how", "why", "what", "who", "new",
        "more", "most", "some", "many", "all", "one", "two", "first",
        "last", "also", "just", "now", "still", "only", "very",
        "out", "off", "up", "down", "on", "in", "at", "to", "of",
        "a", "an", "as", "by"
    }

    TECH_WORDS = {
        "ai", "artificial", "intelligence", "agent", "agents",
        "autonomous", "automation", "robot", "robots", "robotics",
        "drone", "drones", "model", "models", "language",
        "machine", "learning", "generative", "llm", "chatbot",
        "computer", "vision", "software", "hardware", "chip",
        "chips", "gpu", "gpus", "semiconductor", "cloud",
        "cyber", "cybersecurity", "quantum", "satellite",
        "space", "coding", "developer", "developers", "openai",
        "anthropic", "google", "microsoft", "nvidia", "meta",
        "apple", "tesla", "dji", "skydio", "robotaxi",
        "electric", "vehicle", "vehicles", "self-driving",
        "data", "training", "inference"
    }

    def normalise_phrase(phrase):
        phrase = str(phrase).lower()

        # Remove possessives.
        phrase = re.sub(r"['’]s\b", "", phrase)

        # Remove remaining apostrophes.
        phrase = phrase.replace("'", "").replace("’", "")

        words = phrase.split()
        cleaned = []

        for word in words:
            word = re.sub(r"[^a-z0-9-]", "", word)

            if not word:
                continue

            # Remove single-letter noise, but keep "ai".
            if len(word) == 1 and word != "ai":
                continue

            # Conservative singularisation.
            if len(word) > 5 and word.endswith("ies"):
                word = word[:-3] + "y"

            elif len(word) > 5 and word.endswith("ses"):
                word = word[:-2]

            elif (
                len(word) > 4
                and word.endswith("s")
                and not word.endswith(("ous", "ss", "us", "is"))
            ):
                word = word[:-1]

            if word in STOP_WORDS:
                continue

            cleaned.append(word)

        return " ".join(cleaned)

    # ------------------------------------------------------------
    # COLLECT PHRASE CANDIDATES
    # ------------------------------------------------------------

    phrase_articles = defaultdict(set)
    phrase_counts = Counter()

    for article in articles:
        article_id = str(article.get("id", ""))

        title = str(article.get("title", "") or "")
        body = str(article.get("text", "") or "")[:12000]

        # Titles are stronger evidence than body text.
        sections = [
            (title, 5),
            (body, 1)
        ]

        for text, weight in sections:
            raw_words = re.findall(
                r"[A-Za-z0-9][A-Za-z0-9'-]*",
                text.lower()
            )

            for n in (2, 3, 4):
                if len(raw_words) < n:
                    continue

                for i in range(len(raw_words) - n + 1):
                    raw_phrase = " ".join(
                        raw_words[i:i+n]
                    )

                    phrase = normalise_phrase(raw_phrase)

                    words = phrase.split()

                    if len(words) < 2:
                        continue

                    if len(words) > 4:
                        continue

                    if not any(
                        word in TECH_WORDS
                        for word in words
                    ):
                        continue

                    # Reject phrases containing obvious sentence noise.
                    if any(
                        word in STOP_WORDS
                        for word in words
                    ):
                        continue

                    phrase_articles[phrase].add(article_id)
                    phrase_counts[phrase] += weight

    # ------------------------------------------------------------
    # KEEP CORPUS-BACKED PHRASES
    # ------------------------------------------------------------

    candidates = []

    for phrase, ids in phrase_articles.items():
        if len(ids) < 3:
            continue

        words = set(phrase.split())

        if len(words) < 2:
            continue

        candidates.append({
            "phrase": phrase,
            "articles": ids,
            "article_count": len(ids),
            "count": phrase_counts[phrase]
        })

    candidates.sort(
        key=lambda x: (
            x["article_count"],
            x["count"]
        ),
        reverse=True
    )

    # ------------------------------------------------------------
    # CLUSTER RELATED PHRASES
    # ------------------------------------------------------------

    clusters = []

    for candidate in candidates:
        phrase = candidate["phrase"]
        words = set(phrase.split())

        best_cluster = None

        for cluster in clusters:
            representative = set(
                cluster["representative"].split()
            )

            overlap = (
                len(words & representative)
                / max(1, len(words | representative))
            )

            contained = (
                phrase in cluster["representative"]
                or cluster["representative"] in phrase
            )

            if overlap >= 0.50 or contained:
                best_cluster = cluster
                break

        if best_cluster is None:
            clusters.append({
                "representative": phrase,
                "phrases": [phrase],
                "article_ids": set(candidate["articles"]),
                "score": candidate["count"]
            })
        else:
            best_cluster["phrases"].append(phrase)
            best_cluster["article_ids"].update(
                candidate["articles"]
            )
            best_cluster["score"] += candidate["count"]

    # ------------------------------------------------------------
    # REMOVE NEAR-DUPLICATE CONCEPTS
    # ------------------------------------------------------------

    clusters.sort(
        key=lambda x: (
            len(x["article_ids"]),
            x["score"]
        ),
        reverse=True
    )

    final_topics = []

    for cluster in clusters:
        representative = cluster["representative"]
        rep_words = set(representative.split())

        duplicate = False

        for existing in final_topics:
            existing_words = set(
                existing["topic"].split()
            )

            overlap = (
                len(rep_words & existing_words)
                / max(1, len(rep_words | existing_words))
            )

            if overlap >= 0.65:
                duplicate = True
                break

        if duplicate:
            continue

        article_ids = list(
            cluster["article_ids"]
        )

        related = sorted(
            cluster["phrases"],
            key=lambda x: (
                len(x.split()),
                -phrase_counts[x]
            )
        )

        final_topics.append({
            "topic": representative,
            "related_phrases": related[:12],
            "article_count": len(article_ids),
            "article_ids": article_ids[:50]
        })

        if len(final_topics) >= max_topics:
            break

    return final_topics

def build_signals(articles, topics, growth):
    """
    Convert discovered topic clusters into Machina signals.

    This version consumes the V3 topic structure directly.
    It does not depend on the old keyword/topic schema.
    """

    from collections import Counter, defaultdict
    from datetime import datetime, timezone

    article_lookup = {
        str(article.get("id", "")): article
        for article in articles
    }
    # keyword_growth() returns a list of records.
    # Convert it into a lookup table so signals can query
    # growth by keyword/phrase.
    growth_lookup = {}

    if isinstance(growth, list):
        for item in growth:
            if not isinstance(item, dict):
                continue

            keyword = str(
                item.get("keyword", "")
            ).strip().lower()

            if keyword:
                growth_lookup[keyword] = item

    elif isinstance(growth, dict):
        growth_lookup = growth



    # ------------------------------------------------------------
    # SOURCE EXTRACTION
    # ------------------------------------------------------------

    def get_source(article):
        url = str(article.get("url", "") or "")

        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc.lower()
            host = host.replace("www.", "")
            return host
        except Exception:
            return url

    # ------------------------------------------------------------
    # DATE PARSING
    # ------------------------------------------------------------

    def parse_date(value):
        if not value:
            return None

        try:
            value = str(value).replace("Z", "+00:00")
            dt = datetime.fromisoformat(value)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt
        except Exception:
            return None

    dated_articles = []

    for article in articles:
        dt = parse_date(article.get("published"))

        if dt:
            dated_articles.append((article, dt))

    if dated_articles:
        latest_date = max(
            dt for _, dt in dated_articles
        )
    else:
        latest_date = datetime.now(timezone.utc)

    # ------------------------------------------------------------
    # BUILD SIGNALS
    # ------------------------------------------------------------

    signals = []

    for index, topic in enumerate(topics, start=1):

        topic_name = str(
            topic.get("topic", "unknown signal")
        ).strip()

        related_phrases = topic.get(
            "related_phrases",
            []
        )

        evidence = topic.get(
            "evidence",
            []
        )

        article_ids = topic.get(
            "article_ids",
            []
        )

        # Resolve evidence articles.
        resolved_articles = []

        for evidence_item in evidence:
            article_id = (
                evidence_item.get("article_id")
                or evidence_item.get("id")
            )

            if article_id in article_lookup:
                resolved_articles.append(
                    article_lookup[article_id]
                )

        # If evidence is absent, resolve from article_ids.
        if not resolved_articles:
            for article_id in article_ids:
                article = article_lookup.get(article_id)

                if article:
                    resolved_articles.append(article)

        if not resolved_articles:
            continue

        # --------------------------------------------------------
        # SOURCE DIVERSITY
        # --------------------------------------------------------

        sources = set()

        for article in resolved_articles:
            source = get_source(article)

            if source:
                sources.add(source)

        # --------------------------------------------------------
        # RECENCY
        # --------------------------------------------------------

        recent_count = 0
        total_count = len(resolved_articles)

        for article in resolved_articles:
            dt = parse_date(article.get("published"))

            if not dt:
                continue

            days_old = (
                latest_date - dt
            ).total_seconds() / 86400

            if days_old <= 45:
                recent_count += 1

        if total_count:
            recency_ratio = recent_count / total_count
        else:
            recency_ratio = 0

        # --------------------------------------------------------
        # GROWTH
        # --------------------------------------------------------

        growth_values = []

        for phrase in related_phrases:
            item = growth_lookup.get(str(phrase).lower())

            if isinstance(item, dict):
                value = item.get("growth")

                if isinstance(value, (int, float)):
                    growth_values.append(float(value))

            elif isinstance(item, (int, float)):
                growth_values.append(float(item))

        if growth_values:
            average_growth = sum(
                growth_values
            ) / len(growth_values)
        else:
            average_growth = 0.0

        # --------------------------------------------------------
        # SIGNAL STRENGTH
        # --------------------------------------------------------

        article_score = min(
            len(resolved_articles) / 20,
            1.0
        )

        source_score = min(
            len(sources) / 10,
            1.0
        )

        recency_score = recency_ratio

        # Growth is capped so one noisy percentage doesn't
        # completely dominate the signal.
        growth_score = min(
            max(average_growth, 0) / 5,
            1.0
        )

        strength = (
            article_score * 0.30
            + source_score * 0.30
            + recency_score * 0.20
            + growth_score * 0.20
        ) * 100

        # --------------------------------------------------------
        # CATEGORIES
        # --------------------------------------------------------

        categories = Counter()

        for article in resolved_articles:
            category = str(
                article.get("category", "")
            ).strip()

            if category:
                categories[category] += 1

        # --------------------------------------------------------
        # ENTITIES
        # --------------------------------------------------------

        entities = Counter()

        for article in resolved_articles:
            for entity in article.get(
                "entities",
                []
            ) if isinstance(article.get("entities"), list) else []:

                if isinstance(entity, str):
                    entities[entity] += 1

        # --------------------------------------------------------
        # EVIDENCE
        # --------------------------------------------------------

        evidence_output = []

        for article in resolved_articles[:12]:
            evidence_output.append({
                "id": article.get("id"),
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                "published": article.get("published", ""),
                "category": article.get("category", "")
            })

        # --------------------------------------------------------
        # SIGNAL OBJECT
        # --------------------------------------------------------

        signal = {
            "id": f"signal-{index:03d}",

            "name": topic_name,

            "strength": round(
                strength,
                1
            ),

            "article_count": len(
                resolved_articles
            ),

            "source_count": len(
                sources
            ),

            "sources": sorted(
                sources
            ),

            "recent_article_count": recent_count,

            "recent_ratio": round(
                recency_ratio,
                3
            ),

            "average_growth": round(
                average_growth,
                2
            ),

            "related_topics": related_phrases,

            "categories": [
                {
                    "name": name,
                    "articles": count
                }
                for name, count
                in categories.most_common(10)
            ],

            "entities": [
                {
                    "name": name,
                    "articles": count
                }
                for name, count
                in entities.most_common(20)
            ],

            "evidence": evidence_output
        }

        signals.append(signal)

    # ------------------------------------------------------------
    # SORT STRONGEST FIRST
    # ------------------------------------------------------------

    signals.sort(
        key=lambda signal: (
            signal.get("strength", 0),
            signal.get("article_count", 0),
            signal.get("source_count", 0)
        ),
        reverse=True
    )

    # Re-number after sorting.
    for index, signal in enumerate(
        signals,
        start=1
    ):
        signal["rank"] = index

    return signals

def attach_signals_to_articles(articles, signals):
    mapping = defaultdict(list)

    for signal in signals:

        for evidence in signal["evidence"]:

            article_id = evidence.get("article_id", evidence.get("id"))

            mapping[article_id].append({
                "signal": signal["name"],
                "strength": signal["strength"],
                "similarity": evidence.get("similarity", evidence.get("hits", 0))
            })

    return {
        article_id: sorted(
            values,
            key=lambda x: x["similarity"],
            reverse=True
        )[:5]
        for article_id, values in mapping.items()
    }


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():

    print()
    print("=" * 64)
    print("MACHINA INTELLIGENCE ENGINE")
    print("=" * 64)
    print()

    articles = load_articles()

    if not articles:
        print("ERROR: No rewritten articles found.")
        return

    print(f"Articles loaded: {len(articles)}")

    # --------------------------------------------------------
    # DataFrame
    # --------------------------------------------------------

    df = pd.DataFrame(articles)

    df["date"] = pd.to_datetime(
        df["published"],
        errors="coerce",
        utc=True
    )

    valid_dates = df["date"].dropna()

    if len(valid_dates):
        date_min = valid_dates.min().isoformat()
        date_max = valid_dates.max().isoformat()
    else:
        date_min = None
        date_max = None

    # --------------------------------------------------------
    # Core intelligence
    # --------------------------------------------------------

    print()
    print("[1/7] Extracting keywords...")
    keywords = extract_keywords(articles)

    print("[2/7] Measuring keyword growth...")
    growth = keyword_growth(articles)

    print("[3/7] Extracting entities...")
    entities = extract_entities(articles)

    print("[4/7] Analysing categories...")
    categories = category_analysis(articles)

    print("[5/7] Analysing sources...")
    sources = source_analysis(articles)

    print("[6/7] Discovering semantic topics...")
    topics = discover_topics(articles)

    print("[7/7] Building Machina signals...")
    signals = build_signals(
        articles,
        topics,
        growth
    )

    article_signals = attach_signals_to_articles(
        articles,
        signals
    )

    # --------------------------------------------------------
    # Corpus statistics
    # --------------------------------------------------------

    unique_sources = {
        domain_from_url(article["url"])
        for article in articles
        if domain_from_url(article["url"])
    }

    unique_categories = {
        article["category"]
        for article in articles
        if article["category"]
    }

    corpus = {
        "articles": len(articles),
        "sources": len(unique_sources),
        "categories": len(unique_categories),
        "date_min": date_min,
        "date_max": date_max,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    output = {
        "version": "1.0",
        "generated_at": corpus["generated_at"],
        "corpus": corpus,
        "keywords": keywords,
        "keyword_growth": growth,
        "entities": entities,
        "categories": categories,
        "sources": sources,
        "topics": topics,
        "signals": signals,
        "article_signals": article_signals
    }

    output_file = OUTPUT_DIR / "signals.json"

    output_file.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Console summary
    # --------------------------------------------------------

    print()
    print("=" * 64)
    print("MACHINA INTELLIGENCE COMPLETE")
    print("=" * 64)
    print()
    print(f"Articles:        {corpus['articles']}")
    print(f"Sources:         {corpus['sources']}")
    print(f"Categories:      {corpus['categories']}")
    print(f"Topics found:    {len(topics)}")
    print(f"Signals found:   {len(signals)}")
    print(f"Entities found:  {len(entities)}")
    print()
    print("TOP MACHINA SIGNALS")
    print("-" * 64)

    for index, signal in enumerate(signals[:10], 1):

        print(
            f"{index:02d}. "
            f"{signal['name']} "
            f"| strength={signal['strength']} "
            f"| articles={signal['article_count']} "
            f"| sources={signal['source_count']}"
        )

    print()
    print(f"Saved intelligence to:")
    print(output_file)
    print()


if __name__ == "__main__":
    main()













