from flask import Flask, abort, jsonify, send_from_directory, request
from pathlib import Path
from datetime import datetime, timezone
import json, re, email.utils as eutils

app = Flask(__name__)
REWRITTEN_DIR = Path(__file__).parent / "data" / "rewritten"
RAW_DIR       = Path(__file__).parent / "data" / "raw"
INTELLIGENCE_FILE = Path(__file__).parent / "data" / "intelligence" / "article_analysis_v2.json"

def load_article_intelligence(article_id: str) -> dict | None:
    if not INTELLIGENCE_FILE.exists():
        return None
    try:
        data = json.loads(INTELLIGENCE_FILE.read_text(encoding="utf-8"))
        return data.get("articles", {}).get(article_id)
    except Exception:
        return None
# ---------- config ------------------------------------------
CAT_ORDER   = ["tech", "drones", "autonomous"]
MAX_PER_CAT = 5
AD_KEYWORDS = {
    "deal", "discount", "save $", "lowest price", "coupon", "on sale",
    "buy now", "promo code", "early bird", "purchase", "shop", "amazon"
}

# ---------- helpers ------------------------------------------
def format_date(dt: datetime | str | None) -> str:
    if not dt:
        return "Unknown"
    if isinstance(dt, str):
        dt = parse_dt(dt)
    if not isinstance(dt, datetime):
        return str(dt)
    return dt.astimezone(timezone.utc).strftime("%b %d, %Y â€¢ %I:%M %p UTC")

def parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        dt = eutils.parsedate_to_datetime(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def og_image(html: str) -> str | None:
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                  html, flags=re.I)
    return m.group(1) if m else None

def first_img(html: str) -> str | None:
    m = re.search(r'<img\s+[^>]*src=["\']([^"\']+)["\']', html, flags=re.I)
    return m.group(1) if m else None

def fallback_thumb(cat: str | None) -> str:
    cat = (cat or "").lower()
    if "drone" in cat:
        return "/frontend/thumb-drones.jpg"
    if "autonomous" in cat or "robot" in cat:
        return "/frontend/thumb-autonomous.jpg"
    return "/frontend/thumb-tech.jpg"

def looks_like_ad(title: str, text: str) -> bool:
    blob = (title + " " + text).lower()
    return any(kw in blob for kw in AD_KEYWORDS) or len(text) < 200

def get_thumbnail(data: dict) -> str:
    html_src = data.get("html", "")
    return (og_image(html_src) or
            first_img(html_src) or
            first_img(data.get("text", "")) or
            fallback_thumb(data.get("category")))

# ---------- loaders -------------------------------------------
def load_all_articles_from(*dirs) -> list[dict]:
    items = []
    seen_ids = set()
    for directory in dirs:
        for jf in directory.glob("*.json"):
            try:
                data  = json.loads(jf.read_text(encoding="utf-8"))
                id_   = data.get("id")
                if not id_ or id_ in seen_ids:
                    continue
                seen_ids.add(id_)

                title = data.get("title", "")
                text  = data.get("text", "")
                if looks_like_ad(title, text):
                    continue

                pub_dt = parse_dt(data.get("published")) or datetime.min

                items.append({
                    "id"        : id_,
                    "title"     : title,
                    "category"  : data.get("category"),
                    "published" : format_date(pub_dt),
                    "sort_dt"   : pub_dt,
                    "authors"   : data.get("authors", []),
                    "text"      : text,
                    "url"       : data.get("url", "#"),
                    "thumbnail" : get_thumbnail(data)
                })
            except Exception:
                continue

    items.sort(key=lambda x: x["sort_dt"], reverse=True)
    return items

def load_rewritten_articles() -> list[dict]:
    return load_all_articles_from(REWRITTEN_DIR)

def newest_balanced() -> list[dict]:
    items   = load_rewritten_articles()
    buckets = {c: [] for c in CAT_ORDER}
    for art in items:
        c = (art["category"] or "").lower()
        if c in buckets and len(buckets[c]) < MAX_PER_CAT:
            buckets[c].append(art)
        if all(len(v) == MAX_PER_CAT for v in buckets.values()):
            break
    ordered = []
    for c in CAT_ORDER:
        ordered.extend(buckets[c])
    return ordered

# ---------- routes -------------------------------------------
@app.route("/sitemap.xml")
def sitemap():
    articles = load_rewritten_articles()

    urls = [
        "  <url><loc>https://machinadaily.xyz/</loc></url>",
        "  <url><loc>https://machinadaily.xyz/archive</loc></url>"
    ]

    for article in articles:
        article_id = article.get("id")
        if article_id:
            urls.append(
                f'  <url><loc>https://machinadaily.xyz/article/{article_id}</loc></url>'
            )

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
%s
</urlset>
""" % "\n".join(urls)

    return xml, 200, {"Content-Type": "application/xml; charset=utf-8"}


@app.route("/subscribe", methods=["POST"])
def subscribe():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()

    if not email or "@" not in email:
        return jsonify({"ok": False, "message": "Invalid email."}), 400

    contacts_file = Path(__file__).parent / "data" / "contacts.json"

    try:
        contacts = json.loads(contacts_file.read_text(encoding="utf-8"))
    except Exception:
        contacts = []

    if email not in [c.get("email") for c in contacts]:
        contacts.append({
            "email": email,
            "joined": datetime.now(timezone.utc).isoformat()
        })
        contacts_file.write_text(
            json.dumps(contacts, indent=2),
            encoding="utf-8"
        )

    return jsonify({"ok": True, "message": "You're in."})

@app.route("/")
def home():           return send_from_directory("frontend", "index.html")

@app.route("/archive")
def archive_page():   return send_from_directory("frontend", "archive.html")

@app.route("/frontend/<path:f>")
def frontend_files(f): return send_from_directory("frontend", f)

@app.route("/articles")
def newest():         return jsonify(newest_balanced())

@app.route("/archive.json")
def archive_json():
    # Combine rewritten + raw (but exclude duplicates)
    return jsonify(load_all_articles_from(REWRITTEN_DIR, RAW_DIR))

@app.route("/intelligence/signals")
def intelligence_signals():
    signals_file = Path(__file__).parent / "data" / "intelligence" / "signals_v2.json"

    if not signals_file.exists():
        return jsonify({"signals": []})

    try:
        data = json.loads(
            signals_file.read_text(encoding="utf-8")
        )

        return jsonify(data)

    except Exception:
        return jsonify({"signals": []}), 500

@app.route("/article/<article_id>")
def article(article_id):
    # Prefer rewritten version
    for folder in [REWRITTEN_DIR, RAW_DIR]:
        fp = folder / f"{article_id}.json"
        if fp.exists():
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                data["published"] = format_date(parse_dt(data.get("published")))
                data["thumbnail"] = get_thumbnail(data)
                data["machina_analysis"] = load_article_intelligence(article_id)
                return jsonify(data)
            except Exception:
                abort(500)
    abort(404)

# ---------- main ---------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)


