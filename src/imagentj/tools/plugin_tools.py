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

__all__ = ['search_fiji_plugins', 'install_fiji_plugin', 'check_plugin_installed', 'get_plugin_docs', 'find_plugin_examples']

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
def get_plugin_docs(plugin_name: str, url: str = "") -> dict:
    """
    Fetch and parse the documentation for a specific Fiji plugin on demand.

    Returns structured usage guidance: interaction mode (scripted/guided/null),
    menu path, parameters with types and default values, GUI steps, scripting notes,
    and caveats. Uses vision on dialog screenshots when available.

    Call this after search_fiji_plugins selects a plugin and BEFORE delegating to
    imagej_coder or presenting instructions to the user.

    Args:
        plugin_name: The plugin name (used for cache key and context).
        url: Optional direct documentation URL. When provided, skips the registry
             lookup and fetches this URL directly. Use this when imagej_coder returns
             a doc_url in its PLUGIN DIALOG REPORT (e.g. from find_plugin_examples).
    """
    cache_key = f"{plugin_name}::{url}" if url else plugin_name
    if cache_key in _docs_cache:
        return _docs_cache[cache_key]

    # Determine the documentation URL to fetch
    entry_description = ""
    if url:
        # Caller supplied a direct URL — use it without registry lookup
        doc_url = url
        print(f"[get_plugin_docs] Using caller-supplied URL for '{plugin_name}': {doc_url}")
    else:
        # Look up registry entry
        plugins = _load_plugin_registry()
        entry = next((p for p in plugins if p["name"].lower() == plugin_name.lower()), None)
        if entry is None:
            return {"error": f"Plugin '{plugin_name}' not found in registry."}
        entry_description = entry.get("description", "")
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
        f"Registry description: {entry_description}\n\n"
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

    _docs_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# find_plugin_examples — scan Fiji's local scripts/jars for usage examples
# ---------------------------------------------------------------------------

_FIJI_ROOT = Path("/opt/Fiji.app")
_SCRIPT_EXTENSIONS = {".ijm", ".groovy", ".py", ".bsh", ".js"}

# Known base documentation URLs for jars that bundle a help.config
_JAR_DOC_BASES: dict[str, str] = {
    "gdsc-smlm": "https://gdsc-smlm.readthedocs.io/en/latest/",
}


def _lookup_help_config(jar_path: Path, plugin_name: str, zf) -> str | None:
    """
    Parse a help.config file inside a jar (if present) and return the full
    documentation URL for the given plugin name.
    """
    try:
        help_entries = [e for e in zf.namelist() if e.endswith("help.config")]
        if not help_entries:
            return None
        raw = zf.read(help_entries[0]).decode("utf-8", errors="ignore")
    except Exception:
        return None

    # Find the base URL for this jar
    base_url = None
    jar_slug = jar_path.name.lower()
    for key, url in _JAR_DOC_BASES.items():
        if key in jar_slug:
            base_url = url
            break
    if not base_url:
        return None

    # Convert plugin name to the slug format used in help.config (e.g. "PeakFit" → "peak-fit")
    name_slug = re.sub(r'(?<=[a-z])(?=[A-Z])', '-', plugin_name)  # camelCase → camel-Case
    name_slug = re.sub(r'[\s_]+', '-', name_slug).lower()          # spaces/underscores → -

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        config_slug, rel_path = parts
        if config_slug == name_slug:
            return base_url + rel_path
    return None


