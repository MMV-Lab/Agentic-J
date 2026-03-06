import json
import re
import os
import subprocess
from pathlib import Path
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from .vector_stores import is_plugin_db_available
from .rag_tools import get_expanded_queries
from config.rag_config import QDRANT_DATA_PATH, PLUGINS_COLLECTION_NAME
from config.imagej_config import FIJI_JAVA_HOME

__all__ = ['search_fiji_plugins', 'install_fiji_plugin', 'check_plugin_installed', 'get_plugin_docs']

_gpt_key = os.getenv("OPENAI_API_KEY")
_llm = ChatOpenAI(model="gpt-5.2", temperature=0, api_key=_gpt_key, model_kwargs={"response_format": {"type": "json_object"}})

# Simple in-session cache so repeated calls for the same plugin don't re-fetch
_docs_cache: dict = {}

PLUGIN_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "rag" / "plugin_registry.json"


def _load_plugin_registry():
    """Load the plugin registry JSON file."""
    with open(PLUGIN_REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _search_registry_fallback(query: str, limit: int = 5) -> list:
    """Fallback search using simple keyword matching on the JSON registry."""
    plugins = _load_plugin_registry()
    query_lower = query.lower()
    query_terms = query_lower.split()

    scored_plugins = []
    for p in plugins:
        score = 0
        # Include new fields in searchable text for better matching
        use_cases_text = ' '.join(p.get('typical_use_cases', []))
        searchable = (
            f"{p['name']} {p['description']} {' '.join(p.get('tags', []))} "
            f"{p.get('category', '')} {p.get('input_data', '')} "
            f"{p.get('output_data', '')} {p.get('use_when', '')} {use_cases_text}"
        ).lower()

        # Score based on term matches
        for term in query_terms:
            if term in searchable:
                score += 1
            if term in p['name'].lower():
                score += 2  # Boost name matches
            if term in p.get('tags', []):
                score += 1.5  # Boost tag matches
            # Boost matches in use_when (high relevance for task selection)
            if term in p.get('use_when', '').lower():
                score += 1.5

        if score > 0:
            scored_plugins.append((score, p))

    # Sort by score descending
    scored_plugins.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, p in scored_plugins[:limit]:
        results.append({
            "name": p["name"],
            "description": p["description"],
            "category": p.get("category"),
            "input_data": p.get("input_data"),
            "output_data": p.get("output_data"),
            "use_when": p.get("use_when"),
            "do_not_use_when": p.get("do_not_use_when"),
            "typical_use_cases": p.get("typical_use_cases"),
            "update_site_name": p["update_site_name"],
            "update_site_url": p["update_site_url"],
            "documentation_url": p.get("documentation_url"),
            "score": score,
        })

    return results


@tool("search_fiji_plugins")
def search_fiji_plugins(query: str) -> list:
    """
    Search the curated Fiji plugin database for plugins relevant to a task.
    Returns ranked results with plugin name, description, category, update site info, and score.
    Use this before delegating complex image analysis tasks to find existing Fiji plugins.
    """
    # Try Qdrant-based semantic search first
    if is_plugin_db_available():
        try:
            from ..rag.RAG import hybrid_search_with_rrf, apply_rrf

            # Expand the query for better retrieval
            queries = get_expanded_queries(query)

            all_points = []
            for q in queries:
                points = hybrid_search_with_rrf(q, collection_name=PLUGINS_COLLECTION_NAME, limit=5)
                all_points.extend(points)

            # RRF re-ranking across all query variants
            final_results = apply_rrf(all_points, k=60)[:5]

            results = []
            for p in final_results:
                meta = p.payload.get("metadata", {})
                results.append({
                    "name": meta.get("name"),
                    "description": meta.get("description"),
                    "category": meta.get("category"),
                    "input_data": meta.get("input_data"),
                    "output_data": meta.get("output_data"),
                    "use_when": meta.get("use_when"),
                    "do_not_use_when": meta.get("do_not_use_when"),
                    "typical_use_cases": meta.get("typical_use_cases"),
                    "update_site_name": meta.get("update_site_name"),
                    "update_site_url": meta.get("update_site_url"),
                    "documentation_url": meta.get("documentation_url"),
                    "score": p.score,
                })

            return results
        except Exception as e:
            print(f"Qdrant search failed, falling back to keyword search: {e}")

    # Fallback to keyword-based search on JSON registry
    return _search_registry_fallback(query)


@tool("install_fiji_plugin")
def install_fiji_plugin(plugin_name: str) -> str:
    """
    Install a Fiji plugin by activating its update site and running the Fiji updater.
    Requires an exact plugin name from the registry. Fiji must be restarted after installation.
    NEVER call this without explicit user confirmation.
    """
    # Look up plugin in registry (exact match)
    try:
        plugins = _load_plugin_registry()
    except Exception as e:
        return f"Failed to load plugin registry: {e}"

    plugin = None
    for p in plugins:
        if p["name"].lower() == plugin_name.lower():
            plugin = p
            break

    if plugin is None:
        return f"Plugin '{plugin_name}' not found in the registry. Available plugins can be found via search_fiji_plugins."

    site_name = plugin["update_site_name"]
    site_url = plugin["update_site_url"]
    requires_restart = plugin.get("requires_restart", True)

    # Determine Fiji executable
    fiji_path = Path(FIJI_JAVA_HOME)
    executable = None
    for name in ["fiji-linux-x64", "ImageJ-linux64", "fiji", "ImageJ-win64.exe", "Contents/MacOS/ImageJ-macosx"]:
        candidate = fiji_path / name
        if candidate.exists():
            executable = candidate
            break
    if executable is None:
        return f"Fiji executable not found in {fiji_path}. Check FIJI_JAVA_HOME in imagej_config.py."

    # Step 1: Add update site
    try:
        result_add = subprocess.run(
            [str(executable), "--update", "add-update-site", site_name, site_url],
            capture_output=True, text=True, timeout=120,
        )
        if result_add.returncode != 0:
            stderr = result_add.stderr.strip()
            # "already exists" is not a real error
            if "already" not in stderr.lower():
                return f"Failed to add update site '{site_name}': {stderr}"
    except subprocess.TimeoutExpired:
        return f"Timed out adding update site '{site_name}'. Fiji may be unresponsive."
    except Exception as e:
        return f"Error adding update site: {e}"

    # Step 2: Run updater
    try:
        result_update = subprocess.run(
            [str(executable), "--update", "update"],
            capture_output=True, text=True, timeout=120,
        )
        if result_update.returncode != 0:
            return f"Update site added but update failed: {result_update.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Update site added but the updater timed out. Try running Fiji's updater manually."
    except Exception as e:
        return f"Update site added but update failed: {e}"

    msg = f"Successfully installed '{plugin['name']}' from update site '{site_name}'."
    if requires_restart:
        msg += " Fiji must be restarted for the plugin to become available."
    return msg


@tool("check_plugin_installed")
def check_plugin_installed(plugin_name: str) -> dict:
    """
    Check if a Fiji plugin is already installed by searching the plugins and jars directories.
    Returns installation status and the path if found.
    Use this BEFORE suggesting plugin installation to avoid reinstalling existing plugins.
    """
    fiji_path = Path(FIJI_JAVA_HOME)
    search_dirs = [fiji_path / "plugins", fiji_path / "jars"]

    # Normalize search term
    search_term = plugin_name.lower().replace(" ", "").replace("-", "").replace("_", "")

    found_files = []
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for jar_file in search_dir.glob("**/*.jar"):
            # Normalize filename for comparison
            normalized_name = jar_file.stem.lower().replace("-", "").replace("_", "")
            if search_term in normalized_name or normalized_name in search_term:
                found_files.append(str(jar_file))

    if found_files:
        return {
            "installed": True,
            "plugin_name": plugin_name,
            "found_files": found_files,
            "message": f"Plugin '{plugin_name}' appears to be installed. Found: {', '.join(found_files)}"
        }
    else:
        return {
            "installed": False,
            "plugin_name": plugin_name,
            "found_files": [],
            "message": f"Plugin '{plugin_name}' does not appear to be installed."
        }


_GET_PLUGIN_DOCS_SYSTEM = """You are an ImageJ/Fiji expert analysing plugin documentation.

You will receive the text content of a plugin's documentation page and optionally
screenshots of its dialogs and UI. Your job is to extract structured usage guidance
so that an agent can either write correct Groovy code or give a user precise GUI
instructions with correct parameter values.

Pay special attention to any screenshots — these often contain the most accurate
parameter names, dropdown options, and default values that do not appear in the text.
For each dialog screenshot, extract every visible label, input field, checkbox,
dropdown, and slider.

Return a single JSON object with these fields (null if genuinely unknown):

- interaction_mode : "scripted" | "guided" | null
    scripted  = plugin can be fully driven via IJ.run() or a script API
    guided    = plugin requires GUI interaction (wizard, manual steps)
    null      = cannot determine from the documentation

- menu_path : exact Fiji menu path to open the plugin, e.g. "Plugins > StarDist > StarDist 2D"

- run_command : the string passed to IJ.run() for scripted plugins, e.g. "StarDist 2D"

- parameters : list of parameter objects, each with:
    { "name": str, "type": "dropdown"|"checkbox"|"number"|"text"|"slider",
      "default": str|null, "options": [str]|null, "description": str }
  Include ALL parameters visible in dialog screenshots.

- gui_steps : list of plain-language steps for guided mode, e.g.:
    ["Open your image", "Go to Plugins > X", "Set threshold to 0.5", "Click OK"]

- scripting_notes : important notes for writing correct Groovy/macro code,
    e.g. model file requirements, output variable names, known API quirks.

- caveats : anything the user must know before running the plugin,
    e.g. "requires GPU", "image must be 8-bit", "restart required after install".
"""


@tool("get_plugin_docs")
def get_plugin_docs(plugin_name: str) -> dict:
    """
    Fetch and parse the documentation for a specific Fiji plugin on demand.

    Returns structured usage guidance: interaction mode (scripted/guided/null),
    menu path, parameters with types and default values, GUI steps, scripting notes,
    and caveats. Uses vision on dialog screenshots when available.

    Call this after search_fiji_plugins selects a plugin and BEFORE delegating to
    imagej_coder or presenting instructions to the user.
    """
    if plugin_name in _docs_cache:
        return _docs_cache[plugin_name]

    # Look up registry entry
    plugins = _load_plugin_registry()
    entry = next((p for p in plugins if p["name"].lower() == plugin_name.lower()), None)
    if entry is None:
        return {"error": f"Plugin '{plugin_name}' not found in registry."}

    doc_url = entry.get("documentation_url")
    if not doc_url:
        return {
            "error": "No documentation URL available for this plugin.",
            "interaction_mode": None,
            "menu_path": None,
            "run_command": None,
            "parameters": [],
            "gui_steps": [],
            "scripting_notes": None,
            "caveats": None,
        }

    # Fetch content via doc_fetcher
    try:
        from ..rag.doc_fetcher import fetch_content
    except ImportError:
        from imagentj.rag.doc_fetcher import fetch_content

    print(f"[get_plugin_docs] Fetching docs for '{plugin_name}' from {doc_url}")
    doc = fetch_content(doc_url)
    if doc is None:
        return {"error": f"Could not fetch documentation from {doc_url}"}

    # Build the user message — text + all available images
    MAX_TEXT = 32000
    text_block = (
        f"Plugin: {plugin_name}\n\n"
        f"Registry description: {entry.get('description', '')}\n\n"
        f"Documentation content:\n{doc.text[:MAX_TEXT]}"
    )

    content_parts = [{"type": "text", "text": text_block}]
    for img_url in doc.image_urls:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": img_url, "detail": "high"},
        })

    if doc.image_urls:
        print(f"[get_plugin_docs] Sending {len(doc.image_urls)} image(s) to vision LLM")

    # Call vision-capable LLM
    from langchain_core.messages import HumanMessage, SystemMessage
    try:
        response = _llm.invoke([
            SystemMessage(content=_GET_PLUGIN_DOCS_SYSTEM),
            HumanMessage(content=content_parts),
        ])
        raw = response.content.strip()
        # Strip markdown code fences if model wrapped the JSON
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw).rstrip("` \n")
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Model returned prose instead of JSON — extract what we can
        result = {"raw_response": response.content, "interaction_mode": None}
    except Exception as e:
        return {"error": f"LLM call failed: {e}"}

    _docs_cache[plugin_name] = result
    return result
