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

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# Internal helpers (not exposed as tools)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Deterministic tool/image compatibility gate
# ---------------------------------------------------------------------------
# The recommendation from plugin_manager is rendered as a binding
# "USE THIS PLUGIN" instruction for the rest of the run, and nothing downstream
# checks it against the data. 
#
# Sequencing (phase_1_gathering 4a/4b) now gives the router the measured facts
# before it chooses, which narrows the variance. This gate removes the rest: a
# pairing that is MECHANICALLY wrong is caught regardless of which model proposed
# it, because it is decided by the measured image properties, not by wording.
#
# Scope is deliberately narrow. Every rule below encodes a documented, verifiable
# incompatibility between a model's TRAINING DOMAIN and the image's measured
# modality/channel count — not a preference, not a performance opinion. A rule
# that could fire on a legitimate choice does not belong here: a false block is
# worse than the miss, because it strands a run that would otherwise have worked.
_PLUGIN_IMAGE_RULES: tuple[dict, ...] = (
    {
        # StarDist ships two Versatile models with disjoint training domains
        # (skills/stardist_documentation/OVERVIEW.md): "Versatile (fluorescent
        # nuclei)" on DSB-2018 fluorescence, "Versatile (H&E nuclei)" on
        # MoNuSeg/TCGA H&E. Running the fluorescence model on RGB brightfield is
        # the exact failure mode behind the 0.11 score.
        "match": ("versatile (fluorescent nuclei)", "versatile (fluorescent)",
                  "dsb 2018", "dsb2018"),
        "forbid_modality": ("brightfield", "h&e", "he", "histology", "histopathology"),
        "reason": (
            "this StarDist model was trained on FLUORESCENCE nuclei (DSB 2018) but the "
            "image is brightfield/H&E"
        ),
        "use_instead": '"Versatile (H&E nuclei)" — it is trained on raw RGB H&E; do NOT '
                       "colour-deconvolve first",
    },
    {
        "match": ("versatile (h&e nuclei)", "versatile (h&e)", "h&e nuclei"),
        "forbid_modality": ("fluorescence", "fluorescent", "confocal", "widefield",
                            "light-sheet", "lightsheet", "tirf", "smlm"),
        "reason": (
            "this StarDist model was trained on H&E histology but the image is fluorescence"
        ),
        "use_instead": '"Versatile (fluorescent nuclei)"',
    },
)


