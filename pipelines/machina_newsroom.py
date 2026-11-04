"""
MACHINA DAILY — NEWSROOM

Experimental journalism pipeline.

INTELLIGENCE
    ↓
NEWSROOM SCANNER
    ↓
NEWS EDITOR
    ↓
EVIDENCE DESK
    ↓
STORY BOARD
    ↓
JOURNALIST
    ↓
FACT CHECK
    ↓
FINAL EDITOR
    ↓
STORY

Important:
- This is separate from story_hunter.py.
- It does NOT modify story_history.json.
- It does NOT permanently consume intelligence records.
- Gemma handles editorial judgement and prose.
- Python handles structure, evidence selection and fallbacks.

Core newsroom principle:

    Find what changed.
    Establish what is known.
    Find what is missing.
    Find the angle.
    Report it clearly.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data"
EDITORIAL_DIR = DATA_DIR / "editorial"
NEWSROOM_DIR = EDITORIAL_DIR / "newsroom"

MODEL = "gemma2:2b"
OLLAMA_URL = "http://localhost:11434/api/generate"

CANDIDATE_COUNT = 24
EVIDENCE_COUNT = 12

NEWSROOM_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# HELPERS
# ============================================================

def clean(value) -> str:
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    return str(value).strip()


def first(record, *keys) -> str:
    for key in keys:
        value = record.get(key)

        if value not in (None, "", []):
            return clean(value)

    return ""


# ============================================================
# NORMALISE INTELLIGENCE
# ============================================================

def normalise_record(record, index=0):

    if not isinstance(record, dict):
        return None

    title = first(
        record,
        "title",
        "headline",
        "name",
        "article_title",
        "paper_title",
        "story",
        "subject",
    )

    text = first(
        record,
        "summary",
        "description",
        "content",
        "abstract",
        "text",
        "article",
        "body",
        "snippet",
        "insight",
    )

    source = first(
        record,
        "source",
        "source_name",
        "publisher",
        "publication",
        "journal",
        "site",
        "domain",
    )

    url = first(
        record,
        "url",
        "link",
        "source_url",
        "article_url",
    )

    date = first(
        record,
        "date",
        "published",
        "published_at",
        "publication_date",
        "timestamp",
    )

    record_id = first(
        record,
        "record_id",
        "id",
        "uuid",
        "hash",
        "sha256",
    )

    if not record_id:
        record_id = f"local-{index:06d}"

    if not title and not text:
        return None

    return {
        "record_id": record_id,
        "title": title or "(untitled intelligence)",
        "text": text,
        "source": source,
        "url": url,
        "date": date,
        "raw": record,
    }


# ============================================================
# LOAD INTELLIGENCE
# ============================================================

def load_records():

    records = []

    files = []

    for pattern in ("*.json", "*.jsonl", "*.csv"):
        files.extend(DATA_DIR.rglob(pattern))

    # Never accidentally read our own newsroom output.
    files = [
        path
        for path in files
        if EDITORIAL_DIR not in path.parents
    ]

    print(f"Scanning intelligence files: {len(files)}")

    for path in sorted(files):

        try:

            # ------------------------------------------------
            # CSV
            # ------------------------------------------------

            if path.suffix.lower() == ".csv":

                with path.open(
                    "r",
                    encoding="utf-8-sig",
                    newline=""
                ) as file:

                    reader = csv.DictReader(file)

                    for row in reader:

                        item = normalise_record(
                            row,
                            len(records)
                        )

                        if item:
                            records.append(item)

            # ------------------------------------------------
            # JSONL
            # ------------------------------------------------

            elif path.suffix.lower() == ".jsonl":

                with path.open(
                    "r",
                    encoding="utf-8"
                ) as file:

                    for line in file:

                        line = line.strip()

                        if not line:
                            continue

                        obj = json.loads(line)

                        if isinstance(obj, dict):

                            item = normalise_record(
                                obj,
                                len(records)
                            )

                            if item:
                                records.append(item)

            # ------------------------------------------------
            # JSON
            # ------------------------------------------------

            else:

                with path.open(
                    "r",
                    encoding="utf-8"
                ) as file:

                    obj = json.load(file)

                if isinstance(obj, list):

                    iterable = obj

                elif isinstance(obj, dict):

                    iterable = (
                        obj.get("records")
                        or obj.get("articles")
                        or obj.get("items")
                        or obj.get("data")
                        or []
                    )

                    if isinstance(iterable, dict):
                        iterable = list(iterable.values())

                else:

                    iterable = []

                for obj_item in iterable:

                    item = normalise_record(
                        obj_item,
                        len(records)
                    )

                    if item:
                        records.append(item)

        except Exception as exc:

            print(
                f"WARNING: could not read {path.name}: "
                f"{exc}"
            )

    # --------------------------------------------------------
    # Deduplicate
    # --------------------------------------------------------

    unique = []

    seen_ids = set()
    seen_titles = set()

    for record in records:

        record_id = record["record_id"]

        title_key = re.sub(
            r"\W+",
            " ",
            record["title"].lower()
        ).strip()

        if record_id in seen_ids:
            continue

        if title_key and title_key in seen_titles:
            continue

        seen_ids.add(record_id)

        if title_key:
            seen_titles.add(title_key)

        unique.append(record)

    return unique


# ============================================================
# LOCAL AI
# ============================================================

def ask(prompt, temperature=0.2):

    if requests is None:

        print(
            "WARNING: Python requests module is unavailable."
        )

        return ""

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": 4096,
        },
    }

    started = time.time()

    try:

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=180,
        )

        response.raise_for_status()

        data = response.json()

        answer = clean(
            data.get("response", "")
        )

        elapsed = time.time() - started

        print(
            f"Local AI completed in "
            f"{elapsed:.1f}s"
        )

        return answer

    except Exception as exc:

        print(
            f"WARNING: local AI unavailable: {exc}"
        )

        return ""


# ============================================================
# NEWSROOM SCORING
# ============================================================

NEWS_TERMS = {
    "launch",
    "launched",
    "release",
    "released",
    "deployed",
    "deployment",
    "ships",
    "shipped",
    "contract",
    "funding",
    "investment",
    "acquired",
    "acquisition",
    "partnership",
    "trial",
    "test",
    "tested",
    "pilot",
    "regulation",
    "lawsuit",
    "court",
    "incident",
    "accident",
    "failure",
    "recall",
    "cancelled",
    "canceled",
    "delay",
    "deadline",
    "approved",
    "approval",
    "ban",
    "policy",
    "government",
    "customer",
    "production",
    "factory",
    "revenue",
    "price",
    "cost",
    "benchmark",
    "study",
    "research",
}


TECH_TERMS = {
    "ai",
    "artificial intelligence",
    "machine learning",
    "model",
    "robot",
    "robotics",
    "drone",
    "autonomous",
    "agent",
    "chip",
    "gpu",
    "software",
    "semiconductor",
    "computer vision",
    "language model",
    "data center",
    "infrastructure",
    "security",
    "cyber",
    "battery",
    "sensor",
}


def candidate_score(record):

    blob = (
        record["title"]
        + " "
        + record["text"]
        + " "
        + record["source"]
    ).lower()

    score = 0

    for term in NEWS_TERMS:

        if term in blob:
            score += 3

    for term in TECH_TERMS:

        if term in blob:
            score += 1

    if record["source"]:
        score += 2

    if record["date"]:
        score += 1

    event_language = (
        "announced",
        "according to",
        "will",
        "has begun",
        "has signed",
        "has deployed",
        "found that",
        "reported",
        "confirmed",
        "plans to",
        "expects to",
    )

    if any(
        phrase in blob
        for phrase in event_language
    ):
        score += 4

    return score


# ============================================================
# BUILD NEWSROOM BOARD
# ============================================================

def build_candidate_board(records):

    ranked = sorted(
        records,
        key=candidate_score,
        reverse=True,
    )

    selected = []

    existing_topics = []

    for record in ranked:

        title_words = set(
            re.findall(
                r"[a-z]{5,}",
                record["title"].lower()
            )
        )

        overlap = max(
            (
                len(
                    title_words.intersection(
                        previous
                    )
                )
                for previous in existing_topics
            ),
            default=0,
        )

        # Prevent the board being filled with
        # near-identical stories.
        if overlap >= 4 and len(selected) < 12:
            continue

        selected.append(record)
        existing_topics.append(title_words)

        if len(selected) >= CANDIDATE_COUNT:
            break

    return selected


# ============================================================
# NEWS EDITOR
# ============================================================

def choose_story(candidates):

    board = "\n\n".join(

        f"{index + 1}. {record['title']}\n"
        f"Source: {record['source'] or 'unknown'}\n"
        f"Date: {record['date'] or 'unknown'}\n"
        f"Evidence: {record['text'][:800]}"

        for index, record
        in enumerate(candidates)
    )

    prompt = f"""
