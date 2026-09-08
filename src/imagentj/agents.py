import logging
import os
import sqlite3
from typing import Literal, Optional

import httpx
from openai import OpenAIError

from . import stop_signal
from . import agent_watchdog
from . import config
from .safety_filter import BIO_REFUSAL_HINT, is_bio_refusal

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ContextEditingMiddleware,
    ClearToolUsesEdit,
    FilesystemFileSearchMiddleware,
)
from langchain.agents.structured_output import ProviderStrategy, ToolStrategy
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, ConfigDict
from deepagents.middleware.skills import SkillsMiddleware

log = logging.getLogger("imagentj")


from .prompts import (
    imagej_coder_prompt,
    imagej_debugger_prompt,
    build_supervisor_prompt,
    build_quick_prompt,
    build_tutor_prompt,
    python_analyst_prompt,
    qa_reporter_prompt,
    plugin_manager_prompt,
    librarian_prompt,
    vlm_judge_prompt,
)
from .tools import (
    internet_search, inspect_all_ui_windows, capture_plugin_dialog, estimate_cellpose_diameter_manual, estimate_cellpose_diameter_auto,
    merge_cellpose_diameter_runs,
    show_in_imagej_gui, close_imagej_windows,
    rag_retrieve_docs, recall_concepts, inspect_java_class,
    inspect_folder_tree,
    smart_file_reader, inspect_csv_header, summarize_deliverables,
    extract_image_metadata, search_fiji_plugins, install_fiji_plugin,
    check_plugin_installed, mkdir_copy, save_script, edit_script, copy_file, execute_script,
    get_script_info, load_script, get_script_history,
    setup_analysis_workspace, save_markdown,
    NarrationReminderMiddleware, PhaseGuardMiddleware, ToolOutputLimitMiddleware,
    VisionOptionMiddleware, BioRefusalRetryMiddleware,
    update_state_ledger, read_state_ledger, set_ledger_metadata, get_ledger_context,
    check_environment,
    set_dialog_vision_llm,
    get_mcp_tools,
    capture_ij_window, prepare_image_source_for_vlm,
    build_mask_overlay, build_compilation, analyze_image,
    set_vision_llm,
    # multi-mode: tutor tools + mode routing
    list_curriculum, load_chapter, load_track, show_figure, list_sample_images,
    list_practicals, reveal_solution, update_course_progress, set_course_plan, set_mode,
    ModeMiddleware, ModeSpec,
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

def _strict_json_schema(schema: dict) -> None:
    """Make a handoff model's emitted JSON Schema valid for OpenAI strict mode.

    Strict mode demands `additionalProperties: false` and that `required` name
    every property. Pydantic will not produce that on its own: a field only lands
    in `required` when it has no default, and giving up defaults means an
    incomplete reply raises a ValidationError instead of degrading.

    This is not cosmetic. Without `strict: true` the provider treats the schema as
    a hint, and the model answers with the SCHEMA rather than an instance —
    observed on the first live ProviderStrategy call for ScriptHandoff:

        {"properties": {"script_path": {...}, ...}}   ->  3 validation errors,
        script_path / description / success all "Field required".

    So the defaults stay (parsing stays forgiving) and the strict requirements are
    stamped onto the schema here. Optional fields are already `x | None`, so the
    model can satisfy `required` by sending null.
    """
    schema["additionalProperties"] = False
    schema["required"] = list((schema.get("properties") or {}).keys())


class ScriptHandoff(BaseModel):
    """Returned by imagej_coder and imagej_debugger."""
    model_config = ConfigDict(json_schema_extra=_strict_json_schema)
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
    model_config = ConfigDict(json_schema_extra=_strict_json_schema)
    script_path: str
    description: str
    stage: str = "unknown"              # "measurement" | "statistics" | "plotting"
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
    # Scientific plausibility of the DELIVERABLE, measured on disk rather than read
    # from the ledger. Defaulted so an older/partial handoff still validates.
    plausibility_verdict: str = "NOT MEASURED"
    measured_median: float = 0.0
    success: bool


class PipelineStepRecommendation(BaseModel):
    """One step of a multi-step pipeline, each routed to the best software backend.

    A pipeline can mix backends freely: e.g. register with a Fiji plugin (imagej_coder),
    segment with micro_sam in napari (napari) or as a batch script (python_data_analyst),
    then measure with scikit-image/cp_measure (python_data_analyst).
    """
    step_name: str                                  # e.g. "registration", "segmentation", "measurement"
    recommended_tool: Optional[str] = None          # concrete plugin/package/model, e.g. "TurboReg", "StarDist", "micro_sam (vit_b_lm)", "scikit-image"
    backend: str = "imagej_coder"                   # executor: "imagej_coder" | "python_data_analyst" | "napari" | "core"
    env: Optional[str] = None                       # for python_data_analyst steps: the `# imagentj-env` value ("main", "napari-mcp", "brainglobe")
    skill_folder: Optional[str] = None              # skill docs the executor should read (relative to /app/skills/)
    reasoning: str = ""                             # why this tool/backend for this step


class PluginRecommendation(BaseModel):
    """Returned by plugin_manager.

    Two shapes, not mutually exclusive:
      • Single-tool recommendation — the legacy fields (recommended_plugin, skill_folder,
        installation_status, ...) describe the ONE best tool for a single-operation task.
      • Multi-step pipeline — `pipeline_steps` routes each step to its own backend/tool.
        When populated, the single-tool fields describe the PRIMARY/most-critical step so
        older consumers still get a sensible pointer.
    """
    recommended_plugin: Optional[str] = None
    recommended_backend: str = "imagej_coder"       # backend for the primary recommendation
    recommended_env: Optional[str] = None           # env for the primary recommendation when backend == python_data_analyst
    is_installed: bool = False
    needs_restart: bool = False
    skill_folder: Optional[str] = None
    plugin_capabilities: str = ""
    relevance_reasoning: str = ""
    alternative_plugins: list[str] = []
    installation_status: str = "not_needed"
    pipeline_steps: list[PipelineStepRecommendation] = []   # per-step routing for multi-step pipelines; empty for single-tool tasks
    success: bool = True


class VLMCheckResult(BaseModel):
    """One evidence-backed visual observation returned by the VLM judge."""
    check_name: str
    verdict: Literal["PASS", "WARN", "FAIL", "INFO"]
    observation: str
    image_path: Optional[str] = None


class VLMHandoff(BaseModel):
    """Typed handoff from the stateless VLM judge to the supervisor."""
    overall_verdict: Literal["PASS", "WARN", "FAIL", "INFO"]
    summary: str
    checks: list[VLMCheckResult] = []
    issues_found: list[str] = []
    recommended_action: str
    image_paths_inspected: list[str] = []
    pipeline_step: str
    success: bool
    error_message: Optional[str] = None


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


def _agent_reasoning_kwargs(reasoning_effort: Optional[str] = None) -> dict:
    """Return endpoint-compatible options for tool-using text agents.

    OpenRouter currently serves these models through Chat Completions, while in OpenAI api endpoint,
    reasoning plus function tools is rejected starting from gpt-5.4. Direct OpenAI calls use
    the Responses API instead, so they can retain explicit reasoning effort.
    Refer to: https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454/2
    """
    options = {}
    if use_openrouter:
        if reasoning_effort is not None:
            options["reasoning_effort"] = reasoning_effort
        return options

    options["use_responses_api"] = True
    if reasoning_effort is not None:
        options["reasoning"] = {"effort": reasoning_effort}
    return options


# Every LLM client gets a read timeout and a retry.
#
# Without one, a provider that returns 200 OK headers and then stalls mid-body
# leaves httpx blocked in `ssl.read()` FOREVER — the socket never errors, so the
# agent thread simply stops and the whole run wedges with no traceback and no
# tokens billed. Observed 2026-08-07: all three benchmark containers froze at the
# same second on a single OpenRouter body-stall and never recovered.
#
# The curator and the VLM judge already carried timeouts for exactly this reason;
# the four clients that do the real work did not. These are deliberately generous
# — a long reasoning turn on a big context is legitimately slow — but finite.
#
# 240 rather than 300, and the 60 s of daylight is the entire point: it must be
# LESS than agent_watchdog.STALL_SECONDS. At 300 the two raced and the watchdog
# usually won, which is the bad outcome — a watchdog kill destroys the whole
# subagent turn and everything it had accumulated, whereas an httpx timeout is
# retried in place by _LLM_MAX_RETRIES and the turn continues.
#
# Nothing legitimate is at risk here. Measured across 419 unambiguously-paired
# requests in two benchmark runs, the slowest healthy response was 78 s and NOT
# ONE exceeded 90 s; these responses are non-streaming, so a hung stream delivers
# no bytes at all and trips the read timeout cleanly. The distribution is bimodal
# — a request either answers inside ~80 s or never answers at all — so a 240 s
# deadline can only ever fire on a dead stream. Re-issuing works: all 13 stalls
# observed so far returned 200 OK on the very next attempt, in 1.4-2.5 s.
_LLM_TIMEOUT_S = float(os.environ.get("IMAGENTJ_LLM_TIMEOUT", "240"))
_LLM_MAX_RETRIES = int(os.environ.get("IMAGENTJ_LLM_MAX_RETRIES", "2"))

# ---------------------------------------------------------------------------
# Thinking budget, and an available-but-unused determinism knob.
#
# NOTE on `temperature=0.` below: it is NOT a determinism guarantee on every
# backend. It is absent from gpt-5.6-luna's supported_parameters on OpenRouter,
# so that model silently discards it. Do not read it as one.
#
# `seed` IS supported on that model and would make sampling reproducible, but it
# is OFF by default by choice: pinning a seed makes a wrong run reproducibly
# wrong and hides genuine run-to-run variability that a scientific tool should
# expose rather than mask. Available via IMAGENTJ_LLM_SEED=<int> for anyone
# deliberately chasing reproducibility; unset means no seed is sent at all.
#
# Both knobs are env-overridable so a run can be A/B'd without touching this file:
#   IMAGENTJ_LLM_SEED=1234         → opt in to a fixed seed (default: none)
#   IMAGENTJ_REASONING_EFFORT=high → raise the thinking budget for the roles
#                                    that make judgement calls
#
# gpt-5.6-luna-pro is the SAME model as gpt-5.6-luna served with
# reasoning.mode=pro, so pinning it to reasoning_effort="low" — as this file did
# for every role — works against the only thing that distinguishes it.
_LLM_SEED_RAW = os.environ.get("IMAGENTJ_LLM_SEED", "").strip()
_LLM_SEED: Optional[int] = int(_LLM_SEED_RAW) if _LLM_SEED_RAW not in ("", "0") else None

# Effort for the roles that plan, judge and write code. The nano fast-path stays
# unset (it backs the watchdog verdict, where latency delays hang detection).
_REASONING_EFFORT = os.environ.get("IMAGENTJ_REASONING_EFFORT", "medium").strip() or None


def _seed_kwargs() -> dict:
    """`seed` only when explicitly opted into; otherwise send nothing."""
    return {"seed": _LLM_SEED} if _LLM_SEED is not None else {}

llm_supervisor = ChatOpenAI(
    model=m(config.model_for("supervisor", "openai/gpt-5.4")),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    **_agent_reasoning_kwargs(config.reasoning_effort_for("supervisor", _REASONING_EFFORT)),
    **_seed_kwargs(),
    timeout=_LLM_TIMEOUT_S,
    max_retries=_LLM_MAX_RETRIES,
    verbose=True,
    callbacks=[shared_tracker],
)

llm_worker = ChatOpenAI(
    model=m(config.model_for("worker", "openai/gpt-5.3-codex")),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    **_agent_reasoning_kwargs(config.reasoning_effort_for("worker", _REASONING_EFFORT)),
    **_seed_kwargs(),
    timeout=_LLM_TIMEOUT_S,
    max_retries=_LLM_MAX_RETRIES,
    verbose=True,
    callbacks=[shared_tracker],
)

llm_analyst = ChatOpenAI(
    model=m(config.model_for("analyst", "openai/gpt-5.3-codex")),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    **_agent_reasoning_kwargs(config.reasoning_effort_for("analyst", _REASONING_EFFORT)),
    **_seed_kwargs(),
    timeout=_LLM_TIMEOUT_S,
    max_retries=_LLM_MAX_RETRIES,
    verbose=True,
    callbacks=[shared_tracker],
)

llm_nano = ChatOpenAI(
    model=m(config.model_for("nano", "openai/gpt-5.4-nano")),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    # Effort deliberately left unset: this backs the watchdog verdict, where extra
    # deliberation directly delays hang detection. Seeded like the rest, though —
    # a watchdog that reaches a different verdict on identical evidence is worse
    # than one that is merely strict.
    **_agent_reasoning_kwargs(config.reasoning_effort_for("nano", None)),
    **_seed_kwargs(),
    # Shorter: this backs the watchdogs and the fast path, where a slow call is
    # worse than no call — a watchdog that hangs supervises nothing.
    timeout=90,
    max_retries=_LLM_MAX_RETRIES,
    verbose=True,
    callbacks=[shared_tracker],
)

# Model behind the background Librarian agent (curates the learned-memory wiki off
# the hot path) and the gated recall() deep-search fallback. Kept small/cheap.
llm_curator = ChatOpenAI(
    model=m(config.model_for("curator", "openai/gpt-5.4-mini")),
    api_key=api_key,
    base_url=base_url,
    temperature=0.,
    # Kept at "low": the curator is on a 30 s budget and does retrieval, not
    # judgement — extra thinking here buys nothing and risks the timeout.
    **_agent_reasoning_kwargs(config.reasoning_effort_for("curator", "low")),
    **_seed_kwargs(),
    timeout=30,          # never let a stalled call hang the curator thread or
    max_retries=1,       # the (gated) hot-path deep-recall fallback forever
    verbose=True,
    callbacks=[shared_tracker],
)

# Prefer Gemini through OpenRouter when both providers are configured. For an
# OpenAI-only installation, GPT-5.6 reasoning plus function tools belongs on
# the Responses API; keeping this explicit avoids Chat Completions'
# reasoning/tool compatibility limit.
if open_router_key:
    llm_vlm = ChatOpenAI(
        model=config.model_for("vlm", "google/gemini-3.5-flash"),
        api_key=open_router_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.,
        timeout=90,
        max_retries=1,
        verbose=True,
        callbacks=[shared_tracker],
    )
elif openai_key:
    # OpenAI direct cannot serve a non-openai/ model, so drop the prefix and
    # ignore a cross-provider value (e.g. the default google/ VLM model).
    _vlm_openai = config.model_for("vlm", "gpt-5.6-luna")
    if _vlm_openai.startswith("openai/"):
        _vlm_openai = _vlm_openai.split("/", 1)[1]
    elif "/" in _vlm_openai:
        _vlm_openai = "gpt-5.6-luna"
    llm_vlm = ChatOpenAI(
        model=_vlm_openai,
        api_key=openai_key,
        temperature=0.,
        **_agent_reasoning_kwargs(config.reasoning_effort_for("vlm", "high")),
        timeout=90,
        max_retries=1,
        verbose=True,
        callbacks=[shared_tracker],
    )
else:
    llm_vlm = None

# Start supervising script runs. Imported here rather than in run_control so the
# watchdog's lazy `from .agents import llm_nano` can never race module init.
from . import watchdog as _watchdog
_watchdog.install()

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
        # ProviderStrategy, not ToolStrategy — see the note on _analyst_agent.
        # ToolStrategy forces tool_choice="required" on every turn, and every
        # watchdog kill in the v3 benchmark run traced back to an agent built here
        # or by the analyst. ProviderStrategy binds no tool_choice and sends the
        # schema as a native response_format instead.
        #
        # strict=True is load-bearing, not belt-and-braces: without it the provider
        # treats the schema as advisory and the model replies with the schema
        # itself ({"properties": {...}}), which fails to parse. See
        # _strict_json_schema.
        response_format=ProviderStrategy(schema=ScriptHandoff, strict=True),
        name=name,
        middleware=[
            ToolOutputLimitMiddleware(),
            agent_watchdog.middleware(),
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
            # Innermost — see BioRefusalRetryMiddleware. Must stay last.
            BioRefusalRetryMiddleware(),
        ],
    )


