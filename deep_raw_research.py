
#!/usr/bin/env python3
"""MachinaDaily local research search and Ollama Q&A."""
import argparse
import json
import re
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "data" / "deep_raw"
DB_PATH = ROOT / "data" / "intelligence" / "deep_raw_index.sqlite3"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen3:4b"


def text_value(value):
    """Convert JSON values into searchable text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(text_value(v) for v in value if v is not None)
    if isinstance(value, dict):
        return " ".join(
            f"{k}: {text_value(v)}"
            for k, v in value.items()
            if v is not None
        )
    return ""


def field(record, *names):
    for name in names:
        value = text_value(record.get(name))
        if value:
            return value
    return ""


def extract_records(data):
    """Support individual records and common JSON collection formats."""
    if isinstance(data, list):
        for item in data:
            yield from extract_records(item)
        return

    if not isinstance(data, dict):
        return

    for key in ("papers", "articles", "records", "results", "items", "data"):
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                yield from extract_records(item)
            return

    if any(k in data for k in ("title", "summary", "abstract", "url")):
        yield data


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    db.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY,
            paper_id TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            sectors TEXT NOT NULL,
            source_name TEXT NOT NULL,
            url TEXT NOT NULL,
            published TEXT NOT NULL,
            source_file TEXT NOT NULL,
            UNIQUE(source_file, paper_id, title)
        )
    """)

    db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
            title, summary, sectors, source_name, paper_id, url,
            content='papers',
            content_rowid='id'
        )
    """)

    db.executescript("""
        CREATE TRIGGER IF NOT EXISTS papers_insert
        AFTER INSERT ON papers BEGIN
            INSERT INTO papers_fts(
                rowid, title, summary, sectors, source_name, paper_id, url
            ) VALUES (
                new.id, new.title, new.summary, new.sectors,
                new.source_name, new.paper_id, new.url
            );
        END;

        CREATE TRIGGER IF NOT EXISTS papers_delete
        AFTER DELETE ON papers BEGIN
            INSERT INTO papers_fts(
                papers_fts, rowid, title, summary, sectors, source_name,
                paper_id, url
            ) VALUES (
                'delete', old.id, old.title, old.summary, old.sectors,
                old.source_name, old.paper_id, old.url
            );
        END;

        CREATE TRIGGER IF NOT EXISTS papers_update
        AFTER UPDATE ON papers BEGIN
            INSERT INTO papers_fts(
                papers_fts, rowid, title, summary, sectors, source_name,
                paper_id, url
            ) VALUES (
                'delete', old.id, old.title, old.summary, old.sectors,
                old.source_name, old.paper_id, old.url
            );
            INSERT INTO papers_fts(
                rowid, title, summary, sectors, source_name, paper_id, url
            ) VALUES (
                new.id, new.title, new.summary, new.sectors,
                new.source_name, new.paper_id, new.url
            );
        END;
    """)
    db.commit()
    return db


def build_index(rebuild=False):
    if not SOURCE_DIR.is_dir():
        raise SystemExit(f"Research directory not found: {SOURCE_DIR}")

    files = sorted(SOURCE_DIR.rglob("*.json"))
    if not files:
        raise SystemExit(f"No JSON files found in {SOURCE_DIR}")

    db = connect()

    if rebuild:
        db.execute("DELETE FROM papers")
        db.execute("INSERT INTO papers_fts(papers_fts) VALUES ('rebuild')")
        db.commit()

    examined = 0
    saved = 0
    errors = []

    for number, path in enumerate(files, start=1):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))

            for record in extract_records(data):
                examined += 1

                title = field(record, "title", "name")
                summary = field(
                    record, "summary", "abstract", "description", "text"
                )

                if not title and not summary:
                    continue

                paper_id = field(
                    record, "arxiv_id", "paper_id", "id",
                    "arxiv_metadata_id"
                ) or path.stem

                url = field(
                    record, "url", "paper_url", "link",
                    "arxiv_metadata_id"
                )

                if not url and paper_id:
                    cleaned_id = paper_id.replace(
                        "https://arxiv.org/abs/", ""
                    ).replace("http://arxiv.org/abs/", "")

                    if re.match(r"^\d{4}\.\d{4,5}", cleaned_id):
                        url = f"https://arxiv.org/abs/{cleaned_id}"

                values = (
                    paper_id,
                    title or "(Untitled research record)",
                    summary,
                    field(record, "sectors", "categories", "tags", "category"),
                    field(record, "source_name", "source_id"),
                    url,
                    field(record, "published", "published_at", "date", "updated"),
                    str(path.relative_to(ROOT)),
                )

                db.execute("""
                    INSERT INTO papers (
                        paper_id, title, summary, sectors, source_name,
                        url, published, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_file, paper_id, title) DO UPDATE SET
                        summary=excluded.summary,
                        sectors=excluded.sectors,
                        source_name=excluded.source_name,
                        url=excluded.url,
                        published=excluded.published
                """, values)
                saved += 1

        except Exception as exc:
            errors.append((str(path), str(exc)))

        if number % 1000 == 0:
            db.commit()
            print(f"Processed {number:,} of {len(files):,} files")

    db.commit()

    # Ensure the full-text index includes every paper already in the database.
    db.execute("INSERT INTO papers_fts(papers_fts) VALUES ('rebuild')")
    db.commit()

    total = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

    print("\nDEEP RESEARCH INDEX COMPLETE")
    print(f"JSON files found:  {len(files):,}")
    print(f"Records examined:  {examined:,}")
    print(f"Records processed: {saved:,}")
    print(f"Indexed papers:    {total:,}")
    print(f"Errors:            {len(errors):,}")
    print(f"Database:          {DB_PATH}")

    for path, error in errors[:10]:
        print(f"ERROR: {path}: {error}")

    db.close()


def search_papers(query, limit=8):
    """Search the local research index with topic-aware evidence ranking."""
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9._+-]*", query or "")
    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "how", "in", "is", "of", "on", "or", "the", "to", "what", "when",
        "where", "which", "with", "using", "use", "why", "technology",
        "technologies", "research", "study", "studies", "paper", "papers",
        "latest", "new", "recent", "overview", "analysis", "review",
        "impact", "development", "developments", "application", "applications",
        "based", "approach", "method", "methods", "system", "systems"
    }

    terms = []
    for word in words:
        word = word.lower().strip("._+-")
        if len(word) > 1 and word not in terms:
            terms.append(word)

    focused_terms = [t for t in terms if t not in stopwords]
    if not focused_terms:
        focused_terms = terms
    if not focused_terms:
        print("Enter a more specific search term.")
        return []

    def variants(term):
        forms = {term}
        if term.endswith("y") and len(term) > 3:
            forms.add(term[:-1] + "ies")
        if term.endswith("ies") and len(term) > 4:
            forms.add(term[:-3] + "y")
        if term.endswith("s") and not term.endswith("ss") and len(term) > 3:
            forms.add(term[:-1])
        else:
            forms.add(term + "s")
        return forms

    term_forms = {t: variants(t) for t in focused_terms}

    # Expand retrieval vocabulary for battery topics, but score relevance
    # primarily against the concepts the user actually requested.
    query_text = " ".join(focused_terms)
    battery_markers = {
        "battery", "batteries", "lithium", "cathode", "anode",
        "electrolyte", "electrochemical", "storage"
    }
    battery_query = bool(set(focused_terms) & battery_markers)

    expansion = set()
    if battery_query:
        expansion.update({
            "battery", "batteries", "lithium", "ion", "cathode", "anode",
            "electrolyte", "electrochemical", "degradation", "thermal",
            "cooling", "flight", "drone", "drones", "energy", "density",
            "storage", "charging", "discharging", "power", "pack", "packs",
            "health", "capacity", "cycle"
        })

    retrieval_terms = set(focused_terms) | expansion
    fts_terms = set()
    for term in retrieval_terms:
        fts_terms.update(variants(term))

    match_query = " OR ".join(
        '"' + term.replace('"', '""') + '"'
        for term in sorted(fts_terms)
    )

    limit = max(1, min(int(limit), 30))
    candidate_limit = min(4000, max(1000, limit * 120))
    db = connect()

    try:
        rows = db.execute("""
            SELECT
                p.paper_id, p.title, p.summary, p.sectors,
                p.source_name, p.url, p.published, p.source_file,
                bm25(papers_fts, 8.0, 1.0, 2.5, 1.0, 1.0, 0.5) AS score
            FROM papers_fts
            JOIN papers p ON p.id = papers_fts.rowid
            WHERE papers_fts MATCH ?
            ORDER BY score
            LIMIT ?
        """, (match_query, candidate_limit)).fetchall()
    except sqlite3.OperationalError as exc:
        print(f"Search error: {exc}")
        return []
    finally:
        db.close()

    def normalise(text):
        return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))

    def tokens(text):
        return set(re.findall(r"[a-z0-9]+", (text or "").lower()))

    def matches(term, text):
        return bool(tokens(text) & term_forms.get(term, {term}))

    query_phrase = normalise(query)
    query_tokens = query_phrase.split()

    drone_intent = bool(
        set(focused_terms) & {"drone", "drones", "uav", "uavs", "flight"}
    )
    thermal_intent = bool(
        set(focused_terms) & {"thermal", "cooling", "heat", "temperature"}
    )

    ranked = []
    for paper in rows:
        title = paper["title"] or ""
        summary = paper["summary"] or ""
        sectors = paper["sectors"] or ""
        url = paper["url"] or ""
        title_norm = normalise(title)
        summary_norm = normalise(summary)
        combined = title + " " + summary + " " + sectors
        combined_norm = normalise(combined)
        combined_words = set(combined_norm.split())

        # Require evidence of the specific subject, not just generic keyword overlap.
        if drone_intent and not (
            combined_words & {"drone", "drones", "uav", "uavs", "flight"}
        ):
            continue

        if thermal_intent and not (
            combined_words & {"thermal", "cooling", "heat", "temperature"}
        ):
            continue

        # Degradation may be described using related scientific terminology.
        degradation_intent = bool(
            set(focused_terms) & {
                "degradation", "degrade", "aging", "ageing",
                "deterioration", "fade", "fading"
            }
        )
        degradation_markers = {
            "degradation", "degrade", "degraded", "aging", "ageing",
            "deterioration", "cyclic", "cycling", "cycle", "cycles",
            "fade", "fading", "interfacial", "decomposition",
            "coulombic", "lifetime"
        }
        has_degradation_evidence = bool(
            combined_words & degradation_markers
        ) or any(
            phrase in combined_norm
            for phrase in (
                "capacity loss", "side reaction", "side reactions",
                "interfacial reactions", "cycling performance",
                "cycle life", "capacity retention"
            )
        )

        has_cathode_or_electrolyte_evidence = bool(
            combined_words & {
                "cathode", "cathodes", "electrolyte", "electrolytes",
                "anode", "anodes", "electrode", "electrodes"
            }
        )

        if degradation_intent and not (
            has_degradation_evidence and has_cathode_or_electrolyte_evidence
        ):
            continue

        # Do not treat provider placeholders as genuine research abstracts.
        summary_is_missing = (
            not summary_norm
            or summary_norm in {
                "no abstract supplied by crossref",
                "no abstract available",
                "abstract unavailable"
            }
            or len(summary_norm) < 80
        )

        title_hits = [t for t in focused_terms if matches(t, title)]
        summary_hits = [t for t in focused_terms if matches(t, summary)]
        sector_hits = [t for t in focused_terms if matches(t, sectors)]

        # Avoid unrelated papers matching only one generic word.
        if battery_query:
            if not any(
                re.search(
                    r"(?<!\w)" + re.escape(marker) + r"(?!\w)",
                    combined.lower()
                )
                for marker in battery_markers
            ):
                continue

        if len(focused_terms) >= 3:
            required = 2
            if len(set(title_hits + summary_hits)) < required:
                continue

        score = 0.0
        score += len(set(title_hits)) * 18
        score += len(set(summary_hits)) * (0 if summary_is_missing else 4)
        score += len(set(sector_hits)) * 1.5

        # Give the most specific requested concepts additional weight.
        specific_terms = {
            "drone", "drones", "uav", "uavs", "flight", "thermal",
            "cooling", "cathode", "anode", "electrolyte", "degradation",
            "lithium", "density", "capacity", "health", "charging"
        }
        for term in set(focused_terms) & specific_terms:
            if matches(term, title):
                score += 8
            elif not summary_is_missing and matches(term, summary):
                score += 2

        if query_phrase and query_phrase in title_norm:
            score += 24

        # Reward ordered query phrases in the title, but not generic overlap.
        for size in range(min(4, len(query_tokens)), 1, -1):
            phrase = " ".join(query_tokens[:size])
            if phrase and phrase in title_norm:
                score += size * 2
                break

        # Penalise weak evidence and supplementary-material DOI records.
        if summary_is_missing:
            score -= 12
        if re.search(r"\.s\d{3,}$", url.lower().split("?")[0]):
            score -= 10
        if (paper["source_file"] or "").endswith(":crossref"):
            score -= 1

        # Topic-specific bonuses for drone battery thermal questions.
        if drone_intent and any(
            term in combined_norm.split()
            for term in ("drone", "drones", "uav", "uavs", "flight")
        ):
            score += 16
        if thermal_intent and any(
            term in combined_norm.split()
            for term in ("thermal", "cooling", "heat", "temperature")
        ):
            score += 12

        # Keep the original BM25 contribution small: it is a useful tie-breaker.
        try:
            score += min(1.0, max(0.0, -float(paper["score"] or 0)) / 100)
        except (TypeError, ValueError):
            pass

        ranked.append((score, paper))

    ranked.sort(key=lambda item: item[0], reverse=True)

    def canonical_url(value):
        url = (value or "").strip().lower()
        url = re.sub(r"[?#].*$", "", url)
        url = re.sub(r"^https?://", "", url)
        url = re.sub(r"^www\.", "", url).rstrip("/")
        url = re.sub(r"^doi\.org/", "", url)
        url = re.sub(r"(arxiv\.org/abs/[^/]+)v\d+$", r"\1", url)
        url = re.sub(r"\.s\d{3,}$", "", url)
        url = re.sub(r"/(?:full|pdf)$", "", url)
        url = re.sub(r"^arxiv\.org/pdf/([^/]+)\.pdf$", r"arxiv.org/abs/\1", url)
        return url

    results = []
    seen_urls = set()
    seen_titles = set()

    for score, paper in ranked:
        url_key = canonical_url(paper["url"])
        title_key = normalise(paper["title"])

        if url_key and url_key in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue

        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)

        results.append(paper)
        if len(results) >= limit:
            break

    for number, paper in enumerate(results, 1):
        print(f"\n[{number}] {paper['title']}")
        print(f"    ID: {paper['paper_id']}")
        print(f"    Published: {paper['published']}")
        print(f"    Categories: {paper['sectors']}")
        if paper["url"]:
            print(f"    URL: {paper['url']}")
        summary = paper["summary"] or ""
        print(f"    Summary: {summary[:500]}")
        print(f"    File: {paper['source_file']}")

    if not results:
        print("No sufficiently relevant matching records. Try broader keywords.")

    return results

def ask_local_ai(question, model=DEFAULT_MODEL, limit=6):
    papers = search_papers(question, limit)

    if not papers:
        print("\nNo matching research was found. No AI answer generated.")
        return

    sources = "\n\n".join(
        f"[{i}] Title: {p['title']}\n"
        f"Paper ID: {p['paper_id']}\n"
        f"Published: {p['published']}\n"
        f"URL: {p['url']}\n"
        f"Categories: {p['sectors']}\n"
        f"Summary: {p['summary']}"
        for i, p in enumerate(papers, 1)
    )

    prompt = (
        "Answer the research question using only the supplied paper records. "
        "Cite supported claims using source numbers like [1] and [2]. "
        "Do not invent results, authors, or citations. Separate evidence from "
        "inference. If the records are insufficient, say so. End with a Sources "
        "list containing the exact paper titles and URLs.\n\n"
        f"RETRIEVED PAPERS:\n{sources}\n\n"
        f"QUESTION:\n{question}"
    )

    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "messages": [
            {
                "role": "system",
                "content": "You are a careful research assistant. Ground answers in the supplied sources."
            },
            {"role": "user", "content": prompt}
        ],
        "options": {"temperature": 0.2}
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    print(f"\nAsking local model: {model}\n")

    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            result = json.loads(response.read().decode("utf-8"))

        answer = result.get("message", {}).get("content", "").strip()

        if answer:
            print("\n" + answer)
        else:
            print("Ollama returned an empty answer. Try --model llama3.2:latest.")

    except urllib.error.URLError as exc:
        print(f"Could not connect to Ollama: {exc}")
        print("Check that Ollama is running on 127.0.0.1:11434.")


def main():
    parser = argparse.ArgumentParser(
        description="Local search and AI Q&A over MachinaDaily deep_raw."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    index_command = commands.add_parser("index", help="Index JSON research records")
    index_command.add_argument("--rebuild", action="store_true")

    search_command = commands.add_parser("search", help="Search without AI")
    search_command.add_argument("query")
    search_command.add_argument("--limit", type=int, default=8)

    ask_command = commands.add_parser("ask", help="Ask local Ollama about research")
    ask_command.add_argument("question")
    ask_command.add_argument("--model", default=DEFAULT_MODEL)
    ask_command.add_argument("--limit", type=int, default=6)

    args = parser.parse_args()

    if args.command == "index":
        build_index(args.rebuild)
    elif args.command == "search":
        search_papers(args.query, max(1, min(args.limit, 30)))
    elif args.command == "ask":
        ask_local_ai(args.question, args.model, max(1, min(args.limit, 10)))


if __name__ == "__main__":
    main()
