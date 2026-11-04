from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlparse
import json
import re
import tempfile
import unicodedata

from flask import Blueprint, abort, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
PUBLISH_DIR = ROOT / "data" / "research_articles"
INDEX_FILE = PUBLISH_DIR / "index.json"
SLOTS_FILE = PUBLISH_DIR / "featured_slots.json"
SITE_URL = "https://machinadaily.xyz"
SECTORS = {"ai", "drones", "robotics", "autonomy"}
publishing_bp = Blueprint("research_publishing", __name__)


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.stem + "_", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with open(fd, "w", encoding="utf-8", newline="\n", closefd=True) as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        Path(temp_name).replace(path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def all_articles():
    items = read_json(INDEX_FILE, [])
    return items if isinstance(items, list) else []


def all_slots():
    slots = read_json(SLOTS_FILE, {})
    return slots if isinstance(slots, dict) else {}


def slugify(value):
    value = unicodedata.normalize("NFKD", str(value))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:90].strip("-") or "research-story"


def safe_sector(value):
    sector = str(value or "").strip().lower()
    return sector if sector in SECTORS else None


def local_request():
    address = request.remote_addr or ""
    return address in {"127.0.0.1", "::1"}


def safe_sources(sources):
    if not isinstance(sources, list):
        return []
    result = []
    for source in sources[:30]:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        result.append({
            "title": str(source.get("title") or "Source")[:300],
            "url": url[:2000],
        })
    return result


