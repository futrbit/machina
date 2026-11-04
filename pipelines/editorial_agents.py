
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ============================================================
# MACHINA DAILY — LOCAL INTELLIGENCE EDITORIAL BOARD
#
# FUTURIST   -> Ollama
# AUDITOR    -> Ollama
# STRATEGIST -> Ollama
# EDITOR     -> OpenAI
#
# Only validated articles enter editorial_articles.json.
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

BRIEFS_FILE = (
    ROOT / "data" / "deep_research" / "machina_intelligence_briefs.json"
)
EVIDENCE_FILE = (
    ROOT / "data" / "deep_research" / "evidence_adjudicated.json"
)
QUEUE_FILE = (
    ROOT / "data" / "deep_research" / "editorial_queue.json"
)

OUTPUT_DIR = ROOT / "data" / "editorial"
BOARD_OUTPUT = OUTPUT_DIR / "editorial_board_outputs.json"
ARTICLES_OUTPUT = OUTPUT_DIR / "editorial_articles.json"

OLLAMA_URL = os.environ.get(
    "OLLAMA_URL", "http://127.0.0.1:11434"
).rstrip("/")

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b")

EDITOR_MODEL = os.environ.get(
    "MACHINA_EDITOR_MODEL", "gpt-4o-mini"
)

SPECIALIST_TIMEOUT = int(
    os.environ.get("MACHINA_SPECIALIST_TIMEOUT", "900")
)

EDITOR_ATTEMPTS = 2
MINIMUM_ARTICLE_WORDS = 250


# ============================================================
# GENERAL HELPERS
# ============================================================

def load_json(path, default=None):
    path = Path(path)

    if not path.exists():
        return default if default is not None else []

    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARNING: Could not read {path.name}: {exc}")
        return default if default is not None else []


