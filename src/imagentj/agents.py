import os
import sqlite3
from typing import Optional

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ContextEditingMiddleware,
    ClearToolUsesEdit,
    FilesystemFileSearchMiddleware,
)
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel
from deepagents.middleware.skills import SkillsMiddleware


from .prompts import (
    imagej_coder_prompt,
    imagej_debugger_prompt,
    supervisor_prompt,
    python_analyst_prompt,
    qa_reporter_prompt,
    vlm_judge_prompt,
    plugin_manager_prompt,
)
from .tools import (
    internet_search, inspect_all_ui_windows,
    rag_retrieve_docs, inspect_java_class, save_coding_experience,
    rag_retrieve_mistakes, save_reusable_script, inspect_folder_tree,
    smart_file_reader, inspect_csv_header,
    extract_image_metadata, search_fiji_plugins, install_fiji_plugin,
    check_plugin_installed, mkdir_copy, save_script, execute_script,
    get_script_info, load_script, get_script_history,
    setup_analysis_workspace, save_markdown,
    capture_ij_window, build_compilation, analyze_image,
    update_state_ledger, read_state_ledger, set_ledger_metadata, get_ledger_context
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
    print("[agents] WARNING: SqliteSaver not available — using MemorySaver")


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


class PluginRecommendation(BaseModel):
    """Returned by plugin_manager."""
    recommended_plugin: Optional[str] = None   # plugin name, or None if no plugin fits
    is_installed: bool = False                  # already installed in Fiji?
    needs_restart: bool = False                 # Fiji restart needed after install?
    skill_folder: Optional[str] = None          # path to skill docs (e.g. /app/skills/morpholibj_documentation/)
    plugin_capabilities: str = ""               # one-paragraph summary of what the plugin does
    relevance_reasoning: str = ""               # why this plugin fits the task (or why none do)
    alternative_plugins: list[str] = []         # other plugins considered
    installation_status: str = "not_needed"     # "installed" | "ready_to_install" | "user_approval_needed" | "not_needed" | "just_installed"
    success: bool = True



# class VLMCheckResult(BaseModel):
#     """Result of a single visual check performed by the VLM judge."""
#     check_name:    str   # e.g. "segmentation_quality", "scale_bar"
#     verdict:       str   # "PASS" | "WARN" | "FAIL"
#     observation:   str   # exactly what the vision model reported
#     image_path:    Optional[str] = None  # path to the image (or compilation) used for this check
 
 
# class VLMHandoff(BaseModel):
#     """Returned by vlm_judge."""
#     overall_verdict:       str                  # "PASS" | "WARN" | "FAIL"
#     summary:               str                  # 2–4 sentence plain-English summary
#     checks:                list[VLMCheckResult] # one entry per visual check
#     issues_found:          list[str]            # empty on PASS
#     recommended_action:    str                  # exact next step for the supervisor
#                                                 # e.g. "FAIL: send segmenter.groovy to
#                                                 #  imagej_debugger — nuclei merging detected"
#     image_paths_inspected: list[str]            # all images / compilations analysed
#     pipeline_step:         str                  # echoed from the task for logging
#     success:               bool                 # False only if the agent itself crashed
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
    base_url = None  # default OpenAI endpoint
    use_openrouter = False
else:
    raise RuntimeError("No API key found. Set OPEN_ROUTER_API_KEY or OPENAI_API_KEY.")

def m(name: str) -> str:
    if use_openrouter:
        return name
    # only keep openai/* models when hitting OpenAI directly
    if name.startswith("openai/"):
        return name.split("/", 1)[1]
    raise ValueError(f"Model {name} not available on OpenAI direct; needs OpenRouter.")


llm_supervisor = ChatOpenAI(
    model=m("openai/gpt-5.2"),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    reasoning_effort="none",
    verbose=True,
    callbacks=[shared_tracker],
)

llm_worker = ChatOpenAI(
    model=m("openai/gpt-5.3-codex"),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    reasoning_effort="none",
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

llm_vlm = ChatOpenAI(
    model=m("openai/gpt-5.4-nano"),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    reasoning_effort="none",
    verbose=True,
    callbacks=[shared_tracker],
)

from .tools.vision_tools import set_vision_llm 
set_vision_llm(llm_vlm)

# ---------------------------------------------------------------------------
# Subagent instances — created once at module level, stateless invocation
# ---------------------------------------------------------------------------
# Subagents have no checkpointer — they are stateless workers.
# The supervisor holds all project state and re-injects context per call.
# ContextEditingMiddleware trims their internal tool history if a single
# call grows large (e.g. a coder writing many scripts in one invocation).

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
            inspect_folder_tree,   # ← lets agent survey /app/skills/ before reading
        ],
        system_prompt=system_prompt,
        response_format=ScriptHandoff,
        name=name,
        middleware=[
            FilesystemFileSearchMiddleware(
                root_path="/app/skills/",  # ← scoped to skills only
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

    # Auto-inject ledger context so the coder has image metadata, previous step
    # outputs, skill paths, and RAG findings without the supervisor relaying them.
    sections = [f"PROJECT ROOT: {project_root}"]
    ledger_ctx = get_ledger_context(project_root)
    if ledger_ctx:
        sections.append(f"PROJECT STATE (auto-injected from state ledger):\n{ledger_ctx}")
    sections.append(f"TASK: {task}")

    agent = _make_coder_agent(model, "imagej_coder", imagej_coder_prompt)

    result = agent.invoke({
        "messages": [{
            "role": "user",
            "content": "\n\n".join(sections),
        }]
    })
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
    # Inject ledger so the debugger understands image properties and pipeline context
    if project_root:
        ledger_ctx = get_ledger_context(project_root)
        if ledger_ctx:
            sections.insert(1, f"PROJECT STATE (for context):\n{ledger_ctx}")

    result = agent.invoke({
        "messages": [{
            "role": "user",
            "content": "\n\n".join(sections),
        }]
    })
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

    result = _analyst_agent.invoke({
        "messages": [{
            "role": "user",
            "content": "\n\n".join(sections),
        }]
    })
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

    result = _qa_agent.invoke({
        "messages": [{
            "role": "user",
            "content": "\n\n".join(sections),
        }]
    })
    return result["structured_response"]


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

    result = _plugin_agent.invoke({
        "messages": [{
            "role": "user",
            "content": "\n\n".join(sections),
        }]
    })
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

def init_agent():
    fs_backend = FilesystemBackend(
        root_dir="/app/data/",
        virtual_mode=False,
    )

    # Note: create_deep_agent already adds SummarizationMiddleware internally.
    # Adding it here too would cause a duplicate-name error in create_agent
    # (middleware names are checked via __class__.__name__).
    # deepagents' built-in SummarizationMiddleware also persists history to
    # the backend, so there is no need to add our own.
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
    ]

    supervisor = create_deep_agent(
        name="ImageJ_Supervisor",
        tools=[
            # ── subagents as tools (return typed JSON) ──────────────────────
            imagej_coder,
            imagej_debugger,
            python_data_analyst,
            plugin_manager,
            #vlm_judge,
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
            mkdir_copy,
            inspect_csv_header,
            execute_script,
            get_script_info,
            setup_analysis_workspace,
            save_markdown,
            # ── state ledger (persistent project memory) ─────────────────────
            update_state_ledger,
            read_state_ledger,
            set_ledger_metadata,
        ],
        system_prompt=supervisor_prompt,
        subagents=[],
        middleware=supervisor_middleware,
        model=llm_supervisor,
        debug=False,
        backend=fs_backend,
        checkpointer=checkpointer_supervisor,
        skills=["/app/skills/supervisor_phases"],
    )

    return supervisor, checkpointer_supervisor, shared_metrics, shared_bridge, shared_tracker