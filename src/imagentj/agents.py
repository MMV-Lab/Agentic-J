import os
import sqlite3
from typing import Optional

from . import stop_signal

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ContextEditingMiddleware,
    ClearToolUsesEdit,
    FilesystemFileSearchMiddleware,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel
from deepagents.middleware.skills import SkillsMiddleware


from .prompts import (
    imagej_coder_prompt,
    imagej_debugger_prompt,
    build_supervisor_prompt,
    python_analyst_prompt,
    qa_reporter_prompt,
    plugin_manager_prompt,
    # vlm_judge_prompt,  # VLM disabled
)
from .tools import (
    internet_search, inspect_all_ui_windows, capture_plugin_dialog,
    show_in_imagej_gui,
    rag_retrieve_docs, inspect_java_class, save_coding_experience,
    rag_retrieve_mistakes, rag_retrieve_recipes, save_recipe,
    save_reusable_script, inspect_folder_tree,
    smart_file_reader, inspect_csv_header,
    extract_image_metadata, search_fiji_plugins, install_fiji_plugin,
    check_plugin_installed, mkdir_copy, save_script, execute_script,
    get_script_info, load_script, get_script_history,
    setup_analysis_workspace, save_markdown,
    NarrationReminderMiddleware, PhaseGuardMiddleware,
    update_state_ledger, read_state_ledger, set_ledger_metadata, get_ledger_context,
    check_environment,
    set_dialog_vision_llm,
    # capture_ij_window, build_compilation, analyze_image,  # VLM disabled
)
from imagentj.tracker import UsageMetrics, MetricsSignalBridge, UsageTrackerCallback


# ---------------------------------------------------------------------------
# Shared tracker
# ---------------------------------------------------------------------------

shared_metrics = UsageMetrics()
shared_bridge  = MetricsSignalBridge()
shared_tracker = UsageTrackerCallback(shared_metrics, shared_bridge)

open_router_key = os.getenv("OPEN_ROUTER_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")


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
    print("[agents] WARNING: langgraph-checkpoint-sqlite not installed — using MemorySaver (history lost on restart)")


# ---------------------------------------------------------------------------
# Handoff schemas
# ---------------------------------------------------------------------------

class ScriptHandoff(BaseModel):
    """Returned by imagej_coder and imagej_debugger."""
    script_path: str
    description: str
    inputs: list[str] = []
    outputs: list[str] = []
    stage: str = "unknown"                          # io_check | preprocessing | segmentation | measurement | debugger_fix
    success: bool
    error_message: Optional[str] = None
    requires_user_approval: bool = False  # True for single-image verification runs
    # Debugger-only fields. The debugger does NOT save the lesson itself
    # (it cannot run the fix to verify correctness); it populates these so
    # the supervisor can call save_coding_experience after execute_script
    # confirms the fix actually works.
    lesson: Optional[str] = None          # one-line imperative rule
    failed_code: Optional[str] = None     # the offending snippet that was replaced
    working_code: Optional[str] = None    # the corrected snippet
    error_type: Optional[str] = None      # MissingMethod | NullPointer | Import | Logic | Path | ...
    class_involved: Optional[str] = None  # main ImageJ/plugin class


class AnalystHandoff(BaseModel):
    """Returned by python_data_analyst."""
    script_path: str
    description: str
    stage: str = "unknown"              # "statistics" | "plotting"
    inputs: list[str] = []
    outputs: list[str] = []
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


class PluginRecommendation(BaseModel):
    """Returned by plugin_manager."""
    recommended_plugin: Optional[str] = None
    is_installed: bool = False
    needs_restart: bool = False
    skill_folder: Optional[str] = None
    plugin_capabilities: str = ""
    relevance_reasoning: str = ""
    alternative_plugins: list[str] = []
    installation_status: str = "not_needed"
    success: bool = True


# VLM disabled — uncomment to re-enable
# class VLMCheckResult(BaseModel):
#     check_name:    str
#     verdict:       str   # "PASS" | "WARN" | "FAIL"
#     observation:   str
#     image_path:    Optional[str] = None
#
# class VLMHandoff(BaseModel):
#     overall_verdict:       str
#     summary:               str
#     checks:                list[VLMCheckResult]
#     issues_found:          list[str]
#     recommended_action:    str
#     image_paths_inspected: list[str]
#     pipeline_step:         str
#     success:               bool
#     error_message:         Optional[str] = None


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

