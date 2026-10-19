from flask import Flask, abort, jsonify, send_from_directory, request
from pathlib import Path
from datetime import datetime, timezone
import json, re, email.utils as eutils

app = Flask(__name__)


from company_data import company_data_bp
app.register_blueprint(company_data_bp)
from signals_observatory import signals_bp
app.register_blueprint(signals_bp)
from dashboard_control import dashboard_bp
app.register_blueprint(dashboard_bp)
from intelligence_layer import intelligence_bp
from market_data import market_bp
app.register_blueprint(market_bp)
app.register_blueprint(intelligence_bp)
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
    return dt.astimezone(timezone.utc).strftime("%b %d, %Y ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢ %I:%M %p UTC")

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

_ARCHIVE_CACHE = {"loaded_at": 0.0, "items": []}

@app.route("/archive.json")
def archive_json():
    import time

    now = time.monotonic()

    if now - _ARCHIVE_CACHE["loaded_at"] >= 60 or not _ARCHIVE_CACHE["items"]:
        _ARCHIVE_CACHE["items"] = load_all_articles_from(REWRITTEN_DIR, RAW_DIR)
        _ARCHIVE_CACHE["loaded_at"] = now

    items = _ARCHIVE_CACHE["items"]

    categories = sorted({
        str(item.get("category"))
        for item in items
        if item.get("category")
    })

    selected_category = request.args.get("category", "all")
    query = request.args.get("q", "").strip().lower()

    if selected_category != "all":
        items = [
            item for item in items
            if str(item.get("category") or "") == selected_category
        ]

    if query:
        def searchable_text(item):
            authors = item.get("authors") or []
            if isinstance(authors, str):
                authors = [authors]

            return " ".join([
                str(item.get("title") or ""),
                str(item.get("category") or ""),
                " ".join(str(author) for author in authors),
            ]).lower()

        items = [item for item in items if query in searchable_text(item)]

    total = len(items)
    per_page = 25
    total_pages = max(1, (total + per_page - 1) // per_page)

    try:
        page = max(1, int(request.args.get("page", "1")))
    except (TypeError, ValueError):
        page = 1

    page = min(page, total_pages)
    start = (page - 1) * per_page

    return jsonify({
        "articles": items[start:start + per_page],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "categories": categories,
    })

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


# ---------- editorial --------------------------------------

EDITORIAL_DIR = Path(__file__).parent / "data" / "editorial"

def load_editorial_file(filename):
    fp = EDITORIAL_DIR / filename

    if not fp.exists():
        return {}

    try:
        return json.loads(
            fp.read_text(encoding="utf-8")
        )
    except Exception:
        return {}


@app.route("/editorial")
def editorial_page():
    return send_from_directory(
        "frontend",
        "editorial.html"
    )


@app.route("/editorial/data")
def editorial_data():
    candidates = load_editorial_file(
        "story_hunter_candidates.json"
    )
    investigation_file = load_editorial_file(
        "machina_original_investigation.json"
    )
    article_file = load_editorial_file(
        "machina_original_article.json"
    )

    investigation_data = investigation_file.get("investigation", {})
    investigation_id = investigation_data.get("research_id")
    article_id = article_file.get("research_id")

    # Show a completed article even when its research ID differs.
    # Keep the mismatch flag for diagnosis without hiding the article.
    article_is_complete = article_file.get("status") == "complete"
    matches = bool(
        article_is_complete
        and investigation_file.get("status") == "complete"
        and investigation_id
        and article_id
        and investigation_id == article_id
    )

    return jsonify({
        "candidates": candidates,
        "investigation": investigation_file,
        "article": article_file if article_is_complete else {},
        "article_matches_investigation": matches,
        "article_match_reason": (
            "Article matches the completed investigation."
            if matches
            else (
                "Completed article displayed, but investigation IDs or statuses differ."
                if article_is_complete
                else "No completed article is available."
            )
        )
    })




@app.route("/editorial/archive")
def editorial_archive():
    """Return completed saved articles for the Editorial page archive."""
    editorial_dir = Path(__file__).parent / "data" / "editorial"

    article_files = [editorial_dir / "machina_original_article.json"]

    if editorial_dir.exists():
        for backup_dir in editorial_dir.glob("run_backup_*"):
            if backup_dir.is_dir():
                article_files.append(
                    backup_dir / "machina_original_article.json"
                )

    articles = []
    seen = set()

    for article_path in article_files:
        if not article_path.is_file():
            continue

        try:
            saved = json.loads(
                article_path.read_text(encoding="utf-8-sig")
            )
        except (OSError, ValueError) as exc:
            print(
                "EDITORIAL ARCHIVE: Could not read",
                article_path,
                "-",
                exc
            )
            continue

        if not isinstance(saved, dict):
            continue

        if str(saved.get("status", "")).lower() != "complete":
            continue

        article = saved.get("article", {})
        if not isinstance(article, dict):
            continue

        headline = str(
            article.get("headline")
            or saved.get("headline")
            or ""
        ).strip()

        if not headline:
            continue

        generated_at = str(saved.get("generated_at") or "")
        research_id = str(saved.get("research_id") or "")

        # Prefer the research ID for deduplication. Fall back to the
        # headline and timestamp when an ID was not recorded.
        identity = (
            research_id.lower()
            if research_id
            else (headline.casefold(), generated_at)
        )

        if identity in seen:
            continue

        seen.add(identity)

        articles.append({
            "id": str(len(articles) + 1),
            "headline": headline,
            "dek": str(
                article.get("dek")
                or article.get("standfirst")
                or article.get("summary")
                or ""
            ),
            "generated_at": generated_at,
            "source_date": str(saved.get("source_date") or ""),
            "file": saved,
        })

    articles.sort(
        key=lambda item: item.get("generated_at", ""),
        reverse=True
    )

    return jsonify({
        "status": "ok",
        "count": len(articles),
        "articles": articles,
    })


# ---------- newsroom ----------------------------------------

FIVE_JOURNALISTS_DIR = (
    Path(__file__).parent
    / "data"
    / "editorial"
    / "five_journalists"
)

FIVE_JOURNALISTS_NEWSROOM_FILE = (
    FIVE_JOURNALISTS_DIR
    / "five_journalists_newsroom.json"
)


FIVE_MORE_JOURNALISTS_DIR = (
    Path(__file__).parent
    / "data"
    / "editorial"
    / "five_more_journalists"
)

FIVE_MORE_JOURNALISTS_NEWSROOM_FILE = (
    FIVE_MORE_JOURNALISTS_DIR
    / "five_more_journalists_newsroom.json"
)


def load_newsroom_file(filepath, desk_name):
    """
    Load one independent journalist newsroom.

    Each journalist system keeps its own aggregate JSON file.
    This function normalises it into a predictable structure
    for the public newsroom.
    """

    if not filepath.exists():
        print(
            f"NEWSROOM: {desk_name} newsroom file not found:",
            filepath
        )

        return {
            "stories": [],
            "count": 0,
            "status": "empty",
            "desk": desk_name
        }

    try:
        data = json.loads(
            filepath.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, list):
            data = {
                "stories": data
            }

        if not isinstance(data, dict):
            raise ValueError(
                f"{filepath.name} must contain "
                "an object or a list of stories."
            )

        stories = data.get("stories", [])

        if not isinstance(stories, list):
            stories = []

        return {
            "stories": stories,
            "count": len(stories),
            "status": "online" if stories else "empty",
            "desk": desk_name
        }

    except Exception as exc:
        print(
            f"NEWSROOM: failed to load {desk_name}: {exc}"
        )

        return {
            "stories": [],
            "count": 0,
            "status": "error",
            "error": str(exc),
            "desk": desk_name
        }


def load_five_journalists_newsroom():
    """
    Load the original five-journalist newsroom.

    This remains completely independent from the new
    five-more-journalists system.
    """

    return load_newsroom_file(
        FIVE_JOURNALISTS_NEWSROOM_FILE,
        "five_journalists"
    )


def load_five_more_journalists_newsroom():
    """
    Load the five-more-journalist newsroom directly from the
    individual successful story JSON files.

    Each journalist has their own directory. Every successfully
    generated story is therefore immediately available to the
    public newsroom, even if the newsroom pipeline is interrupted.
    """

    stories = []
    seen_ids = set()

    if not FIVE_MORE_JOURNALISTS_DIR.exists():
        return {
            "stories": [],
            "count": 0,
            "status": "empty",
            "desk": "five_more_journalists"
        }

    journalist_dirs = [
        FIVE_MORE_JOURNALISTS_DIR / "marta_kowalski",
        FIVE_MORE_JOURNALISTS_DIR / "james_okafor",
        FIVE_MORE_JOURNALISTS_DIR / "amara_diallo",
        FIVE_MORE_JOURNALISTS_DIR / "kenji_tanaka",
        FIVE_MORE_JOURNALISTS_DIR / "priya_sharma",
    ]

    for journalist_dir in journalist_dirs:

        if not journalist_dir.exists():
            continue

        for filepath in journalist_dir.glob("*.json"):

            try:
                data = json.loads(
                    filepath.read_text(encoding="utf-8")
                )

                if not isinstance(data, dict):
                    continue

                story_id = (
                    data.get("id")
                    or data.get("story_id")
                    or filepath.stem
                )

                if story_id in seen_ids:
                    continue

                seen_ids.add(story_id)

                data["desk"] = "five_more_journalists"
                data["desk_label"] = (
                    "MACHINA DAILY â€” INVESTIGATIVE DESK"
                )

                stories.append(data)

            except Exception as exc:
                print(
                    f"NEWSROOM: failed to load {filepath}: {exc}"
                )

    def story_date(story):
        for key in (
            "published",
            "created_at",
            "timestamp",
            "generated_at"
        ):
            value = story.get(key)

            if value:
                parsed = parse_dt(str(value))

                if parsed:
                    return parsed

        return datetime.min.replace(
            tzinfo=timezone.utc
        )

    stories.sort(
        key=story_date,
        reverse=True
    )

    return {
        "stories": stories,
        "count": len(stories),
        "status": "online" if stories else "empty",
        "desk": "five_more_journalists"
    }

def load_combined_newsroom():
    """
    Public Machina Daily newsroom.

    The two journalist systems remain completely separate
    on disk and in their own pipelines.

    They are combined ONLY here for the public newsroom feed.
    """

    original = load_five_journalists_newsroom()
    additional = load_five_more_journalists_newsroom()

    original_stories = original.get(
        "stories",
        []
    )

    additional_stories = additional.get(
        "stories",
        []
    )

    combined = []

    # Mark the source desk so the frontend can identify
    # which newsroom produced each story.
    for story in original_stories:

        if isinstance(story, dict):

            story = dict(story)

            story.setdefault(
                "desk",
                "five_journalists"
            )

            story.setdefault(
                "desk_label",
                "MACHINA DAILY â€” ORIGINAL DESK"
            )

            combined.append(story)

    for story in additional_stories:

        if isinstance(story, dict):

            story = dict(story)

            story.setdefault(
                "desk",
                "five_more_journalists"
            )

            story.setdefault(
                "desk_label",
                "MACHINA DAILY â€” INVESTIGATIVE DESK"
            )

            combined.append(story)

    return {
        "stories": combined,
        "count": len(combined),

        "original_count": len(
            original_stories
        ),

        "five_more_count": len(
            additional_stories
        ),

        "status": (
            "online"
            if combined
            else "empty"
        ),

        "desks": {
            "five_journalists": {
                "count": len(
                    original_stories
                ),
                "status": original.get(
                    "status",
                    "empty"
                )
            },

            "five_more_journalists": {
                "count": len(
                    additional_stories
                ),
                "status": additional.get(
                    "status",
                    "empty"
                )
            }
        }
    }


@app.route("/newsroom")
def newsroom_page():

    return send_from_directory(
        "frontend",
        "newsroom.html"
    )



# ---------- daily newsroom desks -------------------------------

DAILY_DESKS = {
    "yuki_tanaka",
    "callum_reyes",
    "tomas_vega",
    "ingrid_sorensen",
    "dev_okafor",
    "ravi_chatterjee",
    "elena_vasquez",
    "marcus_okafor",
    "kenji_nakamura",
    "sofia_lindqvist",
}

# ---------- daily publications ----------------------------------

@app.route("/daily-briefing")
def daily_briefing_page():

    return send_from_directory(
        "frontend",
        "daily-briefing.html"
    )


@app.route("/daily-briefing/data")
def daily_briefing_data():

    newsroom_file = (
        Path(__file__).parent
        / "data"
        / "editorial"
        / "local_newsroom"
        / "local_newsroom.json"
    )

    with open(newsroom_file, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/daily/<journalist_id>")
def daily_desk_page(journalist_id):

    allowed = DAILY_DESKS

    if journalist_id not in allowed:
        return "Desk not found", 404

    return send_from_directory(
        "frontend/daily",
        journalist_id + ".html"
    )


@app.route("/daily/<journalist_id>/data")
def daily_desk_data(journalist_id):

    allowed = DAILY_DESKS

    if journalist_id not in allowed:
        return jsonify({"error": "Desk not found"}), 404

    newsroom_file = (
        Path(__file__).parent
        / "data"
        / "editorial"
        / "local_newsroom"
        / "local_newsroom.json"
    )

    with open(newsroom_file, "r", encoding="utf-8") as f:
        newsroom = json.load(f)

    generated_at = newsroom.get("generated_at")
    model = newsroom.get("model")

    # ------------------------------------------------------------
    # YUKI â€” EDITORIAL RANKING
    # ------------------------------------------------------------

    if journalist_id == "yuki_tanaka":

        yuki = newsroom.get("yuki", {})

        return jsonify({
            "generated_at": generated_at,
            "model": model,
            "intelligence_records":
                newsroom.get("intelligence_records"),
            "journalist": {
                "journalist_id": "yuki_tanaka",
                "journalist": "Yuki Tanaka",
                "role": "Desk Editor",
                "model": model,
                "generated_at": generated_at,
                "selected_records": [],
                "article": {
                    "body": ""
                },
                "yuki": yuki,
            },
        })

    # ------------------------------------------------------------
    # CURRENT BULLETIN
    # ------------------------------------------------------------

    current = None

    for result in newsroom.get("results", []):
        if result.get("journalist_id") == journalist_id:
            current = result
            break

    # ------------------------------------------------------------
    # HISTORY
    #
    # Every newsroom run is saved beneath:
    #
    # data/editorial/local_newsroom/history/<desk>/
    #
    # Read every file, extract the bulletin, sort newest first,
    # and remove duplicate stories created by repeated runs.
    # ------------------------------------------------------------

    history_dir = (
        Path(__file__).parent
        / "data"
        / "editorial"
        / "local_newsroom"
        / "history"
        / journalist_id
    )

    history = []

    def first_value(data, keys):

        if not isinstance(data, dict):
            return None

        for key in keys:
            value = data.get(key)

            if value not in (
                None,
                "",
                [],
                {},
            ):
                return value

        return None

    def extract_story(data, filename):

        if not isinstance(data, dict):
            return None

        article = data.get("article")

        if isinstance(article, dict):
            body = first_value(
                article,
                [
                    "body",
                    "article",
                    "content",
                    "text",
                ]
            )

            title = first_value(
                article,
                [
                    "headline",
                    "title",
                    "source_title",
                ]
            )

        else:
            body = (
                article
                if isinstance(article, str)
                else None
            )

            title = None

        if not body:
            body = first_value(
                data,
                [
                    "body",
                    "article_body",
                    "content",
                    "text",
                ]
            )

        if not title:
            title = first_value(
                data,
                [
                    "headline",
                    "title",
                    "source_title",
                    "story_title",
                ]
            )

        if not body:
            return None

        timestamp = first_value(
            data,
            [
                "generated_at",
                "created_at",
                "finished_at",
                "timestamp",
                "run_id",
            ]
        )

        if not timestamp:
            timestamp = filename.stem

        selected_records = (
            data.get("selected_records")
            or []
        )

        if not isinstance(
            selected_records,
            list
        ):
            selected_records = []

        source_title = None

        if selected_records:
            first_record = selected_records[0]

            if isinstance(
                first_record,
                dict
            ):
                source_title = first_value(
                    first_record,
                    [
                        "title",
                        "source_title",
                        "headline",
                    ]
                )

        return {
            "generated_at": str(timestamp),
            "title": (
                title
                or source_title
                or "Machina Daily Bulletin"
            ),
            "body": str(body).strip(),
            "source_title": (
                source_title
                or ""
            ),
            "source_records": selected_records,
        }

    if history_dir.exists():

        for history_file in sorted(
            history_dir.glob("*.json"),
            reverse=True
        ):

            try:

                with open(
                    history_file,
                    "r",
                    encoding="utf-8"
                ) as f:
                    saved = json.load(f)

                story = extract_story(
                    saved,
                    history_file
                )

                if story:
                    history.append(story)

            except Exception:
                continue

    # ------------------------------------------------------------
    # DEDUPLICATE
    #
    # Repeated editorial runs can produce the same bulletin.
    # Use title + body as the story identity.
    # ------------------------------------------------------------

    unique_history = []
    seen = set()

    for story in history:

        identity = (
            story.get("title", "").strip().lower(),
            story.get("body", "").strip().lower(),
        )

        if identity in seen:
            continue

        seen.add(identity)
        unique_history.append(story)

    history = unique_history

    # ------------------------------------------------------------
    # CURRENT BULLETIN
    #
    # Ensure today's/current result appears at the top even when
    # the history folder contains an older saved run.
    # ------------------------------------------------------------

    if current:

        article = (
            current.get("article")
            or {}
        )

        current_body = (
            article.get("body")
            or article.get("article")
            or ""
        )

        current_title = (
            article.get("headline")
            or article.get("title")
            or ""
        )

        if current_body:

            current_story = {
                "generated_at":
                    current.get(
                        "generated_at",
                        generated_at
                    ),
                "title":
                    current_title
                    or "Machina Daily Bulletin",
                "body":
                    current_body,
                "source_title": "",
                "source_records":
                    current.get(
                        "selected_records",
                        []
                    ),
            }

            current_identity = (
                current_story["title"]
                    .strip()
                    .lower(),
                current_story["body"]
                    .strip()
                    .lower(),
            )

            history = [
                story
                for story in history
                if (
                    story.get("title", "")
                        .strip()
                        .lower(),
                    story.get("body", "")
                        .strip()
                        .lower(),
                ) != current_identity
            ]

            history.insert(
                0,
                current_story
            )

    return jsonify({
        "generated_at": generated_at,
        "model": model,
        "journalist": current or {
            "journalist_id": journalist_id,
            "journalist": journalist_id,
            "role": "Editorial Desk",
            "model": model,
            "generated_at": generated_at,
            "selected_records": [],
            "article": {
                "body": ""
            },
        },
        "latest": (
            history[0]
            if history
            else None
        ),
        "history": history,
        "history_count": len(history),
    })

@app.route("/newsroom/data")
def newsroom_data():

    return jsonify(
        load_combined_newsroom()
    )



# ---------- weekly deep dive ---------------------------------

WEEKLY_DIR = Path(__file__).resolve().parent / "data" / "editorial" / "weekly"

@app.route("/weekly")
def weekly_page():
    return send_from_directory("frontend", "weekly.html")


@app.route("/weekly/data")
def weekly_data():
    weekly_file = WEEKLY_DIR / "weekly_editorial.json"

    if not weekly_file.exists():
        return jsonify({
            "status": "waiting_for_first_run",
            "message": "The first Weekly Deep Dive has not been generated yet.",
            "generated_at": None,
            "article": {},
            "selected_story": {},
            "research": {"sources": []},
            "quality_warnings": []
        })

    try:
        data = json.loads(weekly_file.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("Weekly editorial JSON must contain an object.")
        return jsonify(data)
    except Exception as exc:
        app.logger.exception("Could not read the Weekly Deep Dive file")
        return jsonify({
            "status": "error",
            "message": "The saved Weekly Deep Dive could not be read.",
            "detail": str(exc)
        }), 500


# ---------- main ---------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)










