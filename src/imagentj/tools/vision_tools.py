"""
vision.py — Vision tools for the VLM judge agent.

  capture_ij_window   → saves a named open IJ window as PNG via PyImageJ/scyjava
  build_mask_overlay  → overlays a segmentation mask on its source image
  build_compilation   → fuses multiple images into a labelled side-by-side panel
  analyze_image       → resizes to ≤1024 px and sends to the configured vision LLM

Comparison workflow:
    path1 = capture_ij_window("raw_DAPI.tif")
    path2 = capture_ij_window("mask_DAPI.tif")
    comp  = build_compilation([path1, path2], ["Original", "Segmentation"])
    result = analyze_image(comp, "Do the segmentation outlines tightly follow
                                  each nucleus without merging adjacent cells?")
"""

from __future__ import annotations

import base64
import concurrent.futures
import contextlib
import io
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

from imagentj.imagej_context import needs_bioformats, open_image_windowless

# ── Config ────────────────────────────────────────────────────────────────────

_log = logging.getLogger(__name__)

_MAX_PX          = 1024   # longest side cap applied to the final compilation

# Hard ceiling on a single Fiji open. `IJ.open` is a synchronous JVM round-trip
# with no timeout of its own: if the opener stalls — an unexpected reader, a
# dialog waiting on input, a format Bio-Formats chokes on — it simply never
# returns, and because the VLM judge calls it inline that wedges the ENTIRE
# agent, not just the visual check. Observed in benchmarking: 29 minutes of a
# completely idle process, killed from outside, with all deliverables already
# written. Generous enough for a large 3D stack over a slow mount; finite so a
# stuck open degrades into a skipped visual check instead of a dead run.
_FIJI_OPEN_TIMEOUT_S = float(os.environ.get("IMAGENTJ_FIJI_OPEN_TIMEOUT", "180"))

# One reusable worker so a timed-out open (whose thread we can never reclaim —
# it is blocked in the JVM) does not leak an unbounded number of threads.
_fiji_open_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="fiji-open"
)


# Fiji's WindowManager is process-global mutable state and its display stack is
# not thread-safe, but nothing stopped two agent threads entering the capture
# path at once — the supervisor and a subagent both reaching for a visual check,
# for instance. That went wrong in two distinct ways.
#
# The visible one: the process froze completely. Two benchmark tasks (b04 of the
# v4 run, b14 of the w2 run) burned their entire 60-minute cap with ZERO log
# output — not one DEBUG line — after their last vision call, and were killed
# from outside with all deliverables already on disk. In both, every HTTP body
# that had been opened had also completed (104/104 and 99/99), so the network was
# idle: the freeze was local, inside the JVM. Both wrote two preview PNGs of
# IDENTICAL size 2.0 ms and 17.2 ms apart — far too fast to be two sequential
# tool calls, each of which needs an API round trip, so two threads were
# genuinely inside the capture at once.
#
# The quiet one: `capture_image_file_via_fiji` identifies its new window by
# diffing WindowManager ids before and after IJ.open. That diff is only correct
# if no other thread opens a window in between; concurrently, two captures can
# claim each other's windows and each save the wrong image — which is the most
# likely reason both frozen runs produced byte-identical previews.
#
# So every JVM-touching vision section runs under one lock, taken with a
# deadline. The deadline matters as much as the lock: if a previous caller has
# already wedged the JVM, waiting forever to enter would spread one stuck call
# into a stuck agent. Timing out instead degrades to a skipped visual check,
# which is the same trade `_FIJI_OPEN_TIMEOUT_S` already makes for IJ.open.
_JVM_VISION_LOCK = threading.RLock()
_VISION_LOCK_TIMEOUT_S = float(os.environ.get("IMAGENTJ_VISION_LOCK_TIMEOUT", "240"))


class _VisionBusy(RuntimeError):
    """Raised when the JVM vision section could not be entered in time."""