def save_json(path, data):
    """Write JSON atomically so interrupted runs don't corrupt files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = path.with_suffix(path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False,
        )
        handle.write("\n")

    temporary_path.replace(path)


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def text_value(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, (int, float, bool)):
        return str(value)

    if isinstance(value, list):
        return "; ".join(
            text_value(item) for item in value if item is not None
        )

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def first_value(record, *keys, default=""):
    if not isinstance(record, dict):
        return default

    for key in keys:
        value = record.get(key)

        if value is not None and value != "":
            return value

    return default


def extract_json(text):
    """Extract a JSON object, including one surrounded by code fences."""
    if isinstance(text, dict):
        return text

    if not isinstance(text, str):
        return None

    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\s*```$", "", text)

    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")

    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False

            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1

            if depth == 0:
                candidate = text[start:index + 1]

                try:
                    result = json.loads(candidate)
                    return (
                        result
                        if isinstance(result, dict)
                        else None
                    )
                except json.JSONDecodeError:
                    return None

    return None


def normalise_text(value):
    value = text_value(value).lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalise_url(value):
    """Normalise a URL without treating unrelated URLs as equivalent."""
    value = text_value(value)

    if not value:
        return ""

    try:
        parsed = urlparse(value)

        if not parsed.netloc:
            return ""

        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        path = parsed.path.rstrip("/")

        return urlunparse(
            (
                parsed.scheme.lower() or "https",
                host,
                path,
                "",
                parsed.query,
                "",
            )
        ).rstrip("/")
    except (ValueError, TypeError):
        return ""


# ============================================================
# ENVIRONMENT AND OPENAI
# ============================================================

def load_dotenv_file():
    """Load project .env values without displaying secrets."""
    env_path = ROOT / ".env"

    if not env_path.exists():
        return

    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return

    for line in lines:
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        if line.lower().startswith("export "):
            line = line[7:].strip()

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value.startswith(("'", '"')) and value.endswith(
            ("'", '"')
        ):
            value = value[1:-1]

        if key and key not in os.environ:
            os.environ[key] = value


def get_openai_client():
    load_dotenv_file()

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Check the project .env file "
            "or the current PowerShell environment."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "The OpenAI Python package is missing. Install it with: "
            "python -m pip install openai"
        ) from exc

    return OpenAI(api_key=api_key)


# ============================================================
# OLLAMA — LOCAL SPECIALIST JOURNALISTS
# ============================================================

def ollama_generate(
    system_prompt,
    user_prompt,
    max_tokens=1400,
    temperature=0.45,
):
    payload = {
        "model": OLLAMA_MODEL,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.85,
            "num_predict": max_tokens,
            "num_ctx": 4096,
        },
    }

    body = json.dumps(payload).encode("utf-8")

    request = Request(
        f"{OLLAMA_URL}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=SPECIALIST_TIMEOUT,
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        output = result.get("response", "")

        if not output.strip():
            raise RuntimeError("Ollama returned an empty response.")

        return output.strip()

    except HTTPError as exc:
        raise RuntimeError(
            f"Ollama HTTP error {exc.code}: {exc.reason}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Cannot reach Ollama at {OLLAMA_URL}. "
            "Check that Ollama is running."
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError("Ollama request timed out.") from exc


# ============================================================
# INTELLIGENCE DATA
# ============================================================

def find_briefs(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in ("briefs", "records", "items", "results"):
        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


def find_evidence(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in (
        "records",
        "evidence",
        "adjudications",
        "items",
        "results",
    ):
        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


def find_selected_investigations(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in (
        "selected_investigations",
        "editorial_queue",
        "candidates",
        "investigations",
        "items",
    ):
        value = data.get(key)

        if isinstance(value, list) and value:
            return value

    return []


def record_for_item(item, briefs):
    if not isinstance(item, dict):
        return {}

    item_id = text_value(
        first_value(item, "record_id", "id", "brief_id")
    )

    item_title = normalise_text(
        first_value(item, "title", "headline", "name")
    )

    for brief in briefs:
        if not isinstance(brief, dict):
            continue

        brief_id = text_value(
            first_value(brief, "record_id", "id", "brief_id")
        )

        if item_id and brief_id and item_id == brief_id:
            return brief

        brief_title = normalise_text(
            first_value(brief, "title", "headline", "name")
        )

        if item_title and brief_title and item_title == brief_title:
            return brief

    return item


def compact_record(record):
    keys = (
        "record_id",
        "id",
        "title",
        "headline",
        "source",
        "url",
        "date",
        "published_at",
        "published",
        "source_type",
        "development_type",
        "entities",
        "claims",
        "quantitative_signals",
        "evidence",
        "open_questions",
        "summary",
        "description",
    )

    if not isinstance(record, dict):
        return {}

    return {
        key: record[key]
        for key in keys
        if key in record and record[key] is not None
    }


def build_material(item, briefs, evidence):
    """
    Build story-specific material.

    Evidence is matched by source URL or exact normalised title.
    We deliberately do not give every story the same first 20 records.
    """
    selected = item if isinstance(item, dict) else {}
    record = record_for_item(selected, briefs)

    selected_title = normalise_text(
        first_value(
            record,
            "title",
            "headline",
            default=first_value(
                selected, "title", "headline", "name"
            ),
        )
    )

    selected_url = normalise_url(
        first_value(
            record,
            "url",
            "source_url",
            "link",
            default=first_value(
                selected, "url", "source_url", "link"
            ),
        )
    )

    matching_evidence = []

    for entry in evidence:
        if not isinstance(entry, dict):
            continue

        evidence_url = normalise_url(
            first_value(entry, "url", "source_url", "link")
        )

        evidence_title = normalise_text(
            first_value(entry, "title", "headline", "name")
        )

        same_url = bool(
            selected_url
            and evidence_url
            and selected_url == evidence_url
        )

        same_title = bool(
            selected_title
            and evidence_title
            and selected_title == evidence_title
        )

        if same_url or same_title:
            matching_evidence.append(entry)

    material = {
        "selected_item": selected,
        "record": compact_record(record),
        "evidence": matching_evidence[:20],
        "evidence_match_count": len(matching_evidence),
        "evidence_gap": len(matching_evidence) == 0,
    }

    return material


# ============================================================
# THREE LOCAL SPECIALISTS
# ============================================================

def futurist_prompt(material):
    return f"""
You are FUTURIST, a technology correspondent at Machina Daily.

Analyse the intelligence below. Do not write the final article.

Identify:
- What is technically new or significant.
- What the technology demonstrably does versus what is claimed.
- Relevant capabilities, limitations and deployment constraints.
- Whether this is a genuine shift, incremental progress or hype.
- What evidence would establish that it matters.
- What might happen next, clearly labelled as analysis rather than fact.