You are the NEWS EDITOR of Machina Daily.

Your job is to choose the ONE item that contains
the strongest genuine news development.

Do NOT write an article.

Choose something where:

- something actually happened or changed
- there is a specific claim
- evidence exists
- the development could matter to technology,
  business, government or people

Reject:

- generic trend stories
- vague predictions
- pure marketing
- generic research descriptions
- old background material
- stories where nothing actually changed

A press release is not automatically news.

Return ONLY:

NUMBER: X

NEWSROOM BOARD

{board}
"""

    answer = ask(
        prompt,
        temperature=0.1
    )

    match = re.search(
        r"NUMBER\s*:\s*(\d+)",
        answer.upper()
    )

    if match:

        number = int(
            match.group(1)
        )

        if 1 <= number <= len(candidates):
            return candidates[number - 1]

    print(
        "WARNING: editor did not return a valid "
        "selection. Using newsroom scoring fallback."
    )

    return candidates[0]


# ============================================================
# EVIDENCE DESK
# ============================================================

def find_related_evidence(
    story,
    records
):

    story_words = set(
        re.findall(
            r"[a-z]{4,}",
            (
                story["title"]
                + " "
                + story["text"]
            ).lower()
        )
    )

    scored = []

    for record in records:

        if record["record_id"] == story["record_id"]:
            continue

        blob = (
            record["title"]
            + " "
            + record["text"]
            + " "
            + record["source"]
        ).lower()

        words = set(
            re.findall(
                r"[a-z]{4,}",
                blob
            )
        )

        overlap = len(
            story_words.intersection(words)
        )

        score = (
            overlap * 2
            + candidate_score(record)
        )

        # Same publisher is useful evidence,
        # but it is NOT independent confirmation.
        if (
            record["source"]
            and record["source"]
            == story["source"]
        ):
            score += 1

        scored.append(
            (score, record)
        )

    scored.sort(
        key=lambda item: item[0],
        reverse=True
    )

    evidence = []

    seen_titles = set()

    for _, record in scored:

        title_key = re.sub(
            r"\W+",
            " ",
            record["title"].lower()
        ).strip()

        if title_key in seen_titles:
            continue

        evidence.append(record)
        seen_titles.add(title_key)

        if len(evidence) >= EVIDENCE_COUNT:
            break

    return evidence


# ============================================================
# STORY BOARD
# ============================================================

def build_story_board(
    story,
    evidence
):

    evidence_text = "\n\n".join(

        f"SOURCE {index + 1}\n"
        f"Title: {record['title']}\n"
        f"Source: {record['source'] or 'unknown'}\n"
        f"Date: {record['date'] or 'unknown'}\n"
        f"Text: {record['text'][:1300]}"

        for index, record
        in enumerate(
            [story] + evidence
        )
    )

    prompt = f"""
