"""
State Ledger — persistent, JSON-backed project state for the ImageJ Supervisor.

The ledger is a file on disk at <project_root>/state_ledger.json.
It survives context compaction, conversation summarization, and tool-use clearing.
The supervisor reads it at phase boundaries and writes to it after each step.

Design principles:
  - Append-only steps list (no silent overwrites)
  - Compact format (the whole ledger should fit in ~800 tokens even for long pipelines)
  - Human-readable JSON (for debugging and QA)
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# Internal helpers (not exposed as tools)
# ---------------------------------------------------------------------------

def _ledger_path(project_root: str) -> str:
    return os.path.join(project_root, "state_ledger.json")


def _load_ledger(project_root: str) -> dict:
    path = _ledger_path(project_root)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        # Corrupted or empty file (e.g. from a partial/interrupted write).
        # Return empty so the caller re-initialises rather than crashing.
        return {}


def _save_ledger(project_root: str, ledger: dict) -> None:
    # Guard: project_root must be inside /app/data to avoid writing to system paths.
    # The supervisor sometimes guesses a path before setup_analysis_workspace is called.
    if not os.path.normpath(project_root).startswith("/app/data"):
        raise ValueError(
            f"project_root '{project_root}' is outside /app/data. "
            "Call setup_analysis_workspace first to create the project folder."
        )
    # Atomic write: serialise to a temp file in the same directory, then
    # replace the target. os.replace() is atomic on POSIX, so readers never
    # see a partially-written or empty file.
    path = _ledger_path(project_root)
    dir_ = os.path.dirname(path)
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(ledger, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_ledger(ledger: dict) -> str:
    """Pretty-print the ledger for injection into the supervisor's context."""
    lines = []

    lines.append(f"PROJECT: {ledger.get('project_root', 'unknown')}")
    lines.append(f"SCIENTIFIC GOAL: {ledger.get('scientific_goal', '[not set]')}")
    lines.append(f"OPERATING MODE: {ledger.get('operating_mode', '[not set]')}")
    lines.append(f"CURRENT PHASE: {ledger.get('current_phase', '[not set]')}")

    # Pipeline plan
    plan = ledger.get("pipeline_plan", [])
    if plan:
        lines.append(f"PIPELINE PLAN: {' → '.join(plan)}")

    # Key decisions
    decisions = ledger.get("key_decisions", [])
    if decisions:
        lines.append("KEY DECISIONS:")
        for d in decisions:
            lines.append(f"  • {d}")

    # Image metadata snapshot
    meta = ledger.get("image_metadata", {})
    if meta:
        parts = [f"{k}={v}" for k, v in meta.items()]
        lines.append(f"IMAGE METADATA: {', '.join(parts)}")

    # Completed steps
    steps = ledger.get("completed_steps", [])
    if steps:
        lines.append("COMPLETED STEPS:")
        for s in steps:
            status_icon = "✓" if s["status"] == "completed" else "⏳" if s["status"] == "awaiting_approval" else "✗"
            line = f"  [{status_icon}] {s['phase']}/{s['step']}: {s['details']}"
            if s.get("script_path"):
                line += f"  script={s['script_path']}"
            if s.get("output_paths"):
                line += f"  outputs={s['output_paths']}"
            lines.append(line)

    # Recommended plugin (must be respected by coder)
    rec = ledger.get("recommended_plugin")
    if rec:
        lines.append(
            f"RECOMMENDED PLUGIN: {rec}  "
            f"← USE THIS PLUGIN. Do not substitute an alternative "
            f"(e.g., do not use SIFT when TurboReg is recommended). "
            f"If the recommended plugin is genuinely unusable for the task, "
            f"state the reason explicitly in the script's documentation."
        )

    # Skill paths identified
    skills = ledger.get("relevant_skills", [])
    if skills:
        lines.append(f"RELEVANT SKILLS: {', '.join(skills)}")

    # RAG knowledge references (compact summaries of retrieved docs)
    rag_refs = ledger.get("rag_references", [])
    if rag_refs:
        lines.append("RAG REFERENCES (re-retrieve with these queries if full content needed):")
        for ref in rag_refs:
            line = f"  [{ref['step']}] query=\"{ref['query']}\" → {ref['finding']}"
            lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public helper (for programmatic injection by tool wrappers — NOT a tool)
# ---------------------------------------------------------------------------

def get_ledger_context(project_root: str) -> str:
    """
    Return the formatted ledger as a string, or empty string if no ledger exists.

    Use this in tool wrappers to auto-inject project state into subagent context.
    This is NOT a LangChain tool — it's a plain function for use in Python code.
    """
    ledger = _load_ledger(project_root)
    if not ledger:
        return ""
    return _format_ledger(ledger)


# ---------------------------------------------------------------------------
# Tools (exposed to the supervisor)
# ---------------------------------------------------------------------------

