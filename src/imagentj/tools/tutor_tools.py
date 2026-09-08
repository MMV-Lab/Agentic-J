"""
Tutor tools — teaching from the generated bioimage-analysis course package.

These power the supervisor's **education mode**. They read the course produced by
`scripts/build_bioimage_course.py` (+ `harvest_generated_figures.py`) at
`$TUTOR_COURSE_ROOT` (default `/app/skills/bioimage_course`):

    curriculum.json   parts -> chapters -> tracks (imagej/python) & sub-pages
    content/<id>/      concept.md, imagej.md, python.md
    assets/<id>/       figures
    figure_index.json  figure id/label -> asset + caption
    practicals.json    Practical/Solution pairs

Design notes
------------
* Content tools (`list_curriculum`, `load_chapter`, `load_track`, `show_figure`,
  `list_practicals`, `reveal_solution`) are pure file reads — no LLM, no state.
* Progress + mode tools (`update_course_progress`, `set_course_plan`, `set_mode`)
  return a `Command` that updates the **checkpointed graph state**, so progress is
  per-chat (per `thread_id`) for free. Current progress is also injected into the
  tutor system prompt each turn (see `build_tutor_prompt`), so the tutor can read
  it without a tool call and only *writes* through these tools.
* Figures are opened LARGE in the Fiji/ImageJ viewer (never inline in the chat);
  `show_figure` returns the caption for the tutor to talk over.
"""

import copy
import json
import os
from pathlib import Path
from typing import Annotated, Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

COURSE_ROOT = Path(os.getenv("TUTOR_COURSE_ROOT", "/app/skills/bioimage_course"))

# Real sample images from the book's official "practical-data" set, bundled so
# live demos have data to run on.
SAMPLES_DIR = COURSE_ROOT / "samples"

VALID_MODES = ("advanced", "quick", "education")


# ── internal helpers ────────────────────────────────────────────────────────

def _load(name: str) -> dict | list:
    path = COURSE_ROOT / name
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _curriculum() -> dict:
    return _load("curriculum.json") or {}


def _chapter(chapter_id: str) -> dict:
    return _curriculum().get("chapters", {}).get(chapter_id, {})


def _abs_asset(rel: str) -> str:
    return str((COURSE_ROOT / rel).resolve())


def _absolutize_images(md: str) -> str:
    """Rewrite `](assets/...)` to absolute paths so any renderer can find them."""
    return md.replace("](assets/", f"]({COURSE_ROOT}/assets/")


def _open_figure_in_gui(abs_path: str, title: str | None = None) -> str | None:
    """Open a figure large in the ImageJ/Fiji viewer, optionally renaming the
    window to `title`. Returns the status string on success, or None if the GUI
    isn't available."""
    try:
        from imagentj.tools.imagej_tools import open_in_imagej_gui
    except Exception:
        return None
    status = open_in_imagej_gui(abs_path, title=title)
    return status if isinstance(status, str) and status.startswith("Opened") else None


def _chapter_title(chapter_id: str, ch: dict) -> str:
    """Display title for a chapter. The build script leaves `title` empty for at
    least one page (0.1, the book's Preface), which would otherwise render as a
    nameless entry in the course plan — fall back to the slug, then the id."""
    t = (ch.get("title") or "").strip()
    if t:
        return t
    slug = (ch.get("slug") or "").strip()
    return slug.replace("-", " ").replace("_", " ").title() if slug else chapter_id


def _figure_label(fig_id: str, entry: dict) -> str:
    """Build a stable, human-readable window title, e.g. 'Fig 1.1-2 — image as array'.
    This is BOTH the ImageJ window title and the name the tutor cites in prose."""
    n = fig_id.split("#")[-1] if "#" in fig_id else ""
    chap = entry.get("chapter", "")
    tag = f"Fig {chap}-{n}" if n else f"Fig {chap}"
    cap = (entry.get("caption") or "").strip().lstrip("*").strip()
    cap = cap.split(". ")[0].strip()            # first sentence, keep it short
    if len(cap) > 60:
        cap = cap[:57].rstrip() + "…"
    return f"{tag} — {cap}" if cap else tag


_SECTION_TRACKS = ("concept", "imagej", "python", "all")