You are a technology newspaper reporter
working at Machina Daily.

Build a STORY BOARD.

Do not write the article.

Do not invent facts.

Do not assume a company claim is verified.

Do not describe the intelligence database.

Answer:

WHAT HAPPENED:
WHO:
WHAT:
WHEN:
WHERE:
WHY:
HOW:

PRIMARY CLAIM:

EVIDENCE:

INDEPENDENT CONFIRMATION:

WHAT IS NEW:

WHAT IS VERIFIED:

WHAT IS UNKNOWN:

CONTRADICTIONS OR LIMITATIONS:

TECHNICAL SIGNIFICANCE:

COMMERCIAL SIGNIFICANCE:

STRATEGIC SIGNIFICANCE:

HUMAN SIGNIFICANCE:

CENTRAL QUESTION:

STORY ANGLE:

WHY IT MATTERS:

SOURCE MATERIAL

{evidence_text}
"""

    answer = ask(
        prompt,
        temperature=0.15
    )

    if answer:
        return answer.strip()

    return (
        f"WHAT HAPPENED:\n"
        f"{story['title']}\n\n"
        f"PRIMARY CLAIM:\n"
        f"The supplied source reports this development.\n\n"
        f"EVIDENCE:\n"
        f"{story['text'][:700]}\n\n"
        f"WHAT IS VERIFIED:\n"
        f"The source record exists and contains this claim.\n\n"
        f"WHAT IS UNKNOWN:\n"
        f"Independent confirmation is not established "
        f"by the corpus alone.\n\n"
        f"CENTRAL QUESTION:\n"
        f"What has actually changed beyond the announcement?\n\n"
        f"STORY ANGLE:\n"
        f"Examine the reported development against "
        f"the available evidence.\n"
    )


# ============================================================
# JOURNALIST
# ============================================================

BANNED_LANGUAGE = [
    "this json",
    "here's a breakdown",
    "here is a breakdown",
    "data structure",
    "suggestions for further exploration",
    "enhance the data",
    "the dataset",
    "as an ai",
    "i cannot",
]


def bad_article(article):

    text = article.lower()

    hits = sum(
        phrase in text
        for phrase in BANNED_LANGUAGE
    )

    return hits >= 2


def write_story(
    story,
    evidence,
    board
):

    sources = "\n\n".join(

        f"SOURCE {index + 1}\n"
        f"Title: {record['title']}\n"
        f"Publisher: {record['source'] or 'unknown'}\n"
        f"Date: {record['date'] or 'unknown'}\n"
        f"Text: {record['text'][:1600]}"

        for index, record
        in enumerate(
            [story] + evidence
        )
    )

    prompt = f"""