@tool
def update_state_ledger(
    project_root: str,
    phase: str,
    step: str,
    status: str,
    details: str,
    script_path: Optional[str] = None,
    output_paths: Optional[list[str]] = None,
    parameters: Optional[dict] = None,
) -> str:
    """
    Record a completed (or failed) pipeline step in the project state ledger.

    Call this AFTER every significant action: script execution, user approval,
    debug fix, statistics run, plot generation, etc. The ledger persists on disk
    and survives context compaction — it is your reliable memory.

    Args:
        project_root: Absolute path to the project folder.
        phase:        Current phase identifier (e.g., "1", "2", "4b", "4c", "7").
        step:         Step name (e.g., "io_check", "thresholding", "statistics",
                      "batch_thresholding", "user_approved_thresholding").
        status:       One of: "completed", "failed", "awaiting_approval", "skipped".
        details:      One-line summary of what happened. Include key parameters.
                      Example: "Otsu threshold on DAPI channel, saved binary masks to processed_images/"
        script_path:  Absolute path to the script that was run (if applicable).
        output_paths: List of key output files produced (if applicable).
        parameters:   Dict of processing parameters used (if applicable).
                      Example: {"threshold_method": "Otsu", "gaussian_sigma": 1.5}

    Returns:
        The full formatted ledger as a string (for immediate reference).
    """
    ledger = _load_ledger(project_root)

    # Ensure structure exists
    ledger.setdefault("project_root", project_root)
    ledger.setdefault("completed_steps", [])
    ledger["current_phase"] = phase

    entry = {
        "phase": phase,
        "step": step,
        "status": status,
        "details": details,
        "timestamp": _now_iso(),
    }
    if script_path:
        entry["script_path"] = script_path
    if output_paths:
        entry["output_paths"] = output_paths
    if parameters:
        entry["parameters"] = parameters

    ledger["completed_steps"].append(entry)
    _save_ledger(project_root, ledger)

    return _format_ledger(ledger)


@tool
def read_state_ledger(project_root: str) -> str:
    """
    Read the current project state ledger.

    Call this BEFORE starting any new phase or when you need to recall:
    - What steps have been completed
    - What parameters were used
    - Where output files are located
    - What decisions the user made

    Returns the full ledger as formatted text, or a message if no ledger exists.
    """
    ledger = _load_ledger(project_root)
    if not ledger:
        return "No state ledger found. Call update_state_ledger to initialize one."
    return _format_ledger(ledger)


@tool
def set_ledger_metadata(
    project_root: str,
    scientific_goal: Optional[str] = None,
    operating_mode: Optional[str] = None,
    pipeline_plan: Optional[list[str]] = None,
    key_decision: Optional[str] = None,
    image_metadata: Optional[dict] = None,
    relevant_skill: Optional[str] = None,
    recommended_plugin: Optional[str] = None,
    rag_reference: Optional[dict] = None,
) -> str:
    """
    Set or update high-level project metadata in the state ledger.

    Call this during Phases 1-2 to record the scientific context and plan.
    Call it again during Phase 4b to record RAG findings for each processing step.
    Each call can set one or more fields. Fields not provided are left unchanged.

    Args:
        project_root:    Absolute path to the project folder.
        scientific_goal: One-sentence description of what the user wants to achieve.
                         Example: "Count and measure nuclei in DAPI-stained HeLa cells across 3 drug conditions"
        operating_mode:  How the user wants to work: "script" (automated Groovy scripts, default)
                         or "ui" (step-by-step guidance through the Fiji GUI).
                         Set this once in Phase 1 after asking the user.
        pipeline_plan:   Ordered list of processing step names.
                         Example: ["preprocessing", "thresholding", "watershed_segmentation", "measurement"]
        key_decision:    A single decision to append to the decisions log.
                         Example: "User chose Pipeline B: Otsu threshold → watershed segmentation"
        image_metadata:  Dict of image properties to record.
                         Example: {"bit_depth": 16, "pixel_size_um": 0.325, "channels": 3, "n_images": 24}
        relevant_skill:  Path to a skill folder to record as relevant.
                         Example: "/app/skills/morpholibj/"
        recommended_plugin: Name of the plugin recommended by plugin_manager.
                         The coder MUST prefer this plugin over alternatives.
                         Example: "TurboReg", "StarDist", "TrackMate"
        rag_reference:   Compact summary of a RAG retrieval. Store the query (for re-retrieval)
                         and a one-line finding (for quick reference). One reference per call.
                         Example: {"query": "otsu thresholding fiji", "step": "thresholding",
                                   "finding": "Use 'dark' flag for bright objects. 16-bit needs conversion to 8-bit."}

    Returns:
        The full formatted ledger as a string.
    """
    ledger = _load_ledger(project_root)
    ledger.setdefault("project_root", project_root)

    if scientific_goal is not None:
        ledger["scientific_goal"] = scientific_goal

    if operating_mode is not None:
        ledger["operating_mode"] = operating_mode

    if pipeline_plan is not None:
        ledger["pipeline_plan"] = pipeline_plan

    if key_decision is not None:
        ledger.setdefault("key_decisions", [])
        ledger["key_decisions"].append(key_decision)

    if image_metadata is not None:
        existing = ledger.get("image_metadata", {})
        existing.update(image_metadata)
        ledger["image_metadata"] = existing

    if relevant_skill is not None:
        ledger.setdefault("relevant_skills", [])
        if relevant_skill not in ledger["relevant_skills"]:
            ledger["relevant_skills"].append(relevant_skill)

    if recommended_plugin is not None:
        ledger["recommended_plugin"] = recommended_plugin

    if rag_reference is not None:
        ledger.setdefault("rag_references", [])
        # Avoid duplicates for the same query+step combination
        existing_keys = {(r["query"], r["step"]) for r in ledger["rag_references"]}
        key = (rag_reference.get("query", ""), rag_reference.get("step", ""))
        if key not in existing_keys:
            ledger["rag_references"].append({
                "query": rag_reference.get("query", ""),
                "step": rag_reference.get("step", ""),
                "finding": rag_reference.get("finding", ""),
            })

    _save_ledger(project_root, ledger)
    return _format_ledger(ledger)