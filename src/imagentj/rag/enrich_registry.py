"""
Enrichment script for plugin_registry.json.

For each plugin with a documentation_url, fetches the page via doc_fetcher
and uses GPT to extract improved field values. Keeps update_site_name,
update_site_url, requires_restart, name, and documentation_url unchanged.

Saves progress incrementally so the script can be restarted if interrupted.
"""

import json
import os
import time
from pathlib import Path
from openai import OpenAI
from doc_fetcher import fetch_content, classify_url, is_pdf

# ── Config ────────────────────────────────────────────────────────────────────

INPUT_PATH  = Path(__file__).parent / "plugin_registry.json"
OUTPUT_PATH = Path(__file__).parent / "plugin_registry_update.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL          = "gpt-5.2"
REQUEST_DELAY  = 1.2
LLM_DELAY      = 0.5

client = OpenAI(api_key=OPENAI_API_KEY)


# ── LLM extraction ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert in ImageJ/Fiji image analysis software.
Given documentation content for an ImageJ plugin, extract accurate values for
the registry fields below. Return a single JSON object with ONLY these keys.

Rules:
- If you are not confident about a value, return null — never guess.
- Keep strings concise and plain (no markdown, no bullet symbols).
- Lists: 3-6 items maximum.
- category must be exactly one of: segmentation, tracking, measurement,
  registration, visualization, filtering, colocalization, utilities,
  deep-learning, spectroscopy, morphology, format-io, annotation, statistics.

Fields:
- description      : One clear sentence describing what the plugin does.
- category         : Single category string from the list above.
- tags             : List of 4-8 lowercase keyword strings.
- input_data       : What image types or formats the plugin accepts.
- output_data      : What the plugin produces (label images, tables, ROIs, etc.).
- use_when         : When is this the right tool? One sentence.
- do_not_use_when  : When should the user NOT use this? One sentence.
- typical_use_cases: List of 3-5 concrete use case strings.
"""

def extract_fields_with_llm(plugin_name: str, text: str, existing: dict) -> dict:
    existing_subset = {
        k: existing.get(k)
        for k in ["description", "category", "tags", "input_data",
                  "output_data", "use_when", "do_not_use_when", "typical_use_cases"]
    }
    user_msg = (
        f"Plugin: {plugin_name}\n\n"
        f"Current registry entry (may be incomplete):\n"
        f"{json.dumps(existing_subset, indent=2)}\n\n"
        f"Documentation content:\n{text}\n\n"
        "Return only the JSON object with improved field values."
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"    LLM extraction failed: {e}")
        return {}


# ── Field merging ─────────────────────────────────────────────────────────────

FROZEN_FIELDS = [
    "name", "update_site_name", "update_site_url",
    "requires_restart", "documentation_url",
]

ENRICHED_FIELDS = [
    "description", "category", "tags",
    "input_data", "output_data",
    "use_when", "do_not_use_when",
    "typical_use_cases",
]

def merge(original: dict, extracted: dict) -> dict:
    result = {k: original.get(k) for k in FROZEN_FIELDS}
    for field in ENRICHED_FIELDS:
        value = extracted.get(field)
        result[field] = value if (value is not None and value != "" and value != []) else original.get(field)
    return result


# ── Progress helpers ──────────────────────────────────────────────────────────

def load_progress() -> list:
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_progress(results: list):
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Enrich plugin_registry.json from documentation URLs.")
    parser.add_argument("--pdf-only", action="store_true",
                        help="Only process plugins whose documentation_url is a PDF.")
    parser.add_argument("--url-type", choices=[
                            "imagej.net", "github-repo", "github-subpage",
                            "github.io", "readthedocs", "forum", "external", "pdf",
                        ],
                        help="Only process plugins matching a specific URL type.")
    args = parser.parse_args()

    print(f"Loading {INPUT_PATH.name} ...")
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        plugins = json.load(f)

    def matches_filter(plugin: dict) -> bool:
        url = plugin.get("documentation_url") or ""
        if args.pdf_only or args.url_type == "pdf":
            return is_pdf(url)
        if args.url_type:
            return classify_url(url) == args.url_type
        return True

    results      = load_progress()
    already_done = {r["name"] for r in results}
    filtered     = [p for p in plugins if matches_filter(p)]
    todo         = [p for p in filtered if p["name"] not in already_done]

    filter_desc = "pdf-only" if args.pdf_only else (f"--url-type={args.url_type}" if args.url_type else "all")
    print(f"Filter: {filter_desc} — {len(filtered)} match, {len(todo)} not yet processed.\n")

    for i, plugin in enumerate(todo, start=1):
        name    = plugin["name"]
        doc_url = plugin.get("documentation_url")
        print(f"[{i}/{len(todo)}] {name}")

        doc = None
        if doc_url:
            print(f"  URL type: {classify_url(doc_url)}")
            doc = fetch_content(doc_url)
            time.sleep(REQUEST_DELAY)

        if doc and doc.text:
            print(f"  Calling LLM ({len(doc.text)} chars) ...")
            extracted = extract_fields_with_llm(name, doc.text, plugin)
            time.sleep(LLM_DELAY)
        else:
            print("  No content — keeping existing values.")
            extracted = {}

        results.append(merge(plugin, extracted))
        save_progress(results)
        print()

    print(f"Done. {len(results)} plugins written to {OUTPUT_PATH.name}")


if __name__ == "__main__":
    main()