def _open_section_figures(chapter_id: str, track: str) -> str:
    """Open every rendered figure of a chapter (optionally a single track) in the
    viewer at once, each window TITLED so the tutor can cite it. Returns the list
    of titles so the tutor knows exactly what is on screen."""
    idx = _load("figure_index.json") or {}
    items = [
        (k, v) for k, v in idx.items()
        if v.get("chapter") == chapter_id and v.get("file")
        and (track == "all" or v.get("track") == track)
    ]
    if not items:
        return f"No {track} figures to open for section {chapter_id}."
    titles, failed = [], 0
    for k, v in items:
        label = _figure_label(k, v)
        if _open_figure_in_gui(_abs_asset(v["file"]), title=label):
            titles.append(label)
        else:
            failed += 1
    lines = [f"Opened {len(titles)} {track} figure(s) for section {chapter_id}, "
             f"each titled in the viewer — cite figures by these exact titles:"]
    lines += [f"  • {t}" for t in titles]
    if failed:
        lines.append(f"({failed} could not open — is the ImageJ/Fiji GUI up?)")
    return "\n".join(lines)


# ── content tools ───────────────────────────────────────────────────────────

@tool
def list_curriculum() -> str:
    """
    List the whole bioimage-analysis course: parts, chapters, and which tracks
    (ImageJ / Python) and how many practicals each chapter has.

    Call this at the start of education mode (or when the student asks what the
    course covers, or to build a custom course). Chapter ids like "1.1", "2.3"
    are what you pass to load_chapter / load_track / set_course_plan.
    """
    cur = _curriculum()
    if not cur:
        return f"ERROR: no curriculum found at {COURSE_ROOT}/curriculum.json"

    lines = [f"# {cur.get('title')} — by {cur.get('author')}  ({cur.get('license')})", ""]
    chapters = cur.get("chapters", {})
    for part in cur.get("parts", []):
        lines.append(f"## Part {part['num']}: {part['title']}  ({part.get('kind','')})")
        for cid in part["chapters"]:
            ch = chapters.get(cid, {})
            tracks = list(ch.get("tracks", {}).keys())
            tag = []
            if tracks:
                tag.append("tracks: " + "+".join(tracks))
            if ch.get("n_practicals"):
                tag.append(f"{ch['n_practicals']} practical(s)")
            if ch.get("subpages"):
                tag.append(f"{len(ch['subpages'])} sub-page(s)")
            suffix = f"   [{', '.join(tag)}]" if tag else ""
            lines.append(f"  - {cid}  {_chapter_title(cid, ch)}{suffix}")
        lines.append("")
    lines.append("Use load_chapter(id) to teach a chapter's concept, then "
                 "load_track(id, 'imagej'|'python') for the hands-on demonstration.")
    return "\n".join(lines)


@tool
def load_chapter(chapter_id: str) -> str:
    """
    Load a chapter's core concept text so you can teach it in your own words.

    Returns the concept explanation plus a header listing which tracks
    (ImageJ / Python) and practicals are available for this chapter. Teach the
    concept first; then, on request, call load_track for the hands-on side.
    Figures appear as `[Figure: caption]` — surface important ones with
    show_figure so the student actually sees them.

    Args:
        chapter_id: Chapter id from list_curriculum, e.g. "1.1", "2.3", "4.3.1".
    """
    ch = _chapter(chapter_id)
    if not ch:
        avail = list(_curriculum().get("chapters", {}).keys())
        return (f"ERROR: chapter '{chapter_id}' not found.\n"
                f"Available: {avail}")

    concept_path = COURSE_ROOT / ch["concept_file"]
    if not concept_path.exists():
        return f"ERROR: concept file missing at {concept_path}"
    body = _absolutize_images(concept_path.read_text(encoding="utf-8"))

    tracks = list(ch.get("tracks", {}).keys())
    subpages = ch.get("subpages", [])
    header = [
        f"# Chapter {chapter_id}: {_chapter_title(chapter_id, ch)}   (Part {ch.get('part')})",
        f"Tracks available: {', '.join(tracks) if tracks else 'none (concept only)'}",
        f"Practicals: {ch.get('n_practicals', 0)}"
        + (f" — call list_practicals('{chapter_id}')" if ch.get('n_practicals') else ""),
    ]
    if subpages:
        header.append("Sub-pages: " + ", ".join(f"{s['num']} ({s['title']})" for s in subpages))
    footer = ["", "---",
              f"When the student is ready for hands-on: "
              + " / ".join(f"load_track('{chapter_id}', '{t}')" for t in tracks)
              if tracks else ""]
    return "\n".join(header) + "\n\n" + body + "\n" + "\n".join(footer)


