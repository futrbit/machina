"""Merge daily summaries into a single Markdown digest (for site & newsletter)."""
from datetime import date
from pathlib import Path
from config import DATA_DIR

def run():
    today = date.today().isoformat()
    digest_name = f"digest_{today}.md"
    parts = [f"# Machina Daily • {today}\n"]
    for md in DATA_DIR.glob("*.md"):
        parts.append(md.read_text())
    Path(digest_name).write_text("\n---\n".join(parts))
    print(f"Digest written → {digest_name}")

if __name__ == "__main__":
    run()