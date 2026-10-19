from flask import Blueprint, jsonify, request, send_from_directory
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
import json
import re
import threading
import time

intelligence_bp = Blueprint("new_intelligence", __name__)
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "deep_raw"
FRONTEND_DIR = ROOT / "frontend"
CACHE_SECONDS = 300
_cache = {"at": 0, "data": None}
_lock = threading.Lock()

STOPWORDS = set("""
about above after again against all also among and any are around because been
before being between both but can could did does doing down during each few for
from further had has have having here how into its itself just more most other
our out over own same should some such than that the their them then there these
they this those through under until very was were what when where which while who
will with would your using based method methods study studies paper research
approach model models new proposed results show shows via toward from into onto
their them they this those these your our its itself than then when where what
which while who whom why how all any both each few many much some such only
very also just using based novel improved efficient effective advanced learning not open world system systems
""".split())

# These phrases are often too generic to be useful as standalone discoveries.
GENERIC_PHRASES = {
    "machine learning",
    "deep learning",
    "artificial intelligence",
    "large language",
    "language model",
    "neural network",
    "computer vision",
    "natural language",
    "state of",
    "real world",
    "proposed method",
    "experimental results",
}

def parse_date(value):
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None

def topic_words(record):
    title = str(record.get("title") or "").lower()
    words = re.findall(r"[a-z][a-z0-9-]{2,}", title)
    return [w for w in words if w not in STOPWORDS and not w.isdigit()]


def topic_phrases(record):
    """Extract meaningful adjacent two- and three-word title phrases."""
    title = str(record.get("title") or "").lower()
    words = re.findall(r"[a-z][a-z0-9-]{2,}", title)
    phrases = set()

    for n in (2, 3):
        for i in range(len(words) - n + 1):
            phrase_words = words[i:i + n]

            if any(w in STOPWORDS for w in phrase_words):
                continue

            phrase = " ".join(phrase_words)
            if phrase in GENERIC_PHRASES or len(phrase) < 8:
                continue

            phrases.add(phrase)

    return phrases


def safe_evidence(record, source, dt):
    return {
        "title": str(record.get("title") or "Untitled")[:500],
        "url": str(record.get("url") or "")[:2000],
        "source": source,
        "date": dt.isoformat() if dt else ""
    }

