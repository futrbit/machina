import json
import re
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path


# ============================================================
# MACHINA DAILY — LOCAL DEEP RESEARCHER
# ============================================================
#
# Uses local Ollama / Qwen3 instead of OpenAI.
#
# INPUT:
#   data/deep_research/investigative_report.json
#
# OUTPUT:
#   data/deep_research/deep_research_results.json
#
# MODEL:
#   qwen3:4b
#
# NETWORK:
#   Ollama only — localhost:11434
#
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent

INVESTIGATIVE_FILE = (
    BASE_DIR
    / "data"
    / "deep_research"
    / "investigative_report.json"
)

OUTPUT_DIR = (
    BASE_DIR
    / "data"
    / "deep_research"
)

RESEARCH_OUTPUT = (
    OUTPUT_DIR
    / "deep_research_results.json"
)

PROGRESS_OUTPUT = (
    OUTPUT_DIR
    / "deep_research_progress.json"
)

OLLAMA_URL = "http://localhost:11434/api/generate"

MODEL = "gemma2:2b"

MAX_RESEARCH_RECORDS = 100

OLLAMA_TIMEOUT = 600

TEMPERATURE = 0.2

NUM_PREDICT = 3000

NUM_CTX = 8192


# ============================================================
# DEVELOPMENT PRIORITY
# ============================================================

DEVELOPMENT_PRIORITY = {
    "contract": 10,
    "deployment": 9,
    "funding": 8,
    "acquisition": 8,
    "partnership": 7,
    "launch": 6,
    "research": 5,
    "expansion": 4,
}


# ============================================================
# HELPERS
# ============================================================

def safe_list(value):
    if isinstance(value, list):
        return value

    if value is None:
        return []

    return [value]


def clean_text(value, limit=None):
    if value is None:
        return ""

    if not isinstance(value, str):
        value = str(value)

    value = value.strip()

    if limit and len(value) > limit:
        value = value[:limit]

    return value


def calculate_priority(record):
    """
    Deterministic ranking used to select the most important
    investigative records for deeper local research.
    """

    score = 0

    developments = safe_list(
        record.get("development_types")
        or record.get("developments")
        or record.get("development_type")
    )

    for development in developments:
        development = str(development).lower().strip()

        for key, weight in DEVELOPMENT_PRIORITY.items():
            if key in development:
                score += weight

    companies = safe_list(
        record.get("companies")
    )

    technologies = safe_list(
        record.get("technologies")
    )

    claims = safe_list(
        record.get("claim_candidates")
        or record.get("claims")
    )

    questions = safe_list(
        record.get("research_questions")
        or record.get("questions")
    )

    score += min(len(companies), 10)
    score += min(len(technologies), 8)
    score += min(len(claims), 12)
    score += min(len(questions), 10)

    return score


def make_research_id(record):
    """
    Stable ID derived from the investigative record.
    """

    source_url = clean_text(
        record.get("item_url")
        or record.get("url")
        or ""
    )

    original_id = clean_text(
        record.get("research_id")
        or record.get("id")
        or ""
    )

    raw = f"{original_id}|{source_url}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:16]


# ============================================================
# PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are the Deep Researcher inside MACHINA DAILY.

You are NOT writing a news article.

You are performing structured investigative research on a source record.

Your job is to determine:

1. What is being claimed?
2. Which statements are claims rather than established facts?
3. What evidence would be needed to verify those claims?
4. What primary sources should be searched?
5. What independent sources should be searched?
6. What evidence could contradict the claims?
7. What entities, technologies and developments are involved?
8. What facts appear reasonably established from the supplied source?
9. What remains unknown?

IMPORTANT RULES:

- Do not invent facts.
- Do not invent sources.
- Do not claim that you searched a source when you did not.
- Do not pretend that evidence exists when it was not supplied.
- Clearly distinguish CLAIM from EVIDENCE from INFERENCE from UNKNOWN.
- Treat the supplied source as a source to analyse, not as automatically true.
- Be skeptical of promotional language.
- Identify allegations and reported claims as claims.
- If information is insufficient, say so.
- Prefer primary evidence such as company filings, government documents,
  official announcements, court records, regulatory documents,
  technical papers and direct statements.
