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

from .prompts import (
    imagej_coder_prompt,
    imagej_debugger_prompt,
    supervisor_prompt,
    python_analyst_prompt,
    qa_reporter_prompt,
    vlm_judge_prompt,
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



class VLMCheckResult(BaseModel):
    """Result of a single visual check performed by the VLM judge."""
    check_name:    str   # e.g. "segmentation_quality", "scale_bar"
    verdict:       str   # "PASS" | "WARN" | "FAIL"
    observation:   str   # exactly what the vision model reported
    image_path:    Optional[str] = None  # path to the image (or compilation) used for this check
 
 
class VLMHandoff(BaseModel):
    """Returned by vlm_judge."""
    overall_verdict:       str                  # "PASS" | "WARN" | "FAIL"
    summary:               str                  # 2–4 sentence plain-English summary
    checks:                list[VLMCheckResult] # one entry per visual check
    issues_found:          list[str]            # empty on PASS
    recommended_action:    str                  # exact next step for the supervisor
                                                # e.g. "FAIL: send segmenter.groovy to
                                                #  imagej_debugger — nuclei merging detected"
    image_paths_inspected: list[str]            # all images / compilations analysed
    pipeline_step:         str                  # echoed from the task for logging
    success:               bool                 # False only if the agent itself crashed
    error_message:         Optional[str] = None


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

_vlm_agent = create_agent(
    llm_vlm,
    tools=[
        capture_ij_window,   # save named open IJ window as PNG via PyImageJ
        build_compilation,   # fuse multiple images into a labelled side-by-side panel
        analyze_image,       # send image/compilation to vision LLM, return analysis
    ],
    system_prompt=vlm_judge_prompt,
    response_format=VLMHandoff,
    name="vlm_judge",
)



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

    model = llm_worker  # ← codex is best for code generation, even for Python analyst tasks

    agent = _make_coder_agent(model, "imagej_coder", imagej_coder_prompt)

    result = agent.invoke({
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
    agent = _make_coder_agent(llm_worker, "imagej_debugger", imagej_debugger_prompt)

    result = agent.invoke({
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
def vlm_judge(
    task:            str,
    pipeline_step:   str,
    expected_output: str,
    image_source:    str | list[str],
    labels:          Optional[list[str]] = None,
) -> VLMHandoff:
    """
    Visually inspect one or more images using a vision LLM and return a structured verdict.
 
    ⚠️  COST NOTICE — vision API calls are significantly more expensive than text:
        Call vlm_judge selectively — see WHEN TO CALL below.
 
    IMAGE SOURCE — two modes:
        Single string:  open IJ window title  → captured via IJ API then analysed.
                        absolute file path    → analysed directly, no capture.
        List of strings: multiple window titles and/or file paths
                        → automatically fused into a side-by-side compilation panel
                          before analysis. Much more effective for comparisons than
                          sending images separately (VLM gets direct spatial reference).
 
    Args:
        task:            What to inspect and what criteria to judge against.
        pipeline_step:   Short stage identifier for traceability, e.g. "segmentation".
        expected_output: What a correct result looks like — used as pass/fail benchmark.
        image_source:    Window title, file path, or list of either.
                         Window titles: e.g. "MAX_DAPI.tif", "mask_nuclei.tif"
                         File paths:    e.g. "/app/data/projects/study/processed/mask.tif"
        labels:          Optional panel captions for compilations, e.g. ["Original", "Mask"].
                         Ignored for single images.
 
    Returns VLMHandoff with overall_verdict ("PASS"/"WARN"/"FAIL"), per-check breakdown,
    issues_found, and recommended_action.
 
    WHEN TO CALL (be selective — each call costs money):
        ✅ Sample verification (Phase 4b) — once per pipeline, on the verification image.
        ✅ Segmentation / threshold output — use compilation with original + result.
        ✅ When a script exits cleanly but output is suspected to be wrong.
        ✅ Final QA before qa_reporter — scale bar and output image check.
        ✅ When the user reports a visual problem.
        ❌ Do NOT call after every batch script execution.
        ❌ Do NOT call to list open windows — use inspect_all_ui_windows.
        ❌ Do NOT call to read CSV or log output — use inspect_csv_header / smart_file_reader.
 
    ACTING ON THE VERDICT:
        PASS → proceed. Show summary to user at sample verification.
        WARN → continue pipeline; report issues in Phase 5 summary.
        FAIL → stop. Send script path + issues_found to imagej_debugger. AFTER asking the user for visual verfification. 
               Re-run and call vlm_judge again after the fix.
    """
    sources = image_source if isinstance(image_source, list) else [image_source]
 
    content = (
        f"PIPELINE STEP: {pipeline_step}\n"
        f"IMAGE SOURCE(S): {sources}\n"
        f"LABELS: {labels or []}\n"
        f"EXPECTED OUTPUT: {expected_output}\n\n"
        f"TASK: {task}"
    )
 
    result = _vlm_agent.invoke({"messages": [{"role": "user", "content": content}]})
    return result["structured_response"]

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
    ]

    supervisor = create_deep_agent(
        name="ImageJ_Supervisor",
        tools=[
            # ── subagents as tools (return typed JSON) ──────────────────────
            imagej_coder,
            imagej_debugger,
            python_data_analyst,
            vlm_judge,
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
        subagents=[],
        middleware=supervisor_middleware,
        model=llm_supervisor,
        debug=False,
        backend=fs_backend,
        checkpointer=checkpointer_supervisor,
        skills=["/app/skills/"],
    )

    return supervisor, checkpointer_supervisor, shared_metrics, shared_bridge, shared_tracker