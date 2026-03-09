"""
tools_plugin_research.py
Web-research and skill-management tools used exclusively by the
PluginSkillBuilder subagent.
"""

from __future__ import annotations

import json
import os
import re
import textwrap
import urllib.parse
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SKILLS_ROOT = os.environ.get("PLUGIN_SKILLS_PATH", "/app/skills/plugins/")
_GITHUB_API  = "https://api.github.com"
_IMAGEJ_WIKI = "https://imagej.net"
_FIJI_GITHUB  = "https://github.com/fiji"
_REQUEST_TIMEOUT = 20
_MAX_PAGE_CHARS  = 40_000   # truncate large pages before handing to LLM

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (ImageJ-PluginSkillBuilder/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/json",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean_html(html: str) -> str:
    """Strip HTML tags and normalise whitespace."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script / style / nav noise
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:_MAX_PAGE_CHARS]


def _get(url: str) -> str:
    """GET a URL; return cleaned text or an error string."""
    try:
        r = requests.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            return json.dumps(r.json(), indent=2)[:_MAX_PAGE_CHARS]
        return _clean_html(r.text)
    except Exception as exc:
        return f"[FETCH ERROR] {url}: {exc}"


# ---------------------------------------------------------------------------
# Tool 1 — Fetch any documentation URL
# ---------------------------------------------------------------------------

@tool
def fetch_plugin_docs_url(url: str) -> str:
    """
    Fetch and return the cleaned text content of any plugin documentation URL.

    Use for:
    - Official plugin website or ImageJ Wiki page
    - GitHub README files (use the raw.githubusercontent.com URL)
    - Any HTML or JSON documentation page

    Returns up to 40 000 characters of cleaned plain text.
    On failure returns a descriptive error string.
    """
    return _get(url)


# ---------------------------------------------------------------------------
# Tool 2 — Search ImageJ Wiki for a plugin
# ---------------------------------------------------------------------------

@tool
def search_imagej_wiki(plugin_name: str) -> str:
    """
    Search the ImageJ Wiki (https://imagej.net) for a plugin by name.

    Returns a list of matching page titles and URLs, then fetches and returns
    the content of the best matching page.

    Use this FIRST when researching any Fiji/ImageJ plugin.
    """
    query = urllib.parse.quote(plugin_name)
    search_url = (
        f"https://imagej.net/w/index.php?search={query}&title=Special:Search"
    )
    results_page = _get(search_url)

    # Also try a direct page hit
    direct_url = f"{_IMAGEJ_WIKI}/plugins/{plugin_name.replace(' ', '_')}"
    direct_page = _get(direct_url)

    output = f"=== SEARCH RESULTS for '{plugin_name}' ===\n{results_page}\n\n"
    output += f"=== DIRECT PAGE ATTEMPT ({direct_url}) ===\n{direct_page}"
    return output[:_MAX_PAGE_CHARS]


# ---------------------------------------------------------------------------
# Tool 3 — GitHub repository explorer
# ---------------------------------------------------------------------------

@tool
def fetch_github_plugin_info(repo_url: str) -> str:
    """
    Fetch structural information from a GitHub plugin repository.

    Provide the full GitHub repository URL, e.g.:
      https://github.com/fiji/TrackMate

    Returns:
    - README content
    - List of source files (.java, .groovy) with paths
    - Content of up to 3 most relevant source files (those mentioning 'run', 'setup', or 'IJ.run')

    Use to discover all Groovy-callable commands and their parameters.
    """
    # Normalise URL → owner/repo
    match = re.search(r"github\.com/([^/]+/[^/]+)", repo_url)
    if not match:
        return "[ERROR] Could not parse GitHub URL. Expected: https://github.com/owner/repo"
    repo_path = match.group(1).rstrip("/")

    output_parts: list[str] = []

    # --- README ---
    for readme_name in ("README.md", "readme.md", "README.rst"):
        raw = f"https://raw.githubusercontent.com/{repo_path}/main/{readme_name}"
        text = _get(raw)
        if not text.startswith("[FETCH ERROR]"):
            output_parts.append(f"=== README ({readme_name}) ===\n{text[:8000]}")
            break
    else:
        output_parts.append("=== README: not found ===")

    # --- File tree via GitHub API ---
    tree_url = f"{_GITHUB_API}/repos/{repo_path}/git/trees/HEAD?recursive=1"
    tree_data = _get(tree_url)
    try:
        tree_json = json.loads(tree_data)
        all_paths = [
            item["path"] for item in tree_json.get("tree", [])
            if item.get("type") == "blob"
        ]
        src_files = [
            p for p in all_paths
            if p.endswith((".java", ".groovy", ".py"))
        ]
        output_parts.append(f"=== SOURCE FILES ({len(src_files)} found) ===\n"
                             + "\n".join(src_files[:60]))
    except Exception:
        output_parts.append(f"=== FILE TREE (raw) ===\n{tree_data[:3000]}")
        src_files = []

    # --- Fetch up to 3 key source files ---
    priority_keywords = ("plugin", "command", "run", "execute", "process")
    candidates = [
        p for p in src_files
        if any(kw in p.lower() for kw in priority_keywords)
    ][:3]

    for path in candidates:
        raw = f"https://raw.githubusercontent.com/{repo_path}/main/{path}"
        content = _get(raw)
        output_parts.append(f"=== SOURCE: {path} ===\n{content[:5000]}")

    return "\n\n".join(output_parts)[:_MAX_PAGE_CHARS]


# ---------------------------------------------------------------------------
# Tool 4 — Fetch a specific raw source file from GitHub
# ---------------------------------------------------------------------------

@tool
def fetch_github_file(repo_url: str, file_path: str) -> str:
    """
    Fetch the raw content of a specific file from a GitHub repository.

    Args:
        repo_url:  Full GitHub repo URL, e.g. https://github.com/fiji/TrackMate
        file_path: Path within the repo, e.g. src/main/java/fiji/plugin/trackmate/TrackMatePlugIn.java

    Returns the file's raw text content (up to 40 000 characters).
    Use to inspect command signatures, parameter names, and IJ.run calls.
    """
    match = re.search(r"github\.com/([^/]+/[^/]+)", repo_url)
    if not match:
        return "[ERROR] Could not parse GitHub URL."
    repo_path = match.group(1).rstrip("/")

    for branch in ("main", "master"):
        raw = f"https://raw.githubusercontent.com/{repo_path}/{branch}/{file_path}"
        content = _get(raw)
        if not content.startswith("[FETCH ERROR]"):
            return content
    return f"[ERROR] Could not fetch {file_path} from {repo_url}"


# ---------------------------------------------------------------------------
# Tool 5 — Save a plugin skill file
# ---------------------------------------------------------------------------

@tool
def save_plugin_skill_file(
    plugin_name: str,
    filename: str,
    content: str,
) -> str:
    """
    Save a skill file for a plugin to the plugin skills directory.

    Args:
        plugin_name: Name of the plugin (used as folder name), e.g. "TrackMate"
        filename:    File to write, must be one of:
                       SKILL.md          ← master LLM-facing summary
                       OVERVIEW.md       ← use case, inputs, UI vs automated
                       UI_GUIDE.md       ← step-by-step UI instructions + workflow
                       GROOVY_API.md     ← all commands, parameters, return values
                       GROOVY_WORKFLOW.groovy  ← complete tested automation script
        content:     Full markdown or Groovy text to write.

    Returns the absolute path of the saved file, or an error string.

    Skill folder location: /app/skills/plugins/{plugin_name}/
    """
    allowed = {
        "SKILL.md", "OVERVIEW.md", "UI_GUIDE.md",
        "GROOVY_API.md", "GROOVY_WORKFLOW.groovy",
    }
    if filename not in allowed:
        return (
            f"[ERROR] filename must be one of: {sorted(allowed)}. "
            f"Got: '{filename}'"
        )

    folder = Path(_SKILLS_ROOT) / _sanitise(plugin_name)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_text(content, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Tool 6 — Read a plugin skill file
# ---------------------------------------------------------------------------

@tool
def read_plugin_skill_file(plugin_name: str, filename: str) -> str:
    """
    Read an existing skill file for a plugin.

    Use to review what has already been written before updating a file,
    or to verify the final SKILL.md before marking the task complete.

    Args:
        plugin_name: Plugin folder name, e.g. "TrackMate"
        filename:    File to read (e.g. "SKILL.md", "GROOVY_API.md")

    Returns the file content or an error string.
    """
    path = Path(_SKILLS_ROOT) / _sanitise(plugin_name) / filename
    if not path.exists():
        return f"[NOT FOUND] {path}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tool 7 — List all files in a plugin's skill folder
# ---------------------------------------------------------------------------

@tool
def list_plugin_skill_folder(plugin_name: str) -> str:
    """
    List all files currently saved in a plugin's skill folder.

    Use at the end of the skill-building process to confirm all 5 required
    files are present before reporting completion.

    Returns a newline-separated list of file paths.
    """
    folder = Path(_SKILLS_ROOT) / _sanitise(plugin_name)
    if not folder.exists():
        return f"[NOT FOUND] Skill folder does not exist yet: {folder}"
    files = sorted(folder.iterdir())
    return "\n".join(str(f) for f in files) or "(empty folder)"


# ---------------------------------------------------------------------------
# Tool 8 — Build a test Groovy script for plugin validation
# ---------------------------------------------------------------------------

@tool
def create_plugin_test_script(
    plugin_name: str,
    groovy_code: str,
    project_root: str,
) -> str:
    """
    Save a Groovy validation script for a plugin to the test workspace.

    This is used ONLY during the skill-building process to test whether the
    generated GROOVY_WORKFLOW is executable — NOT for production pipelines.

    Args:
        plugin_name:  Name of the plugin (used in filename)
        groovy_code:  Complete Groovy script to test
        project_root: Absolute path to the test project workspace

    Returns the absolute path of the saved test script.
    """
    scripts_dir = Path(project_root) / "scripts" / "imagej"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitise(plugin_name)
    path = scripts_dir / f"TEST_{safe_name}_workflow.groovy"
    path.write_text(groovy_code, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitise(name: str) -> str:
    """Convert plugin name to a safe folder/file name."""
    return re.sub(r"[^A-Za-z0-9_\-]", "_", name).strip("_")