# Python skills backend — scoped to /app/skills/python/ so the analyst sees only the
# Python library + standards skills, not the ~26 Groovy/Fiji plugin doc skills.
# SkillsMiddleware's scan is one level deep (it looks for <source>/<skill>/SKILL.md),
# so /app/skills/python/ is invisible to the plugin_manager's /app/skills/ scan and
# vice versa — the two skill sets stay cleanly separated.
_python_skills_backend = FilesystemBackend(
    root_dir="/app/",
    virtual_mode=False,
)

_analyst_agent = create_agent(
    # Codex model (gpt-5.3-codex) — same one the coder/debugger run on. The analyst
    # was previously on gpt-5.2, where an A/B test showed edit_script tripled the tool-loop
    # rate (~50% vs ~17% for save_script): gpt-5.2 treated a surgical patch as a blind write
    # and re-read (load_script/inspect) to "verify", cascading into a loop. That was a gpt-5.2
    # pathology, not an edit_script one — the codex model trusts its own patches and never
    # loops, which is exactly why edit_script has always been safe on the coder/debugger.
    # Moving the analyst onto codex removes that pathology, so edit_script + copy_file are
    # now enabled here too (surgical fixes/param tweaks + seeding a script from a template),
    # mirroring the coder. (get_script_info stays off — Supervisor-only verify tool.)
    llm_worker,
    tools=[
        inspect_csv_header,
        copy_file,             # seed a new script from any existing file (returns its content)
        save_script,           # full write (from-scratch only)
        edit_script,           # surgical patch — preferred for fixes + param tweaks
        load_script,
        get_script_history,
        recall,
        # SkillsMiddleware lists skill metadata and tells the agent to read the full
        # SKILL.md on demand; it ships no reader of its own, so these two supply it.
        smart_file_reader,
        inspect_folder_tree,
    ],
    system_prompt=python_analyst_prompt,
    # ProviderStrategy for the same reason as plugin_manager: ToolStrategy binds
    # tool_choice="required" on every turn (langchain factory.py, "Force tool use
    # if we have structured output tools"), and that forcing is what stalls the
    # agent — the request gets HTTP 200 headers and then no body at all, for
    # minutes, until the watchdog kills it.
    #
    # This agent could not take the fix until `edits` was typed. ProviderStrategy
    # also binds the real tools in strict mode, and `edits: Optional[list]` emitted
    # `{"items": {}}`, which OpenAI rejects. A schema audit of all nine tools bound
    # here found that this was the only hard blocker.
    response_format=ProviderStrategy(schema=AnalystHandoff, strict=True),
    name="python_data_analyst",
    middleware=[
        ToolOutputLimitMiddleware(),
        SkillsMiddleware(
            backend=_python_skills_backend,
            # /app/skills/napari/ is included so the analyst can read the micro_sam skill and
            # run its automatic-segmentation script (with `# imagentj-env: napari-mcp`). The
            # napari_general skill also lives there but is routing guidance, not a Python API.
            sources=["/app/skills/python/", "/app/skills/napari/"],
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
        # Innermost — see BioRefusalRetryMiddleware. Must stay last, i.e. after
        # SkillsMiddleware, so a retry is not re-injected with the catalogue.
        BioRefusalRetryMiddleware(),
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
        summarize_deliverables,
        load_script,
    ],
    system_prompt=qa_reporter_prompt,
    response_format=ToolStrategy(schema=QAHandoff, handle_errors=True),
    name="qa_reporter",
    # Feeds the agent watchdog its tool-call history — this is the agent whose
    # write→re-read loop went unbounded for 34 minutes.
    middleware=[ToolOutputLimitMiddleware(), agent_watchdog.middleware()],
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
    # ProviderStrategy explicitly, NOT a bare `response_format=PluginRecommendation`.
    #
    # A bare schema goes through AutoStrategy, whose _supports_provider_strategy()
    # returns False for "openai/gpt-5.6-luna" (no model profile, and the fallback
    # list stops at gpt-5.5). It then silently degrades to ToolStrategy, which sets
    # tool_choice="required" on EVERY turn.
    #
    # That forcing is what wedged this agent. Once it has gathered its evidence the
    # model wants to answer in prose; compelled to emit a tool call anyway, the
    # upstream spins and returns HTTP 200 with finish_reason="error", cost 0 and no
    # tool_calls — so there is no structured_response and the loop pays again.
    # Measured on the real payload: tool_choice="required" gave 452 s / >14 min
    # non-answers, while tool_choice="auto" on the identical request returned in
    # 12-22 s every time. Stall rates track the forcing exactly — plugin_manager
    # 13/56, python_data_analyst 8.6%, and the supervisor (no structured output,
    # hence no forced call) 0/402.
    #
    # ProviderStrategy binds no tool_choice and sends the schema as response_format
    # instead. Verified on the wire: tool_choice absent, 5 real tools instead of 6,
    # and json_schema with strict=false — so the nested pipeline_steps model needs
    # no `extra="forbid"` rewrite to be accepted.
    response_format=ProviderStrategy(schema=PluginRecommendation),
    name="plugin_manager",
    middleware=[
        ToolOutputLimitMiddleware(),
        SkillsMiddleware(
            backend=_plugin_skills_backend,
            # Three skill families, so the manager can route each pipeline step to the
            # best backend — a Fiji plugin, a Python package, or a napari plugin:
            #   /app/skills/         → Fiji/ImageJ plugin skills (*_documentation)  → imagej_coder
            #   /app/skills/python/  → Python library skills (scikit-image, cp_measure, …) → python_data_analyst
            #   /app/skills/napari/  → napari plugin skills (micro_sam, napari_general) → napari / python_data_analyst
            # SkillsMiddleware scans one level deep (<source>/<skill>/SKILL.md), so these
            # three sources stay cleanly separated and none shadows another.
            sources=["/app/skills/", "/app/skills/python/", "/app/skills/napari/"],
        ),
        # Innermost — see BioRefusalRetryMiddleware. Must stay last, i.e. after
        # SkillsMiddleware. This is the agent the benchmark evidence caught being
        # refused: refused_debug.log's traceback lands one frame below
        # deepagents' skills.py wrap_model_call inside plugin_manager.
        BioRefusalRetryMiddleware(),
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
        ToolOutputLimitMiddleware(),
        SkillsMiddleware(
            backend=_librarian_skills_backend,
            sources=["/app/skills/learned_memory/"],  # only the Librarian's own skill
        ),
    ],
)

_vlm_agent = (
    create_agent(
        llm_vlm,
        tools=[
            capture_ij_window,   # save a named open IJ window as PNG
            build_mask_overlay,  # alpha-overlay a mask on the source image
            build_compilation,   # build a labelled comparison panel
            analyze_image,       # send one image/panel to the vision model
        ],
        system_prompt=vlm_judge_prompt,
        response_format=ToolStrategy(schema=VLMHandoff, handle_errors=True),
        name="vlm_judge",
        middleware=[ToolOutputLimitMiddleware(), agent_watchdog.middleware()],
    )
    if llm_vlm is not None
    else None
)


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


# The failure handoffs do not share one prose field: ScriptHandoff/AnalystHandoff/
# VLMHandoff carry `error_message`, PluginRecommendation carries
# `relevance_reasoning` and no `error_message` at all. Writing to a field a model
# does not declare raises in pydantic v2, so an unconditional
# `setattr(handoff, "error_message", ...)` silently dropped the note on
# plugin_manager — the one subagent the benchmark evidence shows being refused.
_HANDOFF_NOTE_FIELDS = ("error_message", "relevance_reasoning", "reasoning")


def _annotate_handoff(handoff, note: str):
    """Append *note* to whichever prose field this handoff type declares."""
    declared = getattr(type(handoff), "model_fields", {}) or {}
    for field in _HANDOFF_NOTE_FIELDS:
        if field not in declared:
            continue
        try:
            existing = getattr(handoff, field, None) or ""
            setattr(handoff, field, (existing + " " + note).strip())
        except Exception:
            log.warning("could not annotate %s.%s with the refusal note",
                        type(handoff).__name__, field)
        return handoff
    log.warning("%s declares no field to carry the refusal note",
                type(handoff).__name__)
    return handoff


def _run_capped(agent, payload, on_cap, name: str = "subagent"):
    """Run a stateless subagent under BOTH bounds, returning on_cap() if either trips.

    1. `recursion_limit` — a hard ceiling on super-steps.
    2. the agent watchdog — kills a spinning loop (identical tool calls), a hung
       tool call (no activity for STALL_SECONDS), or an LLM-judged runaway.

    The recursion cap alone is not enough: it only fires once the agent has burned
    ~22 turns, and it cannot fire at all while a single tool call is blocked. The
    watchdog covers both gaps. Either way the Supervisor still receives a
    structured result it can act on.

    The same guarantee has to hold when the agent comes back WITHOUT a structured
    response. That happens for reasons entirely outside this process — the model
    emits prose instead of the schema tool call, or the connection drops mid-stream
    (`httpx.RemoteProtocolError: peer closed connection without sending complete
    message body`). A bare `result["structured_response"]` turned that into a
    KeyError which escaped this function, propagated through the supervisor's tool
    node, and ended the whole session with "unhandled agent error" — losing a run
    whose deliverables were already complete on disk. Degrade to on_cap() instead:
    one subagent call fails, the pipeline continues.
    """
    handle = agent_watchdog.register(name)
    try:
        # No bio-refusal retry here on purpose. BioRefusalRetryMiddleware already
        # reformulates and retries at the model boundary, where it can actually
        # drop the injected skill catalogue the provider objected to. Retrying at
        # this level would instead replay the whole subagent — every tool call
        # again — around a payload whose only reformulation is a rewrite of the
        # user's own wording. Reaching the handler below means the middleware
        # exhausted its ladder, so all that is left is to degrade cleanly.
        result = stop_signal.SubagentRunner(
            agent.invoke,
            payload,
            config={"recursion_limit": _RECURSION_LIMIT},
            watchdog=handle,
        ).run()
        structured = (result or {}).get("structured_response")
        if structured is None:
            log.warning(
                "%s returned no structured_response (model emitted prose, or the "
                "stream was cut) — degrading to a failure handoff so the pipeline "
                "continues.", name
            )
            return on_cap()
        return structured
    except GraphRecursionError:
        return on_cap()
    except agent_watchdog.AgentAborted:
        return on_cap()
    except (httpx.HTTPError, OpenAIError) as exc:
        # Transport / provider failure. The science already on disk must not be lost
        # because one call died in the socket.
        log.warning("%s failed at the transport layer (%s: %s) — degrading to a "
                    "failure handoff.", name, type(exc).__name__, exc)
        return on_cap()
    except Exception as exc:
        if is_bio_refusal(exc):
            # All reformulation attempts were refused. Hand the supervisor an
            # explicit explanation — this is a different signal from a timeout
            # or a watchdog abort, and the supervisor must not burn time
            # re-running the same wording.
            log.warning(
                "%s refused by provider biological-risk filter after every "
                "reformulation attempt — degrading to failure handoff.", name,
            )
            return _annotate_handoff(on_cap(), BIO_REFUSAL_HINT)
        # Nested tool validation/runtime failures must stay local to the subagent.
        # One observed example is a provider emitting a content-block list for a
        # regex ``pattern`` argument; FilesystemFileSearchMiddleware then raises
        # ``TypeError: expected string or bytes-like object, got 'list'``. Letting
        # that escape aborts the entire supervisor and discards otherwise valid
        # image deliverables. Return the same typed failure handoff used for a
        # watchdog/transport failure so the supervisor can debug, retry, or choose
        # another backend. BaseException subclasses (KeyboardInterrupt,
        # SystemExit) deliberately remain uncaught.
        log.exception(
            "%s failed inside a nested model/tool call (%s: %s) — degrading "
            "to a failure handoff so the pipeline continues.",
            name,
            type(exc).__name__,
            exc,
        )
        return on_cap()
    finally:
        agent_watchdog.release(handle)


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
        name="imagej_coder",
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
        name="imagej_debugger",
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
def python_data_analyst(task: str, input_path: str, output_dir: str, project_root: str) -> AnalystHandoff:
    """
    The Python allrounder: measure images, run statistics, or generate publication figures.

    Call ONCE PER STAGE, never combined:
      Stage 0 (measurement): task describes segmentation / feature extraction from an image
                             or label mask (scikit-image, cp_measure, scikit-learn,
                             brainglobe). Outputs a per-object CSV.
      Stage 1 (statistics):  task describes hypothesis testing. Returns stats_csv_path.
      Stage 2 (plotting):    task describes plot types. Call only after Stage 1 CSV exists.

    Args:
        task:         What to do — the measurement to extract, the hypothesis and groups to
                      compare, or the plot types.
        input_path:   Absolute path to the input for THIS stage: an image or label mask for
                      Stage 0, a raw measurement CSV for Stage 1, Statistics_Results.csv for
                      Stage 2.
        output_dir:   Absolute path to the directory where scripts and outputs should be saved.
        project_root: Absolute path to the project folder.

    Returns an AnalystHandoff with script_path, outputs, stats_csv_path or figure_paths.
    """
    sections = [
        f"INPUT PATH: {input_path}",
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
        name="python_data_analyst",
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

# Last plausibility verdict from qa_reporter, so the run-level outcome can reflect
# whether the SCIENCE passed rather than only whether the process avoided crashing.
# Without this the benchmark's result.json reported success=true on a deliverable the
# QA agent had just measured as 65x too small: the verdict existed, but stayed trapped
# inside the handoff and never reached the file an evaluator reads.
LAST_QA_VERDICT: dict = {}


def _record_qa_verdict(handoff) -> None:
    global LAST_QA_VERDICT
    try:
        LAST_QA_VERDICT = {
            "plausibility_verdict": getattr(handoff, "plausibility_verdict", "NOT MEASURED"),
            "measured_median": float(getattr(handoff, "measured_median", 0.0) or 0.0),
            "qa_success": bool(getattr(handoff, "success", False)),
            "critical_failures": list(getattr(handoff, "critical_failures", []) or []),
        }
    except Exception:                                     # never break QA over telemetry
        LAST_QA_VERDICT = {}


def set_qa_enabled(enabled: bool) -> None:
    global _qa_enabled
    _qa_enabled = enabled


@tool
def qa_reporter(project_root: str, user_request: str = "", deliverable_dir: str = "") -> QAHandoff:
    """
    Audit the completed project folder and generate QA_Checklist_Report.md.

    Call once at the end of every project after all scripts have run successfully.

    Args:
        project_root: Absolute path to the project root folder. The reporter reads all
                      scripts, CSVs, and images to evaluate against workflow and image
                      publishing standards.
        user_request: The user's ORIGINAL request, quoted verbatim — especially any
                      stated quantity ("up to 2,000 cells per image", "~50 nuclei").
                      The reporter measures the delivered files against this number.
                      Omitting it disables the plausibility check, so always pass it.
        deliverable_dir: Absolute path where the final deliverables were written, if it
                      differs from project_root (e.g. '/benchmark/output').

    Returns a QAHandoff with checklist_path, pass/fail counts, critical_failures, and a
    plausibility_verdict measured from the files on disk. Relay critical_failures and any
    FAIL verdict to the user verbatim — a FAIL means the result is wrong, not just undocumented.
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
    if deliverable_dir:
        sections.append(f"DELIVERABLE DIRECTORY (measure this one): {deliverable_dir}")
    if user_request:
        # The stated quantities live here and nowhere else — the ledger's
        # scientific_goal is a paraphrase that drops the numbers.
        sections.append(
            "ORIGINAL USER REQUEST (verbatim — extract any stated quantity from it "
            "and pass it to summarize_deliverables as expected_per_file):\n"
            f"{user_request}"
        )
    # Inject the full ledger — it contains the workflow summary, all parameters,
    # all scripts, all outputs. This is exactly what the QA agent needs to audit.
    ledger_ctx = get_ledger_context(project_root)
    if ledger_ctx:
        sections.append(f"WORKFLOW SUMMARY (from state ledger — use as primary reference):\n{ledger_ctx}")

    # Bounded like every other subagent. This call previously ran uncapped and
    # unsupervised: a benchmark run had the reporter write QA_Checklist_Report.md
    # and read it back 57 times over 34 minutes without ever emitting its handoff,
    # and nothing stopped it. On either bound tripping we hand back a partial
    # report rather than failing the whole pipeline — by this point the science
    # is already finished and saved.
    def _on_cap() -> QAHandoff:
        checklist = os.path.join(project_root, "QA_Checklist_Report.md")
        return QAHandoff(
            checklist_path=checklist if os.path.exists(checklist) else "",
            minimal_workflow_passed=0,
            minimal_workflow_total=0,
            critical_failures=[
                "QA audit was stopped after exceeding its tool-call budget; the "
                "analysis outputs are unaffected. Any checklist written before the "
                "stop is partial — re-run the audit if you need a complete one."
            ],
            success=False,
        )

    handoff = _run_capped(
        _qa_agent,
        {"messages": [{"role": "user", "content": "\n\n".join(sections)}]},
        _on_cap,
        name="qa_reporter",
    )
    _record_qa_verdict(handoff)
    return handoff


def _vlm_failure(pipeline_step: str, message: str) -> VLMHandoff:
    """Return a non-throwing handoff so visual QA cannot crash the core pipeline."""
    return VLMHandoff(
        overall_verdict="WARN",
        summary="Visual assessment was unavailable; continue with metadata and human review.",
        recommended_action="Continue with the non-visual checks and show the output to the user.",
        pipeline_step=pipeline_step,
        success=False,
        error_message=message,
    )


@tool
def vlm_judge(
    task: str,
    pipeline_step: str,
    expected_output: str,
    image_source: str | list[str],
    labels: Optional[list[str]] = None,
    create_mask_overlay: bool = False,
    overlay_opacity: float = 0.35,
) -> VLMHandoff:
    """Visually inspect input context or a completed image-processing result.

    This is a stateless specialist with a typed handoff to the supervisor.  When
    enabled for the chat, use it (1) alongside initial metadata extraction for an
    advisory whole-image review, and (2) after every image-producing processing step.

    For a segmentation result, pass ``image_source=[original_path, mask_path]``
    and ``create_mask_overlay=True``.  A transparent overlay is generated
    deterministically and the judge compares Original / Mask / Overlay.

    Args:
        task: Focused visual question and biological context.
        pipeline_step: Traceability label, e.g. ``input_review`` or ``segmentation``.
        expected_output: Observable criteria for a satisfactory result.
        image_source: One path/window title, or an ordered list for comparison.
            PNG/JPG/JPEG paths are read directly; all other existing paths are
            opened in Fiji and captured as PNG before visual analysis.
        labels: Optional captions matching the sources.
        create_mask_overlay: Build an alpha overlay from the first two prepared sources.
        overlay_opacity: Mask tint opacity in the range 0..1.
    """
    if _vlm_agent is None:
        return _vlm_failure(
            pipeline_step,
            "VLM judge requires OPENAI_API_KEY or OPEN_ROUTER_API_KEY.",
        )

    sources = list(image_source) if isinstance(image_source, list) else [image_source]
    if not sources or any(not isinstance(source, str) or not source.strip() for source in sources):
        return _vlm_failure(pipeline_step, "image_source must contain at least one non-empty source.")

    # Two-level fallback: intrinsically 2D web images remain direct inputs;
    # every other existing bioimage path is opened/rendered by Fiji first.
    # Window titles pass through unchanged and keep the existing capture path.
    prepared_sources = []
    for source in sources:
        prepared = prepare_image_source_for_vlm.invoke({"image_source": source})
        if prepared.startswith("ERROR:"):
            return _vlm_failure(pipeline_step, prepared)
        prepared_sources.append(prepared)
    sources = prepared_sources

    panel_labels = list(labels) if labels else []
    overlay_note = ""

    if create_mask_overlay:
        if len(sources) != 2:
            return _vlm_failure(
                pipeline_step,
                "create_mask_overlay requires exactly two sources: [original_path, mask_path].",
            )
        overlay_path = build_mask_overlay.invoke({
            "original_path": sources[0],
            "mask_path": sources[1],
            "opacity": overlay_opacity,
            "color": "magenta",
        })
        if overlay_path.startswith("ERROR:"):
            return _vlm_failure(pipeline_step, overlay_path)
        sources.append(overlay_path)
        panel_labels = panel_labels[:2]
        defaults = ["Original", "Mask"]
        while len(panel_labels) < 2:
            panel_labels.append(defaults[len(panel_labels)])
        panel_labels.append(f"Overlay ({int(overlay_opacity * 100)}% mask)")
        overlay_note = (
            "A mask overlay has already been generated as the third source. "
            "Build a three-panel compilation before analysis.\n"
        )

    content = (
        f"PIPELINE STEP: {pipeline_step}\n"
        f"IMAGE SOURCE(S): {sources}\n"
        f"LABELS: {panel_labels}\n"
        f"EXPECTED OUTPUT: {expected_output}\n"
        f"{overlay_note}\n"
        f"TASK: {task}"
    )

    try:
        return _run_capped(
            _vlm_agent,
            {"messages": [{"role": "user", "content": content}]},
            lambda: _vlm_failure(pipeline_step, "VLM judge reached its tool-call limit."),
            name="vlm_judge",
        )
    except Exception as exc:
        return _vlm_failure(pipeline_step, f"{type(exc).__name__}: {exc}")


@tool
def plugin_manager(task: str, project_root: str = "") -> PluginRecommendation:
    """
    Find, evaluate, and optionally install Fiji plugins for an image analysis task.

    Call in Phase 1 to find the best plugin for the scientific goal.
    Call again with "INSTALL <plugin_name>" after user approval to install.

    Args:
        task:         Describe the scientific task (e.g., "segment touching nuclei in
                      fluorescence images") OR an install command ("INSTALL MorphoLibJ").
        project_root: Absolute path to the project folder. The recommendation is read
                      out of this project's ledger (PROJECT STATE), so CALL
                      set_ledger_metadata(image_metadata=...) FIRST — see below.

    CALL ORDER MATTERS. Record the image properties (modality, n_channels, bit_depth,
    pixel size, dimensions) in the ledger BEFORE calling this. Those properties
    mechanically admit or exclude a tool: a brightfield H&E image cannot use a
    fluorescent-nuclei model no matter how the task is worded. `modality` is the one
    of those that extract_image_metadata does NOT measure — establish it from the
    user, the acquisition metadata, or the Vision Judge, and ASK THE USER when those
    do not settle it. Never infer it from bit depth or channel count (8-bit RGB is
    not evidence of brightfield), and never record "unknown" — nothing downstream
    fills it in for you.
    Called concurrently with extract_image_metadata — e.g. in one parallel tool batch —
    this sees an empty PROJECT STATE and must decide from the task PROSE ALONE, which is
    the highest-variance input available. Measured: an H&E segmentation task scored 0.11
    with one supervisor backbone and 0.75 with another, diverging at this call, before
    any parameter was chosen. The recommendation is then rendered as a binding
    "USE THIS PLUGIN" instruction for the rest of the run, so a bad pick here is not
    self-correcting.

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

    # Capped and supervised like every other subagent. This ran bare until
    # 2026-08-07, when a hung OpenRouter socket inside the plugin manager wedged
    # three benchmark containers indefinitely: no recursion cap, no watchdog, and
    # so nothing could see it. Failing to find a plugin must never be fatal — the
    # supervisor can pick a backend without a recommendation.
    def _on_cap() -> PluginRecommendation:
        return PluginRecommendation(
            recommended_plugin=None,
            installation_status="unknown",
            reasoning=(
                "Plugin search was stopped after exceeding its time/tool budget. "
                "Proceed by choosing a backend from the available skills instead of "
                "waiting on a recommendation."
            ),
        )

    return _run_capped(
        _plugin_agent,
        {"messages": [{"role": "user", "content": "\n\n".join(sections)}]},
        _on_cap,
        name="plugin_manager",
    )


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
        vlm_judge,
    ]

    set_dialog_vision_llm(llm_nano)
    if llm_vlm is not None:
        set_vision_llm(llm_vlm)

    vision_prompt = build_supervisor_prompt(enable_qa=True, enable_vision=True)
    no_vision_prompt = build_supervisor_prompt(enable_qa=True, enable_vision=False)

    # ── Advanced mode = the full pipeline toolset (current behaviour) ────────
    advanced_tools = [
        # subagents as tools (return typed JSON)
        *subagent_tools,
        plugin_manager,
        # supervisor's own tools
        internet_search,
        inspect_all_ui_windows,
        capture_plugin_dialog,
        # Rebase note (2026-09-07): these three landed on main after this branch
        # was cut (cellpose diameter estimation). advanced_tools replaces main's
        # explicit supervisor tool list, so they must be carried over here or the
        # supervisor silently loses them.
        estimate_cellpose_diameter_manual,
        estimate_cellpose_diameter_auto,
        merge_cellpose_diameter_runs,
        show_in_imagej_gui,
        close_imagej_windows,
        rag_retrieve_docs,
        # Rebase note (2026-08-03): the educator branch listed save_coding_experience,
        # rag_retrieve_mistakes, rag_retrieve_recipes and save_recipe here. All four
        # were removed from main when the learned-memory tier landed and no longer
        # exist anywhere in src/imagentj/tools — keeping them would NameError at
        # graph construction. Replaced with main's current equivalents.
        recall_concepts,
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
        # dynamically-discovered MCP server tools (e.g. in-container napari-mcp).
        # Discovered at startup; the viewer opens lazily on first napari tool call.
        # Discovery failures are non-fatal (adapter returns only diagnostics tools).
        *get_mcp_tools(),
        # state ledger (persistent project memory)
        update_state_ledger,
        read_state_ledger,
        set_ledger_metadata,
    ]

    # ── Tool sets per mode ───────────────────────────────────────────────────
    tutor_tools = [
        list_curriculum, load_chapter, load_track, show_figure, list_sample_images,
        list_practicals, reveal_solution, update_course_progress, set_course_plan,
    ]
    # Demos reuse the EXISTING execution path: execute_script runs a saved .py
    # (→ python) or .groovy (→ ImageJ in the GUI), and save_script writes it
    # first. No pipeline tools (workspace/coder/plugin/ledger), so education can
    # demonstrate a concept but not run the student's analysis project.
    demo_tools = [save_script, execute_script, show_in_imagej_gui, inspect_all_ui_windows,
                  capture_plugin_dialog, close_imagej_windows]

    quick_tools = [
        imagej_coder, imagej_debugger, plugin_manager, execute_script, save_script, load_script,
        get_script_history, smart_file_reader, inspect_folder_tree,
        extract_image_metadata, setup_analysis_workspace, inspect_all_ui_windows,
        show_in_imagej_gui, close_imagej_windows, rag_retrieve_docs, mkdir_copy,
        check_environment, set_mode,
    ]
    education_tools = tutor_tools + [set_mode] + demo_tools

    # Register the UNION of every mode's tools (deduped by identity). The
    # ModeMiddleware only NARROWS what each mode is offered — it cannot inject a
    # tool that isn't registered on the graph.
    def _dedup(tools):
        seen, out = set(), []
        for t in tools:
            if id(t) not in seen:
                seen.add(id(t))
                out.append(t)
        return out
    registered_tools = _dedup(advanced_tools + quick_tools + education_tools)

    # ── Mode registry ────────────────────────────────────────────────────────
    #   advanced  → pass-through: deep-agent-composed supervisor prompt + full tools.
    #   quick     → lean single-operation prompt + a minimal tool subset.
    #   education → tutor prompt (with live per-chat progress) + tutor/demo tools.
    # advanced offers the deep-agent's full toolset EXCEPT the education/tutor
    # tools (hidden by name so the injected builtins + advanced tools + set_mode
    # all survive). quick/education replace the toolset outright.
    modes = {
        "advanced":  ModeSpec(exclude_tools=[t.name for t in tutor_tools]),
        "quick":     ModeSpec(prompt=build_quick_prompt(), tools=quick_tools),
        "education": ModeSpec(prompt=build_tutor_prompt, tools=education_tools, model=llm_analyst),
    }

    supervisor_middleware = [
        ToolOutputLimitMiddleware(),
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
        # Rebase note (2026-08-03): main's VisionOptionMiddleware and the educator
        # branch's ModeMiddleware both claimed the "innermost, final say on the
        # system prompt" slot. Both are kept, in this order, because they compose:
        #   - ModeMiddleware runs first. For "advanced" its ModeSpec sets no prompt,
        #     so the deep-agent-composed supervisor prompt passes through untouched.
        #     For quick/education it substitutes that mode's own prompt.
        #   - VisionOptionMiddleware runs last and swaps the vision-on supervisor
        #     base for its vision-off variant by substring. In advanced mode the
        #     base is present, so the swap works exactly as it does on main today.
        #     In quick/education the substring is absent, so it is a no-op — those
        #     modes simply don't carry the vision instructions.
        # UNVERIFIED AT RUNTIME — this ordering is the reviewed intent, not a
        # tested behaviour. Exercise all three modes with vision on AND off.
        ModeMiddleware(modes),
        VisionOptionMiddleware(
            enabled_prompt=vision_prompt,
            disabled_prompt=no_vision_prompt,
        ),
        # Last line before a provider biological-risk refusal unwinds the whole
        # supervisor loop. create_deep_agent inserts user middleware after its
        # own Skills/Filesystem/SubAgent stack, so this sees their injected
        # system-message blocks and can drop them on retry 1; retry 2 also
        # neutralises pathogen proper nouns. Must stay last in this list.
        BioRefusalRetryMiddleware(),
    ]

    supervisor = create_deep_agent(
        name="ImageJ_Supervisor",
        # registered_tools is the deduped UNION of advanced + quick + education
        # tools (the educator branch's structure). ModeMiddleware only narrows
        # what each mode is offered, so the union must be registered here.
        tools=registered_tools,
        # Kept as main's vision-on prompt rather than the educator branch's plain
        # build_supervisor_prompt(enable_qa=True): VisionOptionMiddleware swaps this
        # exact string for its vision-off variant, so it must be the string that
        # middleware was constructed with.
        system_prompt=vision_prompt,
        subagents=[],
        middleware=supervisor_middleware,
        model=llm_supervisor,
        debug=False,
        backend=fs_backend,
        checkpointer=checkpointer_supervisor,
        skills=["/app/skills/workflow"],
    )

    return supervisor, checkpointer_supervisor, shared_metrics, shared_bridge, shared_tracker
