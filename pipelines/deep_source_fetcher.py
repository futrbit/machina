import os
import re
import json
import time
import hashlib
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import feedparser

try:
    from .deep_sources import DEEP_SOURCES
except ImportError:
    from deep_sources import DEEP_SOURCES


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "deep_raw")

USER_AGENT = (
    "MachinaDaily/1.0 "
    "(Deep Source Intelligence Research System)"
)

AUDIO_EXTENSIONS = (
    ".mp3",
    ".m4a",
    ".wav",
    ".aac",
    ".ogg",
    ".opus",
)


def ensure_directories():
    os.makedirs(RAW_DIR, exist_ok=True)


def clean_text(value):
    if not value:
        return ""

    value = re.sub(r"<[^>]+>", " ", str(value))
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def canonical_url(url):
    if not url:
        return ""

    url = url.strip()

    parsed = urllib.parse.urlsplit(url)

    query = urllib.parse.parse_qsl(
        parsed.query,
        keep_blank_values=True
    )

    filtered_query = [
        (key, value)
        for key, value in query
        if not key.lower().startswith("utm_")
    ]

    query_string = urllib.parse.urlencode(filtered_query)

    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            query_string,
            ""
        )
    )


def make_id(source_id, url, title):
    base = "|".join(
        [
            source_id or "",
            canonical_url(url),
            clean_text(title).lower(),
        ]
    )

    return hashlib.sha256(
        base.encode("utf-8")
    ).hexdigest()


def fetch_html(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=20
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="replace"
        )


def discover_feed(url):
    try:
        html = fetch_html(url)
    except Exception:
        return None

    patterns = [
        r'<link[^>]+rel=["\']?[^"\'>]*alternate[^"\'>]*["\']?[^>]+type=["\']application/rss\+xml["\'][^>]+href=["\']([^"\']+)',
        r'<link[^>]+rel=["\']?[^"\'>]*alternate[^"\'>]*["\']?[^>]+type=["\']application/atom\+xml["\'][^>]+href=["\']([^"\']+)',
        r'<link[^>]+type=["\']application/rss\+xml["\'][^>]+href=["\']([^"\']+)',
        r'<link[^>]+type=["\']application/atom\+xml["\'][^>]+href=["\']([^"\']+)',
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            html,
            flags=re.IGNORECASE
        )

        if match:
            discovered = match.group(1)

            return urllib.parse.urljoin(
                url,
                discovered
            )

    return None


def parse_date(entry):
    for field in (
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ):

        parsed = entry.get(field)

        if parsed:
            try:
                return datetime(
                    *parsed[:6],
                    tzinfo=timezone.utc
                ).isoformat()
            except Exception:
                pass

    return ""


def find_audio_url(entry):
    candidates = []

    for enclosure in entry.get(
        "enclosures",
        []
    ):

        href = enclosure.get("href")

        if href:
            candidates.append(href)

    for link in entry.get(
        "links",
        []
    ):

        href = link.get("href")

        if href:
            candidates.append(href)

    for url in candidates:

        lower = url.lower()

        if any(
            lower.split("?")[0].endswith(ext)
            for ext in AUDIO_EXTENSIONS
        ):
            return url

    for enclosure in entry.get(
        "enclosures",
        []
    ):

        href = enclosure.get("href")

        mime = (
            enclosure.get("type")
            or ""
        ).lower()

        if href and (
            mime.startswith("audio/")
            or "mpeg" in mime
            or "mp4" in mime
        ):
            return href

    return ""


