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
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel
from deepagents.middleware.skills import SkillsMiddleware


from .prompts import (
    imagej_coder_prompt,
    imagej_debugger_prompt,
    build_supervisor_prompt,
    python_analyst_prompt,
    qa_reporter_prompt,
    plugin_manager_prompt,
    librarian_prompt,
    # vlm_judge_prompt,  # VLM disabled
)
from .tools import (
    internet_search, inspect_all_ui_windows, capture_plugin_dialog,
    show_in_imagej_gui, close_imagej_windows,
    rag_retrieve_docs, inspect_java_class,
    inspect_folder_tree,
    smart_file_reader, inspect_csv_header,
    extract_image_metadata, search_fiji_plugins, install_fiji_plugin,
    check_plugin_installed, mkdir_copy, save_script, edit_script, copy_file, execute_script,
    get_script_info, load_script, get_script_history,
    setup_analysis_workspace, save_markdown,
    NarrationReminderMiddleware, PhaseGuardMiddleware,
    update_state_ledger, read_state_ledger, set_ledger_metadata, get_ledger_context,
    check_environment,
    set_dialog_vision_llm,
    get_mcp_tools,
    # capture_ij_window, build_compilation, analyze_image,  # VLM disabled
)
from .tools.learned_memory import (
    register_pending_lesson, core_pitfalls, core_recipes, recall,
    library_add_pitfall, library_add_recipe, library_remove, library_set_core,
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
    # (it cannot run the fix to verify correctness); it populates these and the
    # lesson is committed automatically once execute_script confirms the fix.
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
    # Populated ONLY when this run fixed a previously-failing script. Like the
    # debugger's, the lesson is saved automatically once execute_script confirms
    # the fix is green (no manual save call needed).
    lesson: Optional[str] = None          # one-line imperative rule
    failed_code: Optional[str] = None     # the offending snippet that was replaced
    working_code: Optional[str] = None    # the corrected snippet
    error_type: Optional[str] = None      # Pandas | Plotting | Import | Logic | Path | ...
    class_involved: Optional[str] = None  # main library/object (e.g. "seaborn", "DataFrame")


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
    model=m("openai/gpt-5.4-nano"),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    verbose=True,
    callbacks=[shared_tracker],
)

