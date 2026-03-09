import os
import sqlite3
from typing import Optional

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents import create_agent
from langchain.agents.middleware import (
    SummarizationMiddleware,
    ContextEditingMiddleware,
    ClearToolUsesEdit,
    FilesystemFileSearchMiddleware,
)
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from .prompts import (
    imagej_coder_prompt,
    imagej_debugger_prompt,
    supervisor_prompt,
    python_analyst_prompt,
    qa_reporter_prompt,
    plugin_skill_builder_prompt
)
from .tools import (
    internet_search, inspect_all_ui_windows, run_script_safe,
    rag_retrieve_docs, inspect_java_class, save_coding_experience,
    rag_retrieve_mistakes, save_reusable_script, inspect_folder_tree,
    smart_file_reader, run_python_code, inspect_csv_header,
    extract_image_metadata, search_fiji_plugins, install_fiji_plugin,
    check_plugin_installed, mkdir_copy, save_script, execute_script,
    get_script_info, load_script, get_script_history,
    setup_analysis_workspace, save_markdown,
    fetch_plugin_docs_url,
    search_imagej_wiki,
    fetch_github_plugin_info,
    fetch_github_file,
    save_plugin_skill_file,
    read_plugin_skill_file,
    list_plugin_skill_folder,
    create_plugin_test_script,
)
from imagentj.tracker import UsageMetrics, MetricsSignalBridge, UsageTrackerCallback


# ---------------------------------------------------------------------------
# Shared tracker
# ---------------------------------------------------------------------------

shared_metrics = UsageMetrics()
shared_bridge  = MetricsSignalBridge()
shared_tracker = UsageTrackerCallback(shared_metrics, shared_bridge)

open_router_key = os.getenv("OPEN_ROUTER_API_KEY")


# ---------------------------------------------------------------------------
# Checkpointer — supervisor only (subagents are stateless by design)
# ---------------------------------------------------------------------------

_CHATS_DIR = os.environ.get("CHAT_DATA_PATH", "/app/data/chats")
os.makedirs(_CHATS_DIR, exist_ok=True)

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    _db_path = os.path.join(_CHATS_DIR, "checkpoints.db")
    _conn    = sqlite3.connect(_db_path, check_same_thread=False)
    checkpointer_supervisor = SqliteSaver(_conn)
    print(f"[agents] Using SqliteSaver at {_db_path}")
except ImportError:
    checkpointer_supervisor = MemorySaver()
    print("[agents] WARNING: SqliteSaver not available — using MemorySaver")


# ---------------------------------------------------------------------------
# Handoff schemas
# ---------------------------------------------------------------------------

class ScriptHandoff(BaseModel):
    """Returned by imagej_coder and imagej_debugger."""
    script_path: str
    description: str
    inputs: list[str]
    outputs: list[str]
    stage: str                          # io_check | preprocessing | segmentation | measurement | debugger_fix
    success: bool
    error_message: Optional[str] = None
    requires_user_approval: bool = False  # True for single-image verification runs
    lesson: Optional[str] = None          # debugger only: "PROBLEM: x FIX: y"


class AnalystHandoff(BaseModel):
    """Returned by python_data_analyst."""
    script_path: str
    description: str
    stage: str                          # "statistics" | "plotting"
    inputs: list[str]
    outputs: list[str]
    stats_csv_path: Optional[str] = None  # Stage 1 only
    statistical_tests: list[str] = []
    figure_paths: list[str] = []          # Stage 2 only
    success: bool
    error_message: Optional[str] = None


class QAHandoff(BaseModel):
    """Returned by qa_reporter."""
    checklist_path: str
    minimal_workflow_passed: int
    minimal_workflow_total: int
    critical_failures: list[str]
    success: bool


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
# Models
# ---------------------------------------------------------------------------

llm_supervisor = ChatOpenAI(
    model="google/gemini-3-pro-preview",
    api_key=open_router_key,
    base_url="https://openrouter.ai/api/v1",
    temperature=0.,
    reasoning_effort="low",
    verbose=True,
    callbacks=[shared_tracker],
)