if open_router_key:
    api_key = open_router_key
    base_url = "https://openrouter.ai/api/v1"
    use_openrouter = True
elif openai_key:
    api_key = openai_key
    base_url = None
    use_openrouter = False
else:
    raise RuntimeError("No API key found. Set OPEN_ROUTER_API_KEY or OPENAI_API_KEY.")

def m(name: str) -> str:
    if use_openrouter:
        return name
    if name.startswith("openai/"):
        return name.split("/", 1)[1]
    raise ValueError(f"Model {name} not available on OpenAI direct; needs OpenRouter.")


llm_supervisor = ChatOpenAI(
    model=m("openai/gpt-5.2"),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    reasoning_effort="low",
    verbose=True,
    callbacks=[shared_tracker],
)

llm_worker = ChatOpenAI(
    model=m("openai/gpt-5.3-codex"),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    reasoning_effort="low",
    verbose=True,
    callbacks=[shared_tracker],
)

llm_analyst = ChatOpenAI(
    model=m("openai/gpt-5.2"),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    reasoning_effort="none",
    verbose=True,
    callbacks=[shared_tracker],
)

llm_nano = ChatOpenAI(
    model=m("openai/gpt-4o-mini"),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    verbose=True,
    callbacks=[shared_tracker],
)

# llm_vlm = ChatOpenAI(  # VLM disabled
#     model=m("openai/gpt-5.4-nano"),
#     api_key=api_key,
#     base_url=base_url,
#     temperature=0.,
#     reasoning_effort="none",
#     verbose=True,
#     callbacks=[shared_tracker],
# )

# ---------------------------------------------------------------------------
# Subagent instances — created once at module level, stateless invocation
# ---------------------------------------------------------------------------