# Model behind the background Librarian agent (curates the learned-memory wiki off
# the hot path) and the gated recall() deep-search fallback. Kept small/cheap.
llm_curator = ChatOpenAI(
    model=m("openai/gpt-5.4-mini"),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    reasoning_effort="low",
    timeout=30,          # never let a stalled call hang the curator thread or
    max_retries=1,       # the (gated) hot-path deep-recall fallback forever
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
            copy_file,             # seed a new script from any existing file (returns its content)
            save_script,           # full write (from-scratch only)
            edit_script,           # surgical patch — preferred for fixes + param tweaks
            load_script,
            get_script_history,
            smart_file_reader,
            recall,
            inspect_folder_tree,   # lets agent survey /app/skills/ before reading
        ],
        system_prompt=system_prompt,
        response_format=ToolStrategy(schema=ScriptHandoff, handle_errors=True),
        name=name,
        middleware=[
            FilesystemFileSearchMiddleware(
                # Scoped to /app/skills/ — the workflow templates / SKILL.md the coder
                # copies from. Do NOT widen to /app/: /app/data is ~66 GB of images and
                # a broad glob/grep that descends into it stalls for minutes (looks like
                # an infinite loop). The project's own scripts live under the project_root
                # temp dir (outside /app), so widening bought nothing.
                root_path="/app/skills/",
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
    # NOTE: save_script only — NO edit_script/copy_file. Proven (A/B, same model+prompt):
    # edit_script triples the loop rate on this agent's model (gpt-5.2 ~50% vs save_script
    # ~17%). edit_script is a blind patch, so gpt-5.2 re-reads (load_script/inspect) to
    # "verify" and cascades into a loop — even when edit_script echoes the full result and
    # says not to. Analyst scripts are tiny, so a full save_script rewrite costs nothing and
    # the model trusts content it authored itself. edit_script stays on the coder/debugger
    # (gpt-5.3-codex), which trusts its patches and never loops. get_script_info also removed
    # (Supervisor-only verify tool that invited the same post-commit cycle).
    tools=[
        inspect_csv_header,
        save_script,
        load_script,
        get_script_history,
        recall,
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
    llm_analyst,
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

# Background Librarian — curates the learned-memory wiki off the hot path. Fired by
# learned_memory.on_success() in a daemon thread on every verified-green run (the
# task never waits). Acts ONLY through the deterministic library_* tools; its
# operating manual is the skills/learned_memory skill (loaded via SkillsMiddleware).
_librarian_skills_backend = FilesystemBackend(root_dir="/app/", virtual_mode=False)

librarian_agent = create_agent(
    llm_curator,
    tools=[
        library_add_pitfall,
        library_add_recipe,
        library_remove,
        library_set_core,
    ],
    system_prompt=librarian_prompt,
    name="librarian",
    middleware=[
        SkillsMiddleware(
            backend=_librarian_skills_backend,
            sources=["/app/skills/learned_memory/"],  # only the Librarian's own skill
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


# ---------------------------------------------------------------------------
# Recursion cap — bound a runaway tool loop in a stateless subagent
# ---------------------------------------------------------------------------
# LangGraph's default recursion_limit is 1000 super-steps (~500 turns), so a tool
# loop (e.g. an analyst re-verifying after it already committed) can burn credits
# unbounded. We cap every subagent. Legit runs use ~3-8 turns, but a heavy
# supervisor-driven task (recommended-plugin SKILL.md reads + several inspect_java_class
# checks) can reach ~12-16 turns (~24-32 super-steps), so 30 was too tight and could
# clip a legitimate run. 45 (~22 turns) keeps generous headroom while still turning a
# true runaway into a bounded stop. When the cap IS hit, _on_cap below salvages any
# saved script (success=True) so the Supervisor executes it — the artifact is usually
# complete; the agent merely failed to emit a final handoff. So the cap is now a
# graceful "stop and hand back what you have", not a hard failure.
_RECURSION_LIMIT = int(os.environ.get("AGENT_RECURSION_LIMIT", "45"))


def _salvage_or_fail_script(script_path, kind):
    """Build a graceful ScriptHandoff for a subagent that hit the recursion cap.

    If a non-empty script was saved, hand it back as success=True so the Supervisor
    runs it through execute_script (ground truth) instead of discarding it — most caps
    happen AFTER a complete save, while the agent loops on self-verification. If nothing
    was saved, fail cleanly with a retry hint and NO internal 'recursion' wording.
    """
    has_script = bool(script_path) and os.path.isfile(script_path) and os.path.getsize(script_path) > 0
    if has_script:
        return ScriptHandoff(
            script_path=script_path,
            description=(
                f"{kind} produced a script but did not emit a final handoff. It is most "
                "likely complete — execute it to confirm; if it errors, send it to imagej_debugger."
            ),
            success=True,
        )
    return ScriptHandoff(
        script_path="",
        description=f"{kind} could not produce a usable script for this task.",
        success=False,
        error_message="No script was generated — re-issue the request once with a simpler, more explicit task.",
    )


def _snapshot_scripts(directory: str) -> dict:
    """Map {path: mtime} of every .py/.groovy under `directory` (recursive), taken BEFORE
    a subagent runs. Lets the cap salvage tell a script THIS run produced from a stale one
    left by an earlier task — these project folders accumulate many scripts over time."""
    snap = {}
    try:
        for root, _dirs, files in os.walk(directory):
            for fn in files:
                if fn.lower().endswith((".py", ".groovy")):
                    p = os.path.join(root, fn)
                    try:
                        snap[p] = os.path.getmtime(p)
                    except OSError:
                        continue
    except Exception:
        pass
    return snap


def _newest_script_since(directory: str, pre: dict) -> str:
    """The most recently modified .py/.groovy under `directory` that was CREATED or MODIFIED
    after the `pre` snapshot — i.e. produced during THIS run. Returns "" if nothing changed,
    so the caller fails cleanly instead of salvaging (and executing) a stale script from an
    earlier task."""
    newest, newest_mtime = "", -1.0
    try:
        for root, _dirs, files in os.walk(directory):
            for fn in files:
                if not fn.lower().endswith((".py", ".groovy")):
                    continue
                p = os.path.join(root, fn)
                try:
                    mt = os.path.getmtime(p)
                except OSError:
                    continue
                # new file (absent from pre), or existing file whose mtime advanced this run
                if mt > pre.get(p, -1.0) and mt > newest_mtime:
                    newest, newest_mtime = p, mt
    except Exception:
        pass
    return newest


def _run_capped(agent, payload, on_cap):
    """Run a stateless subagent with a hard recursion cap. On hitting the cap (a runaway
    tool loop) return on_cap() — a best-effort handoff — instead of raising/looping forever,
    so the Supervisor still receives a structured result it can act on."""
    try:
        result = stop_signal.SubagentRunner(
            agent.invoke,
            payload,
            config={"recursion_limit": _RECURSION_LIMIT},
        ).run()
        return result["structured_response"]
    except GraphRecursionError:
        return on_cap()


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

    # Always inject the CORE pitfalls (can't-miss floor) + featured recipes. The
    # coder pulls extra task-specific lessons/recipes itself via the recall() tool.
    sections.append(core_pitfalls("Groovy"))
    sections.append(core_recipes("Groovy"))

    agent = _make_coder_agent(model, "imagej_coder", imagej_coder_prompt)

    scripts_dir = os.path.join(project_root, "scripts", "imagej")
    pre_scripts = _snapshot_scripts(scripts_dir)

    def _on_cap():
        path = _newest_script_since(scripts_dir, pre_scripts)
        return _salvage_or_fail_script(path, "The coder")

    return _run_capped(
        agent,
        {"messages": [{"role": "user", "content": "\n\n".join(s for s in sections if s)}]},
        _on_cap,
    )


@tool
def imagej_debugger(script_path: str, error_message: str, project_root: str = "") -> ScriptHandoff:
    """
    Diagnose and repair a failing ImageJ/Fiji Groovy script.

    Args:
        script_path:   Absolute path to the faulty .groovy script.
        error_message: Full error output from execute_script (stack trace, line numbers, etc.).
        project_root:  Absolute path to the project folder.

    Returns a ScriptHandoff with the repaired script_path and a lesson field.
    The lesson on the returned handoff is saved automatically once execute_script
    confirms the repaired script runs green.
    """
    agent = _make_coder_agent(llm_worker, "imagej_debugger", imagej_debugger_prompt)

    sections = [f"FAULTY SCRIPT: {script_path}", f"ERROR:\n{error_message}"]
    if project_root:
        ledger_ctx = get_ledger_context(project_root)
        if ledger_ctx:
            sections.insert(1, f"PROJECT STATE (for context):\n{ledger_ctx}")

    # Always inject the CORE pitfalls floor. The debugger pulls error-specific
    # lessons itself via the recall() tool (keyed on the stack trace).
    sections.append(core_pitfalls("Groovy"))

    def _on_cap():
        return _salvage_or_fail_script(script_path, "The debugger")

    handoff = _run_capped(
        agent,
        {"messages": [{"role": "user", "content": "\n\n".join(s for s in sections if s)}]},
        _on_cap,
    )

    # Buffer the lesson for deterministic capture. The debugger CANNOT verify its
    # own fix; execute_script persists this automatically once the supervisor
    # reruns the repaired script and it passes — no manual save call involved.
    # On a recursion-cap salvage the handoff carries no lesson/working_code, so
    # nothing is recorded — a run that never self-confirmed must not teach.
    try:
        if handoff.lesson and handoff.working_code:
            register_pending_lesson(
                handoff.script_path,
                language="Groovy",
                rule=handoff.lesson,
                failed_code=handoff.failed_code or "",
                working_code=handoff.working_code or "",
                error_type=handoff.error_type or "Logic",
                class_involved=handoff.class_involved or "",
            )
    except Exception:
        pass

    return handoff



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

    # Always inject the CORE pitfalls floor + featured recipes (Python). The
    # analyst pulls extra lessons/recipes itself via the recall() tool.
    sections.append(core_pitfalls("Python"))
    sections.append(core_recipes("Python"))

    pre_scripts = _snapshot_scripts(output_dir)

    def _on_cap():
        path = _newest_script_since(output_dir, pre_scripts)
        has = bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0
        if has:
            return AnalystHandoff(
                script_path=path,
                description=("The analyst produced a script but did not emit a final handoff. "
                            "It is most likely complete — execute it to confirm."),
                success=True,
            )
        return AnalystHandoff(
            script_path="",
            description="The analyst could not produce a usable script for this task.",
            success=False,
            error_message="No script was generated — re-issue the request once with a simpler, more explicit task.",
        )

    handoff = _run_capped(
        _analyst_agent,
        {"messages": [{"role": "user", "content": "\n\n".join(s for s in sections if s)}]},
        _on_cap,
    )

    # Deterministic lesson capture for the Python flow, mirroring imagej_debugger.
    # Populated only when this run fixed a failing script; execute_script commits
    # it once the rerun is green. A recursion-cap salvage carries no lesson, so a
    # run that never self-confirmed records nothing.
    try:
        if handoff.lesson and handoff.working_code:
            register_pending_lesson(
                handoff.script_path,
                language="Python",
                rule=handoff.lesson,
                failed_code=handoff.failed_code or "",
                working_code=handoff.working_code or "",
                error_type=handoff.error_type or "Logic",
                class_involved=handoff.class_involved or "",
            )
    except Exception:
        pass

    return handoff


# ---------------------------------------------------------------------------
# QA enabled flag — toggled at runtime without rebuilding the supervisor graph
# ---------------------------------------------------------------------------

_qa_enabled: bool = False


def set_qa_enabled(enabled: bool) -> None:
    global _qa_enabled
    _qa_enabled = enabled


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
    if not _qa_enabled:
        return QAHandoff(
            checklist_path="",
            minimal_workflow_passed=0,
            minimal_workflow_total=0,
            critical_failures=["QA Agent is disabled — enable it in the panel to run the audit."],
            success=False,
        )

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

def init_agent():
    fs_backend = FilesystemBackend(
        root_dir="/app/data/",
        virtual_mode=False,
    )

    subagent_tools = [
        imagej_coder,
        imagej_debugger,
        python_data_analyst,
        qa_reporter,   # always present; _qa_enabled flag controls execution
        # vlm_judge,  # VLM disabled
    ]

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
            close_imagej_windows,
            rag_retrieve_docs,
            recall,
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
            # ── dynamically-discovered MCP server tools (e.g. in-container ───
            #    napari-mcp). Discovered at startup; the napari viewer itself
            #    opens lazily on the first napari tool call. Discovery failures
            #    are non-fatal (the adapter returns only diagnostics tools).
            *get_mcp_tools(),
            # ── state ledger (persistent project memory) ─────────────────────
            update_state_ledger,
            read_state_ledger,
            set_ledger_metadata,
        ],
        system_prompt=build_supervisor_prompt(enable_qa=True),
        subagents=[],
        middleware=supervisor_middleware,
        model=llm_supervisor,
        debug=False,
        backend=fs_backend,
        checkpointer=checkpointer_supervisor,
        skills=["/app/skills/workflow"],
    )

    return supervisor, checkpointer_supervisor, shared_metrics, shared_bridge, shared_tracker