def parse_feed(source, feed_url):
    parsed = feedparser.parse(
        feed_url,
        agent=USER_AGENT
    )

    entries = []

    for entry in parsed.entries:

        title = clean_text(
            entry.get("title", "")
        )

        url = (
            entry.get("link")
            or entry.get("id")
            or ""
        )

        url = canonical_url(url)

        if not title and not url:
            continue

        summary = clean_text(
            entry.get("summary")
            or entry.get("description")
            or ""
        )

        audio_url = find_audio_url(
            entry
        )

        item_id = make_id(
            source["id"],
            url,
            title
        )

        item = {
            "id": item_id,
            "source_id": source["id"],
            "source_name": source["name"],
            "source_type": source["type"],
            "source_url": source["url"],
            "sectors": source.get(
                "sectors",
                []
            ),
            "title": title,
            "url": url,
            "summary": summary,
            "published": parse_date(entry),
            "audio_url": audio_url,
            "fetched_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        entries.append(item)

    return entries



def parse_sitemap(source, sitemap_url):
    xml_text = fetch_html(sitemap_url)
    root = ET.fromstring(xml_text)

    # Support both normal URL sitemaps and sitemap indexes.
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    items = []

    if root.tag.endswith("sitemapindex"):
        child_sitemaps = [
            node.findtext(namespace + "loc", default="").strip()
            for node in root.findall(namespace + "sitemap")
        ]
        for child_url in child_sitemaps:
            if not child_url:
                continue
            try:
                child_items = parse_sitemap(source, child_url)
                items.extend(child_items)
            except Exception as exc:
                print(f"  Sitemap child skipped: {child_url} ({exc})")
        return items

    for node in root.findall(namespace + "url"):
        url = node.findtext(namespace + "loc", default="").strip()
        lastmod = node.findtext(namespace + "lastmod", default="").strip()

        if not url:
            continue

        url = canonical_url(url)
        parsed_url = urllib.parse.urlsplit(url)
        path = parsed_url.path.lower()

        # Restrict discovery to the known article sections of these sites.
        article_path = source.get("sitemap_article_path", "")
        if article_path and article_path not in path:
            continue

        slug = parsed_url.path.rstrip("/").split("/")[-1]
        title = re.sub(r"[-_]+", " ", slug)
        title = clean_text(title)

        if not title:
            continue

        published = ""
        if lastmod:
            try:
                normalized = lastmod.replace("Z", "+00:00")
                parsed_date = datetime.fromisoformat(normalized)
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                published = parsed_date.astimezone(timezone.utc).isoformat()
            except Exception:
                published = lastmod

        item_id = make_id(source["id"], url, title)

        items.append({
            "id": item_id,
            "source_id": source["id"],
            "source_name": source["name"],
            "source_type": source["type"],
            "source_url": source["url"],
            "sectors": source.get("sectors", []),
            "title": title,
            "url": url,
            "summary": "",
            "published": published,
            "audio_url": "",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })

    return items


def save_item(item):
    path = os.path.join(
        RAW_DIR,
        f"{item['id']}.json"
    )

    if os.path.exists(path):
        return False

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as handle:

        json.dump(
            item,
            handle,
            ensure_ascii=False,
            indent=2
        )

    return True


def process_source(source):
    print(
        f"\\n[{source['type'].upper()}] "
        f"{source['name']}"
    )

    feed_url = source.get("feed")
    discovered = False

    if not feed_url:
        print("  Discovering RSS/Atom...")
        feed_url = discover_feed(source["url"])
        if feed_url:
            discovered = True

    sitemap_url = source.get("sitemap")

    # Preserve RSS/Atom as the preferred path. Use the sitemap only when
    # no feed is configured or discoverable.
    if feed_url:
        print(f"  Feed: {feed_url}")
        if discovered:
            print("  Feed discovered automatically.")
        try:
            items = parse_feed(source, feed_url)
        except Exception as exc:
            print(f"  ERROR reading feed: {exc}")
            return {
                "source": source["name"],
                "status": "error",
                "items": 0,
                "error": str(exc),
            }

    elif sitemap_url:
        print(f"  Sitemap: {sitemap_url}")
        try:
            items = parse_sitemap(source, sitemap_url)
        except Exception as exc:
            print(f"  ERROR reading sitemap: {exc}")
            return {
                "source": source["name"],
                "status": "error",
                "items": 0,
                "error": str(exc),
            }

    else:
        print("  No RSS/Atom feed or sitemap configured.")
        return {
            "source": source["name"],
            "status": "no_feed",
            "items": 0,
        }

    saved = 0
    existing = 0

    for item in items:
        if save_item(item):
            saved += 1
        else:
            existing += 1

    print(f"  Entries: {len(items)}")
    print(f"  New: {saved}")
    print(f"  Existing: {existing}")

    audio_count = sum(1 for item in items if item.get("audio_url"))
    if audio_count:
        print(f"  Podcast audio URLs: {audio_count}")

    return {
        "source": source["name"],
        "status": "ok",
        "items": len(items),
        "new": saved,
        "existing": existing,
        "audio_urls": audio_count,
    }


def main():

    ensure_directories()

    print(
        "========================================"
    )

    print(
        "MACHINA DEEP SOURCE FETCHER"
    )

    print(
        "========================================"
    )

    print(
        f"Sources: {len(DEEP_SOURCES)}"
    )

    results = []

    total_items = 0
    total_new = 0
    total_audio = 0

    for index, source in enumerate(
        DEEP_SOURCES,
        start=1
    ):

        print(
            f"\nSOURCE {index}/{len(DEEP_SOURCES)}"
        )

        result = process_source(
            source
        )

        results.append(result)

        total_items += result.get(
            "items",
            0
        )

        total_new += result.get(
            "new",
            0
        )

        total_audio += result.get(
            "audio_urls",
            0
        )

        time.sleep(0.25)

    summary = {
        "fetched_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "source_count": len(
            DEEP_SOURCES
        ),

        "total_items": total_items,

        "total_new": total_new,

        "total_audio_urls": total_audio,

        "results": results,
    }

    summary_path = os.path.join(
        RAW_DIR,
        "_run.json"
    )

    with open(
        summary_path,
        "w",
        encoding="utf-8"
    ) as handle:

        json.dump(
            summary,
            handle,
            ensure_ascii=False,
            indent=2
        )

    print(
        "\n========================================"
    )

    print(
        "DEEP SOURCE FETCH COMPLETE"
    )

    print(
        "========================================"
    )

    print(
        f"Sources scanned: {len(DEEP_SOURCES)}"
    )

    print(
        f"Items found: {total_items}"
    )

    print(
        f"New items saved: {total_new}"
    )

    print(
        f"Podcast audio URLs: {total_audio}"
    )

    print(
        f"Stored in: {RAW_DIR}"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":
    main()
