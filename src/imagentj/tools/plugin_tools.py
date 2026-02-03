import json
import subprocess
from pathlib import Path
from langchain.tools import tool
from .vector_stores import is_plugin_db_available
from .rag_tools import get_expanded_queries
from config.rag_config import QDRANT_DATA_PATH, PLUGINS_COLLECTION_NAME
from config.imagej_config import FIJI_JAVA_HOME

__all__ = ['search_fiji_plugins', 'install_fiji_plugin', 'check_plugin_installed']

PLUGIN_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "rag" / "plugin_registry.json"


def _load_plugin_registry():
    """Load the plugin registry JSON file."""
    with open(PLUGIN_REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@tool("search_fiji_plugins")
def search_fiji_plugins(query: str) -> list:
    """
    Search the curated Fiji plugin database for plugins relevant to a task.
    Returns ranked results with plugin name, description, category, update site info, and score.
    Use this before delegating complex image analysis tasks to find existing Fiji plugins.
    """
    if not is_plugin_db_available():
        return [{"message": "Plugin database is not available. The fiji_plugins collection has not been ingested into Qdrant. Proceed with standard code generation."}]

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
            "update_site_name": meta.get("update_site_name"),
            "update_site_url": meta.get("update_site_url"),
            "documentation_url": meta.get("documentation_url"),
            "score": p.score,
        })

    return results


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
