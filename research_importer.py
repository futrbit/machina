import argparse
import hashlib
import html
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import deep_raw_research as research

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "intelligence" / "deep_raw_index.sqlite3"
USER_AGENT = "MachinaDailyResearchImporter/1.0 (research metadata discovery)"

def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def canonical_url(value):
    value = (value or "").strip().lower()
    value = re.sub(r"[?#].*$", "", value)
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value).rstrip("/")
    value = re.sub(r"^doi\.org/", "", value)
    # Treat arXiv version URLs as the same underlying paper.
    value = re.sub(r"(arxiv\.org/abs/[^/]+)v\d+$", r"\1", value)
    # Supplementary-material DOIs often point to the same underlying paper.
    value = re.sub(r"\.s\d{3,}$", "", value)
    value = re.sub(r"/(?:full|pdf)$", "", value)
    return value


def relevant_battery_record(item):
    title = clean_text(item.get("title", "")).lower()
    summary = clean_text(item.get("summary", "")).lower()
    combined = title + " " + summary

    # Exclude quantum battery theory from this practical battery-technology
    # collection. It can be collected separately with its own query.
    if "quantum battery" in combined or "quantum batteries" in combined:
        return False

    battery_terms = (
        "battery", "batteries", "lithium-ion", "lithium ion",
        "lithium-metal", "lithium metal", "cathode", "anode",
        "electrolyte", "electrochemical energy storage",
        "battery energy storage", "state of charge",
        "battery degradation", "battery health",
        "battery management", "solid-state battery",
        "redox flow battery", "sodium-ion battery",
        "lithium sulfur battery", "lithium-sulfur battery",
        "battery pack", "battery thermal", "battery charging"
    )

    if not any(term in combined for term in battery_terms):
        return False

    if any(term in title for term in (
        "globular cluster", "cosmological lithium", "lithium problem",
        "dark energy", "cosmic sound"
    )):
        return False

    if title.startswith("correction to "):
        return False

    return True