@tool
def load_track(chapter_id: str, track: str) -> str:
    """
    Load the hands-on ImageJ or Python demonstration for a chapter.

    Teach it as an *illustration of the concept*, not a coding lesson: explain
    what each step shows and why, not language syntax. Python code blocks are
    kept so you can walk through what they demonstrate and, if useful, run them.

    Args:
        chapter_id: Chapter id, e.g. "1.1".
        track:      "imagej" or "python".
    """
    ch = _chapter(chapter_id)
    if not ch:
        return f"ERROR: chapter '{chapter_id}' not found."
    tracks = ch.get("tracks", {})
    if track not in tracks:
        return (f"ERROR: chapter {chapter_id} has no '{track}' track.\n"
                f"Available tracks: {list(tracks.keys()) or 'none'}")
    path = COURSE_ROOT / tracks[track]
    if not path.exists():
        return f"ERROR: track file missing at {path}"
    return _absolutize_images(path.read_text(encoding="utf-8"))


@tool
def show_figure(figure_ref: str) -> str:
    """
    Display course figures in the image viewer (Fiji/ImageJ GUI) — LARGE and
    zoomable. Each window is TITLED (e.g. "Fig 1.1-2 — image as array"); the tool
    tells you the titles it set. Images are shown ONLY in the viewer, never inline,
    so in your reply cite figures by their EXACT window title ("Look at the window
    titled 'Fig 1.1-2 — image as array' — notice …") so the student knows which of
    the open windows you mean.

    Two modes:
    * ONE figure — pass a figure id ("1.1#1"), a label ("fig-image-array"), or a
      relative asset path ("assets/1.1/gen_fig-image-array.png").
    * A WHOLE SECTION — pass a chapter id to open ALL of that section's figures at
      once: "1.1" (concept figures), or "1.1:imagej" / "1.1:python" / "1.1:all".
      Use this when you ENTER a section (after closing the previous section's
      images with close_imagej_windows(close_all_images=True)).

    Args:
        figure_ref: a figure id/label/path, OR a section spec like "1.1" or "1.1:imagej".
    """
    ref = figure_ref.strip()

    # Section form: "1.1" | "1.1:concept" | "1.1:imagej" | "1.1:python" | "1.1:all"
    if ":" in ref:
        chap, _, trk = ref.partition(":")
        chap, trk = chap.strip(), (trk.strip().lower() or "concept")
        if _chapter(chap):
            return _open_section_figures(chap, trk if trk in _SECTION_TRACKS else "concept")
    elif _chapter(ref):  # bare chapter id → open that section's concept figures
        return _open_section_figures(ref, "concept")

    idx = _load("figure_index.json") or {}

    entry = idx.get(figure_ref)
    fig_id = figure_ref if entry is not None else None
    if entry is None:  # try matching by label
        for k, v in idx.items():
            if v.get("label") == figure_ref:
                entry, fig_id = v, k
                break

    if entry is not None:
        rel = entry.get("file")
        if not rel:
            return f"Figure '{figure_ref}' is not yet rendered (caption only): {entry.get('caption','')}"
        abs_path = _abs_asset(rel)
        caption = entry.get("caption", "")
        title = _figure_label(fig_id or figure_ref, entry)
        if _open_figure_in_gui(abs_path, title=title):
            return f"Opened '{title}' in the viewer (cite it by that title).\n*{caption}*"
        return (f"Could not open the figure in the viewer (is the ImageJ/Fiji GUI up?). "
                f"Caption: {caption}")

    # treat as a direct asset path
    if (COURSE_ROOT / figure_ref).exists():
        abs_path = _abs_asset(figure_ref)
        if _open_figure_in_gui(abs_path):
            return "Opened the figure in the image viewer."
        return (f"Could not open the figure in the viewer (is the ImageJ/Fiji GUI up?): "
                f"{abs_path}")

    sample = list(idx.keys())[:10]
    return (f"ERROR: figure '{figure_ref}' not found. "
            f"Pass a figure id (e.g. {sample}), a label, or an assets/… path.")


@tool
def list_sample_images() -> str:
    """
    List the real sample images bundled with the course — Pete Bankhead's
    official "practical-data" set (Spooked.tif, Neuron-composite.tif,
    cell_outlier.tif, similar_1..4.tif, …).

    Use these as input for LIVE DEMONSTRATIONS: pass a returned absolute path to
    show_in_imagej_gui(path) to open it, or use it inside a demo script. Prefer
    these real images over synthetic arrays when a concept is easier to see on a
    genuine microscopy image.
    """
    if not SAMPLES_DIR.exists():
        return f"No sample images found (expected at {SAMPLES_DIR})."
    _IMG_EXT = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".gif",
                ".ids", ".ics", ".czi", ".lif", ".nd2", ".bmp"}
    files = sorted(
        p for p in SAMPLES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _IMG_EXT
    )
    if not files:
        return f"No sample images in {SAMPLES_DIR}."
    lines = [f"{len(files)} sample image(s) in {SAMPLES_DIR}:"]
    for p in files:
        lines.append(f"- {p.name}  ({p.stat().st_size // 1024} KB)  ->  {p}")
    return "\n".join(lines)


