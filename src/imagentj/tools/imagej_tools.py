import base64
import io
import json
import os
from langchain.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from imagentj.imagej_context import get_ij
from .metadata_tools import extract_file_metadata

_DIALOG_VISION_SYSTEM = """You are an ImageJ/Fiji expert analysing a screenshot of a plugin dialog window.

Your task: extract every interactive element visible in the dialog so that an AI agent
can give the user precise, field-by-field parameter guidance.

Return a JSON object with these fields:

- dialog_title : string — the window title bar text
- fields : list of objects, one per visible interactive element:
    {
      "label":         string  — the exact text label shown next to the element,
      "type":          string  — "text_input" | "number_input" | "dropdown" | "checkbox" |
                                 "radio_button" | "slider" | "button" | "tab" | "label_only",
      "current_value": string  — the value currently shown (empty string if blank),
      "options":       list    — dropdown/radio options if visible, else [],
      "description":   string  — brief plain-English description of what this parameter controls
    }
- buttons : list of button labels visible at the bottom (e.g. ["OK", "Cancel", "Help"])
- warnings : list of any warning or info text visible in the dialog (empty list if none)

Be exhaustive — include every field, checkbox, and dropdown visible, in top-to-bottom order.
Do not guess values that are not visible in the screenshot."""

_vision_llm = None

def _get_vision_llm():
    global _vision_llm
    if _vision_llm is None:
        _vision_llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    return _vision_llm


@tool
def ask_user(prompt: str) -> str:
    """
    Ask the user a question and return their input.
    Always ask in a way that a biologists without programming experience can understand.
    """
    return input(f"🖐 USER INPUT REQUIRED: {prompt}\n> ")


@tool
def load_image_ij(path: str)  -> object:
    """Load an image from a given path using ImageJ.

    Args:
        path (str): The file path to the image.

    Returns:
        [].
    """

    global image

    ij = get_ij()

    image = ij.io().open(path)
    return "Loaded image from " + path


@tool
def inspect_all_ui_windows():
    """
    Inspect everything visible in the ImageJ UI:
    1. Image Windows (title, file path, dimensions, bit depth, min/max stats)
    2. Results Tables (row/column counts)
    3. ROI Manager (ROI count)
    4. Log Window (full text content — use this when the user reports a console error)
    5. Exception/Error Windows (full stack trace text)

    Call this whenever the user mentions an error in the console or exception window,
    or to verify what is currently open in Fiji.
    """
    ij = get_ij()

    # Correct way to import Java classes in PyImageJ
    from scyjava import jimport
    WindowManager = jimport('ij.WindowManager')
    ResultsTable = jimport('ij.measure.ResultsTable')
    RoiManager = jimport('ij.plugin.frame.RoiManager')
    Frame = jimport('java.awt.Frame')

    all_inspections = {
        "images": [],
        "tables_and_text": []
    }

    # --- 1. Inspect Image Windows ---
    image_ids = WindowManager.getIDList()
    if image_ids:
        for img_id in image_ids:
            imp = WindowManager.getImage(img_id)
            try:
                # Resolve the on-disk path so the agent can pass it to other tools
                file_path = None
                file_path_note = None
                try:
                    fi = imp.getOriginalFileInfo()
                    if fi is not None and fi.directory and fi.fileName:
                        import os as _os
                        candidate = _os.path.join(str(fi.directory), str(fi.fileName))
                        if _os.path.exists(candidate):
                            file_path = candidate
                        else:
                            file_path_note = f"path from ImageJ ({candidate}) does not exist on disk — ask the user for the actual file location"
                except Exception:
                    pass

                # Convert ImagePlus to Dataset for stats
                dataset = ij.py.to_dataset(imp)

                min_val = ij.op().stats().min(dataset).getRealDouble()
                max_val = ij.op().stats().max(dataset).getRealDouble()

                entry = {
                    "title": imp.getTitle(),
                    "file_path": file_path,
                    "dimensions": f"{imp.getWidth()}x{imp.getHeight()}x{imp.getNSlices()}",
                    "stats": {"min": min_val, "max": max_val},
                    "bit_depth": imp.getBitDepth()
                }
                if file_path_note:
                    entry["file_path_note"] = file_path_note
                all_inspections["images"].append(entry)
            except Exception as e:
                all_inspections["images"].append({"title": imp.getTitle(), "file_path": None, "error": str(e)})

    # --- 2. Inspect Non-Image Windows ---
    IJ = jimport('ij.IJ')
    all_frames = Frame.getFrames()
    for frame in all_frames:
        if frame.isVisible():
            title = frame.getTitle()

            if title == "Results":
                rt = ResultsTable.getResultsTable()
                all_inspections["tables_and_text"].append({
                    "type": "Results Table",
                    "rows": rt.size(),
                    "columns": rt.getLastColumn() + 1
                })
            elif title == "ROI Manager":
                rm = RoiManager.getInstance()
                all_inspections["tables_and_text"].append({
                    "type": "ROI Manager",
                    "roi_count": rm.getCount() if rm else 0
                })
            elif title == "Log":
                log_text = ""
                try:
                    log_text = str(IJ.getLog()) or ""
                except Exception:
                    pass
                all_inspections["tables_and_text"].append({
                    "type": "Log Window",
                    "content": log_text[-4000:] if len(log_text) > 4000 else log_text
                })
            elif "exception" in title.lower() or "error" in title.lower():
                # Capture text from exception/error dialog frames
                try:
                    TextArea = jimport('java.awt.TextArea')
                    text_content = ""
                    for comp in frame.getComponents():
                        if isinstance(comp, TextArea):
                            text_content += str(comp.getText()) + "\n"
                    all_inspections["tables_and_text"].append({
                        "type": "Exception Window",
                        "title": title,
                        "content": text_content[-4000:] if len(text_content) > 4000 else text_content
                    })
                except Exception as e:
                    all_inspections["tables_and_text"].append({
                        "type": "Exception Window",
                        "title": title,
                        "content": f"(could not read content: {e})"
                    })

    return str(all_inspections)


