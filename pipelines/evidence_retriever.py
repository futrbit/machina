import os
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import requests
import feedparser
from bs4 import BeautifulSoup


BASE_DIR = Path(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

INPUT_FILE = (
    BASE_DIR
    / "data"
    / "deep_research"
    / "deep_research_results.json"
)

OUTPUT_DIR = (
    BASE_DIR
    / "data"
    / "deep_research"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "evidence_candidates.json"
)


MAX_RESEARCH_RECORDS = 100
MAX_TARGETS_PER_RECORD = 5
MAX_RESULTS_PER_QUERY = 5
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 1.0


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36 "
        "MachinaDailyResearch/1.0"
    )
}


PRIMARY_DOMAIN_HINTS = [
    ".gov",
    ".gov.uk",
    ".mil",
    "darpa.mil",
    "diu.mil",
    "nasa.gov",
    "nato.int",
    "europa.eu",
    "esa.int",
    "dstl.gov.uk",
    "mod.uk",
    "gov.au",
    "gov.ca",
    "gov.jp",
    "gov.kr",
]


COMPANY_DOMAIN_HINTS = [
    "openai.com",
    "anthropic.com",
    "deepmind.google",
    "google.com",
    "meta.com",
    "x.ai",
    "mistral.ai",
    "figure.ai",
    "agilityrobotics.com",
    "1x.tech",
    "apptronik.com",
    "bostondynamics.com",
    "anduril.com",
    "shield.ai",
    "skydio.com",
    "zipline.com",
    "waymo.com",
    "aurora.tech",
    "zoox.com",
    "spacex.com",
    "nvidia.com",
    "amd.com",
    "tsmc.com",
    "asml.com",
]


def load_input():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing input file: {INPUT_FILE}"
        )

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as handle:
        return json.load(handle)


def normalise_url(url):
    if not url:
        return ""

    url = url.strip()

    if not url.startswith(("http://", "https://")):
        return ""

    return url


def domain_from_url(url):
    try:
        return (
            urlparse(url)
            .netloc
            .lower()
            .replace("www.", "")
        )
    except Exception:
        return ""


def classify_source(url):
    domain = domain_from_url(url)

    for hint in PRIMARY_DOMAIN_HINTS:
        if hint in domain:
            return "primary"

    for hint in COMPANY_DOMAIN_HINTS:
        if hint in domain:
            return "company_primary"

    return "independent_candidate"


def make_evidence_id(url):
    return hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()[:24]


def clean_text(text):
    if not text:
        return ""

    text = " ".join(
        text.replace("\xa0", " ").split()
    )

    return text[:12000]


def extract_page(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code >= 400:
            return None

        content_type = (
            response.headers
            .get("content-type", "")
            .lower()
        )

        if "text/html" not in content_type:
            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup([
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header"
        ]):
            tag.decompose()

        title = ""

        if soup.title:
            title = soup.title.get_text(
                " ",
                strip=True
            )

        paragraphs = []

        for element in soup.find_all(
            ["p", "article"]
        ):
            text = element.get_text(
                " ",
                strip=True
            )

            if len(text) >= 40:
                paragraphs.append(text)

        body = clean_text(
            " ".join(paragraphs)
        )

        return {
            "final_url": response.url,
            "title": title,
            "text": body,
            "status_code": response.status_code
        }

    except Exception:
        return None


def google_news_search(query):
    encoded = quote(query)

    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded}"
        "&hl=en-GB"
        "&gl=GB"
        "&ceid=GB:en"
    )

    try:
        feed = feedparser.parse(url)

        results = []

        for entry in feed.entries[
            :MAX_RESULTS_PER_QUERY
        ]:

            result_url = (
                entry.get("link")
                or ""
            )

            result_url = normalise_url(
                result_url
            )

            if not result_url:
                continue

            results.append({
                "title": (
                    entry.get(
                        "title",
                        ""
                    )
                ),
                "url": result_url,
                "published": (
                    entry.get(
                        "published",
                        ""
                    )
                ),
                "summary": clean_text(
                    entry.get(
                        "summary",
                        ""
                    )
                )
            })

        return results

    except Exception as exc:
        print(
            f"    Search error: {exc}"
        )
        return []