# ---------------------------------------------------------------------------
# Modality-ranked first-choice ordering
# ---------------------------------------------------------------------------
# The compatibility rules above only catch a pairing that is MECHANICALLY wrong.
# They cannot separate two choices that are both admissible for the modality —
# a deep-learning segmenter and a classical watershed are peers as far as the
# registry is concerned (`use_when` is prose; there is no modality field in any
# of its 290 entries). 
# It is a DEFAULT ORDER, not a lock. Each entry is "try this first"; falling to
# the next is expected and requires only that the reason be recorded. Making it
# binding would repeat the mistake the mismatch branch above exists to undo.
#
# Each rule must state ALL of: modality tokens, modality tokens that DISQUALIFY it,
# allowed dimensionality, and the target it applies to. An earlier version omitted
# the last three and was measured against the 16 benchmark task specs: it produced a
# wrong or unjustified first choice on 7 of them. The three failure modes are worth
# naming, because they are the ones any new rule will repeat:
#
#   1. DIMENSIONALITY. The Fiji StarDist plugin is 2D/2D+t only — the registry says
#      so outright ("Do not use when your data are truly 3D volumes"). Without a dims
#      check the fluorescence-nuclei rule recommended StarDist for two 3D tasks.
#   2. SUBSTRING BLEED. "20x brightfield/phase-contrast" contains "brightfield", so
#      a phase-contrast microglia task was handed the H&E histology model.
#   3. TASK CONFUSION. These are SEGMENTATION defaults. Firing them on spot-detection,
#      colocalization or filament tasks recommended a cell segmenter for counting
#      puncta and for tracing microtubules. Hence the primary_task gate, and target
#      tokens narrow enough not to match the word "cells" in any passing sentence.
_MODALITY_TOOL_PRIORITY: tuple[dict, ...] = (
    {
        "modality": ("h&e", "histology", "histopathology"),
        "not_modality": ("phase-contrast", "phase contrast", "dic", "fluorescence"),
        "dims": ("2d",),
        "target": ("nuclei",),
        "order": (
            'StarDist "Versatile (H&E nuclei)" — trained on raw RGB H&E, no colour deconvolution',
            "Cellpose (BIOP) cyto3 on the haematoxylin channel",
            "classical: colour-deconvolve -> Auto Threshold -> Distance Transform Watershed",
        ),
    },
    {
        "modality": ("fluorescence", "fluorescent", "confocal", "widefield",
                     "spinning", "airyscan"),
        "not_modality": ("phase-contrast", "phase contrast", "dic", "brightfield"),
        "dims": ("2d",),
        "target": ("nuclei",),
        "order": (
            "Cellpose (BIOP) nucleitorch_0",
            'StarDist "Versatile (fluorescent nuclei)" — the trained generalist for 2D nuclei',
            "classical: Auto Threshold -> Distance Transform Watershed (only if both fail)",
        ),
    },
    {
        "modality": ("fluorescence", "fluorescent", "confocal", "widefield",
                     "spinning", "airyscan"),
        "not_modality": ("phase-contrast", "phase contrast", "dic", "brightfield"),
        "dims": ("2d",),
        "target": ("cytoplasm", "whole cell", "cell body", "cell outline", "membrane"),
        "order": (
            "Cellpose (BIOP) cyto3 — cytoplasm/whole-cell is its trained domain, not StarDist's",
            "micro_sam (vit_b_lm; vit_t_lm on CPU)",
            "classical: seeded/Marker-controlled Watershed from a nuclear marker",
        ),
    },
    {
        # 3D is a different toolset entirely: the Fiji StarDist plugin cannot do it,
        # and Cellpose's Fiji wrapper is 2D/per-plane. micro_sam has a real 3D path.
        "modality": ("fluorescence", "fluorescent", "confocal", "light-sheet",
                     "lightsheet", "spinning", "airyscan"),
        "not_modality": (),
        "dims": ("3d",),
        "target": ("nuclei", "cytoplasm", "whole cell", "cell body", "membrane"),
        "order": (
            "micro_sam 3D (annotator_3d / automatic_instance_segmentation, ndim=3)",
            "per-plane 2D segmentation + label stitching across z",
            "classical: 3D Auto Threshold -> 3D Watershed (MorphoLibJ)",
        ),
    },
)


# Values that LOOK like a recorded modality but carry no information.
_PLACEHOLDER_MODALITY: frozenset = frozenset({
    "unknown", "unspecified", "not specified", "not recorded", "undetermined",
    "unclear", "n/a", "na", "none", "null", "tbd", "?", "-",
})


def _normalise_modality(metadata: dict) -> str:
    """Recorded modality, or "" when nothing informative was recorded."""
    modality = str(metadata.get("modality") or "").strip().lower()
    return "" if modality in _PLACEHOLDER_MODALITY else modality


# Axis-order strings are built from these letters and nothing else. Used to tell
# an axis listing ("XYCZ") apart from free prose or a pixel-size string.
_AXIS_LETTERS: frozenset = frozenset("xyczts")