@tool
def list_practicals(chapter_id: str) -> str:
    """
    List a chapter's practicals — the prompts only, WITHOUT solutions — so you
    can pose them to the student and let them attempt an answer first.

    Reveal a solution with reveal_solution(practical_id) only after the student
    has tried.

    Args:
        chapter_id: Chapter id, e.g. "1.1".
    """
    practicals = [p for p in (_load("practicals.json") or []) if p["chapter"] == chapter_id]
    if not practicals:
        return f"No practicals for chapter {chapter_id}."
    out = [f"{len(practicals)} practical(s) for chapter {chapter_id}:"]
    for p in practicals:
        out.append(f"\n[{p['id']}] (track: {p['track']})\n{p['prompt']}")
    out.append("\nAfter the student attempts one, call reveal_solution(practical_id).")
    return "\n".join(out)


@tool
def reveal_solution(practical_id: str) -> str:
    """
    Reveal the solution to a practical — only after the student has attempted it.

    Args:
        practical_id: Practical id from list_practicals, e.g. "1.1-p1".
    """
    p = next((p for p in (_load("practicals.json") or []) if p["id"] == practical_id), None)
    if not p:
        return f"ERROR: practical '{practical_id}' not found."
    return f"Solution to {practical_id}:\n{p['solution']}"


# ── progress + mode tools (state-updating) ──────────────────────────────────

@tool
def update_course_progress(
    chapter_id: str,
    status: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    note: str = "",
) -> Command:
    """
    Record the student's progress after teaching a chapter. Persists per-chat.

    Call after the student confirms they've understood a chapter (status=
    "completed"), or when you start one (status="studying"). Progress is shown
    back to you in your prompt each turn, so you always know where you left off.

    Args:
        chapter_id: Chapter just taught/started, e.g. "1.1".
        status:     "studying" or "completed".
        note:       Optional short note about the student (struggles, interests).
    """
    # Deep-copy, not dict(): a shallow copy would alias the "completed"/"notes"
    # LISTS held in graph state, so the appends below would mutate the checkpointed
    # value in place before (and regardless of whether) this Command is applied.
    prog = copy.deepcopy(state.get("course_progress") or {})
    prog.setdefault("completed", [])
    prog.setdefault("notes", [])
    prog["current"] = chapter_id
    if status == "completed" and chapter_id not in prog["completed"]:
        prog["completed"].append(chapter_id)
    if note:
        prog["notes"].append({"chapter": chapter_id, "note": note})

    msg = f"Progress saved: chapter {chapter_id} → {status}. Completed: {prog['completed']}"
    return Command(update={
        "course_progress": prog,
        "messages": [ToolMessage(msg, tool_call_id=tool_call_id)],
    })


@tool
def set_course_plan(
    chapter_ids: list[str],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """
    Set a custom course: an ordered list of chapter ids to teach (a subset of the
    full curriculum). Use when the student wants only certain topics. Pass [] to
    clear it and teach the full curriculum.

    Args:
        chapter_ids: Ordered chapter ids, e.g. ["1.1", "1.3", "2.3"].
    """
    valid = set(_curriculum().get("chapters", {}).keys())
    unknown = [c for c in chapter_ids if c not in valid]
    if unknown:
        return Command(update={"messages": [ToolMessage(
            f"ERROR: unknown chapter ids {unknown}. Call list_curriculum first.",
            tool_call_id=tool_call_id)]})
    label = " → ".join(chapter_ids) if chapter_ids else "(full curriculum)"
    return Command(update={
        "course_plan": chapter_ids,
        "messages": [ToolMessage(f"Course plan set: {label}", tool_call_id=tool_call_id)],
    })


@tool
def set_mode(mode: str, tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """
    Switch the agent's operating mode for this chat.

    - "advanced":  full multi-phase image-analysis pipeline (planning, coding,
                   statistics, QA) — for real analysis projects.
    - "quick":     fast single-operation image processing, minimal ceremony.
    - "education":  tutor mode — teach bioimage-analysis concepts from the course.

    Switch when the user's intent clearly changes (e.g. "teach me about
    thresholding" → education; "now threshold my images" → quick/advanced).

    Args:
        mode: one of "advanced", "quick", "education".
    """
    if mode not in VALID_MODES:
        return Command(update={"messages": [ToolMessage(
            f"ERROR: invalid mode '{mode}'. Choose one of {VALID_MODES}.",
            tool_call_id=tool_call_id)]})
    return Command(update={
        "mode": mode,
        "messages": [ToolMessage(f"Mode switched to '{mode}'.", tool_call_id=tool_call_id)],
    })