def _extract_proto_fields(proto_text: str, plugin_name: str) -> dict[str, dict]:
    """
    Parse a .proto file and return field definitions from message blocks whose
    name contains the plugin name (case-insensitive, spaces/underscores ignored).

    Returns {message_name: {field_name: type_string}}.
    """
    slug = plugin_name.lower().replace(" ", "").replace("_", "")
    results: dict[str, dict] = {}

    # Find all message blocks: message FooSettings { ... }
    for m in re.finditer(r'message\s+(\w+)\s*\{([^}]*)\}', proto_text, re.DOTALL):
        msg_name = m.group(1)
        if slug not in msg_name.lower().replace("_", ""):
            continue
        fields: dict[str, str] = {}
        for line in m.group(2).splitlines():
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("/*"):
                continue
            # proto3 field: <type> <name> = <number>;
            fmatch = re.match(r'(\w+)\s+(\w+)\s*=\s*\d+', line)
            if fmatch:
                fields[fmatch.group(2)] = fmatch.group(1)
        if fields:
            results[msg_name] = fields
    return results


def _extract_run_calls(text: str, plugin_name: str) -> list[dict]:
    """
    Extract run("...", "params") calls that reference the plugin.
    Returns a list of dicts with 'call' and 'params' (parsed key=value pairs).
    """
    results = []
    # Match run("anything containing plugin_name", "params") — case-insensitive
    pattern = re.compile(
        r'run\(\s*"([^"]*' + re.escape(plugin_name.split()[0]) + r'[^"]*)"'
        r'\s*(?:,\s*"([^"]*)")?\s*\)',
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        call_name = m.group(1)
        param_str = m.group(2) or ""
        # Parse "key=value key2 key3=value3" into a dict
        fields: dict[str, str] = {}
        for token in param_str.split():
            if "=" in token:
                k, _, v = token.partition("=")
                fields[k.strip()] = v.strip()
            elif token:
                fields[token.strip()] = "(flag)"
        results.append({"command": call_name, "param_string": param_str, "fields": fields})
    return results


def _search_file(path: Path, plugin_name: str) -> list[dict]:
    """Read a single script file and return matching run() calls + surrounding context."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    if plugin_name.lower() not in text.lower():
        return []

    calls = _extract_run_calls(text, plugin_name)

    # Also grab surrounding lines for context (groovy/python API style)
    context_lines = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if plugin_name.lower() in line.lower():
            start = max(0, i - 2)
            end = min(len(lines), i + 5)
            context_lines.append("\n".join(lines[start:end]))

    return [{"source": str(path), "run_calls": calls, "context": context_lines[:3]}]


def _flatten_json_params(obj, prefix="", out=None) -> dict:
    """Recursively flatten a JSON object into dotted key paths with scalar leaf values."""
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten_json_params(v, f"{prefix}{k}.", out)
    elif isinstance(obj, list):
        # Only record lists of scalars as a single entry
        if all(not isinstance(i, (dict, list)) for i in obj):
            out[prefix.rstrip(".")] = str(obj)
    else:
        out[prefix.rstrip(".")] = str(obj)
    return out


def _parse_plugins_config(raw: str, plugin_name: str) -> list[dict]:
    """
    Parse a Fiji plugins.config file and return matching menu entries.

    Format:  Menu>Path, "Label", fully.qualified.ClassName
    Returns a list of {menu_path, label, class_name} for entries whose label
    or class name contains the plugin name (case-insensitive).
    """
    slug = plugin_name.lower().replace(" ", "").replace("-", "").replace("_", "")
    entries = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Format: Menu>Sub, "Label Text", some.Class  (comma-separated, optional spaces)
        m = re.match(r'^([^,]+),\s*"([^"]+)",\s*(\S+)$', line)
        if not m:
            continue
        menu_path, label, class_name = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        label_slug = label.lower().replace(" ", "").replace("-", "").replace("_", "")
        class_slug = class_name.lower().replace(".", "").replace("_", "")
        if slug in label_slug or slug in class_slug:
            entries.append({"menu_path": menu_path, "label": label, "class_name": class_name})
    return entries


def _search_jar(jar_path: Path, plugin_name: str) -> list[dict]:
    """Search a jar for embedded script templates, proto definitions, JSON configs, and help URLs."""
    import zipfile
    import json as _json
    results = []
    try:
        with zipfile.ZipFile(jar_path, "r") as zf:
            all_entries = zf.namelist()

            # --- help.config → specific documentation URL for this plugin ---
            doc_url = _lookup_help_config(jar_path, plugin_name, zf)
            if doc_url:
                results.append({
                    "source": f"{jar_path.name}!help.config",
                    "run_calls": [],
                    "context": [],
                    "json_params": {},
                    "proto_fields": {},
                    "doc_url": doc_url,
                    "menu_entries": [],
                })

            # --- plugins.config → menu path and main class name ---
            if "plugins.config" in all_entries:
                try:
                    raw_pc = zf.read("plugins.config").decode("utf-8", errors="ignore")
                    menu_entries = _parse_plugins_config(raw_pc, plugin_name)
                    if menu_entries:
                        results.append({
                            "source": f"{jar_path.name}!plugins.config",
                            "run_calls": [],
                            "context": [],
                            "json_params": {},
                            "proto_fields": {},
                            "doc_url": None,
                            "menu_entries": menu_entries,
                        })
                except Exception:
                    pass

            # --- Script files (.ijm, .groovy, etc.) ---
            for entry in all_entries:
                if Path(entry).suffix.lower() not in _SCRIPT_EXTENSIONS:
                    continue
                try:
                    text = zf.read(entry).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if plugin_name.lower() not in text.lower():
                    continue
                calls = _extract_run_calls(text, plugin_name)
                context_lines = []
                lines = text.splitlines()
                for i, line in enumerate(lines):
                    if plugin_name.lower() in line.lower():
                        start = max(0, i - 2)
                        end = min(len(lines), i + 5)
                        context_lines.append("\n".join(lines[start:end]))
                results.append({
                    "source": f"{jar_path.name}!{entry}",
                    "run_calls": calls,
                    "context": context_lines[:3],
                    "json_params": {},
                    "proto_fields": {},
                    "doc_url": None,
                    "menu_entries": [],
                })

            # --- Proto definition files (.proto) ---
            # These define every GUI dialog's fields with explicit types.
            # Match by plugin name appearing in a message block name.
            for entry in all_entries:
                if Path(entry).suffix.lower() != ".proto":
                    continue
                try:
                    proto_text = zf.read(entry).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                proto_fields = _extract_proto_fields(proto_text, plugin_name)
                if proto_fields:
                    results.append({
                        "source": f"{jar_path.name}!{entry}",
                        "run_calls": [],
                        "context": [],
                        "json_params": {},
                        "proto_fields": proto_fields,
                        "menu_entries": [],
                    })

            # --- JSON config / template files ---
            # Only include a JSON file if the plugin name explicitly appears in the
            # filename or the file content. We do NOT match on jar-level class presence
            # because multiple plugins share the same jar and would get each other's configs.
            plugin_slug = plugin_name.lower().replace(" ", "")
            for entry in all_entries:
                if Path(entry).suffix.lower() != ".json":
                    continue
                entry_stem = Path(entry).stem.lower().replace("-", "").replace("_", "")
                try:
                    raw = zf.read(entry).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if plugin_slug not in entry_stem and plugin_name.lower() not in raw.lower():
                    continue
                try:
                    data = _json.loads(raw)
                except Exception:
                    continue
                flat = _flatten_json_params(data)
                # Drop notes/metadata fields and very long values
                relevant = {k: v for k, v in flat.items()
                            if not k.startswith("notes") and len(v) < 100}
                if relevant:
                    results.append({
                        "source": f"{jar_path.name}!{entry}",
                        "run_calls": [],
                        "context": [],
                        "json_params": relevant,
                        "proto_fields": {},
                        "menu_entries": [],
                    })
    except Exception:
        pass
    return results


@tool("find_plugin_examples")
def find_plugin_examples(plugin_name: str) -> dict:
    """
    Search Fiji's local installation for script examples, macro recordings, and
    embedded jar templates that reference a specific plugin.

    Use this BEFORE writing a script for any plugin, and BEFORE guiding a user
    through a plugin's GUI — it returns the exact dialog field names and accepted
    value formats extracted from real Fiji usage examples.

    Args:
        plugin_name: The plugin name as it appears in Fiji menus (e.g., "Analyze Particles",
                     "Coloc 2", "TrackMate", "Gaussian Blur").

    Returns:
        A dict with:
        - dialog_fields: merged dict of {field_name: example_value} from run() macro calls
        - config_params: merged dict of {param_path: value} from JSON config/template files
        - proto_dialog_fields: dict of {MessageName: {field: type}} from .proto definitions
        - menu_entries: list of {menu_path, label, class_name} from plugins.config — use
          class_name with inspect_java_class when proto_fields are absent
        - doc_url: direct documentation URL from help.config (e.g. for GDSC-SMLM plugins)
        - example_run_calls: list of raw run("...", "...") strings
        - script_context: code snippets showing how the plugin is used in practice
        - sources: which files/jars the info came from
        - note: human-readable summary
    """
    hits = []

    # 1. Search standalone script files
    for search_dir in [_FIJI_ROOT / "macros", _FIJI_ROOT / "scripts"]:
        if not search_dir.exists():
            continue
        for f in search_dir.rglob("*"):
            if f.suffix.lower() in _SCRIPT_EXTENSIONS and f.is_file():
                file_hits = _search_file(f, plugin_name)
                for h in file_hits:
                    h.setdefault("json_params", {})
                    h.setdefault("proto_fields", {})
                    h.setdefault("doc_url", None)
                    h.setdefault("menu_entries", [])
                hits.extend(file_hits)

    # 2. Search embedded scripts and JSON configs inside jars
    for jar_dir in [_FIJI_ROOT / "plugins", _FIJI_ROOT / "jars"]:
        if not jar_dir.exists():
            continue
        for jar in jar_dir.glob("*.jar"):
            hits.extend(_search_jar(jar, plugin_name))

    if not hits:
        return {
            "dialog_fields": {},
            "config_params": {},
            "proto_dialog_fields": {},
            "menu_entries": [],
            "doc_url": None,
            "example_run_calls": [],
            "script_context": [],
            "sources": [],
            "note": (
                f"No local Fiji examples found for '{plugin_name}'. "
                "Try inspect_java_class or get_plugin_docs for parameter information."
            ),
        }

    merged_fields: dict[str, str] = {}
    merged_config: dict[str, str] = {}
    merged_proto: dict[str, dict] = {}
    merged_menu: list[dict] = []
    example_calls: list[str] = []
    contexts: list[str] = []
    sources: list[str] = []
    doc_url: str | None = None

    for hit in hits:
        sources.append(hit["source"])
        for call in hit["run_calls"]:
            merged_fields.update(call["fields"])
            if call["param_string"]:
                example_calls.append(
                    f'run("{call["command"]}", "{call["param_string"]}")'
                )
        contexts.extend(hit["context"])
        merged_config.update(hit.get("json_params", {}))
        merged_proto.update(hit.get("proto_fields", {}))
        if hit.get("doc_url"):
            doc_url = hit["doc_url"]
        for me in hit.get("menu_entries", []):
            if me not in merged_menu:
                merged_menu.append(me)

    return {
        "dialog_fields": merged_fields,
        "config_params": merged_config,
        "proto_dialog_fields": merged_proto,
        "menu_entries": merged_menu,
        "doc_url": doc_url,
        "example_run_calls": list(dict.fromkeys(example_calls))[:6],
        "script_context": contexts[:6],
        "sources": list(dict.fromkeys(sources)),
        "note": (
            f"Found {len(hits)} file(s) referencing '{plugin_name}'. "
            f"Macro fields: {list(merged_fields.keys()) or 'none'}. "
            f"Proto dialog fields: {list(merged_proto.keys()) or 'none'}. "
            f"Menu entries: {[m['label'] for m in merged_menu] or 'none'}. "
            f"Doc URL: {doc_url or 'not found'}."
        ),
    }