def load_records():
    now = time.time()
    if _cache["data"] is not None and now - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]

    with _lock:
        now = time.time()
        if _cache["data"] is not None and now - _cache["at"] < CACHE_SECONDS:
            return _cache["data"]

        records = []
        if DATA_DIR.exists():
            for path in DATA_DIR.rglob("*.json"):
                try:
                    with path.open("r", encoding="utf-8-sig") as handle:
                        item = json.load(handle)

                    if not isinstance(item, dict):
                        continue

                    item["_effective_date"] = (
                        parse_date(item.get("published"))
                        or parse_date(item.get("fetched_at"))
                        or parse_date(item.get("updated"))
                    )
                    item["_topic_words"] = topic_words(item)
                    item["_topic_phrases"] = topic_phrases(item)
                    item["_sectors"] = [
                        str(s).strip().lower()
                        for s in (item.get("sectors") or [])
                        if str(s).strip()
                    ] if isinstance(item.get("sectors"), list) else []

                    records.append(item)
                except (OSError, ValueError, TypeError):
                    continue

        now_dt = datetime.now(timezone.utc)
        dated = [r for r in records if r["_effective_date"]]
        latest_date = max(
            (r["_effective_date"] for r in dated),
            default=now_dt
        )
        current_start = latest_date - timedelta(days=30)
        previous_start = latest_date - timedelta(days=60)

        sector_counts = Counter()
        source_counts = Counter()
        daily_counts = Counter()

        # Track word signals and phrase signals independently.
        stats = {
            "word": {
                "current": Counter(),
                "previous": Counter(),
                "sources": defaultdict(set),
                "evidence": defaultdict(list),
            },
            "phrase": {
                "current": Counter(),
                "previous": Counter(),
                "sources": defaultdict(set),
                "evidence": defaultdict(list),
            },
        }

        for record in records:
            for sector in set(record["_sectors"]):
                sector_counts[sector] += 1

            source = str(
                record.get("source_name")
                or record.get("source_id")
                or "Unknown source"
            )
            source_counts[source] += 1

            dt = record["_effective_date"]
            if dt:
                daily_counts[dt.strftime("%Y-%m-%d")] += 1
            else:
                continue

            if current_start <= dt <= latest_date:
                period = "current"
            elif previous_start <= dt < current_start:
                period = "previous"
            else:
                continue

            # Deduplicate within each record so repeated terms do not inflate
            # a single paper's contribution.
            collections = {
                "word": set(record["_topic_words"]),
                "phrase": set(record["_topic_phrases"]),
            }

            for kind, topics in collections.items():
                bucket = stats[kind]
                for topic in topics:
                    bucket[period][topic] += 1

                    if period == "current":
                        bucket["sources"][topic].add(source)
                        if len(bucket["evidence"][topic]) < 3:
                            bucket["evidence"][topic].append(
                                safe_evidence(record, source, dt)
                            )

        trends = []

        for kind, bucket in stats.items():
            for topic, count in bucket["current"].items():
                previous = bucket["previous"][topic]
                source_count = len(bucket["sources"][topic])

                # Require repeated evidence and independent source coverage.
                minimum_mentions = 3 if kind == "phrase" else 6
                minimum_sources = 2 if kind == "phrase" else 3

                if count < minimum_mentions or source_count < minimum_sources:
                    continue

                growth = (
                    round(((count - previous) / previous) * 100, 1)
                    if previous else None
                )

                # Cap growth influence so tiny baselines cannot dominate.
                if previous == 0:
                    growth_component = 8 if count >= 8 else 3
                else:
                    growth_ratio = (count - previous) / max(previous, 8)
                    growth_component = max(
                        0, min(20, growth_ratio * 20)
                    )

                volume_component = min(35, count * 1.5)
                source_component = min(30, source_count * 5)
                recurrence_component = 15 if previous >= 5 else 5

                score = round(
                    min(
                        100,
                        volume_component
                        + source_component
                        + growth_component
                        + recurrence_component
                    ),
                    1
                )

                if previous == 0:
                    status = "new signal"
                elif previous >= 8 and growth is not None and growth >= 25:
                    status = "accelerating"
                elif previous >= 8 and growth is not None and growth <= -20:
                    status = "cooling"
                else:
                    status = "active"

                trends.append({
                    "topic": topic,
                    "topic_type": kind,
                    "recent_mentions": count,
                    "previous_mentions": previous,
                    "growth_pct": growth,
                    "source_count": source_count,
                    "score": score,
                    "status": status,
                    "evidence": bucket["evidence"][topic],
                })

        trends.sort(
            key=lambda item: (
                item["score"],
                item["source_count"],
                item["recent_mentions"],
                item["topic_type"] == "phrase",
            ),
            reverse=True,
        )

        # Reserve space for meaningful multiword signals.
        phrase_trends = [
            item for item in trends if item["topic_type"] == "phrase"
        ]
        word_trends = [
            item for item in trends if item["topic_type"] == "word"
        ]

        selected_trends = phrase_trends[:20] + word_trends[:40]
        selected_ids = {
            (item["topic_type"], item["topic"])
            for item in selected_trends
        }

        # Fill any unused places with the next-highest-ranked signals.
        for item in trends:
            if len(selected_trends) >= 60:
                break
            key = (item["topic_type"], item["topic"])
            if key not in selected_ids:
                selected_trends.append(item)
                selected_ids.add(key)

        # Keep the final display ordered by score and supporting evidence.
        selected_trends.sort(
            key=lambda item: (
                item["score"],
                item["source_count"],
                item["recent_mentions"],
                item["topic_type"] == "phrase",
            ),
            reverse=True,
        )

        timeline = []
        if dated:
            day = previous_start.date()
            end = latest_date.date()
            while day <= end:
                key = day.isoformat()
                timeline.append({
                    "date": key,
                    "count": daily_counts.get(key, 0)
                })
                day += timedelta(days=1)

        result = {
            "generated_at": now_dt.isoformat(),
            "effective_latest_date": latest_date.isoformat(),
            "record_count": len(records),
            "dated_count": len(dated),
            "undated_count": len(records) - len(dated),
            "source_count": len(source_counts),
            "sector_count": len(sector_counts),
            "sectors": [
                {"name": name, "count": count}
                for name, count in sector_counts.most_common(20)
            ],
            "sources": [
                {"name": name, "count": count}
                for name, count in source_counts.most_common(15)
            ],
            "timeline": timeline,
            "trends": selected_trends,
            "records": records,
        }

        _cache["data"] = result
        _cache["at"] = time.time()
        return result

