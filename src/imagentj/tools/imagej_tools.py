import base64
import io
import json
import os
import re
from pathlib import Path
from typing import Optional
from langchain.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from imagentj.imagej_context import get_ij, needs_bioformats, open_image_windowless
from .metadata_tools import extract_file_metadata

_SKILLS_DIR = Path(os.environ.get("SKILLS_DIR", "/app/skills"))


def _message_text(content) -> str:
    """Normalize a LangChain message's .content to plain text.

    Some providers (and multimodal responses in general) return content as a
    list of blocks (e.g. [{"type": "text", "text": "..."}]) instead of a bare
    string, so callers should not assume `.content` is always str.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return str(content or "")


def _find_ui_docs_for_dialog(dialog_title: str) -> str:
    """
    Given a dialog title (e.g. 'CiliaQ on Linux - detection preferences'),
    look for a matching plugin skill folder under _SKILLS_DIR and return
    the concatenated contents of all UI_*.md files found there.
    Returns an empty string if nothing matches.
    """
    if not _SKILLS_DIR.exists():
        return ""

    # Extract a short plugin name: take the first meaningful token(s) before
    # separators like " - ", " on ", " (", numbers, or "preferences/settings/options"
    short = re.split(r'\s+[-–]\s+|\s+on\s+|\s+\(', dialog_title)[0]
    short = re.sub(r'\s+(preferences?|settings?|options?|parameters?|wizard).*', '',
                   short, flags=re.IGNORECASE).strip()
    slug = re.sub(r'[\s_\-]+', '', short).lower()  # "CiliaQ" → "ciliaq"

    # Score each skill folder by how much its name overlaps with the slug
    best_dir: Path | None = None
    best_score = 0
    for skill_dir in _SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        folder_slug = re.sub(r'[\s_\-]+(documentation|docs?|plugin)?$', '',
                              skill_dir.name, flags=re.IGNORECASE)
        folder_slug = re.sub(r'[\s_\-]+', '', folder_slug).lower()
        # Simple overlap score
        score = 0
        if slug == folder_slug:
            score = 100
        elif slug in folder_slug or folder_slug in slug:
            score = max(len(slug), len(folder_slug))
        if score > best_score:
            best_score = score
            best_dir = skill_dir

    if best_dir is None or best_score == 0:
        return ""

    # Read all UI_*.md files from the matched folder
    ui_files = sorted(best_dir.glob("UI_*.md"))
    if not ui_files:
        return ""

    parts = [f"[Skill documentation from: {best_dir.name}]"]
    for f in ui_files:
        try:
            parts.append(f"\n--- {f.name} ---\n{f.read_text(encoding='utf-8', errors='ignore')}")
        except Exception:
            pass
    return "\n".join(parts)

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

_dialog_llm = None

def set_dialog_vision_llm(llm) -> None:
    global _dialog_llm
    _dialog_llm = llm

def _get_vision_llm():
    if _dialog_llm is not None:
        return _dialog_llm
    # Fallback: construct directly (works only for direct OpenAI users)
    return ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


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


# Text and table files must NOT go through IJ.open. `ij.io.Opener.open()` routes
# anything it cannot decode as an image to net.imagej.legacy's openInEditor hook,
# which builds the SciJava Swing script editor — and under Xvfb the look-and-feel
# supplies no UI delegates, exactly as for the Bio-Formats importer dialog (see
# imagej_context). Measured on the 2026-08-31 Parasite run: ONE such call at
# 12:31:02 produced 49 `java.lang.Error: no ComponentUI class for` in 660 ms — a
# JTextArea (TextEditor.java:233), then one JRadioButtonMenuItem per script
# language as EditorPane.geSyntaxForNoneLang built the syntax menu (BeanShell,
# Clojure, Groovy, ImageJ Macro, Java, JavaScript, Python, … YAML) — followed by
#   NullPointerException … because "highlighter" is null
# and a JOptionPane that could not be constructed to report it.
# SciJava CATCHES and logs all of that, so IJ.open returns normally: this tool
# used to answer "Opened in ImageJ GUI: <table>.csv" while nothing was displayed
# and a half-built editor frame was left behind in the window list.
# ImageJ1's own text/table windows are AWT (ij.text.TextWindow extends Frame), so
# they need no Swing UI delegate and work here.
_TEXT_EXTENSIONS = {".txt", ".log", ".md", ".json", ".yaml", ".yml", ".xml", ".ijm"}
_TABLE_EXTENSIONS = {".csv", ".tsv"}
# A text window is for reading, not for holding a whole dataset in the UI.
_TEXT_WINDOW_MAX_CHARS = 200_000


def _show_text_file(abs_path: str) -> str:
    """Display a text or table file in an ImageJ1 (AWT) window.

    Returns "" on success, or a human-readable reason on failure. A table is
    shown as a Results table when it parses as one; anything else — including a
    .csv that ResultsTable rejects — falls back to a plain text window.
    """
    from scyjava import jimport
    title = os.path.basename(abs_path)
    ext = os.path.splitext(abs_path)[1].lower()

    if ext in _TABLE_EXTENSIONS:
        try:
            ResultsTable = jimport('ij.measure.ResultsTable')
            rt = ResultsTable.open(abs_path)
            if rt is not None:
                rt.show(title)
                return ""
        except Exception:
            pass                      # not tabular after all — show it as text

    try:
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            text = fh.read(_TEXT_WINDOW_MAX_CHARS + 1)
    except OSError as e:
        return f"could not read the file ({e!s})"
    if len(text) > _TEXT_WINDOW_MAX_CHARS:
        text = (text[:_TEXT_WINDOW_MAX_CHARS] +
                f"\n\n[truncated at {_TEXT_WINDOW_MAX_CHARS} characters — "
                "open the file directly to see the rest]")

    TextWindow = jimport('ij.text.TextWindow')
    TextWindow(title, text, 800, 600)   # constructing it shows it
    return ""


@tool
def show_in_imagej_gui(path: str) -> str:
    """Open a file in the Fiji/ImageJ GUI so the user can see it.

    Behaves like the Fiji "File → Open..." menu — supports image formats
    (TIFF, PNG, JPG, BMP, CZI, LIF, ND2, etc.) as well as plain-text and
    table files (.txt, .csv, .tsv), which are shown in a text window or
    Results table.

    Use this ONLY to display something to the user. It does not return the
    file contents — for programmatic access use load_image_ij,
    smart_file_reader, or inspect_csv_header instead.

    Safe by design: empty, missing, non-file, or unreadable paths return a
    clear error string and never raise.

    Args:
        path: Absolute path to the file to display.

    Returns:
        A short status string: success message or human-readable error.
    """
    return open_in_imagej_gui(path)


def open_in_imagej_gui(path: str, title: str | None = None) -> str:
    """Open a file in the Fiji/ImageJ GUI. Plain helper (not a tool) so other
    tools can reuse the exact same behaviour. Never raises — returns a status
    string that starts with "Opened" on success, or a human-readable error.

    If `title` is given, the newly opened image window is renamed to it (so the
    caller can refer to the window by a stable, human-readable label)."""
    if not isinstance(path, str) or not path.strip():
        return "Could not open file: empty or invalid path."

    abs_path = os.path.abspath(path.strip())

    if not os.path.exists(abs_path):
        return f"Could not open file: path does not exist -> {abs_path}"
    if os.path.isdir(abs_path):
        return f"Could not open file: path is a directory, not a file -> {abs_path}"
    if not os.path.isfile(abs_path):
        return f"Could not open file: not a regular file -> {abs_path}"

    try:
        get_ij()  # ensure JVM/Fiji is up
        from scyjava import jimport
        IJ = jimport('ij.IJ')
        # Bio-Formats formats must NOT go through IJ.open: that builds a modal
        # importer dialog which hangs/throws under Xvfb (see imagej_context).
        if needs_bioformats(abs_path):
            imps = open_image_windowless(abs_path, show=True)
            if not imps:
                return (f"Could not open file in ImageJ GUI ({abs_path}): "
                        "Bio-Formats returned no image.")
        elif os.path.splitext(abs_path)[1].lower() in (_TEXT_EXTENSIONS |
                                                       _TABLE_EXTENSIONS):
            # Never the script-editor route — see the note above _TEXT_EXTENSIONS.
            reason = _show_text_file(abs_path)
            if reason:
                return f"Could not open file in ImageJ GUI ({abs_path}): {reason}"
        else:
            # Images plus the IJ1 types Opener handles natively (.roi, .zip ROI
            # sets, .lut, .avi), none of which reach openInEditor.
            IJ.open(abs_path)
        if title:
            try:
                WindowManager = jimport('ij.WindowManager')
                imp = WindowManager.getCurrentImage()  # the just-opened image
                if imp is not None:
                    imp.setTitle(str(title))
            except Exception:
                pass  # renaming is best-effort; opening already succeeded
    except Exception as e:
        return f"Could not open file in ImageJ GUI ({abs_path}): {e!s}"

    return f"Opened in ImageJ GUI: {abs_path}"


@tool
def close_imagej_windows(
    titles: list[str] | None = None,
    close_all_images: bool = False,
    close_non_image: bool = False,
) -> str:
    """Close ImageJ/Fiji windows to clean up the GUI.

    Call this after a verification step or once the user has confirmed they
    no longer need a set of windows on screen — accumulating images, logs,
    and plot windows clutter Fiji and slow batch runs.

    The main ImageJ/Fiji control window is NEVER closed by this tool.

    Args:
        titles: Specific window titles to close (image windows or non-image
                windows like "Log", "Results", "ROI Manager", or plugin
                dialogs). Matches by exact title.
        close_all_images: If True, close every visible image window.
        close_non_image: If True, close visible non-image windows
                         (Log, Results, ROI Manager, exception popups, plugin
                         dialogs) — but never the main ImageJ control window.

    Returns:
        Human-readable summary of which windows were closed.
    """
    try:
        get_ij()
        from scyjava import jimport
        WindowManager = jimport('ij.WindowManager')
        Window = jimport('java.awt.Window')
    except Exception as e:
        return f"Could not access ImageJ window system: {e!s}"

    requested_titles = set(t for t in (titles or []) if isinstance(t, str) and t.strip())
    closed_images: list[str] = []
    closed_non_image: list[str] = []
    failed: list[str] = []

    # --- 1. Close image windows ---
    try:
        image_ids = WindowManager.getIDList() or []
    except Exception:
        image_ids = []
    for img_id in image_ids:
        try:
            imp = WindowManager.getImage(img_id)
            if imp is None:
                continue
            title = str(imp.getTitle())
            if close_all_images or title in requested_titles:
                imp.changes = False  # suppress "save changes?" dialog
                imp.close()
                closed_images.append(title)
                requested_titles.discard(title)
        except Exception as e:
            failed.append(f"{title if 'title' in dir() else '?'}: {e!s}")

    # --- 2. Close non-image windows (Log, Results, dialogs, etc.) ---
    if close_non_image or requested_titles:
        try:
            windows = list(Window.getWindows())
        except Exception:
            windows = []
        for win in windows:
            try:
                if not win.isVisible():
                    continue
                try:
                    title = str(win.getTitle())
                except Exception:
                    title = ""
                # Never close the main ImageJ/Fiji control window
                if _is_main_imagej_window(title):
                    continue
                want_close = (close_non_image and not _IMAGE_EXT_RE.search(title)) \
                              or (title in requested_titles)
                if not want_close:
                    continue
                # Dispose closes both Frame and Dialog without prompting
                try:
                    win.dispose()
                except Exception:
                    win.setVisible(False)
                closed_non_image.append(title or win.getClass().getSimpleName())
                requested_titles.discard(title)
            except Exception as e:
                failed.append(f"{title if 'title' in dir() else '?'}: {e!s}")

    parts = []
    if closed_images:
        parts.append(f"Closed {len(closed_images)} image window(s): {closed_images}")
    if closed_non_image:
        parts.append(f"Closed {len(closed_non_image)} non-image window(s): {closed_non_image}")
    if requested_titles:
        parts.append(f"Not found / already closed: {sorted(requested_titles)}")
    if failed:
        parts.append(f"Failed to close: {failed}")
    if not parts:
        parts.append("No windows matched the request — nothing to close.")
    return " | ".join(parts)


def _is_main_imagej_window(title: str) -> bool:
    if not title:
        return False
    tl = title.lower()
    return tl == "fiji" or "imagej" in tl


@tool
def inspect_all_ui_windows():
    """
    Inspect everything visible in the ImageJ UI:
    1. Image Windows (title, file path, dimensions, bit depth, min/max stats)
    2. Results Tables (row/column counts)
    3. ROI Manager (ROI count)
    4. Log Window (full text content)
    5. Console / Script Editor console tab (stdout/stderr from running scripts)
    6. Exception/Error Windows (full stack trace text)

    Call this whenever the user mentions an error in the console, script editor,
    or exception window, or to verify what is currently open in Fiji.
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
    # Use Window.getWindows() (not Frame.getFrames()) to also catch Dialogs,
    # which is what Fiji uses for many error/exception popups.
    IJ = jimport('ij.IJ')
    Window = jimport('java.awt.Window')

    def _collect_text_recursive(root):
        """Return all non-empty getText() values from root and every descendant."""
        parts = []
        try:
            t = str(root.getText())
            if t.strip():
                parts.append(t)
        except Exception:
            pass
        try:
            for child in root.getComponents():
                parts.extend(_collect_text_recursive(child))
        except Exception:
            pass
        return parts

    def _get_window_title(win):
        try:
            return str(win.getTitle())
        except Exception:
            try:
                return win.getClass().getSimpleName()
            except Exception:
                return ""

    for win in Window.getWindows():
        try:
            if not win.isVisible():
                continue
            title = _get_window_title(win)

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
            elif "console" in title.lower() or "script editor" in title.lower():
                # Script Editor has a JTabbedPane; find the "Console" tab first.
                # Fall back to collecting all text if no tab is found.
                console_text = ""
                try:
                    JTabbedPane = jimport('javax.swing.JTabbedPane')

                    def _find_console_tab(comp):
                        try:
                            if isinstance(comp, JTabbedPane):
                                for i in range(comp.getTabCount()):
                                    if "console" in str(comp.getTitleAt(i)).lower():
                                        tab_comp = comp.getComponentAt(i)
                                        parts = _collect_text_recursive(tab_comp)
                                        return "\n".join(parts)
                        except Exception:
                            pass
                        try:
                            for child in comp.getComponents():
                                result = _find_console_tab(child)
                                if result:
                                    return result
                        except Exception:
                            pass
                        return ""

                    console_text = _find_console_tab(win)
                    if not console_text.strip():
                        # No tabbed pane found — grab all text in the window
                        console_text = "\n".join(_collect_text_recursive(win))
                except Exception as e:
                    console_text = f"(could not read console: {e})"

                if console_text.strip():
                    all_inspections["tables_and_text"].append({
                        "type": "Console",
                        "title": title,
                        "content": console_text[-4000:] if len(console_text) > 4000 else console_text
                    })
            elif "exception" in title.lower() or "error" in title.lower():
                parts = _collect_text_recursive(win)
                text_content = "\n".join(parts)
                print(f"[inspect_ui] Exception window '{title}': found {len(parts)} text parts, {len(text_content)} chars")
                all_inspections["tables_and_text"].append({
                    "type": "Exception Window",
                    "title": title,
                    "content": text_content[-4000:] if len(text_content) > 4000 else text_content
                })
            elif not _is_main_imagej_window(title):
                # Anything else visible and titled (a plugin's own parameter dialog,
                # a "command not found" popup, ...) used to be silently dropped here,
                # so it never showed up in this report even though it was genuinely
                # open — the window enumeration above found it, this branch just had
                # nowhere to put it. Surface at least its existence + title; call
                # capture_plugin_dialog() for the actual fields/values/buttons.
                all_inspections["tables_and_text"].append({
                    "type": "Other Window (likely a plugin dialog)",
                    "title": title,
                    "note": "Call capture_plugin_dialog() to see its fields, values, and buttons.",
                })
        except Exception as e:
            print(f"[inspect_ui] Skipped window: {e}")

    return str(all_inspections)