def _derive_dimensionality(metadata: dict) -> str:
    """Return "3d", "2d", or "" — never the caller's raw `dimensions` string.

    The rules in _MODALITY_TOOL_PRIORITY are keyed on the DIMENSION COUNT ("2d" /
    "3d"), but `dimensions` is free text written by the supervisor, and the only
    guidance it has (set_ledger_metadata's docstring) shows AXIS-ORDER notation —
    "XYCZT", example "XYC". Those two vocabularies never intersect: an axis string
    is all letters, so `"2d" in dims` cannot be true for any well-formed value.
    Measured on 29 real ledgers: 0 contained "2d" or "3d", and 16 of them reached
    the rule loop with a matching modality only to be rejected here.

    So dimensionality is DERIVED rather than string-matched:
      1. an explicit "2d"/"3d" token, if the supervisor happened to write one —
         a deliberate statement outranks anything inferred;
      2. otherwise the axis listing ('Z' present means a volume) and `n_z_slices`
         (int in 17 of the 29 ledgers) both vote, and **"3d" wins any split**.
    Time is NOT a spatial dimension: "XYT" is 2d, which is what the 2D rules mean
    when they say "2D/2D+t". Anything else returns "" and the caller stays silent.

    The split is broken toward 3d deliberately. The two signals disagree in real
    ledgers ("XYCZ" recorded next to n_z_slices=1, or "XY" next to n_z_slices=12),
    and the two errors are not symmetric: calling a volume 2d puts the Fiji StarDist
    plugin — which the registry says outright cannot do volumes — at the top of the
    list, which is failure mode 1 in the comment above _MODALITY_TOOL_PRIORITY.
    Calling a plane 3d only costs a detour to micro_sam, which handles 2d fine.
    """
    if not isinstance(metadata, dict):
        return ""
    raw = str(metadata.get("dimensions") or metadata.get("spatial_dimensions") or "")
    text = raw.strip().lower()

    # 1. Explicit statement wins outright.
    if "3d" in text:
        return "3d"
    if "2d" in text:
        return "2d"

    votes = set()

    # 2a. Axis listing. Real values carry trailing prose ("XYCZ tiles") and stray
    #     punctuation ("XYC?Z"), so read the first token and keep only letters.
    #     Requiring the result to be ALL axis letters is what makes "1024x1024" and
    #     "640x480x1" fall through instead of being misread as axes.
    for candidate in (text, str(metadata.get("series_axes") or "").strip().lower()):
        head = candidate.split()[0] if candidate.split() else ""
        letters = "".join(ch for ch in head if ch.isalpha())
        if letters and letters == "".join(ch for ch in head if ch.isalnum()) \
                and set(letters) <= _AXIS_LETTERS:
            votes.add("3d" if "z" in letters else "2d")

    # 2b. Documented numeric key. Only a clean int counts — this field has also been
    #     seen holding "156;127;157" and a filename note, which mean nothing here.
    z = metadata.get("n_z_slices")
    if not isinstance(z, bool) and isinstance(z, int):
        votes.add("3d" if z > 1 else "2d")

    if "3d" in votes:
        return "3d"
    if "2d" in votes:
        return "2d"
    return ""


