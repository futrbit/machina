# pipelines/news_fetcher.py
import sys, json, hashlib, feedparser, newspaper
from datetime import datetime, timezone
from pathlib import Path

# ── 1. add project root to sys.path so config.py is found ───────────────
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

try:
    from config import FEEDS, DATA_DIR, REWRITTEN_DIR
except ModuleNotFoundError as e:
    raise RuntimeError(
        f"Could not import config.py. Make sure it lives at {project_root / 'config.py'}"
    ) from e

print(">>> News fetcher is running…")

# ── 2. ensure data folders exist ────────────────────────────────────────
DATA_DIR.mkdir(parents=True, exist_ok=True)
REWRITTEN_DIR.mkdir(parents=True, exist_ok=True)

# ── 3. newspaper config with friendly User-Agent ────────────────────────
from newspaper import Config
np_cfg = Config()
np_cfg.browser_user_agent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36"
)
np_cfg.request_timeout = 12

# ── 4. helpers ──────────────────────────────────────────────────────────
def md5(txt: str) -> str:
    return hashlib.md5(txt.encode("utf-8")).hexdigest()

def fetch_full_article(url: str) -> dict | None:
    art = newspaper.Article(url, config=np_cfg)
    try:
        art.download(); art.parse()
    except Exception:
        return None
    return {
        "title"    : art.title,
        "text"     : art.text,
        "html"     : art.html or "",
        "authors"  : art.authors,
        "published": art.publish_date.isoformat() if art.publish_date else "",
    }

def rewrite_stub(txt: str) -> str:
    return "Rewritten: " + txt[:1500]

# ── 5. main loop over all FEEDS ─────────────────────────────────────────
saved_raw = saved_rewrite = 0

for cat, urls in FEEDS.items():
    print(f"\n— Category: {cat}")
    for feed_url in urls:
        print(f"  Parsing feed: {feed_url}")
        feed = feedparser.parse(feed_url)
        if feed.bozo:
            print(f"    ! Feed error: {feed.bozo_exception}")
            continue
        if not feed.entries:
            print("    • 0 entries")
            continue

        for ent in feed.entries[:10]:
            art_id   = md5(ent.link)
            raw_path = DATA_DIR / f"{art_id}.json"
            rew_path = REWRITTEN_DIR / f"{art_id}.json"

            if raw_path.exists() and rew_path.exists():
                continue  # already processed

            fetched = fetch_full_article(ent.link) or {}
            text    = fetched.get("text") or ent.get("summary", "")
            title   = fetched.get("title") or ent.get("title", "")
            html    = fetched.get("html", "")

            if not text.strip():
                print(f"    • skipped empty: {title}")
                continue

            base_doc = {
                "id"       : art_id,
                "url"      : ent.link,
                "title"    : title,
                "category" : cat,
                "authors"  : fetched.get("authors", []),
                "published": fetched.get("published", ent.get("published", "")),
                "fetched"  : datetime.now(timezone.utc).isoformat(),
                "html"     : html,  # 👈 now included
            }

            # raw
            if not raw_path.exists():
                base_doc["text"] = text
                raw_path.write_text(json.dumps(base_doc, ensure_ascii=False, indent=2), encoding="utf-8")
                saved_raw += 1
                print(f"    + raw       : {title[:70]}")

            # rewritten
            if not rew_path.exists():
                base_doc["text"] = rewrite_stub(text)
                rew_path.write_text(json.dumps(base_doc, ensure_ascii=False, indent=2), encoding="utf-8")
                saved_rewrite += 1
                print(f"    + rewritten : {title[:70]}")

print(f"\nDone — new raw: {saved_raw}, new rewritten: {saved_rewrite}")