# Titles of known non-dialog Fiji windows to skip when looking for plugin dialogs
_SKIP_TITLES = {"ImageJ", "Fiji", "Log", "Results", "ROI Manager", "Recorder",
                "Brightness/Contrast", "Channels Tool", "Synchronize Windows",
                "Console"}

_IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".gif",
                     ".fits", ".hdf5", ".h5", ".czi", ".lif", ".nd2", ".ims"}

_IMAGE_EXT_RE = re.compile(
    r'\.(' + '|'.join(e.lstrip('.') for e in _IMAGE_EXTENSIONS) + r')(\s|$|\[|\()',
    re.IGNORECASE,
)

def _is_non_dialog_window(title: str) -> bool:
    """Return True for windows that are definitely not plugin parameter dialogs."""
    if title in _SKIP_TITLES:
        return True
    # Main Fiji/ImageJ window variations  e.g. "(Fiji Is Just) ImageJ"
    tl = title.lower()
    if "imagej" in tl or tl == "fiji":
        return True
    # Image display windows — title contains a known image extension followed by
    # end-of-string, whitespace, or bracket (handles "img.tif (50%)", "stack.tif [1/10]")
    if _IMAGE_EXT_RE.search(title):
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
            ui_docs = _find_ui_docs_for_dialog(title)
            text_prompt = f"Analyze this plugin dialog screenshot (window title: '{title}')."
            if ui_docs:
                text_prompt += (
                    "\n\nThe following documentation describes the parameters of this plugin. "
                    "Use it to enrich the 'description' field of each parameter with accurate, "
                    "specific guidance (recommended values, valid ranges, what it controls):\n\n"
                    + ui_docs
                )
                print(f"[capture_plugin_dialog] Enriching '{title}' with UI docs ({len(ui_docs)} chars)")

            response = llm.invoke([
                SystemMessage(content=_DIALOG_VISION_SYSTEM),
                HumanMessage(content=[
                    {"type": "text", "text": text_prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
                ]),
            ])
            raw = _message_text(response.content).strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\n?", "", raw).rstrip("` \n")
            parsed = json.loads(raw)
            results.append(parsed)
        except Exception as e:
            results.append({"dialog_title": title, "error": str(e)})

    return json.dumps(results, indent=2)


# ── Cellpose diameter estimation from user-drawn ROIs ────────────────────────
# Cellpose v3 rescales the image by (diameter / model_training_diameter), so a wrong
# `diameter` is the single biggest quality lever on a NON-fine-tuned stock model. These
# helpers turn hand-drawn polygons into that number.

def _no_interactive_user() -> bool:
    """True when nobody can draw ROIs in Fiji, so the manual route is impossible.

    Mirrors docker-entrypoint.sh's own resolution order: benchmark auto-pilot first (there is
    definitively no human), then the IMAGENTJ_UNATTENDED env var, then `runtime.unattended`
    in imagentj_config.yaml.

    NOTE: "unattended" is NOT "headless". The entrypoint keeps Xvfb + fluxbox running and
    only skips the VNC layer (x11vnc/noVNC), so Fiji windows, AWT-Robot dialog screenshots
    and napari all still render — what is missing is a human who can *see and click* them.
    So the test cannot be "is there a DISPLAY"; it has to be this.
    """
    truthy = {"1", "true", "yes", "on"}

    if (os.environ.get("BENCHMARK_MODE", "").strip().lower() == "true"
            and os.environ.get("BENCHMARK_INTERACTIVE", "").strip().lower() != "true"):
        return True

    env = os.environ.get("IMAGENTJ_UNATTENDED", "").strip().lower()
    if env:
        return env in truthy

    try:
        import yaml
        cfg_path = os.environ.get("IMAGENTJ_CONFIG", "/app/imagentj_config.yaml")
        with open(cfg_path) as fh:
            cfg = yaml.safe_load(fh) or {}
        return str((cfg.get("runtime") or {}).get("unattended", "")).strip().lower() in truthy
    except Exception:
        return False


def _equivalent_circular_diameter(area_px: float) -> float:
    """Diameter of the circle with the same area — 2*sqrt(A/pi).

    Area MUST be in pixels: cellpose's `diameter` is strictly px (SCRIPT_API.md), while
    ImageJ reports ImageStatistics.area in CALIBRATED units on a calibrated image. On a
    0.645 um/px image a 40x40 px ROI reports area=665.64 (um^2) but pixelCount=1600 —
    feeding the former here yields 29.1 px instead of 45.1 px, a silent 1.55x error.
    Always source this from `pixelCount`.
    """
    import numpy as np
    return float(2.0 * np.sqrt(area_px / np.pi))


def _best_two_cluster_split(log_values):
    """Exact 1-D 2-means, by exhaustive split search on sorted values.

    For 1-D data the optimal 2-cluster partition is always a split of the sorted order, so
    trying every cut is exact — no initialisation sensitivity or iteration like general
    k-means. Operates on LOG diameters so separation is judged multiplicatively: a 2x gap
    counts the same at 20 px as at 200 px, which is what matters for cellpose rescaling.

    Returns (within_sse, split_index, left_mean, right_mean) in log space.
    """
    import numpy as np
    v = np.sort(np.asarray(log_values, dtype=float))
    best = None
    for i in range(1, len(v)):
        left, right = v[:i], v[i:]
        sse = float(((left - left.mean()) ** 2).sum() + ((right - right.mean()) ** 2).sum())
        if best is None or sse < best[0]:
            best = (sse, i, float(left.mean()), float(right.mean()))
    return best


def _out_of_tolerance_fraction(diameters, reference, tolerance):
    """Fraction of objects a single `reference` diameter would scale badly.

    Cellpose presents an object of true diameter d to the network at
    d * (train_diam / reference) px, so detection quality tracks the RATIO d/reference,
    not the absolute difference. Anything outside [1/tolerance, tolerance] is counted as
    poorly served by that reference.
    """
    import numpy as np
    d = np.asarray(diameters, dtype=float)
    ratio = d / reference
    return float(((ratio < 1.0 / tolerance) | (ratio > tolerance)).mean())


@tool
def estimate_cellpose_diameter_manual(
    scale_tolerance: float = 1.5,
    max_out_of_tolerance: float = 0.25,
) -> str:
    """Turn the user's hand-drawn ROIs into a Cellpose `diameter` (px), and say whether
    ONE segmentation run is enough or the objects need TWO runs at different diameters.

    Use this for a NON-fine-tuned stock Cellpose v3 model (cyto3, nucleitorch_0, ...),
    where `diameter` is the main accuracy lever. Ask the user to open the image in Fiji,
    draw a polygon/freehand outline around ~8-15 representative objects (whatever they
    want segmented — whole cell outline, or just the nucleus), pressing **T** after each
    to add it to the ROI Manager. Then call this with no arguments.

    Reads every ROI in the ROI Manager, converts each to an equivalent circular diameter
    (2*sqrt(area/pi)) in PIXELS, and reports the distribution plus a recommendation.

    REQUIRES AN INTERACTIVE USER. In an unattended run (benchmark auto-pilot,
    IMAGENTJ_UNATTENDED, runtime.unattended) nobody can draw ROIs, so use
    estimate_cellpose_diameter_auto() instead — never wait on a user who is not there.

    Args:
        scale_tolerance: How far off a single diameter may be before an object counts as
            badly scaled, as a ratio (1.5 = anything under 1/1.5x or over 1.5x the chosen
            diameter). Heuristic — see the skill docs.
        max_out_of_tolerance: Fraction of badly-scaled objects tolerated before
            recommending two runs (0.25 = split once more than a quarter are off).

    Returns:
        JSON: per-ROI diameters, summary stats, and `recommendation` with the
        diameter(s) in px to pass as `cp.diameter`.
    """
    import numpy as np
    from scyjava import jimport

    if scale_tolerance <= 1.0:
        return json.dumps({"error": "scale_tolerance must be > 1.0 (it is a ratio, e.g. 1.5)."})

    try:
        get_ij()  # ensure the JVM/Fiji is up
        RoiManager = jimport('ij.plugin.frame.RoiManager')
        rm = RoiManager.getInstance()
    except Exception as e:
        return json.dumps({"error": f"Could not reach the ImageJ ROI Manager: {e}"})

    if rm is None or rm.getCount() == 0:
        return json.dumps({
            "error": "no_rois_unattended" if _no_interactive_user() else "no_rois",
            "message": (
                # There is no human to draw anything, so telling the agent to "ask the user"
                # would strand it in a loop waiting on input that can never arrive.
                "The ROI Manager is empty and this run is UNATTENDED (benchmark auto-pilot / "
                "IMAGENTJ_UNATTENDED / runtime.unattended) — nobody can draw ROIs. Do NOT ask "
                "the user to outline anything. Use estimate_cellpose_diameter_auto() instead, "
                "which needs no interaction."
                if _no_interactive_user() else
                "The ROI Manager is empty. Ask the user to open the image in Fiji, pick the "
                "polygon or freehand selection tool, outline ~8-15 representative objects, "
                "and press T after each one to add it to the ROI Manager."
            ),
        })

    # Pixel areas. Roi.getStatistics() works standalone (no image attached) and its
    # pixelCount is always a raw pixel count, so this is immune to image calibration
    # and does not disturb whatever selection the user currently has active.
    areas_px, skipped = [], []
    for i in range(rm.getCount()):
        try:
            roi = rm.getRoi(i)
            n_px = float(roi.getStatistics().pixelCount)
            if n_px <= 0:
                skipped.append({"index": i, "reason": "zero-area ROI"})
                continue
            areas_px.append(n_px)
        except Exception as exc:
            skipped.append({"index": i, "reason": str(exc)})

    if not areas_px:
        return json.dumps({"error": "no_measurable_rois", "skipped": skipped})

    areas = np.asarray(areas_px, dtype=float)
    diameters = np.array([_equivalent_circular_diameter(a) for a in areas])
    n = int(diameters.size)

    mean_d = float(diameters.mean())
    # Summarise on the MEDIAN area, then convert — robust to one sloppily-drawn outline,
    # unlike the mean-area variant (sqrt is concave, so averaging areas is dominated by the
    # largest ROIs: a single oversized polygon among 11 tight nuclei pulled that variant to
    # 42.7 px against a true ~30 px).
    #
    # d = 2*sqrt(A/pi) is monotonic, so order statistics are preserved: for ODD n this is
    # exactly the median of the per-ROI diameters. For EVEN n numpy averages the two middle
    # values, and averaging areas is not the same as averaging their diameters — usually a
    # rounding-level difference, but it grows when the two middle values straddle a gap
    # (measured: 43.0 vs 48.3 px on a bimodal 12-ROI set). That case is precisely where a
    # single diameter is the wrong answer anyway and the two-run split below takes over, so
    # it does not change the recommendation.
    median_d = _equivalent_circular_diameter(float(np.median(areas)))

    p10, p90 = (float(x) for x in np.percentile(diameters, [10, 90]))
    cv = float(diameters.std(ddof=1) / mean_d) if n > 1 else 0.0
    spread_ratio = float(p90 / p10) if p10 > 0 else float("inf")

    single_bad = _out_of_tolerance_fraction(diameters, median_d, scale_tolerance)

    result = {
        "n_rois": n,
        "per_roi_diameter_px": [round(float(d), 1) for d in np.sort(diameters)],
        "summary": {
            # The recommended single-run value. Named for how it is computed so it is not
            # confused with np.median(diameters), which differs slightly for even n.
            "diameter_from_median_area_px": round(median_d, 1),
            "mean_diameter_px": round(mean_d, 1),
            "p10_px": round(p10, 1),
            "p90_px": round(p90, 1),
            "p90_over_p10": round(spread_ratio, 2),
            "coefficient_of_variation": round(cv, 3),
        },
        "units_note": (
            "All diameters are in PIXELS, sourced from Roi.getStatistics().pixelCount — "
            "cellpose's `diameter` is px, never microns."
        ),
    }
    if skipped:
        result["skipped_rois"] = skipped
    if n < 5:
        result["warning"] = (
            f"Only {n} ROI(s) measured — too few to judge the size distribution reliably. "
            "Ask the user for ~8-15 outlines before trusting the single/two-run call."
        )

    # ── One run or two? ──────────────────────────────────────────────────────
    # Decided on how badly a SINGLE diameter would scale the population, not on an
    # abstract bimodality score: what matters to cellpose is the d/diameter ratio per
    # object. This treats "one broad continuous spread" and "two tight clusters" on the
    # same footing — in both cases many objects are mis-scaled by one diameter.
    if single_bad <= max_out_of_tolerance or n < 4:
        result["recommendation"] = {
            "n_runs": 1,
            "diameters_px": [round(median_d, 1)],
            "fraction_poorly_scaled": round(single_bad, 3),
            "reason": (
                f"{single_bad:.0%} of objects fall outside {scale_tolerance}x of the median "
                f"diameter ({median_d:.1f} px), at or below the {max_out_of_tolerance:.0%} "
                "threshold — one run covers the population."
            ),
        }
        return json.dumps(result, indent=2)

    sse, idx, log_c1, log_c2 = _best_two_cluster_split(np.log(diameters))
    c1, c2 = float(np.exp(log_c1)), float(np.exp(log_c2))
    sorted_d = np.sort(diameters)
    small, large = sorted_d[:idx], sorted_d[idx:]
    # Each object is now served by whichever of the two diameters suits it better.
    two_bad = float(np.mean([
        min(_out_of_tolerance_fraction([d], c1, scale_tolerance),
            _out_of_tolerance_fraction([d], c2, scale_tolerance))
        for d in diameters
    ]))

    smallest_group = min(len(small), len(large))
    centre_ratio = float(max(c1, c2) / min(c1, c2))
    # Only worth two runs if BOTH groups are substantial (else it is a couple of outliers,
    # better fixed by redrawing), the centres differ enough for the rescale to matter, and
    # splitting genuinely reduces the mis-scaled fraction.
    worth_splitting = (
        smallest_group >= max(2, int(round(0.15 * n)))
        and centre_ratio >= scale_tolerance
        and two_bad < single_bad
    )

    if worth_splitting:
        result["recommendation"] = {
            "n_runs": 2,
            "diameters_px": [round(min(c1, c2), 1), round(max(c1, c2), 1)],
            "group_sizes": [len(small), len(large)],
            "centre_ratio": round(centre_ratio, 2),
            "fraction_poorly_scaled_one_run": round(single_bad, 3),
            "fraction_poorly_scaled_two_runs": round(two_bad, 3),
            "reason": (
                f"A single diameter mis-scales {single_bad:.0%} of objects (> "
                f"{max_out_of_tolerance:.0%}). Two size groups found ({len(small)} and "
                f"{len(large)} objects, centres {min(c1, c2):.1f} and {max(c1, c2):.1f} px, "
                f"{centre_ratio:.1f}x apart); running twice drops that to {two_bad:.0%}. "
                "Run cellpose once per diameter, then merge the two label images."
            ),
        }
    else:
        result["recommendation"] = {
            "n_runs": 1,
            "diameters_px": [round(median_d, 1)],
            "fraction_poorly_scaled": round(single_bad, 3),
            "reason": (
                f"Sizes are spread out ({single_bad:.0%} of objects outside "
                f"{scale_tolerance}x of the median) but they do NOT separate into two "
                f"usable groups (groups of {len(small)}/{len(large)}, centres "
                f"{centre_ratio:.1f}x apart) — a continuous spread rather than two "
                "populations. Splitting would not help; use one run and expect some "
                "misses at the size extremes, or segment the extremes separately by hand."
            ),
        }
    return json.dumps(result, indent=2)


# Cellpose ships a per-model "size model" (a linear regression from the network's style
# vector to object size). Only these four names have one, and the KEY is the name the
# PYTHON API expects — which is not always the name used elsewhere in this deployment.
#
#   Groovy / BIOP wrapper (cp.model)     -> "nucleitorch_0"
#   Python models.Cellpose(model_type=)  -> "nuclei"
#
# They are the same weights: cellpose's own `model_path("nuclei")` resolves to the file
# `nucleitorch_0`, and `size_model_path("nuclei")` to `size_nucleitorch_0.npy`. But
# `size_model_path("nucleitorch_0")` raises FileNotFoundError — the whitelist below is
# literal. So callers keep using this deployment's `nucleitorch_0` vocabulary and this map
# translates at the API boundary; nobody has to remember the inversion.
_CELLPOSE_SIZE_MODEL_ALIASES = {
    "nucleitorch_0": "nuclei",
    "nuclei": "nuclei",
    "cyto3": "cyto3",
    "cyto2": "cyto2",
    "cyto": "cyto",
}

# Verbatim runner executed inside the `cellpose` conda env (python 3.10). It cannot live in
# the main env: cellpose is not installed there (python 3.13). Emits one JSON line.
_CELLPOSE_DIAMETER_RUNNER = r'''
import sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np

def _load(path):
    low = path.lower()
    if low.endswith((".tif", ".tiff")):
        import tifffile
        return tifffile.imread(path)
    import skimage.io
    return np.asarray(skimage.io.imread(path))

def main():
    cfg = json.loads(sys.argv[1])
    from cellpose import models
    model = models.Cellpose(gpu=bool(cfg["gpu"]), model_type=cfg["model_type"])
    diam_mean = float(model.diam_mean)
    out = {"diam_mean": diam_mean, "per_image": []}
    for path in cfg["image_paths"]:
        rec = {"path": path}
        try:
            img = _load(path)
            if img.ndim > 3:
                raise ValueError(
                    "image has %dD shape %s; the size model only works on 2D "
                    "(optionally multi-channel) images" % (img.ndim, img.shape))
            # sz.eval() is the same call Cellpose.eval(diameter=None) makes internally,
            # minus the third full segmentation pass whose masks we would discard.
            diam, diam_style = model.sz.eval(img, channels=cfg["channels"])
            diam, diam_style = float(diam), float(diam_style)
            # Step 2 refines the style estimate by segmenting and taking the median object
            # size; if it finds NOTHING it silently returns diam_mean, which looks like a
            # real answer. Detect that exactly rather than passing a default off as a
            # measurement.
            rec["diam_px"] = diam
            rec["diam_style_px"] = diam_style
            rec["refine_fell_back"] = bool(abs(diam - diam_mean) < 1e-9)
            rec["style_fell_back"] = bool(abs(diam_style - diam_mean) < 1e-9)
        except Exception as exc:
            rec["error"] = "%s: %s" % (type(exc).__name__, exc)
        out["per_image"].append(rec)
    sys.stdout.write("__RESULT__" + json.dumps(out))

main()
'''


@tool
def estimate_cellpose_diameter_auto(
    image_paths: list[str],
    model: str = "cyto3",
    channels: Optional[list[int]] = None,
    timeout_seconds: int = 900,
) -> str:
    """Estimate the Cellpose `diameter` (px) AUTOMATICALLY, using Cellpose's own built-in
    size model — no user interaction required.

    This is the automatic counterpart to `estimate_cellpose_diameter_manual()` (which measures
    hand-drawn ROIs). Cellpose ships a per-model size model that regresses object size from
    the network's style vector, then refines it by segmenting once and taking the median
    object size. Run it on ONE representative image (the first of a group) and reuse the
    result for the whole group.

    Choosing between the two:
      - AUTOMATIC (this tool): objects look like what the model was trained on (typical
        fluorescent nuclei / cells), and you just need a sane starting diameter. Zero user
        effort, but it can fail silently on unusual data — this tool reports when it does.
      - MANUAL (`estimate_cellpose_diameter_manual`): unusual morphology, low contrast, a mixed
        size population, or when this tool reports `reliable: false`. Costs the user a
        minute of drawing but is grounded in what they actually want segmented, and is the
        only one of the two that can recommend a two-diameter split.
      Cross-checking one against the other (or against `vlm_judge` on an overlay) is cheap
      insurance before committing to a long batch run.

    Only `cyto3`, `cyto2`, `cyto` and `nucleitorch_0` have a size model. `cpsam` and the
    specialised `*_cp3` models do not — use the manual tool for those.

    Args:
        image_paths: Image(s) to estimate from. ONE representative image is usually enough;
            more are averaged (median) but each costs a full inference pass.
        model: The model you will segment with — this deployment's names, e.g. `"cyto3"` or
            `"nucleitorch_0"`.
        channels: Cellpose channel pair `[segment, nuclear]`; 0=grayscale, 1=red, 2=green,
            3=blue. Defaults to `[0, 0]` (grayscale). For nuclei in the blue channel of an
            RGB image use `[3, 0]`; for cells in green with nuclei in blue use `[2, 3]`.
        timeout_seconds: Give up after this long. Inference is slow on CPU (~60 s per
            1 MP image), so budget accordingly.

    Returns:
        JSON with the per-image estimates, the recommended `diameter_px`, and a `reliable`
        flag that is false when Cellpose fell back to its built-in default instead of
        actually measuring.
    """
    import subprocess
    import numpy as np

    if not image_paths:
        return json.dumps({"error": "image_paths is empty — pass at least one image."})
    if channels is None:
        channels = [0, 0]
    if not (isinstance(channels, list) and len(channels) == 2):
        return json.dumps({"error": "channels must be a 2-element list, e.g. [0, 0]."})

    key = str(model).strip()
    api_model = _CELLPOSE_SIZE_MODEL_ALIASES.get(key)
    if api_model is None:
        return json.dumps({
            "error": "no_size_model",
            "message": (
                f"'{model}' has no Cellpose size model, so the diameter cannot be estimated "
                "automatically. Only cyto3, cyto2, cyto and nucleitorch_0 ship one. Use the "
                "manual route instead: ask the user to outline ~8-15 objects in Fiji and "
                "call estimate_cellpose_diameter_manual()."
            ),
        })

    missing = [p for p in image_paths if not os.path.isfile(p)]
    if missing:
        return json.dumps({"error": "missing_images", "paths": missing})

    python_bin = "/opt/conda/envs/cellpose/bin/python"
    if not os.path.exists(python_bin):
        return json.dumps({"error": f"cellpose env python not found at {python_bin}"})

    cfg = json.dumps({
        "image_paths": list(image_paths),
        "model_type": api_model,
        "channels": [int(c) for c in channels],
        "gpu": os.environ.get("IMAGENTJ_GPU", "").lower() == "true",
    })

    try:
        proc = subprocess.run(
            [python_bin, "-c", _CELLPOSE_DIAMETER_RUNNER, cfg],
            capture_output=True, text=True, timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": "timeout",
            "message": (
                f"Size estimation exceeded {timeout_seconds}s. Cellpose inference is slow on "
                "CPU (~60 s per 1 MP image) — estimate from ONE image, or raise "
                "timeout_seconds."
            ),
        })
    except Exception as e:
        return json.dumps({"error": f"Could not run the cellpose env: {e}"})

    marker = "__RESULT__"
    if marker not in (proc.stdout or ""):
        return json.dumps({
            "error": "cellpose_failed",
            "returncode": proc.returncode,
            "stderr": (proc.stderr or "")[-1500:],
        })
    payload = json.loads(proc.stdout.split(marker, 1)[1])

    per_image = payload["per_image"]
    diam_mean = payload["diam_mean"]
    good = [r for r in per_image if "diam_px" in r and not r["refine_fell_back"]]
    style_only = [r for r in per_image if "diam_px" in r and r["refine_fell_back"]
                  and not r["style_fell_back"]]
    failed = [r for r in per_image if "error" in r]

    result = {
        "model": key,
        "model_type_passed_to_cellpose": api_model,
        "channels": channels,
        "cellpose_default_diameter_px": diam_mean,
        "per_image": per_image,
        "failed_images": failed,
    }
    if key != api_model:
        result["naming_note"] = (
            f"Called cellpose's Python API with model_type='{api_model}' — the same weights "
            f"as '{key}' (model_path('{api_model}') resolves to the {key} file). The Python "
            f"size-model API only accepts '{api_model}'; passing '{key}' raises "
            "FileNotFoundError. Keep using this deployment's name everywhere else."
        )

    if good:
        diam = float(np.median([r["diam_px"] for r in good]))
        result["recommendation"] = {
            "diameter_px": round(diam, 1),
            "reliable": True,
            "based_on_n_images": len(good),
            "reason": (
                f"Cellpose's size model measured {diam:.1f} px "
                f"(median over {len(good)} image(s)). Pass this as `cp.diameter`."
            ),
        }
    elif style_only:
        diam = float(np.median([r["diam_style_px"] for r in style_only]))
        result["recommendation"] = {
            "diameter_px": round(diam, 1),
            "reliable": False,
            "based_on_n_images": len(style_only),
            "reason": (
                f"UNRELIABLE. Cellpose's refinement step found NO objects, so its own answer "
                f"silently collapsed to the built-in default ({diam_mean} px) rather than a "
                f"measurement. The value above is the step-1 style regression only "
                f"({diam:.1f} px), which is a real estimate but unverified by segmentation — "
                "typically means the data does not look like this model's training set. "
                "Verify with the manual ROI route (estimate_cellpose_diameter_manual) or vlm_judge "
                "before running a batch."
            ),
        }
    else:
        result["recommendation"] = {
            "diameter_px": None,
            "reliable": False,
            "reason": (
                "Automatic estimation failed on every image (see failed_images / "
                "per_image). Fall back to the manual route: ask the user to outline "
                "~8-15 objects in Fiji and call estimate_cellpose_diameter_manual()."
            ),
        }
    return json.dumps(result, indent=2)


@tool
def merge_cellpose_diameter_runs(
    small_run_mask_path: str,
    small_run_diameter_px: float,
    large_run_mask_path: str,
    large_run_diameter_px: float,
    output_path: str,
    overlap_threshold: float = 0.5,
) -> str:
    """Merge the two label images produced by a two-diameter Cellpose run into ONE
    instance-label image with unique, sequential IDs.

    Use this after `estimate_cellpose_diameter_manual()` recommended `n_runs: 2` and cellpose has
    been run once per diameter. NEVER merge label images by adding/max-ing them: IDs from
    the two runs collide, so addition invents objects with fused IDs and `max` silently
    merges touching neighbours into one.

    How it resolves the two runs (each run detects some of the same physical objects):
      1. Each object is measured (equivalent circular diameter) and assigned to whichever
         run it *should* have come from, split at the geometric mean of the two diameters —
         the small run owns objects below the boundary, the large run above it.
      2. Remaining candidates are accepted greedily, best-matched first, scored by how close
         the object is to its own run's target diameter (|log(ecd / target)|).
      3. A candidate is dropped if more than `overlap_threshold` of its pixels are already
         covered by an accepted object (it is a duplicate detection of the same cell).
      4. A final pass re-admits any object that was assigned away in step 1 but overlaps
         nothing accepted — so an object only ever found by the "wrong" run is not lost.

    Args:
        small_run_mask_path: Label TIFF from the run with the SMALLER diameter.
        small_run_diameter_px: The `diameter` used for that run.
        large_run_mask_path: Label TIFF from the run with the LARGER diameter.
        large_run_diameter_px: The `diameter` used for that run.
        output_path: Where to write the merged uint32 label TIFF.
        overlap_threshold: Fraction of a candidate's own pixels that may already be covered
            before it is treated as a duplicate and dropped (0.5 = half).

    Returns:
        JSON with the object counts kept from each run, duplicates dropped, objects
        recovered by the final pass, and the output path.
    """
    import numpy as np
    import tifffile
    from scipy import ndimage as ndi

    if not (0.0 < overlap_threshold <= 1.0):
        return json.dumps({"error": "overlap_threshold must be in (0, 1]."})
    if small_run_diameter_px <= 0 or large_run_diameter_px <= 0:
        return json.dumps({"error": "Diameters must be positive."})

    d_small, d_large = float(small_run_diameter_px), float(large_run_diameter_px)
    if d_small > d_large:  # tolerate the caller swapping them
        d_small, d_large = d_large, d_small
        small_run_mask_path, large_run_mask_path = large_run_mask_path, small_run_mask_path

    try:
        lab_small = tifffile.imread(small_run_mask_path)
        lab_large = tifffile.imread(large_run_mask_path)
    except Exception as e:
        return json.dumps({"error": f"Could not read a label image: {e}"})

    if lab_small.shape != lab_large.shape:
        return json.dumps({
            "error": "shape_mismatch",
            "message": (
                f"Label images differ in shape: {lab_small.shape} vs {lab_large.shape}. "
                "Both runs must segment the SAME image."
            ),
        })
    if lab_small.ndim != 2:
        return json.dumps({
            "error": "not_2d",
            "message": f"Expected 2-D label images, got shape {lab_small.shape}.",
        })

    def _objects(lab, target, source):
        """One record per label id: pixel coords, ECD, and distance from its run's target."""
        out = []
        # find_objects gives a bounding-box slice per id — far cheaper than scanning the
        # whole image once per label.
        for idx, sl in enumerate(ndi.find_objects(lab.astype(np.int32)), start=1):
            if sl is None:
                continue
            sub = lab[sl] == idx
            n_px = int(sub.sum())
            if n_px == 0:
                continue
            ys, xs = np.nonzero(sub)
            coords = (ys + sl[0].start, xs + sl[1].start)
            ecd = _equivalent_circular_diameter(n_px)
            out.append({
                "coords": coords,
                "area_px": n_px,
                "ecd": ecd,
                "source": source,
                "score": abs(float(np.log(ecd / target))),
            })
        return out

    objs_small = _objects(lab_small, d_small, "small")
    objs_large = _objects(lab_large, d_large, "large")

    # Size band: the small run owns everything below the geometric mean of the two
    # diameters, the large run everything above. Geometric (not arithmetic) mean because
    # cellpose scaling error is multiplicative.
    boundary = float(np.sqrt(d_small * d_large))
    primary = ([o for o in objs_small if o["ecd"] <= boundary]
               + [o for o in objs_large if o["ecd"] > boundary])
    deferred = ([o for o in objs_small if o["ecd"] > boundary]
                + [o for o in objs_large if o["ecd"] <= boundary])

    merged = np.zeros(lab_small.shape, dtype=np.uint32)
    next_id = 0
    kept = {"small": 0, "large": 0}
    dropped_duplicate = 0
    accepted_area: dict[int, int] = {}

    def _try_accept(obj):
        """Accept unless this object duplicates something already accepted.

        The overlap test is deliberately BIDIRECTIONAL. Checking only "how much of me is
        already taken" misses containment: a bogus blob from the large-diameter run that
        fuses several small cells covers only a small fraction of ITS OWN area, so it
        would sail through and sit on top of the correct small objects.
        """
        nonlocal next_id, dropped_duplicate
        coords = obj["coords"]
        under = merged[coords]
        covered = int((under > 0).sum())

        # (a) this candidate is mostly claimed already — a finer duplicate.
        if covered / obj["area_px"] > overlap_threshold:
            dropped_duplicate += 1
            return False

        # (b) this candidate would swallow an already-accepted object — a coarser
        #     duplicate (the large run fusing cells the small run resolved correctly).
        if covered:
            ids, counts = np.unique(under[under > 0], return_counts=True)
            for lid, c in zip(ids.tolist(), counts.tolist()):
                if c / accepted_area[int(lid)] > overlap_threshold:
                    dropped_duplicate += 1
                    return False

        next_id += 1
        merged[coords] = next_id
        accepted_area[next_id] = obj["area_px"]
        kept[obj["source"]] += 1
        return True

    for obj in sorted(primary, key=lambda o: o["score"]):
        _try_accept(obj)

    # Recover objects the size band assigned away that nothing else actually found —
    # without this, an object detected by only one run, on the "wrong" side of the
    # boundary, would vanish from the merge entirely.
    recovered = 0
    for obj in sorted(deferred, key=lambda o: o["score"]):
        before = next_id
        _try_accept(obj)
        if next_id > before:
            recovered += 1

    try:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        tifffile.imwrite(output_path, merged)
    except Exception as e:
        return json.dumps({"error": f"Could not write merged mask: {e}"})

    return json.dumps({
        "output_path": os.path.abspath(output_path),
        "total_objects": int(next_id),
        "kept_from_small_run": kept["small"],
        "kept_from_large_run": kept["large"],
        "recovered_outside_size_band": recovered,
        "dropped_as_duplicate": dropped_duplicate,
        "size_band_boundary_px": round(boundary, 1),
        "input_object_counts": {"small_run": len(objs_small), "large_run": len(objs_large)},
        "dtype": "uint32",
        "note": (
            "Labels are sequential 1..N with 0 = background, ready for regionprops_table / "
            "cp_measure exactly like any other instance mask."
        ),
    }, indent=2)


@tool
def extract_image_metadata(path: str) -> str:
    """Extract calibration, pixel intensity statistics, and suggested
    threshold/filter parameters from an image file.

    Returns a JSON string with pixel scale, intensity stats, recommended
    threshold values, filter sizes, and noise estimates.  Does NOT require
    an active ImageJ dataset — reads the file directly.

    If the file cannot be found or read, returns a JSON object with an
    `error` key and a human-readable `message` instead of raising — the
    supervisor can surface this to the user and continue.

    Args:
        path: Absolute file path to the image.
    """
    if not isinstance(path, str) or not path.strip():
        return json.dumps({
            "error": "invalid_path",
            "message": "extract_image_metadata called with an empty or non-string path.",
            "path": path,
        }, indent=2)

    abs_path = os.path.abspath(path.strip())

    try:
        result = extract_file_metadata(abs_path)
    except FileNotFoundError:
        return json.dumps({
            "error": "file_not_found",
            "message": f"No file at {abs_path}. Ask the user for the correct path "
                       f"or call inspect_folder_tree on the parent directory to list "
                       f"the available files.",
            "path": abs_path,
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "error": "metadata_extraction_failed",
            "message": f"Could not read metadata from {abs_path}: {e!s}",
            "path": abs_path,
        }, indent=2)

    return json.dumps(result, indent=2, default=str)