from flask import Flask, abort, jsonify, send_from_directory
from pathlib import Path
from datetime import datetime, timezone
import json, re, email.utils as eutils

app = Flask(__name__)
REWRITTEN_DIR = Path(__file__).parent / "data" / "rewritten"

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
    return dt.astimezone(timezone.utc).strftime("%b %d, %Y • %I:%M %p UTC")

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

# ---------- loader -------------------------------------------
def load_all_articles() -> list[dict]:
    items = []
    for jf in REWRITTEN_DIR.glob("*.json"):
        try:
            data  = json.loads(jf.read_text(encoding="utf-8"))
            title = data.get("title", "")
            text  = data.get("text", "")
            if looks_like_ad(title, text):
                continue

            pub_dt = parse_dt(data.get("published")) or datetime.min

            items.append({
                "id"        : data.get("id"),
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

def newest_balanced() -> list[dict]:
    items   = load_all_articles()
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
@app.route("/")
def home():           return send_from_directory("frontend", "index.html")

@app.route("/archive")
def archive_page():   return send_from_directory("frontend", "archive.html")

@app.route("/frontend/<path:f>")
def frontend_files(f): return send_from_directory("frontend", f)

@app.route("/articles")
def newest():         return jsonify(newest_balanced())

@app.route("/archive.json")
def archive_json():   return jsonify(load_all_articles())

@app.route("/article/<article_id>")
def article(article_id):
    fp = REWRITTEN_DIR / f"{article_id}.json"
    if not fp.exists():
        abort(404)
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        data["published"] = format_date(parse_dt(data.get("published")))
        data["thumbnail"] = get_thumbnail(data)
    except Exception:
        abort(500)
    return jsonify(data)

# ---------- main ---------------------------------------------
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