- Independent reporting can be identified as a possible research target,
  but do not pretend it has already been checked.
- Return ONLY valid JSON.
- Do not use Markdown.
- Do not put the JSON inside a code fence.
"""


def build_research_prompt(record):

    source = record.get("source", {})

    if not isinstance(source, dict):
        source = {}

    title = clean_text(
        record.get("title")
        or record.get("headline")
        or ""
    )

    summary = clean_text(
        record.get("summary")
        or record.get("description")
        or record.get("text")
        or ""
    )

    source_name = clean_text(
        source.get("name")
        or record.get("source_name")
        or record.get("source")
        or ""
    )

    source_type = clean_text(
        source.get("type")
        or record.get("source_type")
        or ""
    )

    source_url = clean_text(
        source.get("url")
        or record.get("source_url")
        or ""
    )

    item_url = clean_text(
        record.get("item_url")
        or record.get("url")
        or ""
    )

    published = clean_text(
        record.get("published")
        or record.get("published_at")
        or ""
    )

    companies = safe_list(
        record.get("companies")
    )

    technologies = safe_list(
        record.get("technologies")
    )

    developments = safe_list(
        record.get("development_types")
        or record.get("developments")
    )

    claims = safe_list(
        record.get("claim_candidates")
        or record.get("claims")
    )

    questions = safe_list(
        record.get("research_questions")
        or record.get("questions")
    )

    payload = {
        "source_name": source_name,
        "source_type": source_type,
        "source_url": source_url,
        "item_url": item_url,
        "published": published,
        "title": title,
        "summary": summary,
        "companies": companies,
        "technologies": technologies,
        "developments": developments,
        "claim_candidates": claims,
        "research_questions": questions,
    }

    return (
        SYSTEM_PROMPT
        + "\n\nSOURCE RECORD:\n"
        + json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        )
        + """

Return exactly this JSON structure:

{
  "research_id": "",
  "source_assessment": {
    "source_type": "",
    "source_role": "",
    "source_reliability_notes": ""
  },
  "claims": [
    {
      "statement": "",
      "claimant": "",
      "claim_type": "",
      "verification_status": "unverified",
      "evidence_needed": []
    }
  ],
  "established_information": [],
  "entities": {
    "companies": [],
    "people": [],
    "organisations": [],
    "products": [],
    "programmes": [],
    "technologies": []
  },
  "developments": [],
  "research_targets": [
    {
      "question": "",
      "priority": "high",
      "preferred_evidence": [],
      "possible_primary_sources": [],
      "possible_independent_sources": [],
      "possible_contradictory_evidence": []
    }
  ],
  "unknowns": [],
  "contradiction_targets": [],
  "next_action": ""
}

The verification_status should normally be "unverified"
unless the supplied source itself provides enough direct evidence
to establish something.

