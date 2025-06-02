import json
from pathlib import Path

article = {
    "title": "Breaking News: AI is Awesome",
    "content": "Today, OpenAI announced something incredible...",
    "url": "https://news.com/article123"
}

output_dir = Path("data/raw")
output_dir.mkdir(parents=True, exist_ok=True)

with open(output_dir / "article_1.json", "w", encoding="utf-8") as f:
    json.dump(article, f, ensure_ascii=False, indent=2)
