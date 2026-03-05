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
    model="google/gemini-3-pro-preview",
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