llm_worker = ChatOpenAI(
    model="openai/gpt-5.3-codex",
    api_key=open_router_key,
    base_url="https://openrouter.ai/api/v1",
    temperature=0.,
    reasoning_effort="low",
    verbose=True,
    callbacks=[shared_tracker],
)

llm_analyst = ChatOpenAI(
    model="anthropic/claude-haiku-4.5",
    api_key=open_router_key,
    base_url="https://openrouter.ai/api/v1",
    temperature=0.,
    verbose=True,
    callbacks=[shared_tracker],
)

llm_nano = ChatOpenAI(
    model="google/gemini-3.1-flash-lite-preview",
    api_key=open_router_key,
    base_url="https://openrouter.ai/api/v1",
    temperature=0.,
    verbose=True,
    callbacks=[shared_tracker],
)


# ---------------------------------------------------------------------------
# Subagent instances — created once at module level, stateless invocation
# ---------------------------------------------------------------------------
# Subagents have no checkpointer — they are stateless workers.
# The supervisor holds all project state and re-injects context per call.
# ContextEditingMiddleware trims their internal tool history if a single
# call grows large (e.g. a coder writing many scripts in one invocation).

_coder_agent = create_agent(
    llm_worker,
    tools=[
        internet_search,
        inspect_java_class,
        save_script,
        load_script,
        get_script_history,
        rag_retrieve_mistakes,  # mandatory: check past mistakes before writing
    ],
    system_prompt=imagej_coder_prompt,
    response_format=ScriptHandoff,
    name="imagej_coder",
    middleware=[
        ContextEditingMiddleware(
            edits=[
                ClearToolUsesEdit(
                    trigger=50000,
                    keep=10,
                    clear_tool_inputs=False,
                    exclude_tools=[],
                    placeholder="[cleared]",
                ),
            ],
        ),
    ],
)

_debugger_agent = create_agent(
    llm_worker,
    tools=[
        internet_search,
        inspect_java_class,
        rag_retrieve_mistakes,
        save_script,
        load_script,
        get_script_history,
        get_script_info,
    ],
    system_prompt=imagej_debugger_prompt,
    response_format=ScriptHandoff,
    name="imagej_debugger",
    middleware=[
        ContextEditingMiddleware(
            edits=[
                ClearToolUsesEdit(
                    trigger=50000,
                    keep=10,
                    clear_tool_inputs=False,
                    exclude_tools=[],
                    placeholder="[cleared]",
                ),
            ],
        ),
    ],
)

_analyst_agent = create_agent(
    llm_analyst,
    tools=[
        inspect_csv_header,
        save_script,
        load_script,
        get_script_history,
        get_script_info,
    ],
    system_prompt=python_analyst_prompt,
    response_format=AnalystHandoff,
    name="python_data_analyst",
)

_qa_agent = create_agent(
    llm_nano,
    tools=[
        inspect_folder_tree,
        smart_file_reader,
        get_script_info,
        save_markdown,
        inspect_csv_header,
        load_script,
    ],
    system_prompt=qa_reporter_prompt,
    response_format=QAHandoff,
    name="qa_reporter",
)

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
        smart_file_reader,

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
# Subagents as @tool — supervisor calls these like any other tool.
# Returning a Pydantic model makes LangChain serialize it to clean JSON
# in the ToolMessage automatically. No parsing needed on the supervisor side.
# ---------------------------------------------------------------------------

@tool
def imagej_coder(task: str, project_root: str) -> ScriptHandoff:
    """
    Generate and save a production-ready ImageJ/Fiji Groovy script.

    Use for: IO checks, preprocessing, segmentation, measurement scripts.
    Always call with the full task description and absolute project root path.
    Returns a ScriptHandoff with script_path, stage, inputs, outputs, success.
    If requires_user_approval=True, show the user the result before batch processing.
    If success=False, pass script_path + error_message to imagej_debugger.
    """
    result = _coder_agent.invoke({
        "messages": [{
            "role": "user",
            "content": f"PROJECT ROOT: {project_root}\n\nTASK: {task}",
        }]
    })
    return result["structured_response"]