You are a senior technology newspaper journalist
at Machina Daily.

Write ONE original reported news story.

This is journalism.

It is NOT:

- a database summary
- a research report
- an explanation of JSON
- a list of records
- an AI-generated research memo

NEWSROOM RULES:

1. Lead with what actually happened.

2. Use the inverted pyramid.

3. Answer who, what, when, where, why
   and how where the evidence allows.

4. Identify the specific news angle.

5. Explain what changed.

6. Explain why it matters.

7. Attribute claims.

8. Separate claims from verified facts.

9. State clearly when independent confirmation
   is unavailable.

10. Use short sentences.

11. Use active voice.

12. Use concrete nouns and strong verbs.

13. Avoid hype.

14. Avoid corporate language.

15. Do not invent quotes.

16. Do not invent statistics.

17. Do not invent events.

18. Do not turn a technical possibility
    into a deployed capability.

19. Do not turn an announcement
    into an outcome.

20. Do not fill evidence gaps with imagination.

21. Do not mention the intelligence database.

22. Do not say:
    "this JSON"
    "here's a breakdown"
    "the dataset"
    "data structure"
    "suggestions for further exploration"

23. Do not begin with:
    "In today's rapidly evolving..."

24. Do not finish with generic advice.

Write approximately 900-1,300 words.

SOURCE MATERIAL

{sources}

NEWSROOM STORY BOARD

