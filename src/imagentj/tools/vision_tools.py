"""
vision.py — Vision tools for the VLM judge agent.

  capture_ij_window   → saves a named open IJ window as PNG via PyImageJ/scyjava
  build_compilation   → fuses multiple images into a labelled side-by-side panel
  analyze_image       → resizes to ≤1024 px and sends to a vision LLM via OpenAI

Comparison workflow:
    path1 = capture_ij_window("raw_DAPI.tif")
    path2 = capture_ij_window("mask_DAPI.tif")
    comp  = build_compilation([path1, path2], ["Original", "Segmentation"])
    result = analyze_image(comp, "Do the segmentation outlines tightly follow
                                  each nucleus without merging adjacent cells?")
"""

import base64
import io
import os
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# ── Config ────────────────────────────────────────────────────────────────────

_OPENAI_KEY   = os.getenv("OPENAI_API_KEY", "")
_VISION_MODEL = "gpt-4o"
_MAX_PX       = 1024   # longest side cap applied to the final compilation

_CAPTURE_DIR = Path(os.environ.get("CHAT_DATA_PATH", "/app/data/chats")) / "vlm_captures"
_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

_SUPPORTED_FORMATS = {
    ".png": "image/png", ".tif": "image/tiff", ".tiff": "image/tiff",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
}

_LABEL_HEIGHT = 24   # px reserved above each panel for the text label
_LABEL_COLOR  = (255, 255, 255)
_BG_COLOR     = (30, 30, 30)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_ij_classes():
    try:
        import scyjava
        return scyjava.jimport("ij.WindowManager"), scyjava.jimport("ij.IJ")
    except Exception as e:
        raise RuntimeError(f"scyjava import failed — is PyImageJ initialised? {e}")


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


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
    if not _OPENAI_KEY:
        return "ERROR: OPENAI_API_KEY not set."
    try:
        llm = ChatOpenAI(model=_VISION_MODEL, api_key=_OPENAI_KEY, max_tokens=1024)
        msg = HumanMessage(content=[
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            {"type": "text", "text": question},
        ])
        return llm.invoke([msg]).content
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def _load_image(path: Path) -> Image.Image:
    """Load and normalise to RGB regardless of bit depth."""
    img = Image.open(path)
    return _to_rgb(img)


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
    LUT colours and visible overlays (ROI outlines, labels). For raw 16-bit values,
    use the .tif saved by the Groovy script with analyze_image instead.

    Supported output format: PNG only.

    Args:
        window_name: Exact ImageJ window title, e.g. "MAX_DAPI.tif", "mask_nuclei.tif".
                     Use inspect_all_ui_windows() if the title is uncertain.
        label:       Optional filename suffix for traceability, e.g. "after_threshold".

    Returns:
        Absolute path to the saved PNG, or "ERROR: ..." with open window titles on failure.
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    suffix    = f"_{label}" if label else ""
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in window_name)
    out_path  = _CAPTURE_DIR / f"{safe_name}_{timestamp}{suffix}.png"

    try:
        WindowManager, IJ = _get_ij_classes()
    except RuntimeError as e:
        return f"ERROR: {e}"

    imp = WindowManager.getImage(window_name)
    if imp is None:
        return (
            f"ERROR: Window not found: '{window_name}'. "
            f"Open windows: {list(WindowManager.getImageTitles())}"
        )

    try:
        IJ.saveAs(imp.duplicate(), "PNG", str(out_path))
    except Exception as e:
        return f"ERROR: IJ.saveAs failed — {type(e).__name__}: {e}"

    if not out_path.exists():
        return f"ERROR: saveAs ran but file not created at {out_path}."

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
            build_compilation(["raw.tif", "denoised.tif"], ["Raw", "Denoised"])
        Multi-condition comparison:
            build_compilation(["ctrl.tif", "treated.tif"], ["Control", "Treated"])
        Three-panel (raw / mask / overlay):
            build_compilation(["raw.png", "mask.png", "overlay.png"],
                              ["Raw", "Mask", "Overlay"])

    Supported input formats: .png, .tif, .tiff, .jpg, .jpeg
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

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path  = _CAPTURE_DIR / f"compilation_{timestamp}.png"
    canvas.save(out_path, format="PNG")

    return str(out_path)


@tool
def analyze_image(image_path: str, question: str) -> str:
    """
    Send an image file to a vision LLM via OpenRouter and return its analysis.

    Images are downsampled to ≤1024 px on the longest side before sending
    (aspect ratio preserved, originals untouched, no upscaling).
    All formats are normalised to 8-bit RGB PNG before the API call —
    16-bit and 32-bit TIFFs are handled transparently.

    Supported input formats:
        .png              — lossless; default output of capture_ij_window / build_compilation
        .tif / .tiff      — standard IJ output; preferred for quantitative checks
        .jpg / .jpeg      — lossy; fine for structural checks (scale bar, focus, colors)

    For comparison tasks (original vs segmentation, before vs after), always use
    build_compilation first to fuse the images into a single panel before calling
    this tool — it gives the VLM direct spatial reference between the images.

    Args:
        image_path: Absolute path to the image. Accepted: .png, .tif, .tiff, .jpg, .jpeg
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
            f"Convert to TIFF or PNG in your Groovy script first."
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