def stable_id(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        import json
        return json.loads(response.read().decode("utf-8", errors="replace"))

def fetch_xml(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/atom+xml, application/xml",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return ET.fromstring(response.read())

def fetch_arxiv(query, limit):
    atom = "{http://www.w3.org/2005/Atom}"
    search_query = "all:" + query.replace('"', "")
    params = urllib.parse.urlencode({
        "search_query": search_query,
        "start": 0,
        "max_results": limit,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    url = "https://export.arxiv.org/api/query?" + params
    root = fetch_xml(url)
    records = []

    for entry in root.findall(atom + "entry"):
        title = clean_text(entry.findtext(atom + "title", ""))
        summary = clean_text(entry.findtext(atom + "summary", ""))
        link = ""
        for item in entry.findall(atom + "link"):
            href = item.attrib.get("href", "")
            if item.attrib.get("rel") == "alternate" and href:
                link = href
                break
        if not link:
            link = clean_text(entry.findtext(atom + "id", ""))

        published = clean_text(entry.findtext(atom + "published", ""))
        categories = [
            item.attrib.get("term", "")
            for item in entry.findall(
                "{http://arxiv.org/schemas/atom}primary_category"
            )
        ]
        if not title or not link:
            continue

        records.append({
            "title": title,
            "summary": summary or "No abstract supplied by arXiv.",
            "sectors": "research arxiv " + " ".join(categories),
            "source_name": "arXiv",
            "url": link,
            "published": published,
            "source_file": "external:arxiv",
        })
    return records

def fetch_crossref(query, limit):
    params = urllib.parse.urlencode({
        "query.bibliographic": query,
        "rows": limit,
        "select": "DOI,title,abstract,published,created,URL,type",
    })
    url = "https://api.crossref.org/works?" + params
    payload = fetch_json(url)
    items = payload.get("message", {}).get("items", [])
    records = []

    for item in items:
        titles = item.get("title") or []
        title = clean_text(titles[0] if titles else "")
        doi = clean_text(item.get("DOI", ""))
        link = ("https://doi.org/" + doi) if doi else item.get("URL", "")
        if not title or not link:
            continue

        abstract = clean_text(item.get("abstract", ""))
        date_parts = (
            item.get("published", {}).get("date-parts")
            or item.get("created", {}).get("date-parts")
            or []
        )
        published = ""
        if date_parts and date_parts[0]:
            published = "-".join(str(x) for x in date_parts[0])

        records.append({
            "title": title,
            "summary": abstract or "No abstract supplied by Crossref.",
            "sectors": "research crossref " + clean_text(item.get("type", "")),
            "source_name": "Crossref",
            "url": link,
            "published": published,
            "source_file": "external:crossref",
        })
    return records

def existing_keys(connection):
    keys = set()
    for row in connection.execute("SELECT title, url FROM papers"):
        url = canonical_url(row["url"])
        title = re.sub(r"\s+", " ", (row["title"] or "").lower()).strip()
        if url:
            keys.add("url:" + url)
        if title:
            keys.add("title:" + title)
    return keys

def main():
    parser = argparse.ArgumentParser(
        description="Discover and optionally import scholarly metadata into MachinaDaily."
    )
    parser.add_argument(
        "--query",
        default="battery lithium energy density",
        help="Research topic to search for",
    )
    parser.add_argument("--limit", type=int, default=20,
                        help="Maximum records per source, 1-50")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Save new records to the existing database; otherwise preview only",
    )
    args = parser.parse_args()
    args.limit = max(1, min(args.limit, 50))

    print("MachinaDaily Research Importer")
    print("Topic:", args.query)
    print("Database:", DB_PATH)
    print("Mode:", "IMPORT" if args.write else "PREVIEW ONLY")

    candidates = []
    for source, fetcher in (
        ("arXiv", fetch_arxiv),
        ("Crossref", fetch_crossref),
    ):
        try:
            results = fetcher(args.query, args.limit)
            print(f"{source}: retrieved {len(results)} records")
            candidates.extend(results)
        except Exception as exc:
            print(f"{source} request failed: {type(exc).__name__}: {exc}")

    if not candidates:
        print("No records retrieved. Nothing was changed.")
        return

    before_filter = len(candidates)
    candidates = [
        item for item in candidates
        if relevant_battery_record(item)
    ]

    # Deduplicate within this search before comparing with the database.
    deduped = []
    candidate_keys = set()
    for item in candidates:
        url_key = "url:" + canonical_url(item["url"])
        title_key = "title:" + re.sub(
            r"\\s+", " ", item["title"].lower()
        ).strip()

        if url_key in candidate_keys or title_key in candidate_keys:
            continue

        candidate_keys.add(url_key)
        candidate_keys.add(title_key)
        deduped.append(item)

    candidates = deduped
    print(
        f"Relevance filter kept {len(candidates)} of "
        f"{before_filter} candidates."
    )

    if args.write:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_backup = DB_PATH.with_name(
            f"deep_raw_index_PRE_IMPORT_{stamp}.sqlite3"
        )
        # Use SQLite's backup API for a consistent database snapshot.
        with sqlite3.connect(str(DB_PATH)) as src_db:
            with sqlite3.connect(str(db_backup)) as dst_db:
                src_db.backup(dst_db)
        print("Database backup:", db_backup)

    connection = research.connect()
    connection.row_factory = sqlite3.Row
    inserted = 0
    duplicates = 0
    seen = existing_keys(connection)

    try:
        for item in candidates:
            url_key = "url:" + canonical_url(item["url"])
            title_key = "title:" + re.sub(
                r"\s+", " ", item["title"].lower()
            ).strip()

            if url_key in seen or title_key in seen:
                duplicates += 1
                continue

            print(f"\nNEW: {item['title']}")
            print("  Source:", item["source_name"])
            print("  URL:", item["url"])
            print("  Abstract:", item["summary"][:280])

            if args.write:
                paper_id = stable_id(item["url"])
                connection.execute("""
                    INSERT OR IGNORE INTO papers
                    (paper_id, title, summary, sectors, source_name,
                     url, published, source_file)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    paper_id,
                    item["title"],
                    item["summary"],
                    item["sectors"],
                    item["source_name"],
                    item["url"],
                    item["published"] or datetime.now(timezone.utc).isoformat(),
                    item["source_file"],
                ))
                inserted += connection.execute(
                    "SELECT changes()"
                ).fetchone()[0]
                seen.add(url_key)
                seen.add(title_key)

        if args.write:
            connection.commit()

            # External-content FTS tables normally update via triggers.
            # Rebuild only if the database has no papers-table triggers.
            triggers = connection.execute("""
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='trigger' AND tbl_name='papers'
            """).fetchone()[0]

            if not triggers and inserted:
                connection.execute(
                    "INSERT INTO papers_fts(papers_fts) VALUES ('rebuild')"
                )
                connection.commit()

        print("\n=== IMPORT SUMMARY ===")
        print("Candidates retrieved:", len(candidates))
        print("Existing/duplicate candidates skipped:", duplicates)
        print("Records inserted:", inserted if args.write else 0)
        if not args.write:
            print("Preview only: database was not modified.")
        else:
            print("Database total:", connection.execute(
                "SELECT COUNT(*) FROM papers"
            ).fetchone()[0])
    finally:
        connection.close()

if __name__ == "__main__":
    main()