{board}
"""

    article = ask(
        prompt,
        temperature=0.35
    )

    if not article:
        return fallback_story(
            story,
            evidence
        )

    article = article.strip()

    if bad_article(article):
        print(
            "WARNING: journalist produced "
            "database-style prose."
        )

        return fallback_story(
            story,
            evidence
        )

    return article


# ============================================================
# FALLBACK JOURNALISM
# ============================================================

def fallback_story(
    story,
    evidence
):

    source = (
        story["source"]
        or "the supplied source"
    )

    paragraphs = []

    paragraphs.append(
        f"{story['title']}. "
        f"{source} reports the development "
        f"in the supplied intelligence record."
    )

    paragraphs.append(
        f"The central claim is that "
        f"{story['title'].rstrip('.')}. "
        f"The source record states: "
        f"{story['text'][:700].strip()}"
    )

    paragraphs.append(
        "That claim needs to be separated from "
        "what can be independently established. "
        "The available Machina Daily intelligence "
        "contains related records, but the corpus "
        "alone does not establish that every "
        "reported result has been independently "
        "verified."
    )

    for record in evidence[:5]:

        paragraphs.append(
            f"Related reporting adds context. "
            f"{record['source'] or 'A separate source'} "
            f"reported: "
            f"{record['text'][:500].strip()}"
        )

    paragraphs.append(
        "The reporting question is therefore "
        "not simply whether the technology "
        "described in the source is possible. "
        "It is what has actually changed, what "
        "evidence demonstrates that change, "
        "and what remains unverified."
    )

    paragraphs.append(
        "That distinction matters because an "
        "announcement or research result can "
        "establish that a claim has been made. "
        "It does not by itself establish "
        "deployment, commercial adoption, "
        "reliability or real-world impact."
    )

    return "\n\n".join(paragraphs)


# ============================================================
# FACT CHECKER
# ============================================================

def fact_check(
    article,
    story,
    evidence
):

    issues = []

    if not article.strip():
        issues.append(
            "Article is empty."
        )

    if bad_article(article):
        issues.append(
            "Article contains database-analysis language."
        )

    if article.count('"') % 2 != 0:
        issues.append(
            "Possible unmatched quotation mark."
        )

    source_list = "\n".join(

        f"- {record['title']} "
        f"| {record['source'] or 'unknown'}"

        for record
        in [story] + evidence
    )

    prompt = f"""
You are the final fact checker and copy editor
at Machina Daily.

Check the article against the supplied sources.

Return ONLY concrete problems.

Look for:

- unsupported factual claims
- invented quotations
- claims presented as facts
- exaggeration
- missing attribution
- unsupported conclusions
- repeated material
- database-analysis language

If there are no problems, return:

CLEAN

SOURCE MATERIAL

{source_list}

ARTICLE