def _make_coder_agent(model, name, system_prompt):
    return create_agent(
        model,
        tools=[
            internet_search,
            inspect_java_class,
            save_script,
            load_script,
            get_script_history,
            smart_file_reader,
            rag_retrieve_mistakes,
            rag_retrieve_recipes,
            inspect_folder_tree,   # lets agent survey /app/skills/ before reading
        ],
        system_prompt=system_prompt,
        response_format=ToolStrategy(schema=ScriptHandoff, handle_errors=True),
        name=name,
        middleware=[
            FilesystemFileSearchMiddleware(
                root_path="/app/skills/",  # scoped to skills only
                use_ripgrep=True,
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
    response_format=ToolStrategy(schema=AnalystHandoff, handle_errors=True),
    name="python_data_analyst",
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
    response_format=ToolStrategy(schema=QAHandoff, handle_errors=True),
    name="qa_reporter",
)

# Plugin manager — gets SkillsMiddleware so it sees all plugin skill descriptions
# and can read full SKILL.md files on demand via progressive disclosure.
_plugin_skills_backend = FilesystemBackend(
    root_dir="/app/",
    virtual_mode=False,
)

_plugin_agent = create_agent(
    llm_analyst,
    tools=[
        search_fiji_plugins,
        check_plugin_installed,
        install_fiji_plugin,
        smart_file_reader,
        inspect_folder_tree,
    ],
    system_prompt=plugin_manager_prompt,
    response_format=PluginRecommendation,
    name="plugin_manager",
    middleware=[
        SkillsMiddleware(
            backend=_plugin_skills_backend,
            sources=["/app/skills/"],  # scans /app/skills/ for SKILL.md files
        ),
    ],
)

# _vlm_agent = create_agent(
#     llm_vlm,
#     tools=[
#         capture_ij_window,   # save named open IJ window as PNG via PyImageJ
#         build_compilation,   # fuse multiple images into a labelled side-by-side panel
#         analyze_image,       # send image/compilation to vision LLM, return analysis
#     ],
#     system_prompt=vlm_judge_prompt,
#     response_format=VLMHandoff,
#     name="vlm_judge",
# )


@tool
def imagej_coder(task: str, project_root: str) -> ScriptHandoff:
    """
    task: full description of the script to generate, including inputs, outputs, and processing steps.
    project_root: absolute path to the project root, for context on file structure and for saving

    Generate and save a production-ready ImageJ/Fiji Groovy script.

    Use for: IO checks, preprocessing, segmentation, measurement scripts.
    Always call with the full task description and absolute project root path.
    Returns a ScriptHandoff with script_path, stage, inputs, outputs, success.
    If requires_user_approval=True, show the user the result before batch processing.
    If success=False, pass script_path + error_message to imagej_debugger.
    """

    model = llm_worker

    sections = [f"PROJECT ROOT: {project_root}"]
    ledger_ctx = get_ledger_context(project_root)
    if ledger_ctx:
        sections.append(f"PROJECT STATE (from state ledger):\n{ledger_ctx}")

    sections.append(f"TASK: {task}")

    agent = _make_coder_agent(model, "imagej_coder", imagej_coder_prompt)

    result = stop_signal.SubagentRunner(
        agent.invoke,
        {"messages": [{"role": "user", "content": "\n\n".join(sections)}]},
    ).run()
    return result["structured_response"]


@tool
def imagej_debugger(script_path: str, error_message: str, project_root: str = "") -> ScriptHandoff:
    """
    Diagnose and repair a failing ImageJ/Fiji Groovy script.

    Args:
        script_path:   Absolute path to the faulty .groovy script.
        error_message: Full error output from execute_script (stack trace, line numbers, etc.).
        project_root:  Absolute path to the project folder.

    Returns a ScriptHandoff with the repaired script_path and a lesson field.
    After success, pass lesson to save_coding_experience.
    """
    agent = _make_coder_agent(llm_worker, "imagej_debugger", imagej_debugger_prompt)

    sections = [f"FAULTY SCRIPT: {script_path}", f"ERROR:\n{error_message}"]
    if project_root:
        ledger_ctx = get_ledger_context(project_root)
        if ledger_ctx:
            sections.insert(1, f"PROJECT STATE (for context):\n{ledger_ctx}")

    result = stop_signal.SubagentRunner(
        agent.invoke,
        {"messages": [{"role": "user", "content": "\n\n".join(sections)}]},
    ).run()
    return result["structured_response"]



@tool
def python_data_analyst(task: str, input_csv: str, output_dir: str, project_root: str) -> AnalystHandoff:
    """
    Run statistical analysis or generate publication-quality plots from ImageJ CSV data.

    Call TWICE — once per stage, never combined:
      Stage 1 (statistics): task describes hypothesis testing. Returns stats_csv_path.
      Stage 2 (plotting):   task describes plot types. Call only after Stage 1 CSV exists.

    Args:
        task:         What to do — describe the hypothesis, groups to compare, or plot types.
        input_csv:    Absolute path to the CSV file to analyze (raw measurements or Statistics_Results.csv).
        output_dir:   Absolute path to the directory where scripts and outputs should be saved.
        project_root: Absolute path to the project folder. 

    Returns an AnalystHandoff with script_path, outputs, stats_csv_path or figure_paths.
    """
    sections = [
        f"INPUT CSV: {input_csv}",
        f"OUTPUT DIR: {output_dir}",
    ]
    # Inject ledger so the analyst knows the scientific goal (for axis labels),
    # image calibration (for units like μm), and experimental conditions.
    if project_root:
        ledger_ctx = get_ledger_context(project_root)
        if ledger_ctx:
            sections.append(f"PROJECT STATE (use for axis labels, units, and context):\n{ledger_ctx}")
    sections.append(f"TASK: {task}")

    result = stop_signal.SubagentRunner(
        _analyst_agent.invoke,
        {"messages": [{"role": "user", "content": "\n\n".join(sections)}]},
    ).run()
    return result["structured_response"]


@tool
def qa_reporter(project_root: str) -> QAHandoff:
    """
    Audit the completed project folder and generate QA_Checklist_Report.md.

    Call once at the end of every project after all scripts have run successfully.

    Args:
        project_root: Absolute path to the project root folder. The reporter reads all
                      scripts, CSVs, and images to evaluate against workflow and image
                      publishing standards.

    Returns a QAHandoff with checklist_path, pass/fail counts, and critical_failures.
    Relay critical_failures to the user verbatim.
    """
    sections = [f"PROJECT ROOT: {project_root}"]
    # Inject the full ledger — it contains the workflow summary, all parameters,
    # all scripts, all outputs. This is exactly what the QA agent needs to audit.
    ledger_ctx = get_ledger_context(project_root)
    if ledger_ctx:
        sections.append(f"WORKFLOW SUMMARY (from state ledger — use as primary reference):\n{ledger_ctx}")

    result = stop_signal.SubagentRunner(
        _qa_agent.invoke,
        {"messages": [{"role": "user", "content": "\n\n".join(sections)}]},
    ).run()
    return result["structured_response"]


# VLM disabled — uncomment to re-enable
# @tool
# def vlm_judge(task, pipeline_step, expected_output, image_source, labels=None):
#     sources = image_source if isinstance(image_source, list) else [image_source]
#     content = (
#         f"PIPELINE STEP: {pipeline_step}\n"
#         f"IMAGE SOURCE(S): {sources}\n"
#         f"LABELS: {labels or []}\n"
#         f"EXPECTED OUTPUT: {expected_output}\n\n"
#         f"TASK: {task}"
#     )
#     result = _vlm_agent.invoke({"messages": [{"role": "user", "content": content}]})
#     return result["structured_response"]


@tool
def plugin_manager(task: str, project_root: str = "") -> PluginRecommendation:
    """
    Find, evaluate, and optionally install Fiji plugins for an image analysis task.

    Call in Phase 1 to find the best plugin for the scientific goal.
    Call again with "INSTALL <plugin_name>" after user approval to install.

    Args:
        task:         Describe the scientific task (e.g., "segment touching nuclei in
                      fluorescence images") OR an install command ("INSTALL MorphoLibJ").
        project_root: Absolute path to the project folder. Provides the plugin manager
                      with image metadata and scientific goal for intelligent matching.

    Returns a PluginRecommendation with the best plugin, its installation status,
    skill folder path (if docs exist), and reasoning.

    AFTER receiving the recommendation:
    - Record the skill_folder in the ledger via set_ledger_metadata(relevant_skill=...).
    - If installation_status="user_approval_needed", ask the user before calling again
      with "INSTALL <plugin_name>".
    - After installation, remind the user to restart Fiji.
    """
    sections = []
    if project_root:
        ledger_ctx = get_ledger_context(project_root)
        if ledger_ctx:
            sections.append(f"PROJECT STATE (for context):\n{ledger_ctx}")
    sections.append(f"TASK: {task}")

    result = stop_signal.SubagentRunner(
        _plugin_agent.invoke,
        {"messages": [{"role": "user", "content": "\n\n".join(sections)}]},
    ).run()
    return result["structured_response"]


# @tool
# def vlm_judge(
#     task:            str,
#     pipeline_step:   str,
#     expected_output: str,
#     image_source:    str | list[str],
#     labels:          Optional[list[str]] = None,
# ) -> VLMHandoff:
#     """
#     Visually inspect one or more images using a vision LLM and return a structured verdict.
 
#     ⚠️  COST NOTICE — vision API calls are significantly more expensive than text:
#         Call vlm_judge selectively — see WHEN TO CALL below.
 
#     IMAGE SOURCE — two modes:
#         Single string:  open IJ window title  → captured via IJ API then analysed.
#                         absolute file path    → analysed directly, no capture.
#         List of strings: multiple window titles and/or file paths
#                         → automatically fused into a side-by-side compilation panel
#                           before analysis. Much more effective for comparisons than
#                           sending images separately (VLM gets direct spatial reference).
 
#     Args:
#         task:            What to inspect and what criteria to judge against.
#         pipeline_step:   Short stage identifier for traceability, e.g. "segmentation".
#         expected_output: What a correct result looks like — used as pass/fail benchmark.
#         image_source:    Window title, file path, or list of either.
#                          Window titles: e.g. "MAX_DAPI.tif", "mask_nuclei.tif"
#                          File paths:    e.g. "/app/data/projects/study/processed/mask.tif"
#         labels:          Optional panel captions for compilations, e.g. ["Original", "Mask"].
#                          Ignored for single images.
 
#     Returns VLMHandoff with overall_verdict ("PASS"/"WARN"/"FAIL"), per-check breakdown,
#     issues_found, and recommended_action.
 
#     WHEN TO CALL (be selective — each call costs money):
#         ✅ Sample verification (Phase 4b) — once per pipeline, on the verification image.
#         ✅ Segmentation / threshold output — use compilation with original + result.
#         ✅ When a script exits cleanly but output is suspected to be wrong.
#         ✅ Final QA before qa_reporter — scale bar and output image check.
#         ✅ When the user reports a visual problem.
#         ❌ Do NOT call after every batch script execution.
#         ❌ Do NOT call to list open windows — use inspect_all_ui_windows.
#         ❌ Do NOT call to read CSV or log output — use inspect_csv_header / smart_file_reader.
 
#     ACTING ON THE VERDICT:
#         PASS → proceed. Show summary to user at sample verification.
#         WARN → continue pipeline; report issues in Phase 5 summary.
#         FAIL → stop. Send script path + issues_found to imagej_debugger. AFTER asking the user for visual verfification. 
#                Re-run and call vlm_judge again after the fix.
#     """
#     sources = image_source if isinstance(image_source, list) else [image_source]
 
#     content = (
#         f"PIPELINE STEP: {pipeline_step}\n"
#         f"IMAGE SOURCE(S): {sources}\n"
#         f"LABELS: {labels or []}\n"
#         f"EXPECTED OUTPUT: {expected_output}\n\n"
#         f"TASK: {task}"
#     )
 
#     result = _vlm_agent.invoke({"messages": [{"role": "user", "content": content}]})
#     return result["structured_response"]

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def init_agent(enable_qa: bool = False):
    fs_backend = FilesystemBackend(
        root_dir="/app/data/",
        virtual_mode=False,
    )

    subagent_tools = [
        imagej_coder,
        imagej_debugger,
        python_data_analyst,
        # vlm_judge,  # VLM disabled
    ]
    if enable_qa:
        subagent_tools.append(qa_reporter)

    set_dialog_vision_llm(llm_nano)

    supervisor_middleware = [
        ContextEditingMiddleware(
            edits=[
                ClearToolUsesEdit(
                    trigger=35000,
                    keep=8,
                    clear_tool_inputs=True,
                    exclude_tools=[
                        "read_state_ledger",
                        "update_state_ledger",
                        "set_ledger_metadata",
                    ],
                    placeholder="[cleared — see state_ledger.json for project state]",
                ),
            ],
        ),
        FilesystemFileSearchMiddleware(
            root_path="/app/data/",
            use_ripgrep=True,
        ),
        NarrationReminderMiddleware(),
        PhaseGuardMiddleware(),
    ]

    supervisor = create_deep_agent(
        name="ImageJ_Supervisor",
        tools=[
            # ── subagents as tools (return typed JSON) ──────────────────────
            *subagent_tools,
            plugin_manager,
            # ── supervisor's own tools ───────────────────────────────────────
            internet_search,
            inspect_all_ui_windows,
            capture_plugin_dialog,
            show_in_imagej_gui,
            rag_retrieve_docs,
            save_coding_experience,
            rag_retrieve_mistakes,
            rag_retrieve_recipes,
            save_recipe,
            save_reusable_script,
            inspect_folder_tree,
            smart_file_reader,
            extract_image_metadata,
            mkdir_copy,
            inspect_csv_header,
            execute_script,
            get_script_info,
            setup_analysis_workspace,
            save_markdown,
            check_environment,
            # ── state ledger (persistent project memory) ─────────────────────
            update_state_ledger,
            read_state_ledger,
            set_ledger_metadata,
        ],
        system_prompt=build_supervisor_prompt(enable_qa),
        subagents=[],
        middleware=supervisor_middleware,
        model=llm_supervisor,
        debug=False,
        backend=fs_backend,
        checkpointer=checkpointer_supervisor,
        skills=["/app/skills/workflow"],
    )

    return supervisor, checkpointer_supervisor, shared_metrics, shared_bridge, shared_tracker