def build_queries(result):
    targets = result.get(
        "research_targets",
        []
    )

    source = result.get(
        "input_source",
        {}
    )

    source_name = source.get(
        "source_name",
        ""
    )

    queries = []

    for target in targets[
        :MAX_TARGETS_PER_RECORD
    ]:

        question = (
            target.get(
                "question",
                ""
            )
            if isinstance(
                target,
                dict
            )
            else str(target)
        )

        if not question:
            continue

        queries.append(
            f"{question} {source_name}"
        )

    return queries


def collect_evidence(result):
    source = result.get(
        "input_source",
        {}
    )

    source_url = source.get(
        "item_url"
    ) or source.get(
        "source_url"
    )

    candidates = {}

    # First preserve the original source.
    if source_url:
        source_url = normalise_url(
            source_url
        )

        if source_url:
            candidates[source_url] = {
                "title": (
                    source.get(
                        "source_name",
                        ""
                    )
                ),
                "url": source_url,
                "published": (
                    source.get(
                        "published",
                        ""
                    )
                ),
                "discovery_method": (
                    "original_source"
                )
            }

    queries = build_queries(result)

    for query in queries:

        print(
            f"    SEARCH: {query[:140]}"
        )

        search_results = (
            google_news_search(query)
        )

        for item in search_results:

            url = item.get("url")

            if not url:
                continue

            if url not in candidates:
                candidates[url] = item

        time.sleep(
            REQUEST_DELAY
        )

    evidence = []

    for item in list(
        candidates.values()
    ):

        url = item.get("url")

        print(
            f"    FETCH: {url[:120]}"
        )

        page = extract_page(url)

        if not page:
            continue

        final_url = (
            page.get(
                "final_url"
            )
            or url
        )

        domain = domain_from_url(
            final_url
        )

        evidence_type = classify_source(
            final_url
        )

        evidence.append({
            "evidence_id": make_evidence_id(
                final_url
            ),

            "url": final_url,

            "domain": domain,

            "title": (
                page.get(
                    "title"
                )
                or item.get(
                    "title",
                    ""
                )
            ),

            "published": (
                item.get(
                    "published",
                    ""
                )
            ),

            "source_class": evidence_type,

            "discovery_method": (
                item.get(
                    "discovery_method",
                    "web_search"
                )
            ),

            "search_summary": (
                item.get(
                    "summary",
                    ""
                )
            ),

            "extracted_text": (
                page.get(
                    "text",
                    ""
                )
            ),

            "http_status": (
                page.get(
                    "status_code"
                )
            ),

            "retrieved_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )
        })

    return evidence


def main():

    print(
        "========================================"
    )
    print(
        "MACHINA EVIDENCE RETRIEVER"
    )
    print(
        "========================================"
    )

    data = load_input()

    results = data.get(
        "results",
        []
    )

    selected = results[
        :MAX_RESEARCH_RECORDS
    ]

    print(
        f"Research records available: "
        f"{len(results)}"
    )

    print(
        f"Records selected: "
        f"{len(selected)}"
    )

    print("")

    output_records = []

    for index, result in enumerate(
        selected,
        start=1
    ):

        source = result.get(
            "input_source",
            {}
        )

        title = source.get(
            "item_url",
            "Untitled"
        )

        print(
            f"[{index}/{len(selected)}] "
            f"{title[:100]}"
        )

        evidence = collect_evidence(
            result
        )

        output_records.append({
            "research_id": (
                result.get(
                    "research_id",
                    ""
                )
            ),

            "source": source,

            "research_targets": (
                result.get(
                    "research_targets",
                    []
                )
            ),

            "evidence": evidence,

            "retrieved_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )
        })

        print(
            f"    Evidence candidates: "
            f"{len(evidence)}"
        )

        print("")

    output = {
        "generated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "retriever": (
            "MACHINA EVIDENCE RETRIEVER"
        ),

        "records_available": len(
            results
        ),

        "records_processed": len(
            output_records
        ),

        "records": output_records
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as handle:

        json.dump(
            output,
            handle,
            ensure_ascii=False,
            indent=2
        )

    total_evidence = sum(
        len(
            record.get(
                "evidence",
                []
            )
        )
        for record in output_records
    )

    print(
        "========================================"
    )
    print(
        "EVIDENCE RETRIEVAL COMPLETE"
    )
    print(
        "========================================"
    )
    print(
        f"Records processed: "
        f"{len(output_records)}"
    )
    print(
        f"Evidence candidates: "
        f"{total_evidence}"
    )
    print(
        f"Saved to: {OUTPUT_FILE}"
    )
    print(
        "========================================"
    )


if __name__ == "__main__":
    main()