{article}
"""

    review = ask(
        prompt,
        temperature=0.1
    )

    review = review.strip()

    if issues:

        if review and review.upper() != "CLEAN":
            issues.append(review)

        return "\n".join(
            f"- {issue}"
            for issue in issues
        )

    return review or "CLEAN"


# ============================================================
# SAVE STORY
# ============================================================

def save_story(
    records_count,
    story,
    evidence,
    board,
    article,
    review
):

    timestamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    json_path = (
        NEWSROOM_DIR
        / f"newsroom_{timestamp}.json"
    )

    markdown_path = (
        NEWSROOM_DIR
        / f"newsroom_{timestamp}.md"
    )

    output = {

        "run": timestamp,

        "experimental": True,

        "records_available": records_count,

        "model": MODEL,

        "story": {
            "record_id": story["record_id"],
            "title": story["title"],
            "source": story["source"],
            "date": story["date"],
            "url": story["url"],
            "text": story["text"],
        },

        "evidence": [
            {
                "record_id": record["record_id"],
                "title": record["title"],
                "source": record["source"],
                "date": record["date"],
                "url": record["url"],
                "text": record["text"],
            }
            for record in evidence
        ],

        "story_board": board,

        "fact_check": review,

        "article": article,
    }

    json_path.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    markdown = (
        f"# {story['title']}\n\n"
        f"**Machina Daily — Experimental Newsroom**\n\n"
        f"{article}\n\n"
        f"---\n\n"
        f"## Editor's Fact Check\n\n"
        f"{review}\n"
    )

    markdown_path.write_text(
        markdown,
        encoding="utf-8"
    )

    return json_path, markdown_path


# ============================================================
# MAIN NEWSROOM
# ============================================================

def main():

    print()
    print("=" * 72)
    print("MACHINA DAILY — NEWSROOM")
    print("=" * 72)
    print()

    print(
        "FIND WHAT CHANGED."
    )

    print(
        "ESTABLISH WHAT IS KNOWN."
    )

    print(
        "FIND WHAT IS MISSING."
    )

    print(
        "FIND THE ANGLE."
    )

    print(
        "REPORT IT."
    )

    print()

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    records = load_records()

    if not records:

        print(
            "ERROR: No intelligence records found."
        )

        print(
            "Expected intelligence somewhere "
            "under the data\\ directory."
        )

        sys.exit(1)

    print(
        f"Intelligence records: {len(records)}"
    )

    print(
        f"Local model: {MODEL}"
    )

    print(
        f"Candidate board: {CANDIDATE_COUNT}"
    )

    print(
        f"Evidence desk: {EVIDENCE_COUNT}"
    )

    print()

    print(
        "IMPORTANT: experimental run."
    )

    print(
        "Story memory will NOT be changed."
    )

    print()

    # --------------------------------------------------------
    # 1
    # --------------------------------------------------------

    print(
        "1/6  NEWSROOM SCANNER"
    )

    candidates = build_candidate_board(
        records
    )

    print(
        f"Potential developments: "
        f"{len(candidates)}"
    )

    print()

    # --------------------------------------------------------
    # 2
    # --------------------------------------------------------

    print(
        "2/6  NEWS EDITOR"
    )

    story = choose_story(
        candidates
    )

    print(
        f"Selected story: "
        f"{story['title']}"
    )

    print(
        f"Record: "
        f"{story['record_id']}"
    )

    print()

    # --------------------------------------------------------
    # 3
    # --------------------------------------------------------

    print(
        "3/6  EVIDENCE DESK"
    )

    evidence = find_related_evidence(
        story,
        records
    )

    print(
        f"Related evidence: "
        f"{len(evidence)} records"
    )

    print()

    # --------------------------------------------------------
    # 4
    # --------------------------------------------------------

    print(
        "4/6  STORY BOARD"
    )

    board = build_story_board(
        story,
        evidence
    )

    print(
        "Story board complete."
    )

    print()

    # --------------------------------------------------------
    # 5
    # --------------------------------------------------------

    print(
        "5/6  JOURNALIST"
    )

    article = write_story(
        story,
        evidence,
        board
    )

    print(
        f"Article words: "
        f"{len(article.split())}"
    )

    print()

    # --------------------------------------------------------
    # 6
    # --------------------------------------------------------

    print(
        "6/6  FINAL EDITOR"
    )

    review = fact_check(
        article,
        story,
        evidence
    )

    print(
        f"Fact check: "
        f"{review[:600]}"
    )

    print()

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    json_path, markdown_path = save_story(
        len(records),
        story,
        evidence,
        board,
        article,
        review
    )

    print("=" * 72)
    print("NEWSROOM STORY COMPLETE")
    print("=" * 72)
    print()

    print(
        f"HEADLINE: {story['title']}"
    )

    print(
        f"WORDS:    {len(article.split())}"
    )

    print(
        f"ARTICLE:  {markdown_path}"
    )

    print(
        f"RECORD:   {json_path}"
    )

    print()

    print(
        "Story memory was NOT changed."
    )

    print()

    print("-" * 72)
    print("ARTICLE")
    print("-" * 72)
    print()

    print(article)

    print()

    print("-" * 72)
    print("END NEWSROOM")
    print("-" * 72)
    print()


if __name__ == "__main__":
    main()