def article_html(article):
    title = escape(article["title"])
    description = escape(article["description"], quote=True)
    canonical = SITE_URL + "/" + article["sector"] + "/" + article["slug"]
    paragraphs = []
    for line in article["body"].splitlines():
        line = line.strip()
        if line:
            paragraphs.append("<p>" + escape(line) + "</p>")
    source_html = []
    for i, source in enumerate(article["sources"], 1):
        source_html.append(
            '<li><a href="' + escape(source["url"], quote=True) +
            '" rel="noopener noreferrer">' + escape(source["title"]) +
            "</a></li>"
        )
    sources_section = ""
    if source_html:
        sources_section = "<h2>Sources</h2><ol>" + "".join(source_html) + "</ol>"
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>""" + title + """ | Machina Daily</title>
<meta name="description" content=\"""" + description + """\">
<meta name="robots" content="index,follow">
<link rel="canonical" href=\"""" + escape(canonical, quote=True) + """">
<meta property="og:type" content="article">
<meta property="og:title" content=\"""" + title + """">
<meta property="og:description" content=\"""" + description + """">
<meta property="og:url" content=\"""" + escape(canonical, quote=True) + """">
<style>
body{font:18px/1.75 system-ui,sans-serif;max-width:820px;margin:40px auto;padding:0 22px;color:#20242a}
header,footer{border-bottom:1px solid #ddd;padding-bottom:16px;margin-bottom:30px}
h1{font-size:clamp(2rem,6vw,3.5rem);line-height:1.12}
a{color:#087eaa;overflow-wrap:anywhere}
</style>
</head>
<body>
<header><a href="/">Machina Daily</a> / <a href="/""" + article["sector"] + """">""" + article["sector"].title() + """</a></header>
<main><article><p>""" + escape(article["sector"].title()) + """ research</p>
<h1>""" + title + """</h1>
<p><strong>""" + escape(article["standfirst"]) + """</strong></p>
""" + "".join(paragraphs) + sources_section + """
</article></main>
<footer><p>Research article. Claims should be read alongside the linked sources.</p></footer>
</body></html>
"""


@publishing_bp.get("/dashboard/api/published-stories")
def published_stories():
    sector = safe_sector(request.args.get("sector"))
    if not sector:
        return jsonify({"error": "Use sector=ai, drones, robotics or autonomy."}), 400
    articles = [a for a in all_articles() if a.get("sector") == sector]
    articles.sort(key=lambda a: a.get("published_at", ""), reverse=True)
    slots = all_slots().get(sector, {})
    featured = []
    for number in range(1, 11):
        slug = slots.get(str(number))
        article = next((a for a in articles if a.get("slug") == slug), None)
        featured.append({"slot": number, "article": article})
    return jsonify({
        "sector": sector,
        "featured": featured,
        "incoming": articles[:10],
        "total": len(articles),
        "archive_url": "/research-articles/" + sector,
    })


@publishing_bp.post("/dashboard/api/published-stories/publish")
def publish_story():
    if not local_request():
        abort(403)
    body = request.get_json(silent=True) or {}
    sector = safe_sector(body.get("sector"))
    title = str(body.get("title") or "").strip()[:240]
    draft = str(body.get("draft") or "").strip()
    description = str(body.get("description") or "").strip()[:300]
    standfirst = str(body.get("standfirst") or "").strip()[:500]
    sources = safe_sources(body.get("sources"))
    slot_value = body.get("featured_slot")
    slot = None
    if slot_value not in (None, "", 0, "0"):
        try:
            slot = int(slot_value)
        except (TypeError, ValueError):
            return jsonify({"error": "Featured slot must be a number from 1 to 10."}), 400
        if slot < 1 or slot > 10:
            return jsonify({"error": "Featured slot must be a number from 1 to 10."}), 400
    if not sector or not title or not draft:
        return jsonify({"error": "Sector, headline and article draft are required."}), 400
    if not description:
        description = (standfirst or draft).replace("\n", " ")[:240]
    slug = slugify(title)
    articles = all_articles()
    if any(a.get("sector") == sector and a.get("slug") == slug for a in articles):
        return jsonify({"error": "That headline already exists in this sector. Change the headline to create a distinct URL."}), 409
    article = {
        "sector": sector,
        "slug": slug,
        "title": title,
        "description": description,
        "standfirst": standfirst or description,
        "body": draft,
        "sources": sources,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "url": "/" + sector + "/" + slug,
    }
    folder = PUBLISH_DIR / sector
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / (slug + ".html")
    if destination.exists():
        return jsonify({"error": "The article file already exists; no files were overwritten."}), 409
    destination.write_text(article_html(article), encoding="utf-8")
    articles.append(article)
    try:
        write_json(INDEX_FILE, articles)
        if slot is not None:
            slots = all_slots()
            sector_slots = slots.setdefault(sector, {})
            sector_slots[str(slot)] = slug
            write_json(SLOTS_FILE, slots)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return jsonify({"status": "published", "article": article}), 201


@publishing_bp.post("/dashboard/api/published-stories/feature")
def feature_story():
    if not local_request():
        abort(403)
    body = request.get_json(silent=True) or {}
    sector = safe_sector(body.get("sector"))
    slug = str(body.get("slug") or "").strip()
    try:
        slot = int(body.get("slot"))
    except (TypeError, ValueError):
        return jsonify({"error": "Slot must be a number from 1 to 10."}), 400
    if not sector or not 1 <= slot <= 10:
        return jsonify({"error": "Valid sector and slot from 1 to 10 are required."}), 400
    if not any(a.get("sector") == sector and a.get("slug") == slug for a in all_articles()):
        return jsonify({"error": "Published article not found in that sector."}), 404
    slots = all_slots()
    slots.setdefault(sector, {})[str(slot)] = slug
    write_json(SLOTS_FILE, slots)
    return jsonify({"status": "featured", "sector": sector, "slot": slot, "slug": slug})


@publishing_bp.get("/research-articles/<sector>")
def research_archive(sector):
    sector = safe_sector(sector)
    if not sector:
        abort(404)
    articles = [a for a in all_articles() if a.get("sector") == sector]
    articles.sort(key=lambda a: a.get("published_at", ""), reverse=True)
    items = "".join(
        '<li><a href="/' + sector + '/' + escape(a["slug"], quote=True) + '">' +
        escape(a["title"]) + "</a></li>"
        for a in articles
    )
    if not items:
        items = "<li>No published stories yet.</li>"
    return (
        "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>" + sector.title() + " research archive | Machina Daily</title>"
        "<body><p><a href=\"/\">Machina Daily</a></p><h1>" +
        sector.title() + " research archive</h1><ul>" + items +
        "</ul></body></html>"
    )


@publishing_bp.get("/ai/<slug>")
@publishing_bp.get("/drones/<slug>")
@publishing_bp.get("/robotics/<slug>")
@publishing_bp.get("/autonomy/<slug>")
def published_article(slug, sector=None):
    sector = safe_sector(sector or request.path.strip("/").split("/", 1)[0])
    if not sector or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        abort(404)
    article = next(
        (a for a in all_articles()
         if a.get("sector") == sector and a.get("slug") == slug),
        None,
    )
    if not article:
        abort(404)
    folder = PUBLISH_DIR / sector
    filename = slug + ".html"
    if not (folder / filename).is_file():
        abort(404)
    return send_from_directory(folder, filename)


def published_sitemap_urls():
    urls = []
    for article in all_articles():
        sector = safe_sector(article.get("sector"))
        slug = article.get("slug", "")
        if sector and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            urls.append(
                "<url><loc>" + SITE_URL + "/" + sector + "/" + slug +
                "</loc></url>"
            )
    return urls