Do not invent numbers, quotations, sources or events.
Be specific. Distinguish documented facts from inference.

INTELLIGENCE:
{json.dumps(material, ensure_ascii=False, indent=2)}
""".strip()


def auditor_prompt(material):
    return f"""
You are AUDITOR, Machina Daily's evidence and accountability journalist.

Analyse the intelligence. Do not write the final article.

Identify:
- Facts directly supported by the supplied material.
- Claims that need attribution.
- Evidence quality and source limitations.
- Missing figures, dates, context or independent verification.
- Conflicting claims or uncertainty.
- What the final article must not state as established fact.

Never invent corroboration, quotations, figures or sources.
If the evidence is weak or missing, say so explicitly.

INTELLIGENCE:
{json.dumps(material, ensure_ascii=False, indent=2)}
""".strip()


def strategist_prompt(material):
    return f"""
You are STRATEGIST, Machina Daily's business, geopolitical and
competitive intelligence correspondent.

Analyse the intelligence. Do not write the final article.

Identify:
- Who benefits and who faces competitive pressure.
- Commercial, industrial, economic or geopolitical consequences.
- Relevant customers, suppliers, competitors or governments.
- Second-order effects and plausible future scenarios.
- Incentives and strategic trade-offs.
- Which conclusions are facts and which are your analysis.

Do not invent deals, revenue, dates, quotations or outcomes.
Tie every conclusion to the supplied material.

INTELLIGENCE:
{json.dumps(material, ensure_ascii=False, indent=2)}
""".strip()


def run_specialist(name, prompt):
    print(f"  Running {name} on Ollama ({OLLAMA_MODEL})...")

    try:
        analysis = ollama_generate(
            system_prompt=prompt,
            user_prompt=(
                "Analyse the supplied material now. "
                "Return your findings as clear, structured prose."
            ),
            max_tokens=1000,
            temperature=0.4,
        )

        return {
            "specialist": name,
            "model": OLLAMA_MODEL,
            "analysis": analysis,
            "error": None,
        }

    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        print(f"  WARNING: {name} failed: {message}")

        return {
            "specialist": name,
            "model": OLLAMA_MODEL,
            "analysis": "",
            "error": message,
        }


# ============================================================
# FINAL EDITOR — OPENAI
# ============================================================

def editor_prompt(material, futurist, auditor, strategist):
    return f"""
You are the final editor and investigative journalist at Machina Daily.

Write an original, evidence-led article using the intelligence record
and the three specialist reports below.

EDITORIAL STANDARD
- Write original journalism, not a rewritten source article.
- Establish the central development and why it matters.
- Explain the technical, commercial or strategic significance.
- Use the auditor's warnings to prevent unsupported assertions.
- Use the futurist and strategist reports as analysis, not proof.
- Distinguish facts, attributed claims and your own analysis.
- Never invent quotations, interviews, dates, figures, sources or events.
- Never imply independent verification that the evidence does not show.
- Avoid generic introductions, repetition, promotional language and hype.
- Do not mention AI agents, prompts or the process used to create the article.
- If evidence is thin, write a careful, appropriately qualified article.
- Preserve relevant dates and source attribution.
- The article must be at least {MINIMUM_ARTICLE_WORDS} words.
- Use paragraphs and useful section headings where appropriate.
- Do not put the article inside Markdown code fences.

Return one valid JSON object only, with these keys:
{{
  "headline": "A specific, accurate headline",
  "dek": "A concise explanatory standfirst",
  "article": "Full article as plain text with paragraph breaks",
  "key_findings": ["Finding 1", "Finding 2"],
  "evidence_notes": ["What the evidence supports"],
  "uncertainties": ["What remains unknown"],
  "sources": [
    {{
      "title": "Source title if available",
      "url": "Source URL if available",
      "date": "Publication date if available"
    }}
  ]
}}

Do not invent source URLs. Use an empty string when a URL is unavailable.
Use empty lists when the supplied material does not support a list item.
Do not return any keys outside the requested structure.

SELECTED STORY AND EVIDENCE:
{json.dumps(material, ensure_ascii=False, indent=2)}

FUTURIST REPORT:
{futurist}

AUDITOR REPORT:
{auditor}