@intelligence_bp.get("/intelligence/dashboard")
def intelligence_dashboard():
    return send_from_directory(FRONTEND_DIR, "intelligence.html")

@intelligence_bp.get("/intelligence/api/overview")
def intelligence_overview():
    data = load_records()
    return jsonify({
        key: value for key, value in data.items()
        if key != "records"
    })

@intelligence_bp.get("/intelligence/api/records")
def intelligence_records():
    data = load_records()
    query = request.args.get("q", "").strip().lower()[:200]
    sector = request.args.get("sector", "").strip().lower()[:100]

    try:
        page = max(1, min(100000, int(request.args.get("page", "1"))))
    except (ValueError, TypeError):
        page = 1

    matched = []
    for record in data["records"]:
        if sector and sector not in record["_sectors"]:
            continue

        title = str(record.get("title") or "")
        summary = str(record.get("summary") or "")
        source = str(record.get("source_name") or record.get("source_id") or "")

        if query and query not in (
            title + " " + summary + " " + source
        ).lower():
            continue

        dt = record.get("_effective_date")
        matched.append({
            "id": record.get("id", ""),
            "title": title or "Untitled",
            "summary": summary[:600],
            "url": record.get("url", ""),
            "source": source or "Unknown source",
            "source_type": record.get("source_type", "unknown"),
            "sectors": record["_sectors"],
            "published": (
                dt.isoformat() if dt
                else str(
                    record.get("published")
                    or record.get("fetched_at")
                    or record.get("updated")
                    or ""
                )
            ),
        })

    matched.sort(key=lambda item: item["published"], reverse=True)
    size = 25
    start = (page - 1) * size

    return jsonify({
        "total": len(matched),
        "page": page,
        "page_size": size,
        "records": matched[start:start + size],
    })

@intelligence_bp.get("/intelligence/api/health")
def intelligence_health():
    return jsonify({
        "ok": DATA_DIR.exists(),
        "data_directory": str(DATA_DIR),
        "cached": _cache["data"] is not None,
        "cache_seconds": CACHE_SECONDS,
    })

