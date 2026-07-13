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
    lines.append(f"TRACK: {ledger.get('track', '[not set]')}")
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

    # Channels — the supervisor must be able to recall channel order and
    # marker names verbatim (e.g. channel 1 = DAPI, channel 2 = phalloidin)
    # because the coder uses them to address the right channel.
    channels = ledger.get("channels", [])
    if channels:
        lines.append("CHANNELS (index → marker/name):")
        for ch in channels:
            idx = ch.get("index", "?")
            name = ch.get("name", "")
            marker = ch.get("marker", "")
            extra = []
            if marker and marker != name:
                extra.append(f"marker={marker}")
            for k in ("color", "wavelength_nm", "purpose"):
                if ch.get(k):
                    extra.append(f"{k}={ch[k]}")
            extra_str = f"  ({', '.join(extra)})" if extra else ""
            lines.append(f"  [{idx}] {name}{extra_str}")

    # Input files — exact paths of the user's raw data so the coder can
    # hardcode them and not invent a path.
    input_files = ledger.get("input_files", [])
    if input_files:
        lines.append("INPUT FILES (use these exact paths in scripts):")
        for entry in input_files:
            if isinstance(entry, dict):
                p = entry.get("path", "?")
                note = entry.get("note") or entry.get("description") or ""
                lines.append(f"  • {p}" + (f"  — {note}" if note else ""))
            else:
                lines.append(f"  • {entry}")

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
        A one-line confirmation. This tool no longer echoes the whole ledger —
        call read_state_ledger when you need the full project state.
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

    # Return a compact acknowledgement, NOT the full ledger. Echoing the whole
    # ledger after every step floods the supervisor's context and invites it to
    # re-read/re-narrate state it already holds. Keep the "CURRENT PHASE: <x>"
    # token so PhaseGuardMiddleware can still detect the phase from this output.
    n_steps = len(ledger["completed_steps"])
    return (
        f"✓ Ledger updated — phase {phase}, step '{step}' ({status}). "
        f"{n_steps} step(s) recorded. CURRENT PHASE: {phase}. "
        f"Call read_state_ledger for the full project state."
    )


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
    track: Optional[str] = None,
    pipeline_plan: Optional[list[str]] = None,
    key_decision: Optional[str] = None,
    image_metadata: Optional[dict] = None,
    channels: Optional[list[dict]] = None,
    input_files: Optional[list] = None,
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
        track:           Which pipeline track the supervisor chose for this request:
                         "fast" (single self-contained operation — segment/threshold/count/
                         filter/convert one dataset, minimal ceremony) or "full" (the complete
                         multi-phase study pipeline with planning, statistics, plotting, QA).
                         Set this as soon as the track is decided. Re-set to "full" when a
                         fast request is escalated into a larger study.
        pipeline_plan:   Ordered list of processing step names.
                         Example: ["preprocessing", "thresholding", "watershed_segmentation", "measurement"]
        key_decision:    A single decision to append to the decisions log.
                         Example: "User chose Pipeline B: Otsu threshold → watershed segmentation"
        image_metadata:  Dict of image properties to record. RECORD THESE KEYS WHENEVER KNOWN:
                         bit_depth, pixel_size_um, pixel_unit, n_channels, n_z_slices,
                         n_timepoints, n_images, dimensions ("XYCZT" etc.), file_format,
                         modality (fluorescence | brightfield | EM | …), objective.
                         Example: {"bit_depth": 16, "pixel_size_um": 0.325, "n_channels": 3,
                                   "n_images": 24, "dimensions": "XYC", "file_format": "czi",
                                   "modality": "fluorescence", "objective": "63x oil"}
                         For channel NAMES use the dedicated `channels` field below,
                         not image_metadata — channel names are queried verbatim by the coder.
        channels:        Ordered list of channel descriptors, ONE entry per channel,
                         indexed 1-based. MANDATORY for any multi-channel dataset —
                         the coder uses `marker` to address the right channel and
                         the supervisor must be able to recall these verbatim later.
                         Each entry: {index:int, name:str, marker:str (optional, e.g. "DAPI"),
                                      color:str (optional, e.g. "blue"),
                                      wavelength_nm:int (optional),
                                      purpose:str (optional, e.g. "nuclei stain")}.
                         Example: [{"index": 1, "name": "DAPI", "marker": "DAPI",
                                    "color": "blue", "purpose": "nuclei"},
                                   {"index": 2, "name": "GFP-actin",
                                    "marker": "phalloidin-AF488", "color": "green",
                                    "purpose": "cytoskeleton"}]
                         Passing this REPLACES the existing channel list — pass the full
                         set every time so order is preserved.
        input_files:     Absolute paths of the user's raw data. MANDATORY once known.
                         Either a list of paths, or a list of {path, note} dicts when
                         per-file context helps (e.g. condition, replicate, timepoint).
                         Example: ["/data/exp1/well_A1.czi", "/data/exp1/well_B1.czi"]
                         or:      [{"path": "/data/exp1/control.czi", "note": "DMSO"},
                                   {"path": "/data/exp1/treated.czi", "note": "drug 10µM"}]
                         Passing this REPLACES the existing list — pass the full set every time.
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
        A one-line confirmation listing the fields that changed. Call
        read_state_ledger when you need the full project state.
    """
    ledger = _load_ledger(project_root)
    ledger.setdefault("project_root", project_root)

    if scientific_goal is not None:
        ledger["scientific_goal"] = scientific_goal

    if operating_mode is not None:
        ledger["operating_mode"] = operating_mode

    if track is not None:
        ledger["track"] = track

    if pipeline_plan is not None:
        ledger["pipeline_plan"] = pipeline_plan

    if key_decision is not None:
        ledger.setdefault("key_decisions", [])
        ledger["key_decisions"].append(key_decision)

    if image_metadata is not None:
        existing = ledger.get("image_metadata", {})
        existing.update(image_metadata)
        ledger["image_metadata"] = existing

    if channels is not None:
        # Normalise and replace — channel order matters and partial updates
        # break index→marker mapping. The supervisor MUST pass the full list.
        normalised = []
        for ch in channels:
            if not isinstance(ch, dict):
                continue
            entry = {k: v for k, v in ch.items() if v not in (None, "")}
            normalised.append(entry)
        ledger["channels"] = normalised

    if input_files is not None:
        ledger["input_files"] = list(input_files)

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

    # Compact acknowledgement instead of the full ledger (see update_state_ledger).
    updated = [
        name for name, val in (
            ("scientific_goal", scientific_goal),
            ("operating_mode", operating_mode),
            ("track", track),
            ("pipeline_plan", pipeline_plan),
            ("key_decision", key_decision),
            ("image_metadata", image_metadata),
            ("channels", channels),
            ("input_files", input_files),
            ("relevant_skill", relevant_skill),
            ("recommended_plugin", recommended_plugin),
            ("rag_reference", rag_reference),
        ) if val is not None
    ]
    return (
        f"✓ Ledger metadata updated: {', '.join(updated) if updated else 'no fields changed'}. "
        f"Call read_state_ledger for the full project state."
    )