STRATEGIST REPORT:
{strategist}
""".strip()


def validate_editor_result(result, material):
    if not isinstance(result, dict):
        return False, "Editor response is not a JSON object."

    headline = text_value(
        first_value(result, "headline", "title")
    )

    dek = text_value(
        first_value(result, "dek", "standfirst", "subtitle")
    )

    article = text_value(
        first_value(result, "article", "body", "content")
    )

    if not headline:
        return False, "Missing headline."

    if not dek:
        return False, "Missing dek/standfirst."

    if not article:
        return False, "Missing article body."

    words = re.findall(r"\b[\w'-]+\b", article)

    if len(words) < MINIMUM_ARTICLE_WORDS:
        return (
            False,
            f"Article contains {len(words)} words; "
            f"minimum is {MINIMUM_ARTICLE_WORDS}.",
        )

    record = material.get("record", {})
    selected = material.get("selected_item", {})

    source_title = normalise_text(
        first_value(
            record,
            "title",
            "headline",
            default=first_value(
                selected, "title", "headline", "name"
            ),
        )
    )

    headline_text = normalise_text(headline)

    title_words = {
        word for word in source_title.split() if len(word) > 2
    }

    headline_words = set(headline_text.split())

    if len(title_words) >= 3:
        overlap = len(title_words & headline_words) / len(title_words)

        if overlap < 0.15:
            return (
                False,
                "Headline does not appear to match the selected story.",
            )

    result["headline"] = headline
    result["dek"] = dek
    result["article"] = article

    for key in (
        "key_findings",
        "evidence_notes",
        "uncertainties",
        "sources",
    ):
        value = result.get(key)

        if not isinstance(value, list):
            result[key] = []

    result["word_count"] = len(words)

    return True, "Article passed validation."



def build_material(item, briefs, evidence):
    """
    Build story-specific material.

    Match adjudicated evidence using:
    1. Queue ID against evidence research_id.
    2. Selected story URL against nested source.item_url.
    3. Source URL fields at the top level.
    4. Exact normalised story title.
    """
    selected = item if isinstance(item, dict) else {}
    record = record_for_item(selected, briefs)

    selected_id = text_value(
        first_value(
            selected, "record_id", "id", "brief_id"
        )
    )

    record_id = text_value(
        first_value(
            record, "record_id", "id", "brief_id"
        )
    )

    selected_title = normalise_text(
        first_value(
            record,
            "title",
            "headline",
            default=first_value(
                selected, "title", "headline", "name"
            ),
        )
    )

    selected_url = normalise_url(
        first_value(
            record,
            "url",
            "source_url",
            "link",
            default=first_value(
                selected, "url", "source_url", "link"
            ),
        )
    )

    matching_evidence = []

    for entry in evidence:
        if not isinstance(entry, dict):
            continue

        nested_source = entry.get("source", {})
        if not isinstance(nested_source, dict):
            nested_source = {}

        evidence_url_values = [
            entry.get("url"),
            entry.get("source_url"),
            entry.get("item_url"),
            nested_source.get("item_url"),
            nested_source.get("url"),
            nested_source.get("source_url"),
        ]

        evidence_urls = {
            normalise_url(value)
            for value in evidence_url_values
            if normalise_url(value)
        }

        evidence_title = normalise_text(
            first_value(
                entry,
                "title",
                "headline",
                "name",
                default=first_value(
                    nested_source,
                    "title",
                    "item_title",
                    "name",
                ),
            )
        )

        evidence_research_id = text_value(
            first_value(entry, "research_id", "record_id", "id")
        )

        # Exact IDs are the strongest match.
        same_id = bool(
            evidence_research_id
            and evidence_research_id in {
                selected_id,
                record_id,
            }
        )

        same_url = bool(
            selected_url and selected_url in evidence_urls
        )

        same_title = bool(
            selected_title
            and evidence_title
            and selected_title == evidence_title
        )

        if same_id or same_url or same_title:
            matching_evidence.append(entry)

    return {
        "selected_item": selected,
        "record": compact_record(record),
        "evidence": matching_evidence[:20],
        "evidence_match_count": len(matching_evidence),
        "evidence_gap": len(matching_evidence) == 0,
    }

def run_editor(material, futurist, auditor, strategist):
    prompt = editor_prompt(material, futurist, auditor, strategist)

    try:
        client = get_openai_client()
    except Exception as exc:
        return {
            "_valid": False,
            "_error": f"OpenAI setup failed: {exc}",
            "_attempts": 0,
        }

    last_error = "No editor attempt completed."

    for attempt in range(1, EDITOR_ATTEMPTS + 1):
        print(
            f"  Running FINAL EDITOR using OpenAI "
            f"({EDITOR_MODEL}), attempt {attempt}/{EDITOR_ATTEMPTS}..."
        )

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are Machina Daily's rigorous final editor. "
                        "Return only a valid JSON object. Never invent facts."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]

            if attempt > 1:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "This is a new attempt. Follow the requested "
                            "JSON structure exactly. Ensure the article "
                            f"contains at least {MINIMUM_ARTICLE_WORDS} "
                            "words, matches the selected story, and uses "
                            "only supported facts. Return JSON only."
                        ),
                    }
                )

            response = client.chat.completions.create(
                model=EDITOR_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.25,
                max_completion_tokens=4000,
            )

            content = response.choices[0].message.content or ""
            result = extract_json(content)

            if result is None:
                last_error = "OpenAI did not return parseable JSON."
                print(f"  WARNING: {last_error}")
                continue

            valid, validation_message = validate_editor_result(
                result,
                material,
            )

            if not valid:
                last_error = validation_message
                print(f"  WARNING: {validation_message}")
                continue

            result["_valid"] = True
            result["_error"] = None
            result["_attempts"] = attempt
            result["_editor_model"] = EDITOR_MODEL

            print(
                f"  VALID ARTICLE: {result['headline']} "
                f"({result['word_count']} words)"
            )

            return result

        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"  WARNING: OpenAI editor attempt failed: {last_error}")

    return {
        "_valid": False,
        "_error": last_error,
        "_attempts": EDITOR_ATTEMPTS,
        "_editor_model": EDITOR_MODEL,
    }


# ============================================================
# OUTPUT HELPERS
# ============================================================

def clean_public_article(editor_result):
    """Remove internal validation/debug fields from saved article JSON."""
    return {
        key: value
        for key, value in editor_result.items()
        if not key.startswith("_")
    }


def selected_story_title(material):
    record = material.get("record", {})
    selected = material.get("selected_item", {})

    return text_value(
        first_value(
            record,
            "title",
            "headline",
            default=first_value(
                selected, "title", "headline", "name",
                default="Untitled investigation",
            ),
        )
    )


def selected_story_id(material, index):
    record = material.get("record", {})
    selected = material.get("selected_item", {})

    return text_value(
        first_value(
            record,
            "record_id",
            "id",
            "brief_id",
            default=first_value(
                selected,
                "record_id",
                "id",
                "brief_id",
                default=f"unknown-{index:03d}",
            ),
        )
    )


# ============================================================
# MAIN NEWSROOM
# ============================================================

def main():
    print()
    print("=" * 70)
    print("MACHINA DAILY — LOCAL INTELLIGENCE EDITORIAL BOARD")
    print("=" * 70)
    print(f"Root:             {ROOT}")
    print(f"Ollama specialists: {OLLAMA_MODEL}")
    print(f"OpenAI final editor: {EDITOR_MODEL}")
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    briefs_data = load_json(BRIEFS_FILE, default={})
    evidence_data = load_json(EVIDENCE_FILE, default={})
    queue_data = load_json(QUEUE_FILE, default={})

    briefs = find_briefs(briefs_data)
    evidence = find_evidence(evidence_data)
    selected = find_selected_investigations(queue_data)

    if not briefs:
        print(f"ERROR: No intelligence briefs found in {BRIEFS_FILE}")
        return

    if not selected:
        print(f"ERROR: No selected investigations found in {QUEUE_FILE}")
        print("Check that the editorial queue contains selected stories.")
        return

    limit = max(
        1,
        min(5, int(os.environ.get("MACHINA_EDITORIAL_LIMIT", "5"))),
    )

    selected = selected[:limit]

    print(f"Intelligence briefs: {len(briefs)}")
    print(f"Evidence records:    {len(evidence)}")
    print(f"Selected stories:    {len(selected)}")
    print()

    board = {
        "generated_at": utc_now(),
        "specialist_model": OLLAMA_MODEL,
        "editor_model": EDITOR_MODEL,
        "story_count": len(selected),
        "stories": [],
    }

    articles = {
        "generated_at": utc_now(),
        "specialist_model": OLLAMA_MODEL,
        "editor_model": EDITOR_MODEL,
        "articles": [],
    }

    for index, item in enumerate(selected, start=1):
        material = build_material(item, briefs, evidence)
        title = selected_story_title(material)
        record_id = selected_story_id(material, index)

        print("-" * 70)
        print(f"INVESTIGATION {index}/{len(selected)}")
        print(f"Story: {title}")
        print(f"Record: {record_id}")
        print(f"Matched evidence records: {material['evidence_match_count']}")

        story_output = {
            "record_id": record_id,
            "original_title": title,
            "source_url": first_value(
                material.get("record", {}),
                "url",
                "source_url",
                "link",
                default=first_value(
                    material.get("selected_item", {}),
                    "url",
                    "source_url",
                    "link",
                ),
            ),
            "generated_at": utc_now(),
            "specialist_model": OLLAMA_MODEL,
            "editor_model": EDITOR_MODEL,
            "evidence_match_count": material["evidence_match_count"],
        }

        # Run the three local specialist journalists.
        futurist_result = run_specialist(
            "FUTURIST",
            futurist_prompt(material),
        )

        auditor_result = run_specialist(
            "AUDITOR",
            auditor_prompt(material),
        )

        strategist_result = run_specialist(
            "STRATEGIST",
            strategist_prompt(material),
        )

        # Keep going if a specialist fails; the final editor receives
        # the available reports and can see which reports failed.
        editor_result = run_editor(
            material,
            futurist_result["analysis"] or (
                "FUTURIST analysis unavailable: "
                + text_value(futurist_result.get("error"))
            ),
            auditor_result["analysis"] or (
                "AUDITOR analysis unavailable: "
                + text_value(auditor_result.get("error"))
            ),
            strategist_result["analysis"] or (
                "STRATEGIST analysis unavailable: "
                + text_value(strategist_result.get("error"))
            ),
        )

        story_output["specialists"] = {
            "futurist": futurist_result,
            "auditor": auditor_result,
            "strategist": strategist_result,
        }

        story_output["editor"] = clean_public_article(editor_result)
        story_output["article_valid"] = (
            editor_result.get("_valid") is True
        )
        story_output["editor_error"] = editor_result.get("_error")
        story_output["editor_attempts"] = editor_result.get("_attempts")

        board["stories"].append(story_output)

        # Only validated articles enter the publication candidate file.
        if editor_result.get("_valid") is True:
            articles["articles"].append(
                {
                    "article_id": f"machina-editor-{index:03d}",
                    "record_id": record_id,
                    "original_title": title,
                    "source": first_value(
                        material.get("record", {}),
                        "source",
                        default=first_value(
                            material.get("selected_item", {}),
                            "source",
                        ),
                    ),
                    "source_url": story_output["source_url"],
                    "source_date": first_value(
                        material.get("record", {}),
                        "published_at",
                        "published",
                        "date",
                        default=first_value(
                            material.get("selected_item", {}),
                            "published_at",
                            "published",
                            "date",
                        ),
                    ),
                    "generated_at": utc_now(),
                    "specialist_model": OLLAMA_MODEL,
                    "editor_model": EDITOR_MODEL,
                    "article": clean_public_article(editor_result),
                }
            )
        else:
            print(
                "  ARTICLE NOT SAVED: final editor did not pass "
                "validation. Details are in editorial_board_outputs.json."
            )

        # Save checkpoints after every story, including failed attempts.
        board["generated_at"] = utc_now()
        articles["generated_at"] = utc_now()

        save_json(BOARD_OUTPUT, board)
        save_json(ARTICLES_OUTPUT, articles)

        print(
            f"  Valid articles saved: {len(articles['articles'])}"
        )

    print()
    print("=" * 70)
    print("NEWSROOM RUN COMPLETE")
    print("=" * 70)
    print(f"Stories processed: {len(board['stories'])}")
    print(f"Valid articles:    {len(articles['articles'])}")
    print(f"Board diagnostics: {BOARD_OUTPUT}")
    print(f"Article output:    {ARTICLES_OUTPUT}")

    failed_count = sum(
        1 for story in board["stories"]
        if not story.get("article_valid")
    )

    if failed_count:
        print(f"Failed validations: {failed_count}")
        print(
            "Review the editor_error field in the board output "
            "before attempting publication."
        )


if __name__ == "__main__":
    main()