@contextlib.contextmanager
def _jvm_vision_section(what: str):
    """Serialize a JVM-touching vision operation, with a bounded wait."""
    if not _JVM_VISION_LOCK.acquire(timeout=_VISION_LOCK_TIMEOUT_S):
        _log.warning("vision: %s waited %.0fs for the JVM lock and gave up",
                     what, _VISION_LOCK_TIMEOUT_S)
        raise _VisionBusy(
            f"another visual operation has held the Fiji/JVM lock for more than "
            f"{_VISION_LOCK_TIMEOUT_S:.0f}s, so '{what}' was skipped rather than "
            f"blocking the agent behind it."
        )
    try:
        yield
    finally:
        _JVM_VISION_LOCK.release()


def _attach_to_jvm() -> None:
    """Attach the calling thread to the JVM.

    Any thread that touches the JVM must be attached to it first — a pool worker
    is created outside PyImageJ's knowledge, so without this the call raises
    instead of opening. Mirrors the attach done in gui_runner and the benchmark
    dialog dismisser.

    Kept separate from _ij_open_blocking because the Bio-Formats route
    (open_image_windowless) runs on the same pool threads and jimports its own
    Java classes, so it needs the identical attach — folding this into only the
    IJ.open path would leave that route raising on the very formats it exists to
    handle.
    """
    try:
        import jpype
        if jpype.isJVMStarted() and not jpype.isThreadAttachedToJVM():
            jpype.attachThreadToJVM()
    except Exception:
        # No jpype, or already attached under a different binding — the caller
        # below will surface any real problem.
        _log.debug("Could not attach pool thread to the JVM", exc_info=True)


def _ij_open_blocking(IJ, path: str) -> None:
    """Call ``IJ.open`` from a pool thread."""
    _attach_to_jvm()
    IJ.open(path)

_CAPTURE_DIR = Path(os.environ.get("CHAT_DATA_PATH", "/app/data/chats")) / "vlm_captures"
_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

# Only intrinsically 2D display formats are read directly.  Bioimage containers
# (TIFF, CZI, LIF, ND2, OME-Zarr, ...) first go through Fiji so its reader owns
# dimensionality, precision, LUT, and display-plane selection.
_SUPPORTED_FORMATS = {
    ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
}

_LABEL_HEIGHT = 24   # px reserved above each panel for the text label
_LABEL_COLOR  = (255, 255, 255)
_BG_COLOR     = (30, 30, 30)

_llm = None  # injected by agents.py


# ── Helpers ───────────────────────────────────────────────────────────────────



def set_vision_llm(llm):
    global _llm
    _llm = llm

def _get_ij_classes():
    try:
        import scyjava
        return scyjava.jimport("ij.WindowManager"), scyjava.jimport("ij.IJ")
    except Exception as e:
        raise RuntimeError(f"scyjava import failed — is PyImageJ initialised? {e}")


def _to_rgb(img: Image.Image) -> Image.Image:
    """Convert a microscopy image to a visible 8-bit RGB preview.

    PIL's direct ``I;16``/float-to-RGB conversion clips values above 255, which
    turns many 16-bit microscopy images into nearly solid white previews.  Use
    robust percentile scaling for non-8-bit arrays so the VLM sees the same
    structures a user would see after applying display contrast in Fiji.
    """
    if img.mode in ("RGB", "RGBA", "L") and np.asarray(img).dtype == np.uint8:
        return img.convert("RGB")

    arr = np.asarray(img)
    if arr.ndim == 3 and arr.shape[-1] == 4:
        arr = arr[..., :3]

    finite = np.isfinite(arr)
    if not finite.any():
        scaled = np.zeros(arr.shape, dtype=np.uint8)
    else:
        values = arr[finite].astype(np.float64, copy=False)
        low, high = np.percentile(values, (1.0, 99.8))
        if high <= low:
            low, high = float(values.min()), float(values.max())
        if high <= low:
            scaled = np.zeros(arr.shape, dtype=np.uint8)
        else:
            scaled = np.clip((arr.astype(np.float64) - low) * 255.0 / (high - low), 0, 255)
            scaled[~finite] = 0
            scaled = scaled.astype(np.uint8)

    if scaled.ndim == 2:
        return Image.fromarray(scaled, mode="L").convert("RGB")
    if scaled.ndim == 3 and scaled.shape[-1] >= 3:
        return Image.fromarray(scaled[..., :3], mode="RGB")
    raise ValueError(f"Unsupported image shape for preview: {scaled.shape}")