def priority_shortlist(metadata: dict, goal: str = "", primary_task: str = "",
                       sub_tasks: "tuple[str, ...] | list | str | None" = None) -> tuple[str, ...]:
    """Ordered first-choice SEGMENTATION tools, or () when we cannot justify one.

    Silence is the default. Modality unknown, dimensionality unknown, a task that is
    not segmentation, or a target we have no considered opinion on all return () —
    leaving the router exactly as free as it is today. A shortlist is only emitted
    where the ranking is defensible; anywhere else a guess would be worse than the
    variance it replaces.
    """
    if not isinstance(metadata, dict):
        return ()
    # Only a RECORDED modality counts. It is not something extract_image_metadata
    # can report — it is a judgement the supervisor writes or the user states — and
    # it is deliberately not inferred from pixel layout: see the note above
    # _PLACEHOLDER_MODALITY for the measurement that ruled that out. Unrecorded
    # means silence, which is what this function's docstring promises.
    modality = _normalise_modality(metadata)
    if not modality:
        return ()

    # These rank SEGMENTATION approaches, so they apply whenever the pipeline
    # CONTAINS a segmentation step — not only when segmentation is the headline.
    # Gating on the primary label alone was wrong: five of the sixteen benchmark
    # specs declare segmentation as a SUB-task under a feature-extraction,
    # stitching or colocalization headline (measure translocation -> segment the
    # nuclei first; quantify puncta -> segment the nuclei first), and all five
    # were being silenced despite needing exactly this choice made.
    #
    # A pipeline with no segmentation step anywhere still gets silence: counting
    # by spot detection, or localising single molecules, does not want a cell
    # segmenter at the top of its list.
    task = str(primary_task or "").strip().lower()
    subs = sub_tasks or ()
    if isinstance(subs, str):
        subs = (subs,)
    sub_lower = tuple(str(s).strip().lower() for s in subs)
    # Substring, not equality: runtime plan steps are free-form names the
    # supervisor invents ("segmentation_stardist", "segment_nuclei_cellpose"),
    # so an exact match against the literal word never fires. The benchmark
    # specs DO use the bare token, and substring covers both.
    #
    # An EMPTY signal stays permissive on purpose. The shortlist is rendered into
    # PROJECT STATE from Phase 1, before pipeline_plan exists — which is exactly
    # when the router is choosing and the guidance is worth most. Staying silent
    # until a plan is written would mute it for the decision it exists to steer.
    # Non-segmentation runs are still filtered by the modality/dims/target rules
    # below, which is where puncta, filaments and vessels are actually excluded.
    has_seg = (task == "segmentation") or any("segment" in s for s in sub_lower)
    if (task or sub_lower) and not has_seg:
        return ()

    dims = _derive_dimensionality(metadata)
    hay = f"{goal} {metadata.get('biological_target') or ''}".lower()

    # Structures that are NOT blob-like objects need a different family of tools
    # (ridge/filament tracing, spot detectors, vesselness filters), so no cell or
    # nucleus segmenter belongs at the top of their list. Judged on the declared
    # biological_target, not the surrounding prose: a microtubule task was matched
    # on the phrase "cell body" appearing in its instructions while its target
    # field said plainly "microtubules".
    target_field = str(metadata.get("biological_target") or "").lower()
    # NB "actin" is deliberately absent: phalloidin/actin is the standard CYTOPLASM
    # stain, so excluding it would reject ordinary whole-cell segmentation. Only
    # structures that are themselves the thing being traced belong here.
    _NON_BLOB = ("microtubule", "filament", "cytoskelet", "neurite",
                 "axon", "dendrite", "vessel", "vascul", "punct", "foci", "focus",
                 "spot", "granule", "nanoruler", "origami")
    if any(t in target_field for t in _NON_BLOB):
        return ()

    for rule in _MODALITY_TOOL_PRIORITY:
        if not any(m in modality for m in rule["modality"]):
            continue
        if any(bad in modality for bad in rule["not_modality"]):
            continue
        if rule["dims"]:
            if not dims or not any(d in dims for d in rule["dims"]):
                continue
        if rule["target"] and not any(t in hay for t in rule["target"]):
            continue
        return rule["order"]
    return ()


def check_plugin_image_compatibility(plugin: str, metadata: dict) -> Optional[str]:
    """Return a mismatch explanation, or None when nothing is provably wrong.

    Returns None whenever the answer is not certain — an unknown modality, an
    unrecognised plugin string, or missing metadata all mean "cannot judge", and
    the caller must treat that as permission, not suspicion.
    """
    if not plugin or not isinstance(metadata, dict):
        return None
    modality = str(metadata.get("modality") or "").strip().lower()
    if not modality:
        return None
    name = plugin.strip().lower()

    for rule in _PLUGIN_IMAGE_RULES:
        if not any(token in name for token in rule["match"]):
            continue
        if any(bad in modality for bad in rule["forbid_modality"]):
            n_ch = metadata.get("n_channels")
            observed = f"modality={metadata.get('modality')}"
            if n_ch is not None:
                observed += f", n_channels={n_ch}"
            return (
                f"{rule['reason']} ({observed}). "
                f"Use {rule['use_instead']} instead, or state explicitly why the "
                "recommended model is still correct for this data."
            )
    return None


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