@tool
def imagej_debugger(script_path: str, error_message: str) -> ScriptHandoff:
    """
    Diagnose and repair a failing ImageJ/Fiji Groovy script.

    Provide the absolute path to the faulty script and the full error message.
    Returns a ScriptHandoff with the repaired script_path and a lesson field.
    After success, pass lesson to save_coding_experience.
    """
    result = _debugger_agent.invoke({
        "messages": [{
            "role": "user",
            "content": f"FAULTY SCRIPT: {script_path}\n\nERROR:\n{error_message}",
        }]
    })
    return result["structured_response"]


@tool
def python_data_analyst(task: str, input_csv: str, output_dir: str) -> AnalystHandoff:
    """
    Run statistical analysis or generate publication-quality plots from ImageJ CSV data.

    Call TWICE — once per stage, never combined:
      Stage 1 (statistics): task describes hypothesis testing. Returns stats_csv_path.
      Stage 2 (plotting):   task describes plot types. Call only after Stage 1 CSV exists.
    Returns an AnalystHandoff with script_path, outputs, stats_csv_path or figure_paths.
    """
    result = _analyst_agent.invoke({
        "messages": [{
            "role": "user",
            "content": (
                f"INPUT CSV: {input_csv}\n"
                f"OUTPUT DIR: {output_dir}\n\n"
                f"TASK: {task}"
            ),
        }]
    })
    return result["structured_response"]


@tool
def qa_reporter(project_root: str) -> QAHandoff:
    """
    Audit the completed project folder and generate QA_Checklist_Report.md.

    Call once at the end of every project after all scripts have run successfully.
    Provide the absolute path to the project root folder.
    Returns a QAHandoff with checklist_path, pass/fail counts, and critical_failures.
    Relay critical_failures to the user verbatim.
    """
    result = _qa_agent.invoke({
        "messages": [{
            "role": "user",
            "content": f"PROJECT ROOT: {project_root}",
        }]
    })
    return result["structured_response"]

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

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def init_agent():
    fs_backend = FilesystemBackend(
        root_dir="/app/data/",
        virtual_mode=False,
    )

    supervisor = create_deep_agent(
        name="ImageJ_Supervisor",
        tools=[
            # ── subagents as tools (return typed JSON) ──────────────────────
            imagej_coder,
            imagej_debugger,
            python_data_analyst,
            qa_reporter,
            plugin_skill_builder,
            # ── supervisor's own tools ───────────────────────────────────────
            internet_search,
            inspect_all_ui_windows,
            rag_retrieve_docs,
            save_coding_experience,
            rag_retrieve_mistakes,
            save_reusable_script,
            inspect_folder_tree,
            smart_file_reader,
            extract_image_metadata,
            search_fiji_plugins,
            install_fiji_plugin,
            check_plugin_installed,
            mkdir_copy,
            inspect_csv_header,
            execute_script,
            get_script_info,
            setup_analysis_workspace,
            save_markdown,
        ],
        system_prompt=supervisor_prompt,
        subagents=[],           # empty — all subagents are now tools above
        middleware=[
            SummarizationMiddleware(
                model=llm_nano,
                trigger=("tokens", 50000),
                keep=("messages", 20),
            ),
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=50000,
                        keep=10,
                        clear_tool_inputs=False,
                        exclude_tools=[],
                        placeholder="[cleared]",
                    ),
                ],
            ),
            FilesystemFileSearchMiddleware(
                root_path="/app/data/",
                use_ripgrep=True,
            ),
        ],
        model=llm_supervisor,
        debug=False,
        backend=fs_backend,
        checkpointer=checkpointer_supervisor,
        skills=["/app/skills/"],
    )

    return supervisor, checkpointer_supervisor, shared_metrics, shared_bridge, shared_tracker