def _resize_and_encode(img: Image.Image) -> tuple[str, tuple[int, int], tuple[int, int]]:
    img = _to_rgb(img)
    orig = img.size
    w, h = orig
    if max(w, h) > _MAX_PX:
        scale = _MAX_PX / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    sent = img.size
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8"), orig, sent


def _dim_note(orig: tuple[int, int], sent: tuple[int, int]) -> str:
    if sent == orig:
        return f"[Image: {orig[0]}×{orig[1]} px — original resolution]"
    return f"[Image: {orig[0]}×{orig[1]} px → sent as {sent[0]}×{sent[1]} px (capped at {_MAX_PX} px)]"


def _call_vision_api(image_b64: str, question: str) -> str:
    if _llm is None:
        return "ERROR: vision LLM not initialised. Call set_vision_llm() first."
    msg = HumanMessage(content=[
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        {"type": "text", "text": question},
    ])
    try:
        content = _llm.invoke([msg]).content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict) and block.get("text"):
                    text_parts.append(str(block["text"]))
            return "\n".join(text_parts) or str(content)
        return str(content)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

def _load_image(path: Path) -> Image.Image:
    """Load and normalise to RGB regardless of bit depth."""
    img = Image.open(path)
    return _to_rgb(img)


def _capture_path(prefix: str) -> Path:
    """Return a collision-resistant path for concurrently generated previews."""
    return _CAPTURE_DIR / f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns()}.png"


def _image_window_ids(WindowManager) -> set[int]:
    """Snapshot the IDs of open ImageJ image windows."""
    try:
        ids = WindowManager.getIDList()
        return {int(image_id) for image_id in list(ids)} if ids is not None else set()
    except Exception:
        return set()


def _try_get_font(size: int = 14) -> ImageFont:
    """Return a truetype font if available, fall back to default."""
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def capture_ij_window(window_name: str, label: Optional[str] = None) -> str:
    """
    Save a named open ImageJ window as a PNG file using the IJ Java API via scyjava.

    Calls WindowManager.getImage(window_name) and IJ.saveAs(imp, "PNG", path) directly
    from Python — no Groovy scripts, no screen capture. Saves actual pixel data including
    LUT colours and visible overlays (ROI outlines, labels). Bioimage files that
    are not already open should use ``prepare_image_source_for_vlm`` first.

    Supported output format: PNG only.

    Args:
        window_name: Exact ImageJ window title, e.g. "MAX_DAPI.tif", "mask_nuclei.tif".
                     Use inspect_all_ui_windows() if the title is uncertain.
        label:       Optional filename suffix for traceability, e.g. "after_threshold".

    Returns:
        Absolute path to the saved PNG, or "ERROR: ..." with open window titles on failure.
    """
    suffix    = f"_{label}" if label else ""
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in window_name)
    out_path  = _capture_path(f"{safe_name}{suffix}")

    try:
        WindowManager, IJ = _get_ij_classes()
    except RuntimeError as e:
        return f"ERROR: {e}"

    # getImage/duplicate/saveAs all touch the shared display stack, so they must
    # be one atomic section — see _jvm_vision_section.
    try:
        with _jvm_vision_section(f"capture_ij_window({window_name!r})"):
            imp = WindowManager.getImage(window_name)
            if imp is None:
                return (
                    f"ERROR: Window not found: '{window_name}'. "
                    f"Open windows: {list(WindowManager.getImageTitles())}"
                )
            IJ.saveAs(imp.duplicate(), "PNG", str(out_path))
    except _VisionBusy as e:
        return f"ERROR: {e}"
    except Exception as e:
        return f"ERROR: IJ.saveAs failed — {type(e).__name__}: {e}"

    if not out_path.exists():
        return f"ERROR: saveAs ran but file not created at {out_path}."

    return str(out_path)