@intelligence_bp.get("/intelligence/api/network")
def intelligence_network():
    """Build an evidence-backed network from recently dated research records."""
    data = load_records()
    trends = data.get("trends", [])
    records = data.get("records", [])

    phrases = [t for t in trends if t.get("topic_type") == "phrase"]
    words = [t for t in trends if t.get("topic_type") == "word"]

    selected = phrases[:20] + words[:15]
    selected_keys = {
        (t.get("topic_type"), t.get("topic"))
        for t in selected
    }

    for trend in trends:
        key = (trend.get("topic_type"), trend.get("topic"))
        if key not in selected_keys and len(selected) < 35:
            selected.append(trend)
            selected_keys.add(key)

    if not selected:
        return jsonify({
            "nodes": [],
            "edges": [],
            "record_count": 0,
            "topic_count": 0,
            "window_start": None,
            "window_end": None,
        })

    latest = max(
        (r.get("_effective_date") for r in records
         if r.get("_effective_date")),
        default=None,
    )
    if latest is None:
        return jsonify({
            "nodes": [],
            "edges": [],
            "record_count": 0,
            "topic_count": 0,
            "window_start": None,
            "window_end": None,
        })

    start = latest - timedelta(days=30)
    topic_lookup = {}
    for trend in selected:
        kind = trend.get("topic_type")
        topic = trend.get("topic")
        if kind in ("word", "phrase") and topic:
            topic_lookup[(kind, topic)] = trend

    topic_records = Counter()
    topic_sources = defaultdict(set)
    topic_sectors = Counter()
    topic_source_counts = Counter()
    cooccurrence = Counter()
    sector_totals = Counter()
    source_totals = Counter()
    record_count = 0

    for record in records:
        dt = record.get("_effective_date")
        if not dt or dt < start or dt > latest:
            continue

        record_count += 1
        source = str(
            record.get("source_name")
            or record.get("source_id")
            or "Unknown source"
        )[:160]
        sectors = set(record.get("_sectors") or [])
        source_totals[source] += 1

        for sector in sectors:
            sector_totals[sector] += 1

        found = []
        word_set = set(record.get("_topic_words") or [])
        phrase_set = set(record.get("_topic_phrases") or [])

        for (kind, topic), trend in topic_lookup.items():
            matches = phrase_set if kind == "phrase" else word_set
            if topic in matches:
                found.append((kind, topic))
                topic_records[(kind, topic)] += 1
                topic_sources[(kind, topic)].add(source)
                topic_source_counts[((kind, topic), source)] += 1
                for sector in sectors:
                    topic_sectors[((kind, topic), sector)] += 1

        # Co-occurrence means appearing in the same indexed record.
        # It is an observed association, not proof of causation.
        unique_found = sorted(set(found))
        for i, left in enumerate(unique_found):
            for right in unique_found[i + 1:]:
                cooccurrence[(left, right)] += 1

    nodes = []
    edges = []
    node_ids = set()

    def topic_id(key):
        return f"topic:{key[0]}:{key[1]}"

    def add_node(node_id, label, group, value, title, description):
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append({
            "id": node_id,
            "label": str(label)[:160],
            "group": group,
            "value": max(1, min(40, int(value or 1))),
            "title": str(title)[:300],
            "description": str(description)[:400],
        })

    def add_edge(left, right, weight, title, kind):
        if left == right or left not in node_ids or right not in node_ids:
            return
        edges.append({
            "from": left,
            "to": right,
            "value": max(1, min(12, int(weight))),
            "title": str(title)[:300],
            "kind": kind,
        })

    for trend in selected:
        key = (trend.get("topic_type"), trend.get("topic"))
        count = topic_records[key]
        if not count:
            continue
        label = key[1]
        sources = len(topic_sources[key])
        group = "topic_phrase" if key[0] == "phrase" else "topic_word"
        add_node(
            topic_id(key), label, group, count,
            f"{label}: {count} records",
            f"{count} records in the latest 30-day window; "
            f"{sources} distinct sources. Backend trend score: "
            f"{trend.get('score', 0)}/100.",
        )

    # Show the strongest topic-to-topic relationships.
    pair_edges = [
        (pair, count) for pair, count in cooccurrence.items()
        if count >= 2
    ]
    pair_edges.sort(key=lambda item: item[1], reverse=True)

    for (left, right), count in pair_edges[:55]:
        add_edge(
            topic_id(left), topic_id(right), count,
            f"Appeared together in {count} recent records",
            "cooccurrence",
        )

    # Limit the map to the most frequently observed sectors and sources.
    top_sectors = {name for name, _ in sector_totals.most_common(8)}
    top_sources = {name for name, _ in source_totals.most_common(8)}

    for sector in top_sectors:
        add_node(
            f"sector:{sector}", sector, "sector", sector_totals[sector],
            f"Sector: {sector}",
            f"{sector_totals[sector]} recent records tagged with this sector.",
        )

    for source in top_sources:
        add_node(
            f"source:{source}", source, "source", source_totals[source],
            f"Source: {source}",
            f"{source_totals[source]} recent records in the indexed collection.",
        )

    sector_edges = [
        (pair, count) for pair, count in topic_sectors.items()
        if pair[1] in top_sectors and count >= 2
    ]
    sector_edges.sort(key=lambda item: item[1], reverse=True)

    for ((kind, topic), sector), count in sector_edges[:45]:
        add_edge(
            topic_id((kind, topic)), f"sector:{sector}", count,
            f"Tagged to this sector in {count} records",
            "topic-sector",
        )

    source_edges = [
        (pair, count) for pair, count in topic_source_counts.items()
        if pair[1] in top_sources and count >= 2
    ]
    source_edges.sort(key=lambda item: item[1], reverse=True)

    for ((kind, topic), source), count in source_edges[:45]:
        add_edge(
            topic_id((kind, topic)), f"source:{source}", count,
            f"Found in {count} records from this source",
            "topic-source",
        )

    return jsonify({
        "nodes": nodes,
        "edges": edges,
        "record_count": record_count,
        "topic_count": sum(
            1 for node in nodes
            if node["group"] in ("topic_phrase", "topic_word")
        ),
        "window_start": start.isoformat(),
        "window_end": latest.isoformat(),
    })