Do not add explanations outside the JSON.
"""
    )


# ============================================================
# QWEN / OLLAMA
# ============================================================

def call_ollama(prompt):

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
            "num_ctx": NUM_CTX,
        }
    }

    body = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=OLLAMA_TIMEOUT
        ) as response:

            raw = response.read().decode(
                "utf-8"
            )

            result = json.loads(raw)

            return clean_text(
                result.get("response")
            )

    except urllib.error.URLError as exc:

        raise RuntimeError(
            f"Ollama connection failed: {exc}"
        )

    except TimeoutError:

        raise RuntimeError(
            "Ollama request timed out."
        )


# ============================================================
# JSON CLEANING
# ============================================================

def strip_qwen_thinking(text):

    """
    Qwen3 can return:

    <think>
    ...
    </think>

    before the JSON.

    Remove that reasoning section before parsing.
    """

    if not text:
        return ""

    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    return text.strip()


def extract_json(text):

    if not text:
        raise ValueError(
            "Ollama returned an empty response."
        )

    text = strip_qwen_thinking(text)

    # Remove Markdown fences.
    text = re.sub(
        r"```json\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"```\s*",
        "",
        text
    )

    text = text.strip()

    # First attempt: whole response.
    try:
        return json.loads(text)

    except json.JSONDecodeError:
        pass

    # Second attempt: locate JSON object.
    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:

        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)

        except json.JSONDecodeError as exc:

            raise ValueError(
                "Qwen returned text containing JSON, "
                f"but the JSON could not be parsed: {exc}"
            )

    raise ValueError(
        "Could not find a JSON object in Qwen response."
    )


# ============================================================
# NORMALISE RESULT
# ============================================================

def normalise_result(result, record):

    if not isinstance(result, dict):
        raise ValueError(
            "Research result is not a JSON object."
        )

    research_id = (
        result.get("research_id")
        or make_research_id(record)
    )

    result["research_id"] = research_id

    source_assessment = result.get(
        "source_assessment"
    )

    if not isinstance(source_assessment, dict):
        source_assessment = {}

    result["source_assessment"] = {
        "source_type": clean_text(
            source_assessment.get("source_type")
        ),
        "source_role": clean_text(
            source_assessment.get("source_role")
        ),
        "source_reliability_notes": clean_text(
            source_assessment.get(
                "source_reliability_notes"
            )
        ),
    }

    list_fields = [
        "claims",
        "established_information",
        "developments",
        "research_targets",
        "unknowns",
        "contradiction_targets",
    ]

    for field in list_fields:

        if not isinstance(result.get(field), list):
            result[field] = []

    entities = result.get("entities")

    if not isinstance(entities, dict):
        entities = {}

    entity_fields = [
        "companies",
        "people",
        "organisations",
        "products",
        "programmes",
        "technologies",
    ]

    for field in entity_fields:

        if not isinstance(
            entities.get(field),
            list
        ):
            entities[field] = []

    result["entities"] = entities

    if not isinstance(
        result.get("next_action"),
        str
    ):
        result["next_action"] = ""

    return result


# ============================================================
# RESEARCH ONE RECORD
# ============================================================

def research_record(record):

    prompt = build_research_prompt(
        record
    )

    raw_response = call_ollama(
        prompt
    )

    parsed = extract_json(
        raw_response
    )

    return normalise_result(
        parsed,
        record
    )


# ============================================================
# LOAD INVESTIGATIVE DATA
# ============================================================

def load_investigative_records():

    if not INVESTIGATIVE_FILE.exists():

        raise FileNotFoundError(
            "Investigative report not found:\n"
            f"{INVESTIGATIVE_FILE}"
        )

    data = json.loads(
        INVESTIGATIVE_FILE.read_text(
            encoding="utf-8"
        )
    )

    if isinstance(data, list):
        records = data

    elif isinstance(data, dict):

        records = (
            data.get("records")
            or data.get("research_records")
            or data.get("items")
            or []
        )

    else:

        records = []

    if not isinstance(records, list):
        records = []

    return records


# ============================================================
# PROGRESS
# ============================================================

def save_progress(results):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    progress = {
        "status": "running",
        "model": MODEL,
        "provider": "ollama_local",
        "openai_calls": 0,
        "records_completed": len(results),
        "records_target": MAX_RESEARCH_RECORDS,
        "results": results,
    }

    PROGRESS_OUTPUT.write_text(
        json.dumps(
            progress,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("MACHINA DAILY — LOCAL DEEP RESEARCHER")
    print("=" * 70)
    print()
    print(f"Model:              {MODEL}")
    print("Provider:            Ollama / localhost")
    print("OpenAI API calls:    0")
    print(f"Investigative file:  {INVESTIGATIVE_FILE}")
    print()

    records = load_investigative_records()

    print(
        f"Investigative records available: {len(records)}"
    )

    if not records:

        raise RuntimeError(
            "No investigative records were found."
        )

    # --------------------------------------------------------
    # RANK RECORDS
    # --------------------------------------------------------

    ranked = []

    for record in records:

        score = calculate_priority(
            record
        )

        ranked.append(
            (
                score,
                record
            )
        )

    ranked.sort(
        key=lambda item: item[0],
        reverse=True
    )

    selected = [
        record
        for score, record in ranked[
            :MAX_RESEARCH_RECORDS
        ]
    ]

    print(
        f"Records selected for deep research: "
        f"{len(selected)}"
    )

    print()

    # --------------------------------------------------------
    # RESEARCH
    # --------------------------------------------------------

    results = []

    failures = []

    total = len(selected)

    start_time = time.time()

    for index, record in enumerate(
        selected,
        start=1
    ):

        title = clean_text(
            record.get("title")
            or record.get("headline")
            or "Untitled"
        )

        print(
            f"[{index}/{total}] "
            f"Researching: {title[:100]}"
        )

        try:

            result = research_record(
                record
            )

            # Keep useful source metadata alongside
            # the AI research result.

            result["_source"] = {
                "title": title,
                "source_name": clean_text(
                    record.get("source_name")
                    or (
                        record.get("source", {})
                        .get("name", "")
                        if isinstance(
                            record.get("source"),
                            dict
                        )
                        else ""
                    )
                ),
                "item_url": clean_text(
                    record.get("item_url")
                    or record.get("url")
                    or ""
                ),
                "published": clean_text(
                    record.get("published")
                    or record.get("published_at")
                    or ""
                ),
            }

            result["_priority_score"] = (
                calculate_priority(record)
            )

            results.append(
                result
            )

            save_progress(
                results
            )

            print(
                f"      OK — "
                f"{len(result.get('claims', []))} claims, "
                f"{len(result.get('research_targets', []))} targets"
            )

        except Exception as exc:

            error_record = {
                "research_id": make_research_id(
                    record
                ),
                "title": title,
                "error": str(exc),
            }

            failures.append(
                error_record
            )

            print(
                f"      FAILED — {exc}"
            )

        # Small pause prevents hammering local Ollama.
        time.sleep(0.5)

    # --------------------------------------------------------
    # FINAL OUTPUT
    # --------------------------------------------------------

    elapsed = time.time() - start_time

    output = {
        "status": "complete",
        "model": MODEL,
        "provider": "ollama_local",
        "openai_calls": 0,
        "source_records_available": len(records),
        "records_selected": len(selected),
        "records_processed": len(results),
        "records_failed": len(failures),
        "research_records": results,
        "failures": failures,
        "metadata": {
            "investigative_file": str(
                INVESTIGATIVE_FILE
            ),
            "model": MODEL,
            "ollama_url": OLLAMA_URL,
            "max_research_records": MAX_RESEARCH_RECORDS,
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
            "num_ctx": NUM_CTX,
            "elapsed_seconds": round(
                elapsed,
                2
            ),
        }
    }

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    RESEARCH_OUTPUT.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # Final progress state.
    final_progress = {
        "status": "complete",
        "model": MODEL,
        "provider": "ollama_local",
        "openai_calls": 0,
        "records_completed": len(results),
        "records_target": len(selected),
        "records_failed": len(failures),
    }

    PROGRESS_OUTPUT.write_text(
        json.dumps(
            final_progress,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print()
    print("=" * 70)
    print("LOCAL DEEP RESEARCH COMPLETE")
    print("=" * 70)
    print()
    print(
        f"Source records available: {len(records)}"
    )
    print(
        f"Records selected:         {len(selected)}"
    )
    print(
        f"Records researched:       {len(results)}"
    )
    print(
        f"Records failed:           {len(failures)}"
    )
    print(
        f"Model:                    {MODEL}"
    )
    print(
        "Provider:                  Ollama / localhost"
    )
    print(
        "OpenAI API calls:         0"
    )
    print()
    print(
        f"Saved to:\n{RESEARCH_OUTPUT}"
    )
    print()
    print(
        f"Elapsed time:             {elapsed / 60:.1f} minutes"
    )
    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