def _content_text(value: Any) -> str:
    """Normalize provider text blocks used accidentally as ledger text fields."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part for item in value if (part := _content_text(item)))
    if isinstance(value, dict):
        if "text" in value:
            return _content_text(value.get("text"))
        if "content" in value:
            return _content_text(value.get("content"))
        return json.dumps(value, ensure_ascii=False, default=str)
    text = getattr(value, "text", None)
    return _content_text(text) if text is not None else str(value)


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

    # Ranked default for this modality. Rendered from the MEASURED metadata, so it
    # is the same list whichever model is driving — which is the point: without it
    # a deep-learning segmenter and a classical watershed look equally reasonable
    # and the choice is effectively random across backbones.
    # `sub_tasks` is the BENCHMARK spec's vocabulary — nothing in this system emits
    # it. The runtime equivalent of "does this pipeline contain a segmentation
    # step" is the supervisor's own pipeline_plan, written in Phase 2. Passing
    # neither (as this call did originally) leaves the task gate inert: every
    # caller looks like "task unknown", the gate is skipped, and the shortlist can
    # fire on a spot-detection or tracking run it has no opinion about.
    user_pick = str(ledger.get("user_specified_plugin") or "").strip()
    if user_pick:
        lines.append(
            f"USER-SPECIFIED TOOL: {user_pick}  "
            f"← the user asked for this BY NAME. This is the decision. Use it. "
            f"Do not substitute a 'better' default, do not re-open the choice with "
            f"plugin_manager, and do not argue the point — the modality default and "
            f"the compatibility check are both suppressed here on purpose."
        )

    plan = ledger.get("pipeline_plan") or []
    if isinstance(plan, str):
        plan = [plan]
    plan_steps = tuple(str(s).lower() for s in plan)
    # A ranked default is only useful when nobody has decided. Rendering one
    # next to an explicit user choice invites the agent to second-guess it.
    shortlist = () if user_pick else priority_shortlist(
        meta,
        str(ledger.get("scientific_goal") or ""),
        primary_task="",           # not tracked separately at runtime
        sub_tasks=plan_steps,      # derived from the plan the supervisor recorded
    )
    if shortlist:
        lines.append(
            "TRY IN THIS ORDER (default for this modality — not a lock): "
            + "; ".join(f"{i}) {t}" for i, t in enumerate(shortlist, 1))
            + ". Start at 1. Drop to the next ONLY after the previous one has been "
            "tried and found wanting, and record in the ledger which one you used "
            "and why — 'a classical method also works' is not a reason to skip a "
            "trained model, and picking further down the list without evidence is "
            "the single largest source of run-to-run variation."
        )

    # Visual observations complement file metadata but never replace it.  Keep
    # the handoff compact so all downstream specialists can use it safely.
    visual = ledger.get("vlm_assessments", [])
    if visual:
        lines.append("VLM VISUAL ASSESSMENTS (advisory; confirm quantitatively):")
        for assessment in visual:
            stage = assessment.get("pipeline_step", "unknown")
            verdict = assessment.get("overall_verdict", "INFO")
            summary = assessment.get("summary", "")
            lines.append(f"  [{stage}/{verdict}] {summary}")
            issues = assessment.get("issues_found", [])
            if issues:
                lines.append(f"    issues: {'; '.join(str(i) for i in issues)}")
            action = assessment.get("recommended_action", "")
            if action:
                lines.append(f"    recommendation: {action}")

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
        # When the user named the tool themselves, the mismatch note is not
        # surfaced at all. The gate exists to correct an AGENT's pick; the user's
        # choice is the decision, not a proposal to be second-guessed.
        mismatch = None if user_pick else ledger.get("recommended_plugin_mismatch")
        if mismatch:
            # The measured data contradicts the recommendation, so the usual
            # "do not substitute" lock is withdrawn for this case ONLY. That lock
            # exists to stop drift between equivalent tools; it must not pin a
            # choice the image itself rules out.
            lines.append(
                f"RECOMMENDED PLUGIN: {rec}  "
                f"← DATA MISMATCH — DO NOT USE AS-IS. {mismatch} "
                f"This compares the model's training domain against the MEASURED image "
                f"properties, so it holds regardless of which model recommended it. "
                f"Switch to the stated alternative, or record in the script's "
                f"documentation why it is correct anyway."
            )
        else:
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
    details: Any,
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
    # Some provider/tool-call paths encode a text argument as a list of content
    # blocks. Accept and normalize that representation instead of letting a
    # downstream string validator/regex abort the whole supervisor turn.
    details = _content_text(details).strip()
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
    pipeline_plan: Optional[list[str]] = None,
    key_decision: Optional[str] = None,
    image_metadata: Optional[dict] = None,
    channels: Optional[list[dict]] = None,
    input_files: Optional[list] = None,
    relevant_skill: Optional[str] = None,
    recommended_plugin: Optional[str] = None,
    user_specified_plugin: Optional[str] = None,
    rag_reference: Optional[dict] = None,
    vlm_assessment: Optional[dict] = None,
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
        image_metadata:  Dict of image properties to record. RECORD THESE KEYS WHENEVER KNOWN:
                         bit_depth, pixel_size_um, pixel_unit, n_channels, n_z_slices,
                         n_timepoints, n_images, dimensions ("XYCZT" etc.), file_format,
                         modality (fluorescence | brightfield | EM | …), objective.
                         Example: {"bit_depth": 16, "pixel_size_um": 0.325, "n_channels": 3,
                                   "n_images": 24, "dimensions": "XYC", "file_format": "czi",
                                   "modality": "fluorescence", "objective": "63x oil"}
                         `modality` STEERS TOOL CHOICE — record the CONTRAST MECHANISM
                         you actually established ("brightfield", "phase-contrast",
                         "DIC", "H&E", "confocal fluorescence", "EM", "microCT").
                         So do not guess and do not write "unknown"/"unspecified" —
                         a placeholder is treated as no answer. If the file and the
                         user's description do not settle it, ASK THE USER: it is one
                         short question, they always know, and it is far cheaper than
                         a segmentation run aimed at the wrong contrast mechanism.
                         `n_z_slices` also matters beyond bookkeeping — it is how
                         2D-vs-3D is decided when `dimensions` is an axis listing.
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
        vlm_assessment:  Compact structured handoff from vlm_judge. Store at least
                         pipeline_step, overall_verdict, summary, and issues_found.
                         Visual observations are advisory and complement, never replace,
                         numeric metadata or user verification.

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

    if user_specified_plugin is not None:
        # The USER asked for this tool by name. It outranks both the router's
        # recommendation and the modality default: those exist to decide when
        # nobody has, and someone has. Recorded separately from
        # recommended_plugin so the two never overwrite each other and it stays
        # obvious which came from whom.
        ledger["user_specified_plugin"] = user_specified_plugin

    if recommended_plugin is not None:
        ledger["recommended_plugin"] = recommended_plugin
        # Check the choice against the MEASURED image properties at the moment it
        # becomes binding. Stored rather than raised: a hard failure here would
        # strand a run on a rule that might not apply, whereas a recorded mismatch
        # travels with the instruction and lets the coder override it knowingly.
        mismatch = check_plugin_image_compatibility(
            recommended_plugin, ledger.get("image_metadata") or {}
        )
        if mismatch:
            ledger["recommended_plugin_mismatch"] = mismatch
        else:
            ledger.pop("recommended_plugin_mismatch", None)

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

    if vlm_assessment is not None:
        ledger.setdefault("vlm_assessments", [])
        compact = {
            "pipeline_step": vlm_assessment.get("pipeline_step", "unknown"),
            "overall_verdict": vlm_assessment.get("overall_verdict", "INFO"),
            "summary": vlm_assessment.get("summary", ""),
            "issues_found": list(vlm_assessment.get("issues_found") or []),
            "recommended_action": vlm_assessment.get("recommended_action", ""),
            "image_paths_inspected": list(vlm_assessment.get("image_paths_inspected") or []),
            "success": bool(vlm_assessment.get("success", True)),
        }
        # Replace a prior assessment for the same checkpoint so retries after a
        # segmentation fix do not leave a stale FAIL beside the current result.
        stage = compact["pipeline_step"]
        ledger["vlm_assessments"] = [
            item for item in ledger["vlm_assessments"]
            if item.get("pipeline_step") != stage
        ]
        ledger["vlm_assessments"].append(compact)

    _save_ledger(project_root, ledger)

    # Compact acknowledgement instead of the full ledger (see update_state_ledger).
    updated = [
        name for name, val in (
            ("scientific_goal", scientific_goal),
            ("operating_mode", operating_mode),
            ("pipeline_plan", pipeline_plan),
            ("key_decision", key_decision),
            ("image_metadata", image_metadata),
            ("channels", channels),
            ("input_files", input_files),
            ("relevant_skill", relevant_skill),
            ("recommended_plugin", recommended_plugin),
            ("rag_reference", rag_reference),
            ("vlm_assessment", vlm_assessment),
        ) if val is not None
    ]
    return (
        f"✓ Ledger metadata updated: {', '.join(updated) if updated else 'no fields changed'}. "
        f"Call read_state_ledger for the full project state."
    )