# Titles of known non-dialog Fiji windows to skip when looking for plugin dialogs
_SKIP_TITLES = {"ImageJ", "Fiji", "Log", "Results", "ROI Manager", "Recorder",
                "Brightness/Contrast", "Channels Tool", "Synchronize Windows",
                "3D Viewer", "BigDataViewer"}

_IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".gif",
                     ".fits", ".hdf5", ".h5", ".czi", ".lif", ".nd2", ".ims"}

def _is_non_dialog_window(title: str) -> bool:
    """Return True for windows that are definitely not plugin parameter dialogs."""
    if title in _SKIP_TITLES:
        return True
    # Main Fiji/ImageJ window variations  e.g. "(Fiji Is Just) ImageJ"
    tl = title.lower()
    if "imagej" in tl or tl == "fiji":
        return True
    # Image display windows — title ends with a known image extension
    import os as _os
    ext = _os.path.splitext(title)[1].lower()
    if ext in _IMAGE_EXTENSIONS:
        return True
    return False


@tool
def capture_plugin_dialog() -> str:
    """
    Screenshot every visible plugin dialog window and return a structured
    description of its fields (labels, types, current values, options, buttons).

    Call this after the user opens a plugin dialog so you know exactly what
    parameters are on screen and can give precise, field-by-field guidance.

    Returns a JSON array — one entry per dialog found — with:
      dialog_title, fields (label/type/current_value/options/description), buttons, warnings.
    Returns an empty array if no plugin dialogs are currently open.
    """
    from scyjava import jimport
    from PIL import Image as PILImage

    Window = jimport('java.awt.Window')
    Robot  = jimport('java.awt.Robot')
    Rectangle = jimport('java.awt.Rectangle')

    try:
        robot = Robot()
    except Exception as e:
        return json.dumps({"error": f"Could not create AWT Robot: {e}"})

    # Collect all visible windows that look like plugin dialogs
    dialog_images: list[tuple[str, str]] = []  # (title, base64_png)

    for win in Window.getWindows():
        try:
            if not win.isVisible():
                continue
            # getTitle() exists on Frame and Dialog but not all Window subtypes
            title = ""
            try:
                title = str(win.getTitle())
            except Exception:
                title = win.getClass().getSimpleName()

            # Skip known non-dialog Fiji windows and image display windows
            if not title or _is_non_dialog_window(title):
                continue

            bounds = win.getBounds()
            if bounds.width < 50 or bounds.height < 50:
                continue  # ignore tiny/invisible geometry

            # Capture the window region
            awt_rect = Rectangle(bounds.x, bounds.y, bounds.width, bounds.height)
            awt_img  = robot.createScreenCapture(awt_rect)

            # Convert java.awt.BufferedImage → PIL → base64 PNG
            width  = awt_img.getWidth()
            height = awt_img.getHeight()
            pixels = awt_img.getRGB(0, 0, width, height, None, 0, width)
            pil_img = PILImage.new("RGBA", (width, height))
            rgba_pixels = []
            for px in pixels:
                a = (px >> 24) & 0xFF
                r = (px >> 16) & 0xFF
                g = (px >>  8) & 0xFF
                b = (px      ) & 0xFF
                rgba_pixels.append((r, g, b, a if a else 255))
            pil_img.putdata(rgba_pixels)

            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            dialog_images.append((title, b64))
            print(f"[capture_plugin_dialog] Captured: '{title}' ({width}x{height})")

        except Exception as e:
            print(f"[capture_plugin_dialog] Skipped window: {e}")
            continue

    if not dialog_images:
        return json.dumps([])

    results = []
    llm = _get_vision_llm()

    for title, b64 in dialog_images:
        try:
            response = llm.invoke([
                SystemMessage(content=_DIALOG_VISION_SYSTEM),
                HumanMessage(content=[
                    {"type": "text",
                     "text": f"Analyze this plugin dialog screenshot (window title: '{title}')."},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
                ]),
            ])
            import re as _re
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = _re.sub(r"^```(?:json)?\n?", "", raw).rstrip("` \n")
            parsed = json.loads(raw)
            results.append(parsed)
        except Exception as e:
            results.append({"dialog_title": title, "error": str(e)})

    return json.dumps(results, indent=2)


@tool
def extract_image_metadata(path: str) -> str:
    """Extract calibration, pixel intensity statistics, and suggested
    threshold/filter parameters from an image file.

    Returns a JSON string with pixel scale, intensity stats, recommended
    threshold values, filter sizes, and noise estimates.  Does NOT require
    an active ImageJ dataset — reads the file directly.

    Args:
        path: Absolute file path to the image.
    """

    result = extract_file_metadata(path)
    return json.dumps(result, indent=2, default=str)
