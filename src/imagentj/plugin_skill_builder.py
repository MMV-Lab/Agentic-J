"""
plugin_skill_builder.py

Defines the PluginSkillBuilder subagent, its handoff schema, and the
@tool wrapper that the Supervisor calls.

Add to agents.py:
  from .plugin_skill_builder import plugin_skill_builder, PluginSkillHandoff
  Then add `plugin_skill_builder` to the supervisor's tools list.
"""

from __future__ import annotations

from typing import Optional

from langchain.agents import create_agent
from langchain_core.tools import tool
from pydantic import BaseModel

# Reuse the shared LLM and tracker already created in agents.py
# (import from your agents module — adjust the import path as needed)
from .agents import llm_worker

from .prompts import plugin_skill_builder_prompt

from .tools import (
    internet_search,
    inspect_java_class,
    rag_retrieve_docs,
    rag_retrieve_mistakes,
    save_coding_experience,
    check_plugin_installed,
    inspect_all_ui_windows,
    execute_script,
    get_script_info,
    setup_analysis_workspace,
    save_markdown,
)

from .tools import (
    fetch_plugin_docs_url,
    search_imagej_wiki,
    fetch_github_plugin_info,
    fetch_github_file,
    save_plugin_skill_file,
    read_plugin_skill_file,
    list_plugin_skill_folder,
    create_plugin_test_script,
)


# ---------------------------------------------------------------------------
# Handoff schema
# ---------------------------------------------------------------------------

class PluginSkillHandoff(BaseModel):
    """Returned by plugin_skill_builder."""

    plugin_name: str
    skill_folder_path: str                # absolute path to /app/skills/plugins/{name}/

    # Individual file paths
    overview_path: str
    ui_guide_path: str
    groovy_api_path: str
    groovy_workflow_path: str             # "N/A" if plugin has no scripting interface
    skill_md_path: str

    # Validation results
    groovy_test_success: bool             # True only if execute_script ran without errors
    ui_workflow_verified: bool            # True only after explicit user confirmation

    # Summary for the supervisor to relay to the user
    summary: str                          # 2–3 sentence plain-English summary of what was built
    known_limitations: list[str]          # e.g., ["UI-only mode", "requires restart"]

    success: bool
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent instance
# ---------------------------------------------------------------------------

_plugin_skill_builder_agent = create_agent(
    # Use the full reasoning model — this task requires careful multi-step research
    llm_worker,
    tools=[
        # ── Research tools ──────────────────────────────────────────────────
        search_imagej_wiki,
        fetch_plugin_docs_url,
        fetch_github_plugin_info,
        fetch_github_file,
        internet_search,

        # ── ImageJ introspection ────────────────────────────────────────────
        inspect_java_class,
        rag_retrieve_docs,
        rag_retrieve_mistakes,
        save_coding_experience,
        check_plugin_installed,

        # ── Script testing ──────────────────────────────────────────────────
        create_plugin_test_script,
        get_script_info,
        execute_script,
        inspect_all_ui_windows,
        setup_analysis_workspace,

        # ── Skill file management ───────────────────────────────────────────
        save_plugin_skill_file,
        read_plugin_skill_file,
        list_plugin_skill_folder,
        save_markdown,
    ],
    system_prompt=plugin_skill_builder_prompt,
    response_format=PluginSkillHandoff,
    name="plugin_skill_builder",
    # No middleware: research tasks are typically single focused calls;
    # the agent should not truncate its own research context.
)


# ---------------------------------------------------------------------------
# Supervisor-facing @tool wrapper
# ---------------------------------------------------------------------------

@tool
def plugin_skill_builder(
    plugin_name: str,
    github_url: Optional[str] = None,
    docs_url: Optional[str] = None,
    test_image_path: Optional[str] = None,
) -> PluginSkillHandoff:
    """
    Research a Fiji/ImageJ plugin in depth and build a permanent skill folder.

    The skill folder is saved to /app/skills/plugins/{plugin_name}/ and
    contains 5 files:
      SKILL.md            ← LLM-facing quick-reference summary
      OVERVIEW.md         ← use case, input/output types, automation support
      UI_GUIDE.md         ← step-by-step GUI workflow for users
      GROOVY_API.md       ← all IJ.run() commands with parameters
      GROOVY_WORKFLOW.groovy ← complete tested automation script

    The agent will:
    1. Crawl ImageJ Wiki, GitHub, and any provided URLs.
    2. Test the Groovy workflow by executing it (up to 3 retries).
    3. Ask the user to validate the UI workflow and the Groovy output.
    4. Return a PluginSkillHandoff with paths and validation results.

    Args:
        plugin_name:       Exact plugin name as it appears in Fiji menus,
                           e.g. "TrackMate", "MorphoLibJ", "StarDist"
        github_url:        (Optional) GitHub repo URL if known,
                           e.g. "https://github.com/fiji/TrackMate"
        docs_url:          (Optional) Official documentation or tutorial URL
        test_image_path:   (Optional) Absolute path to a sample image to use
                           when testing the Groovy workflow. If omitted, the
                           agent will use any image already open in Fiji or
                           attempt to download a public sample.

    Returns a PluginSkillHandoff. Check groovy_test_success and
    ui_workflow_verified before relying on the skill files.

    WHEN TO CALL:
    - User asks to analyse data with an unfamiliar plugin.
    - imagej_coder returns code that errors with unknown commands.
    - You need to verify what IJ.run() strings a plugin actually accepts.
    - User wants a reusable documented template for a plugin.

    After this tool succeeds, future imagej_coder calls for this plugin
    should include the SKILL.md path in the task context.
    """
    # Build context string for the agent
    context_parts = [f"PLUGIN: {plugin_name}"]
    if github_url:
        context_parts.append(f"GITHUB: {github_url}")
    if docs_url:
        context_parts.append(f"DOCS URL: {docs_url}")
    if test_image_path:
        context_parts.append(f"TEST IMAGE: {test_image_path}")

    context = "\n".join(context_parts)

    result = _plugin_skill_builder_agent.invoke({
        "messages": [{
            "role": "user",
            "content": context,
        }]
    })
    return result["structured_response"]