@tool
def capture_image_file_via_fiji(image_path: str) -> str:
    """Open a bioimage source in Fiji, export its displayed plane, and clean up.

    This is the second level of the VLM input fallback.  Fiji's normal ``IJ.open``
    dispatch is used so installed readers such as Bio-Formats can handle formats
    beyond PNG/JPEG.  Only image windows created by this call are closed; windows
    that were already open are never touched.

    The resulting PNG represents Fiji's initially displayed C/Z/T plane (and its
    LUT), not an automatic projection or a complete review of a stack/time series.

    Args:
        image_path: Existing file or dataset path to ask Fiji to open. Directory
                    datasets such as OME-Zarr are attempted and depend on an
                    installed Fiji reader that accepts the directory path.

    Returns:
        Absolute path to a PNG preview, or ``ERROR: ...``.
    """
    source = Path(image_path).expanduser()
    if not source.exists():
        return f"ERROR: File or dataset not found — {image_path}"

    try:
        WindowManager, IJ = _get_ij_classes()
    except RuntimeError as exc:
        return f"ERROR: {exc}"

    out_path = _capture_path("fiji_preview")

    # The whole open-diff-save-close sequence is one section. Holding the lock
    # only around IJ.open would leave the before/after window diff below racing
    # any other thread's open, which is how two concurrent captures end up
    # claiming each other's windows.
    try:
        _vision_lock_cm = _jvm_vision_section(f"fiji_preview({source.name})")
        _vision_lock_cm.__enter__()
    except _VisionBusy as e:
        return f"ERROR: {e}"

    before_ids = _image_window_ids(WindowManager)
    new_ids: set[int] = set()
    duplicate = None

    try:
        # IJ.open follows Fiji's normal opener/plugin dispatch. In a Fiji
        # installation this includes Bio-Formats for its registered formats —
        # but for those it takes the PROMPTING path, building a modal importer
        # dialog that cannot be answered under Xvfb and throws/retries forever
        # (see imagej_context.open_image_windowless). Route those around it.
        #
        # Both routes still run on a worker with a deadline. Avoiding the modal
        # dialog removes the KNOWN cause of a wedged open; the deadline covers
        # the rest (an unexpected reader, a slow mount, a format Bio-Formats
        # chokes on). Neither call is cancellable — once the JVM blocks, that
        # thread is gone for the life of the process — so on timeout we abandon
        # it (bounded pool, so leakage is capped) and return an error. Skipping
        # one visual check is far better than freezing the agent that asked.
        resolved = str(source.resolve())

        def _open() -> None:
            if needs_bioformats(resolved):
                _attach_to_jvm()          # BF.openImagePlus jimports on this thread
                if not open_image_windowless(resolved, show=True):
                    raise RuntimeError(
                        f"Bio-Formats returned no image for '{source}'."
                    )
            else:
                _ij_open_blocking(IJ, resolved)

        try:
            _fiji_open_pool.submit(_open).result(timeout=_FIJI_OPEN_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            _log.warning("Fiji open timed out after %.0fs: %s",
                         _FIJI_OPEN_TIMEOUT_S, source)
            return (
                f"ERROR: Fiji did not finish opening '{source}' within "
                f"{_FIJI_OPEN_TIMEOUT_S:.0f}s and was abandoned. The reader may be "
                "waiting on an import dialog or the format may be unsupported. "
                "Skip the visual check for this source, or pass a PNG/JPG preview."
            )
        except RuntimeError as exc:
            return f"ERROR: {exc}"
        new_ids = _image_window_ids(WindowManager) - before_ids
        if not new_ids:
            return (
                "ERROR: Fiji did not create a new image window for "
                f"'{source}'. The format may need a reader/import option, or the "
                "opener may have shown a dialog instead. Existing windows were left untouched."
            )

        current = WindowManager.getCurrentImage()
        try:
            current_id = int(current.getID()) if current is not None else None
        except Exception:
            current_id = None
        selected_id = current_id if current_id in new_ids else sorted(new_ids)[-1]
        imp = WindowManager.getImage(selected_id)
        if imp is None:
            return "ERROR: Fiji opened the source but no new ImagePlus could be selected."

        duplicate = imp.duplicate()
        IJ.saveAs(duplicate, "PNG", str(out_path))
        if not out_path.exists():
            return f"ERROR: Fiji opened the source but did not create preview {out_path}."
        return str(out_path)
    except Exception as exc:
        return f"ERROR: Fiji could not prepare a VLM preview — {type(exc).__name__}: {exc}"
    finally:
        if duplicate is not None:
            try:
                duplicate.changes = False
                duplicate.close()
            except Exception:
                pass

        # Re-snapshot in case the opener created more than one series/window.
        opened_ids = _image_window_ids(WindowManager) - before_ids
        for image_id in opened_ids | new_ids:
            try:
                opened = WindowManager.getImage(image_id)
                if opened is not None:
                    opened.changes = False
                    opened.close()
            except Exception:
                pass

        # Released only after the windows this call created are closed, so the
        # next caller's before/after diff starts from a clean stack.
        _vision_lock_cm.__exit__(None, None, None)


@tool
def prepare_image_source_for_vlm(image_source: str) -> str:
    """Resolve one VLM source using a two-level input fallback.

    Existing PNG/JPG/JPEG files pass through unchanged. Every other existing
    file or dataset path is opened and captured through Fiji. A non-path string
    remains unchanged so the VLM judge can treat it as an already-open ImageJ
    window title and use ``capture_ij_window`` as before.
    """
    if not isinstance(image_source, str) or not image_source.strip():
        return "ERROR: image_source must be a non-empty string."

    source_text = image_source.strip()
    source = Path(source_text).expanduser()
    if source.exists():
        if source.is_file() and source.suffix.lower() in _SUPPORTED_FORMATS:
            return str(source.resolve())
        return capture_image_file_via_fiji.invoke({"image_path": str(source)})

    # Match the VLM protocol: strings containing a path separator are paths;
    # other strings are existing Fiji window titles.
    separators = {os.path.sep}
    if os.path.altsep:
        separators.add(os.path.altsep)
    if any(separator in source_text for separator in separators):
        return f"ERROR: File or dataset not found — {source_text}"
    return source_text


@tool
def build_mask_overlay(
    original_path: str,
    mask_path: str,
    opacity: float = 0.35,
    color: str = "magenta",
) -> str:
    """Create a transparent segmentation-mask overlay for visual judging.

    Every non-zero mask pixel is treated as foreground.  The source and mask
    must have the same XY dimensions; a mismatch is reported instead of being
    silently resized because misregistration is itself a segmentation failure.
    The original files are never modified.

    Args:
        original_path: Absolute path to the raw/source image.
        mask_path: Absolute path to the binary or labelled segmentation mask.
        opacity: Foreground tint opacity in the inclusive range 0..1.
        color: Overlay colour: magenta, red, green, cyan, yellow, or blue.

    Returns:
        Absolute path to a PNG overlay, or an ``ERROR: ...`` string.
    """
    colors = {
        "magenta": (255, 0, 255),
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "cyan": (0, 255, 255),
        "yellow": (255, 255, 0),
        "blue": (0, 128, 255),
    }
    if color.lower() not in colors:
        return f"ERROR: Unsupported overlay color '{color}'. Choose from: {', '.join(colors)}."
    if not 0.0 <= opacity <= 1.0:
        return "ERROR: opacity must be between 0 and 1."

    original = Path(original_path)
    mask = Path(mask_path)
    for role, path in (("Original", original), ("Mask", mask)):
        if not path.exists():
            return f"ERROR: {role} file not found — {path}"
        if path.suffix.lower() not in _SUPPORTED_FORMATS:
            return f"ERROR: Unsupported {role.lower()} format '{path.suffix}'."

    try:
        base = _load_image(original)
        mask_img = Image.open(mask)
        mask_arr = np.asarray(mask_img)
        if mask_arr.ndim == 3:
            foreground = np.any(mask_arr != 0, axis=-1)
        elif mask_arr.ndim == 2:
            foreground = mask_arr != 0
        else:
            return f"ERROR: Unsupported mask shape {mask_arr.shape}. Expected a 2D mask."
    except Exception as exc:
        return f"ERROR: Could not load overlay inputs — {type(exc).__name__}: {exc}"

    expected_shape = (base.height, base.width)
    if foreground.shape != expected_shape:
        return (
            "ERROR: Original/mask dimensions do not match — "
            f"original={base.width}×{base.height}, mask={foreground.shape[1]}×{foreground.shape[0]}."
        )

    mask_l = Image.fromarray((foreground.astype(np.uint8) * 255), mode="L")
    tint = Image.new("RGB", base.size, colors[color.lower()])
    tinted = Image.blend(base, tint, opacity)
    overlay = Image.composite(tinted, base, mask_l)
    out_path = _capture_path("mask_overlay")
    overlay.save(out_path, format="PNG")
    return str(out_path)


@tool
def build_compilation(
    image_paths: list[str],
    labels: Optional[list[str]] = None,
) -> str:
    """
    Fuse multiple images into a single labelled side-by-side panel for VLM comparison.

    Sending images as a compilation is far more effective than sending them separately
    because the VLM can directly compare spatial relationships — e.g. whether a
    segmentation outline follows the original structure, or whether two conditions differ.

    All input images are scaled to the same height before stitching.
    The final panel is resized to ≤1024 px on the longest side before any API call.
    A dark label bar above each panel shows the supplied caption.

    Typical use cases:
        Original vs segmentation:
            build_compilation(["raw.png", "mask.png"], ["Original", "Segmentation"])
        Before vs after preprocessing:
            build_compilation(["raw.png", "denoised.png"], ["Raw", "Denoised"])
        Multi-condition comparison:
            build_compilation(["ctrl.jpg", "treated.jpg"], ["Control", "Treated"])
        Three-panel (raw / mask / overlay):
            build_compilation(["raw.png", "mask.png", "overlay.png"],
                              ["Raw", "Mask", "Overlay"])

    Supported input formats: .png, .jpg, .jpeg. Bioimage containers must first
    be converted with ``prepare_image_source_for_vlm``.
    Output: PNG saved to the vlm_captures directory.

    Args:
        image_paths: Ordered list of absolute image paths to include as panels.
                     2–4 images recommended; beyond 4 panels the per-panel
                     resolution after the 1024 px cap becomes too small to judge.
        labels:      Optional caption for each panel (same order as image_paths).
                     If omitted, panels are labelled "Image 1", "Image 2", etc.

    Returns:
        Absolute path to the compiled PNG, ready to pass to analyze_image.
        Or "ERROR: ..." if any input file is missing or unsupported.
    """
    if not image_paths:
        return "ERROR: image_paths is empty."

    # Validate all paths upfront before doing any work
    paths = []
    for p in image_paths:
        path = Path(p)
        if not path.exists():
            return f"ERROR: File not found — {p}"
        if path.suffix.lower() not in _SUPPORTED_FORMATS:
            return (
                f"ERROR: Unsupported format '{path.suffix}' for {p}. "
                f"Accepted: {', '.join(sorted(_SUPPORTED_FORMATS))}."
            )
        paths.append(path)

    captions = labels if labels else [f"Image {i+1}" for i in range(len(paths))]
    if len(captions) < len(paths):
        captions += [f"Image {i+1}" for i in range(len(captions), len(paths))]

    # Load and normalise all images
    imgs = [_load_image(p) for p in paths]

    # Scale all panels to the same height (tallest image wins)
    target_h = max(img.height for img in imgs)
    resized = []
    for img in imgs:
        if img.height != target_h:
            scale = target_h / img.height
            img = img.resize(
                (max(1, int(img.width * scale)), target_h), Image.LANCZOS
            )
        resized.append(img)

    # Build the canvas: panels side by side, label bar on top of each
    panel_h   = target_h + _LABEL_HEIGHT
    total_w   = sum(img.width for img in resized)
    canvas    = Image.new("RGB", (total_w, panel_h), _BG_COLOR)
    draw      = ImageDraw.Draw(canvas)
    font      = _try_get_font(14)

    x_offset = 0
    for img, caption in zip(resized, captions):
        # Paste image below the label bar
        canvas.paste(img, (x_offset, _LABEL_HEIGHT))
        # Draw label centred above the panel
        try:
            bbox = font.getbbox(caption)
            text_w = bbox[2] - bbox[0]
        except AttributeError:
            text_w = len(caption) * 7  # rough fallback for default font
        text_x = x_offset + (img.width - text_w) // 2
        draw.text((text_x, 4), caption, fill=_LABEL_COLOR, font=font)
        x_offset += img.width

    out_path = _capture_path("compilation")
    canvas.save(out_path, format="PNG")

    return str(out_path)


@tool
def analyze_image(image_path: str, question: str) -> str:
    """
    Send an image file to the configured vision LLM and return its analysis.

    Images are downsampled to ≤1024 px on the longest side before sending
    (aspect ratio preserved, originals untouched, no upscaling).
    Inputs are normalised to 8-bit RGB PNG before the API call. Bioimage
    containers and higher-precision data must first pass through Fiji via
    ``prepare_image_source_for_vlm``.

    Supported input formats:
        .png              — lossless; default output of capture_ij_window / build_compilation
        .jpg / .jpeg      — lossy; fine for structural checks (scale bar, focus, colors)

    For comparison tasks (original vs segmentation, before vs after), always use
    build_compilation first to fuse the images into a single panel before calling
    this tool — it gives the VLM direct spatial reference between the images.

    Args:
        image_path: Absolute path to a prepared .png, .jpg, or .jpeg image.
        question:   One specific, falsifiable question per call. Include what you
                    expect to see so the model can confirm or deny. Examples:
                      "Left panel is the original, right is the segmentation.
                       Do the outlines tightly follow each nucleus without merging?"
                      "Is a scale bar present? If yes, copy its label text exactly."
                      "Does the binary mask show clean white objects on black background?"

    Returns:
        Vision model response prefixed with a dimension note, e.g.:
            [Image: 2048×512 px → sent as 1024×256 px (capped at 1024 px)]
        Or "ERROR: ..." on failure.
    """
    path = Path(image_path)

    if not path.exists():
        return f"ERROR: File not found — {image_path}"

    if path.suffix.lower() not in _SUPPORTED_FORMATS:
        return (
            f"ERROR: Unsupported format '{path.suffix}'. "
            f"Accepted: {', '.join(sorted(_SUPPORTED_FORMATS))}. "
            "Resolve bioimage containers through Fiji first."
        )

    try:
        img             = Image.open(path)
        b64, orig, sent = _resize_and_encode(img)
    except Exception as e:
        return f"ERROR: Could not load image — {type(e).__name__}: {e}"

    response = _call_vision_api(b64, question)
    if response.startswith("ERROR:"):
        return response

    return f"{_dim_note(orig, sent)}\n\n{response}"
