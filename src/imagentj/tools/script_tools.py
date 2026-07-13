import jpype
from jpype import JClass, JImplements, JOverride
from matplotlib import text
from langchain.tools import tool
from imagentj.imagej_context import get_ij
import os
import json
from .analyst_tools import run_python_code
import datetime
import shutil
from typing import Optional, Any
from filelock import FileLock
import threading
import time
from scyjava import jimport
from .utils import add_line_numbers, strip_line_numbers

# ── Window classification ─────────────────────────────────────────────────

_ERROR_KEYWORDS = (
    "not a valid choice", "not found", "unrecognized",
    "macro error", "exception", "no such", "requires",
    "unknown", "invalid", "cannot find", "failed",
    "undefined", "expected", "syntax error", "illegal",
)

# Titles that are ALWAYS errors regardless of window class.
# ImageJ opens "Macro Error", "Exception", etc. as plain TextWindows.
_ERROR_TITLE_HINTS = (
    "error", "exception", "macro error", "warning",
)

# TextWindow titles that are tabular data output, not errors.
_RESULTS_TITLE_HINTS = (
    "morphometry", "results", "-bnd", "summary",
    "area", "label", "measurements",
)


def _classify_window(window, title: str, text: str) -> str:
    """
    Return one of: "ERROR", "RESULTS", "INFO".

    Priority order (critical — do not reorder):
      1. Title contains an error keyword  -> ERROR
         (catches TextWindow-based macro errors, which bypass MessageDialog)
      2. Window class is MessageDialog    -> ERROR
         (IJ.error, "command not found" modal dialogs)
      3. Body text contains error keyword -> ERROR
      4. TextWindow with tabular content  -> RESULTS
      5. Everything else                  -> INFO
    """
    try:
        cls = str(window.getClass().getSimpleName())
    except Exception:
        cls = ""

    low_text  = (text or "").lower()
    low_title = (title or "").lower()

    # 1. Title-based error detection — HIGHEST PRIORITY.
    # Must come before the TextWindow/RESULTS branch because ImageJ's
    # "Macro Error" window is a TextWindow, not a MessageDialog.
    if any(h in low_title for h in _ERROR_TITLE_HINTS):
        return "ERROR"

    # 2. Modal error dialogs (IJ.error, plugin "command not found", etc.)
    if cls == "MessageDialog":
        return "ERROR"

    # 3. Body-text error detection
    if any(k in low_text for k in _ERROR_KEYWORDS):
        return "ERROR"

    # 4. Tabular TextWindow → results table, suppress from context
    if cls == "TextWindow":
        if any(h in low_title for h in _RESULTS_TITLE_HINTS):
            return "RESULTS"
        lines = (text or "").splitlines()
        if len(lines) > 5 and sum(1 for l in lines if "\t" in l) > len(lines) * 0.5:
            return "RESULTS"

    return "INFO"


def _get_open_frames() -> dict:
    """
    Snapshot all visible AWT Frames by title.
    Returns {title: frame} — uses title as key since TextWindows
    are identified by title in the Window menu.
    """
    Frame = jimport("java.awt.Frame")
    result = {}
    try:
        for frame in Frame.getFrames():
            if frame.isVisible():
                title = str(frame.getTitle())
                result[title] = frame
    except Exception:
        pass
    return result

def _read_multilinelabel_via_reflection(obj) -> str:
    """
    Scan all declared fields on `obj` (and its superclasses) for a
    MultiLineLabel instance and extract its 'lines' array.

    ImageJ's Macro Error / MessageDialog windows store their text in a
    MultiLineLabel that is NOT added to getComponents(), so normal AWT
    recursion can't find it. The field name varies by ImageJ version
    ("label", "theLabel", etc.), so we scan by type instead of by name.
    """
    try:
        MultiLineLabel = JClass("ij.gui.MultiLineLabel")
    except Exception:
        MultiLineLabel = None

    try:
        cls = obj.getClass()
        while cls is not None:
            try:
                for field in cls.getDeclaredFields():
                    try:
                        field.setAccessible(True)
                        value = field.get(obj)
                        if value is None:
                            continue

                        # Match by type if we have MultiLineLabel available,
                        # otherwise match by class name as a fallback
                        is_mll = False
                        if MultiLineLabel is not None:
                            try:
                                is_mll = jpype.isinstance(value, MultiLineLabel)
                            except Exception:
                                is_mll = False
                        if not is_mll:
                            try:
                                if "MultiLineLabel" in str(value.getClass().getName()):
                                    is_mll = True
                            except Exception:
                                pass

                        if not is_mll:
                            continue

                        # Found it — extract the 'lines' array
                        try:
                            lines_field = value.getClass().getDeclaredField("lines")
                            lines_field.setAccessible(True)
                            lines = lines_field.get(value)
                            if lines is not None:
                                text = "\n".join(str(l) for l in lines).strip()
                                if text:
                                    return text
                        except Exception:
                            pass

                        # Fallback: try getText() on the MultiLineLabel itself
                        try:
                            text = str(value.getText()).strip()
                            if text:
                                return text
                        except Exception:
                            pass
                    except Exception:
                        continue
            except Exception:
                pass

            try:
                parent = cls.getSuperclass()
                if parent is None or str(parent.getName()) == "java.lang.Object":
                    break
                cls = parent
            except Exception:
                break
    except Exception:
        pass

    return ""

def _extract_component_text(component) -> list[str]:
    """
    Recursively extract text from all AWT and Swing components.
    Covers: Label, TextArea, TextField, JLabel, JTextArea, JTextField.
    """
    Label     = JClass("java.awt.Label")
    TextArea  = JClass("java.awt.TextArea")
    TextField = JClass("java.awt.TextField")
    Container = JClass("java.awt.Container")

    try:
        JLabel     = JClass("javax.swing.JLabel")
        JTextArea  = JClass("javax.swing.JTextArea")
        JTextField = JClass("javax.swing.JTextField")
        has_swing  = True
    except Exception:
        has_swing = False

    texts = []
    try:
        if jpype.isinstance(component, Label):
            t = str(component.getText()).strip()
            if t:
                texts.append(t)
        elif jpype.isinstance(component, (TextArea, TextField)):
            t = str(component.getText()).strip()
            if t:
                texts.append(t)
        elif has_swing and jpype.isinstance(component, (JLabel, JTextArea, JTextField)):
            t = str(component.getText()).strip()
            if t:
                texts.append(t)

        if jpype.isinstance(component, Container):
            for child in component.getComponents():
                texts.extend(_extract_component_text(child))
    except Exception:
        pass
    return texts


def _read_frame_text(frame) -> str:
    """
    Attempt to read text content from a frame/dialog.

    Strategies in order:
      1. getTextPanel().getText()          — Log, most TextWindows
      2. getTextPanel().getLine(i) loop    — some TextWindow variants
      3. MultiLineLabel reflection scan    — Macro Error, MessageDialog
      4. Component recursion fallback      — anything else
    """
    # Strategy 1 + 2: TextPanel (Log, Results, etc.)
    try:
        text_panel = frame.getTextPanel()

        try:
            text = str(text_panel.getText()).strip()
            if text:
                return text
        except Exception:
            pass

        try:
            line_count = int(text_panel.getLineCount())
            if line_count > 0:
                lines = []
                for i in range(line_count):
                    try:
                        line = str(text_panel.getLine(i))
                        if line:
                            lines.append(line)
                    except Exception:
                        pass
                if lines:
                    return "\n".join(lines).strip()
        except Exception:
            pass
    except Exception:
        pass

    # Strategy 3: MultiLineLabel reflection (Macro Error window)
    text = _read_multilinelabel_via_reflection(frame)
    if text:
        return text

    # Strategy 4: AWT component recursion
    return "\n".join(_extract_component_text(frame))

def _flush_edt() -> None:
    """Block until all currently queued AWT events have been processed."""
    SwingUtilities = JClass("javax.swing.SwingUtilities")
    if SwingUtilities.isEventDispatchThread():
        return

    @JImplements("java.lang.Runnable")
    class Flusher:
        @JOverride
        def run(self):
            pass

    try:
        SwingUtilities.invokeAndWait(Flusher())
    except Exception:
        pass


def _collect_new_frames(frames_before: dict, timeout: float = 0.5) -> dict:
    """
    Poll for new AWT Frames, classify each, and return:
        {"errors": [...], "results_count": int, "info": [...]}
    """
    result = {"errors": [], "results_count": 0, "info": []}
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        _flush_edt()

        current = _get_open_frames()
        new_frames = {
            title: frame
            for title, frame in current.items()
            if title not in frames_before and title not in _IGNORE_TITLES
        }

        if new_frames:
            for title, frame in new_frames.items():
                text = _read_frame_text(frame)
                kind = _classify_window(frame, title, text)
                entry = f"[{title}]"
                if text and kind in ("ERROR", "INFO"):
                    entry += f"\n{text[:500]}"

                if kind == "ERROR":
                    result["errors"].append(entry)
                elif kind == "RESULTS":
                    result["results_count"] += 1
                else:
                    result["info"].append(entry)
            break

        time.sleep(0.05)

    return result

# ── Popup dialog text extraction ──────────────────────────────────────────

def _read_window_text(window) -> str:
    """
    Read text from any AWT Window. Tries in order:
    1. getTextPanel().getText()
    2. getTextPanel().getLine(i) loop
    3. MultiLineLabel reflection scan (Macro Error, MessageDialog, etc.)
    4. Component recursion
    """
    try:
        text_panel = window.getTextPanel()

        try:
            text = str(text_panel.getText()).strip()
            if text:
                return text
        except Exception:
            pass

        try:
            line_count = int(text_panel.getLineCount())
            if line_count > 0:
                lines = []
                for i in range(line_count):
                    try:
                        line = str(text_panel.getLine(i))
                        if line:
                            lines.append(line)
                    except Exception:
                        pass
                if lines:
                    return "\n".join(lines).strip()
        except Exception:
            pass
    except Exception:
        pass

    text = _read_multilinelabel_via_reflection(window)
    if text:
        return text

    return "\n".join(_extract_component_text(window))


# ── Background monitor for modal dialogs DURING execution ─────────────────

_IGNORE_TITLES = {"ImageJ", "Fiji", "Log", "ROI Manager", "Results", ""}


def _snapshot_all_windows() -> dict:
    """
    Snapshot {classname::title: window} for ALL visible AWT windows
    (Frame + Dialog). Used by _WindowMonitor only — _get_open_frames
    remains the source of truth for TextWindow exception detection.
    """
    Window = jimport("java.awt.Window")
    result = {}
    try:
        for window in Window.getWindows():
            if not window.isVisible():
                continue
            try:
                title = str(window.getTitle())
            except Exception:
                title = str(window.getClass().getSimpleName())
            key = f"{window.getClass().getSimpleName()}::{title}"
            result[key] = window
    except Exception:
        pass
    return result


class _WindowMonitor:
    """
    Polls Window.getWindows() in a background thread while the script runs.
    Classifies each new window into errors / results / info buckets.
    """

    def __init__(self, snapshot_before: dict, poll_interval: float = 0.05):
        self._seen = dict(snapshot_before)
        self._errors: list[str] = []
        self._results_count = 0
        self._info: list[str] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "_WindowMonitor":
        self._thread.start()
        return self

    def _run(self):
        while not self._stop.is_set():
            self._poll()
            time.sleep(0.05)

    def _poll(self):
        try:
            Window = jimport("java.awt.Window")
            for window in Window.getWindows():
                if not window.isVisible():
                    continue
                try:
                    title = str(window.getTitle())
                except Exception:
                    title = str(window.getClass().getSimpleName())

                key = f"{window.getClass().getSimpleName()}::{title}"

                if key in self._seen:
                    continue
                if title in _IGNORE_TITLES:
                    self._seen[key] = window
                    continue

                text = _read_window_text(window)
                kind = _classify_window(window, title, text)
                entry = f"[{title}]" if title else "[Window]"
                if text and kind in ("ERROR", "INFO"):
                    entry += f"\n{text[:500]}"

                with self._lock:
                    if kind == "ERROR":
                        self._errors.append(entry)
                    elif kind == "RESULTS":
                        self._results_count += 1
                    else:
                        self._info.append(entry)

                self._seen[key] = window
        except Exception:
            pass

    def stop(self) -> dict:
        self._stop.set()
        self._thread.join(timeout=2.0)
        with self._lock:
            return {
                "errors": list(self._errors),
                "results_count": self._results_count,
                "info": list(self._info),
            }


# ── IJ Log capture ────────────────────────────────────────────────────────

def get_ij_log_content() -> str:
    """Read current text from ImageJ's Log window (IJ.log() output)."""
    WindowManager = JClass("ij.WindowManager")
    log_frame = WindowManager.getFrame("Log")
    if log_frame is None:
        return ""
    try:
        text_panel = log_frame.getTextPanel()
        return str(text_panel.getText())
    except Exception:
        return ""



def get_new_ij_log_entries(log_before: str) -> str:
    """Return only log lines that appeared after `log_before` was captured."""
    log_after = get_ij_log_content()
    if not log_before:
        return log_after
    if log_after.startswith(log_before):
        return log_after[len(log_before):]
    # Log was cleared or rotated between calls — return full current log
    return log_after


def _truncate(s: str, max_bytes: int = 2048) -> str:
    """Truncate long text blocks so they don't drown the LLM context."""
    if len(s) <= max_bytes:
        return s
    head = s[:max_bytes]
    remaining_lines = s[max_bytes:].count("\n")
    return f"{head}\n...[truncated {remaining_lines} more lines]"


def run_groovy_script(script: str, ij) -> str:
    """
    Execute a Groovy script in ImageJ/Fiji, capturing all output channels
    and classifying windows into errors vs. results vs. info.
    """
    System                = jpype.JClass("java.lang.System")
    ByteArrayOutputStream = jpype.JClass("java.io.ByteArrayOutputStream")
    PrintStream           = jpype.JClass("java.io.PrintStream")

    out_stream   = ByteArrayOutputStream()
    err_stream   = ByteArrayOutputStream()
    original_out = System.out
    original_err = System.err
    System.setOut(PrintStream(out_stream))
    System.setErr(PrintStream(err_stream))

    ij_log_before  = get_ij_log_content()
    frames_before  = _get_open_frames()
    windows_before = _snapshot_all_windows()

    monitor = _WindowMonitor(windows_before).start()

    try:
        result = ij.py.run_script("Groovy", script)
        stdout = str(out_stream.toString())
        stderr = str(err_stream.toString())

        ij_log_new = get_new_ij_log_entries(ij_log_before)

        dialog_buckets = monitor.stop()
        frame_buckets  = _collect_new_frames(frames_before)

        errors = dialog_buckets["errors"] + frame_buckets["errors"]
        results_count = dialog_buckets["results_count"] + frame_buckets["results_count"]
        info = dialog_buckets["info"] + frame_buckets["info"]

        ij_log_has_error = any(
            k in ij_log_new.lower()
            for k in ("error", "exception", "failed")
        )
        ij_log_has_warning = "warning" in ij_log_new.lower()

        # STDERR inspection — catches Groovy exceptions (NPE, AssertionError,
        # FileNotFoundException, etc.) that print stack traces to System.err
        # without opening any dialog or touching IJ.log.
        stderr_lower = stderr.lower()
        stderr_has_error = any(
            k in stderr_lower
            for k in (
                "exception", "error:", "\terror", "traceback",
                "caused by:", "\tat ",  # Java stack trace markers
                "assertionerror", "nullpointer", "illegalargument",
                "filenotfound", "ioexception", "classcast",
            )
        )

        # Status: ERROR dominates WARNING dominates SUCCESS
        if errors or ij_log_has_error or stderr_has_error:
            status = "ERROR"
        elif ij_log_has_warning:
            status = "WARNING"
        else:
            status = "SUCCESS"

        # One-line summary — the first thing the supervisor reads
        if errors:
            first_err = errors[0].replace("\n", " ")[:200]
            summary = f"{status} — {first_err}"
        elif stderr_has_error:
            # Extract the most informative line from stderr:
            # prefer the first line containing "Exception" or "Error"
            stderr_lines = [l.strip() for l in stderr.splitlines() if l.strip()]
            key_line = next(
                (l for l in stderr_lines
                 if "exception" in l.lower() or "error" in l.lower()),
                stderr_lines[0] if stderr_lines else "see STDERR",
            )
            summary = f"{status} — {key_line[:200]}"
        elif ij_log_has_error or ij_log_has_warning:
            summary = f"{status} — see IJ_LOG for details"
        else:
            summary = "SUCCESS"

        # Tighter log budget when we're reporting an error
        log_budget = 800 if status == "ERROR" else 2048

        parts = [
            f"SUMMARY: {summary}",
            f"STATUS: {status}",
            "LANGUAGE: Groovy",
        ]
        # Suppress STDOUT on ERROR — the script's own println often lies
        if stdout.strip() and status != "ERROR":
            parts.append(f"STDOUT:\n{_truncate(stdout, 512)}")
        if stderr.strip():
            stderr_budget = 1024 if status == "ERROR" else 512
            parts.append(f"STDERR:\n{_truncate(stderr, stderr_budget)}")
        if ij_log_new.strip():
            parts.append(f"IJ_LOG:\n{_truncate(ij_log_new, log_budget)}")
        parts.append(
            f"ERRORS:\n{chr(10).join(errors)}" if errors else "ERRORS: (none)"
        )
        parts.append(f"INFO_WINDOWS: {len(info)} window(s) (suppressed)")
        parts.append(f"RESULTS_WINDOWS: {results_count} table(s) (suppressed)")

        return "\n".join(parts)

    except Exception as e:
        ij_log_new = get_new_ij_log_entries(ij_log_before)
        dialog_buckets = monitor.stop()
        frame_buckets  = _collect_new_frames(frames_before)
        errors = dialog_buckets["errors"] + frame_buckets["errors"]

        parts = [
            f"SUMMARY: ERROR — {str(e)[:200]}",
            "STATUS: ERROR",
            "LANGUAGE: Groovy",
            f"STDERR:\n{_truncate(str(e) + chr(10) + str(err_stream.toString()), 512)}",
        ]
        if ij_log_new.strip():
            parts.append(f"IJ_LOG:\n{_truncate(ij_log_new, 800)}")
        if errors:
            parts.append(f"ERRORS:\n{chr(10).join(errors)}")
        return "\n".join(parts)

    finally:
        System.setOut(original_out)
        System.setErr(original_err)

def run_script_safe(language: str, code: str, max_retries: int = 3) -> str:
    """
    Unified safe execution tool for the supervisor.

    This tool executes ImageJ/Fiji scripts safely in the GUI, handling:

      - Window snapshot & automatic cleanup on failure
      - Retry handling (up to `max_retries`)
      - Only shows images after successful execution

    Only supports groovy

    Usage notes for the supervisor:
      - The coder and debugger agents only generate or repair code; they
        never execute scripts.
      - This tool MUST be used to execute all ImageJ/Fiji scripts from
        generated code.
      - On execution failure, new windows created by the script will
        automatically be closed before retrying.
      - Only successful execution leaves windows visible for the user.

    Parameters:
      language (str) : "groovy", "java"
      code (str)     : The script code to execute
      max_retries (int, optional) : Number of times to retry on failure

    Returns:
      str : Output log from script execution, including any error messages.
    """
    ij = get_ij()

    WindowManager = JClass("ij.WindowManager")

    # Map language to the original execution tool
    tool_map = {
        "groovy": run_groovy_script,
    }

    if language.lower() not in tool_map:
        raise ValueError(f"Unsupported language: {language}")

    exec_tool = tool_map[language.lower()]
    last_output = ""

    # Snapshot open windows
    windows_before = set(WindowManager.getImageTitles())

    # Run the script
    try:
        output = exec_tool(code, ij)
    except Exception as e:
        output = f"Exception during execution: {e}"

    last_output = output

    # Snapshot new windows
    windows_after = set(WindowManager.getImageTitles())
    new_windows = windows_after - windows_before

    # Determine failure — check both explicit errors and zero-object outcomes
    output_lower = last_output.lower()
    failed = "status: error" in output_lower

    # Promote all-combos-zero to ERROR even if Java was happy
    if "final object count: 0" in output_lower and not failed:
        last_output = (
            "SUMMARY: ERROR — script completed but found 0 objects in final output\n"
            + last_output
        )

    return last_output



def _existing_description(directory: str, filename: str) -> Optional[str]:
    """Return the stored description for a script, or None if not registered."""
    dict_path = os.path.join(directory, "script_dictionary.json")
    if not os.path.exists(dict_path):
        return None
    try:
        with open(dict_path, 'r') as f:
            return json.load(f).get(filename, {}).get("description")
    except Exception:
        return None


def _commit_script(directory: str, filename: str, content: str, description: str,
                   error_context: Optional[str] = None) -> str:
    """
    Shared versioning core: archive any existing file, write `content`, update
    script_dictionary.json. Used by save_script (full write), edit_script (patch),
    and copy_file (seed from an existing file) so all three are versioned identically.
    """
    allowed_extensions = ('.py', '.groovy')
    if not filename.lower().endswith(allowed_extensions):
        return f"Error: Only {allowed_extensions} files are permitted."

    try:
        os.makedirs(directory, exist_ok=True)
        dict_path = os.path.join(directory, "script_dictionary.json")
        lock_path = os.path.join(directory, "script_dictionary.lock")
        full_path = os.path.join(directory, filename)

        lock = FileLock(lock_path, timeout=30)
        with lock:
            data = {}
            if os.path.exists(dict_path):
                with open(dict_path, 'r') as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = {}

            if os.path.exists(full_path):
                archive_dir = os.path.join(directory, "archive")
                os.makedirs(archive_dir, exist_ok=True)
                # microsecond precision so rapid successive versions (several
                # edit_script patches in the same second) don't overwrite archives.
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                archived_path = os.path.join(archive_dir, f"{timestamp}_{filename}")
                shutil.move(full_path, archived_path)

                if filename in data:
                    old_entry = data[filename]
                    old_entry.setdefault("history", []).append({
                        "archived_at": timestamp,
                        "archived_path": archived_path,
                        "description": old_entry.get("description"),
                        "version": old_entry.get("version", 1),
                        "failure_reason": error_context if error_context else "Updated by user/agent",
                    })
                    current_version = old_entry.get("version", 1) + 1
                else:
                    current_version = 2
            else:
                current_version = 1

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

            data[filename] = {
                "full_path": full_path,
                "language": "Python" if filename.endswith('.py') else "Groovy",
                "description": description,
                "version": current_version,
                "last_modified": datetime.datetime.now().isoformat(),
                "history": data.get(filename, {}).get("history", []),
            }
            with open(dict_path, 'w') as f:
                json.dump(data, f, indent=4)

            return f"Successfully saved version {current_version} of {filename}. Previous version archived."
    except Exception as e:
        return f"Error in save_script: {str(e)}"


@tool("save_script")
def save_script(directory: str, filename: str, content: str, description: str, error_context: Optional[str] = None) -> str:
    """
    Save a FULL script and version it in script_dictionary.json.

    Use this ONLY for a brand-new from-scratch script. To CHANGE an existing script
    (fix a bug, tweak parameters), use `edit_script` instead — it patches just the
    lines you target, which is far faster and cannot break untouched code. To base a
    new script on an existing file, use `copy_file` then `edit_script`.

    Args:
        directory: Where to save, e.g. /app/data/projects/[name]/scripts/imagej/ (Groovy)
                   or .../scripts/python/ (Python).
        filename: Name of the script (must be .py or .groovy).
        content: The full source code.
        description: Short, precise summary (functionality, inputs, outputs, key params).
        error_context: (Optional) If this is a fix, the failure reason being addressed.
    """
    return _commit_script(directory, filename, content, description, error_context)


@tool("edit_script")
def edit_script(directory: str, filename: str,
                old_string: Optional[str] = None, new_string: Optional[str] = None,
                edits: Optional[list] = None,
                error_context: Optional[str] = None, description: Optional[str] = None,
                replace_all: bool = False) -> str:
    """
    Apply SURGICAL patch(es) to an existing saved script. This is the preferred way to
    change a script (fix a bug, tweak parameters) — it touches only the text you target,
    so it is far cheaper than re-emitting the file and cannot introduce errors in
    untouched code. Versioning is handled exactly like save_script.

    Work like a careful engineer: from the file content you ALREADY have (from load_script
    or copy_file), plan ALL your changes up front. Do NOT re-read the file between or after
    edits — patches apply to the content you already have.

    If an edit fails to match ('not found' / 'not unique'), do NOT keep guessing variants:
    re-read the file ONCE with load_script to copy the exact text, and if it still won't
    apply, fall back to save_script with the whole corrected file. Never retry the same
    failing edit more than once.

    TWO forms:
      • Single change — pass `old_string` + `new_string`.
      • SEVERAL disconnected changes — pass `edits`, a list of
        {"old_string": ..., "new_string": ..., optional "replace_all": bool} objects.
        ALWAYS prefer ONE edit_script call with an `edits` list over multiple calls: the
        edits are applied in order and committed as a SINGLE new version, and the whole
        batch is ATOMIC — if ANY old_string is missing or non-unique, NOTHING is written
        and you get told which edit failed, so you never leave a half-patched file.

    Args:
        directory:   Folder containing the script.
        filename:    The .py or .groovy file to patch.
        old_string:  (Single form) Exact text to replace — copy it verbatim (incl.
                     indentation) from the content you have. Must be UNIQUE unless replace_all.
        new_string:  (Single form) Replacement text.
        edits:       (Multi form) List of {old_string, new_string[, replace_all]} objects,
                     each targeting a DISTINCT, non-overlapping region. Applied in order.
        error_context: (Optional) For a fix, the failure reason (stored in history).
        description: (Optional) New one-line description; if omitted the existing one is kept.
        replace_all: (Optional, single form) Replace every occurrence (default: one unique match).
    """
    allowed_extensions = ('.py', '.groovy')
    if not filename.lower().endswith(allowed_extensions):
        return f"Error: Only {allowed_extensions} files can be edited."
    full_path = os.path.join(directory, filename)
    if not os.path.exists(full_path):
        return (f"Error: {full_path} not found. Create it with save_script (new script) "
                f"or copy_file (seed from an existing file) first.")
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

    # Normalize both forms into one ordered list of (old, new, replace_all).
    # strip_line_numbers defensively removes any "<n><TAB>" prefixes the model copied
    # from a numbered load_script view — those prefixes aren't in the file, so without
    # this every such old_string would miss. No-op on normal (unnumbered) text.
    edit_list = []
    if edits:
        if not isinstance(edits, (list, tuple)):
            return "Error: 'edits' must be a list of {old_string, new_string} objects."
        for e in edits:
            if not isinstance(e, dict) or "old_string" not in e or "new_string" not in e:
                return "Error: each item in 'edits' must be an object with 'old_string' and 'new_string'."
            edit_list.append((strip_line_numbers(e["old_string"]), strip_line_numbers(e["new_string"]),
                              bool(e.get("replace_all", False))))
    elif old_string is not None and new_string is not None:
        edit_list.append((strip_line_numbers(old_string), strip_line_numbers(new_string), replace_all))
    else:
        return "Error: provide either (old_string AND new_string) or a non-empty 'edits' list."
    if not edit_list:
        return "Error: no edits provided."

    # Apply sequentially to an in-memory copy. ATOMIC: validate each before anything is
    # written; on any failure return without committing (no half-patched file).
    working = content
    total_repl = 0
    for idx, (os_, ns_, ra_) in enumerate(edit_list, 1):
        tag = f"edit {idx}: " if len(edit_list) > 1 else ""
        if not os_:
            return f"Error: {tag}old_string is empty. No edits applied."
        if os_ == ns_:
            return f"Error: {tag}old_string and new_string are identical — nothing to change. No edits applied."
        cnt = working.count(os_)
        if cnt == 0:
            return (f"Error: {tag}old_string not found (after applying any earlier edits). Copy the exact "
                    f"text verbatim from the content you have; for multiple edits target DISTINCT, "
                    f"non-overlapping regions. No edits applied.")
        if cnt > 1 and not ra_:
            return (f"Error: {tag}old_string occurs {cnt} times — not unique. Add surrounding context to "
                    f"target one spot, or set replace_all=true for this edit. No edits applied.")
        working = working.replace(os_, ns_) if ra_ else working.replace(os_, ns_, 1)
        total_repl += cnt if ra_ else 1

    if working == content:
        return "Error: edits produced no change."
    if description is None:
        description = _existing_description(directory, filename) or "Patched via edit_script."
    result = _commit_script(directory, filename, working, description, error_context)
    if result.startswith("Successfully"):
        ne = len(edit_list)
        return (f"Patched {filename}: {ne} edit{'s' if ne != 1 else ''}, "
                f"{total_repl} replacement{'s' if total_repl != 1 else ''} — one new version. {result}")
    return result


@tool("copy_file")
def copy_file(source_path: str, directory: str, filename: str, description: str) -> str:
    """
    Copy ANY existing script into the project and register it — then RETURN ITS FULL
    CONTENT so you can patch it immediately with `edit_script` WITHOUT a separate
    load_script call (one less round-trip).

    Use whenever you want to base a new script on an existing file instead of writing
    from scratch: a verified recipe/reference SCRIPT, a plugin workflow example under
    /app/skills/, or a prior script in this project. After copying, make every change
    with `edit_script` (patch parameters / input-output paths / sections that don't
    apply); preserve the rest. Do NOT save_script over a copied file, and do NOT
    load_script it — its content is returned below.

    Args:
        source_path: Absolute path to the .groovy/.py file to copy.
        directory:   Destination folder (e.g. .../scripts/imagej/ or .../scripts/python/).
        filename:    Name for the new script (.py or .groovy).
        description: Short summary of what this script will do (stored for the supervisor).
    """
    allowed_extensions = ('.py', '.groovy')
    if not filename.lower().endswith(allowed_extensions):
        return f"Error: Only {allowed_extensions} files are permitted."
    if not source_path.lower().endswith(allowed_extensions):
        return f"Error: source must be a .py or .groovy file, got {source_path}."
    if not os.path.exists(source_path):
        return f"Error: source not found: {source_path}"
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return f"Error reading source: {str(e)}"
    result = _commit_script(directory, filename, content, description)
    if not result.startswith("Successfully"):
        return result
    return (f"Copied '{os.path.basename(source_path)}' -> {filename} and registered it. "
            f"Patch it now with edit_script (do NOT load_script — full content follows).\n"
            f"--- BEGIN {filename} ---\n{content}\n--- END {filename} ---")



@tool("execute_script")
def execute_script(directory: str, filename: str) -> str:
    """
    Triggers the execution of a saved Python or Groovy script within the project environment.

    WHEN TO USE:
    - Use this ONLY after you have verified the script's description via 'get_script_info'.
    - Use this to run a sequence of tasks (e.g., first run the Groovy segmentation, then the Python analysis).

    BEHAVIOR:
    - For .groovy: Automatically handles ImageJ/Fiji window management, snapshots open images,
      and cleans up (closes) new windows if a crash occurs to prevent GUI clutter.
    - For .py: Automatically sets the working directory, pre-imports scientific libraries (pandas,
      numpy, seaborn), and configures high-resolution plotting.

    INPUTS:
    - directory: The directory where the script is located. This will also become the
      working directory for Python execution.
    - filename: The name of the file to execute. Must end in .py or .groovy.

    OUTPUT:
    - Returns the full STDOUT and STDERR of the execution.
    - On SUCCESS: Provides confirmation logs.
    - On FAILURE: Provides a detailed traceback. Pass this traceback to the Debugger agent
      if a fix is required.
    """
    full_path = os.path.join(directory, filename)

    if not os.path.exists(full_path):
        return f"Error: File {full_path} not found."

    with open(full_path, 'r', encoding='utf-8') as f:
        code_content = f.read()

    # Route based on extension
    if filename.endswith('.py'):
        # Calls your existing run_python_code function
        output = run_python_code(code_content, directory)
    elif filename.endswith('.groovy'):
        # Calls your existing run_script_safe function
        output = run_script_safe(language="groovy", code=code_content)
    else:
        return f"Error: File extension of {filename} is not supported for execution."

    # On a verified-green run, hand the result to the background Librarian: it files
    # the reusable recipe and/or the debugger's buffered error->fix lesson, dedups,
    # and (periodically) rebalances CORE — all off the hot path, so the task never
    # waits. Lazy import avoids any import cycle with the agents/RAG layer.
    try:
        from .learned_memory import on_success
        on_success(directory, filename, output)
    except Exception:
        pass

    return output

@tool("get_script_info")
def get_script_info(directory: str, filename: str) -> str:
    """
    (Supervisor-only) Read the one-line description a subagent logged for a script.

    This is an EXCEPTION tool, NOT a routine step. Do NOT call it to "verify" a script
    after the coder saves or before you execute — the coder already returns its
    script_path and description in the ScriptHandoff, so calling this adds a wasted turn
    and can trap you in a verify -> re-save -> verify loop.

    WHEN TO USE (only these):
    - The subagent returned success=False or with NO description, and you need to confirm
      whether anything was logged at all.
    - You genuinely forgot what an OLD file in the directory does and it is not in the
      current handoff.
    Otherwise, trust the handoff and proceed straight to execute_script.

    INPUTS:
    - directory: The project root or output folder where 'script_dictionary.json' resides.
    - filename: The exact name of the script (e.g., 'segment_cells.groovy').

    OUTPUT:
    - Returns a formatted string with the Language and the logged description, or an error
      if the script is not in the dictionary (i.e. the subagent failed to log its work).
    """
    dict_path = os.path.join(directory, "script_dictionary.json")
    if not os.path.exists(dict_path):
        return "Error: script_dictionary.json missing. The subagent may not have saved the script correctly."
    
    with open(dict_path, 'r') as f:
        data = json.load(f)
    
    info = data.get(filename)
    if not info:
        return f"Error: {filename} not found in the project dictionary."
    
    return f"FILE: {filename}\nLANGUAGE: {info['language']}\nPURPOSE: {info['description']}"



@tool("load_script")
def load_script(directory: str, filename: str) -> str:
    """
    Reads the content of a saved Python or Groovy script from the disk.

    WHEN TO USE:
    - CODER: Use this to review existing code before writing a complementary script.
    - DEBUGGER: Use this to retrieve the code that caused an error or traceback.

    CONSTRAINTS:
    - Only .py and .groovy files can be read.
    - Read a given file at most ONCE — its content does not change while you work. Do not
      re-load it to 'verify'; use the content you already have.
    - Do not use this tool to 'verify' a script for the Supervisor (use get_script_info instead).

    Each line is shown with a leading "<line-number><TAB>" for reference (e.g. mapping a
    traceback line to code). These prefixes are display-only — NOT part of the file.
    You may still copy a line verbatim (prefix and all) into edit_script's old_string;
    edit_script strips the prefix before matching, so it just works.
    """
    allowed_extensions = ('.py', '.groovy')
    if not filename.lower().endswith(allowed_extensions):
        return f"Error: Only {allowed_extensions} files can be loaded."

    full_path = os.path.join(directory, filename)

    if not os.path.exists(full_path):
        return f"Error: File {full_path} not found in {directory}."

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"--- START OF FILE: {filename} ---\n{add_line_numbers(content)}\n--- END OF FILE ---"
    except Exception as e:
        return f"Error reading file: {str(e)}"
    


@tool("get_script_history")
def get_script_history(directory: str, filename: str) -> str:
    """
    Retrieves the version history and past failure reasons for a specific script.
    
    WHEN TO USE:
    - DEBUGGER: Use this to see what went wrong in previous versions so you don't 
      attempt the same failed fix twice.
    - CODER: Use this to understand the evolution of the script and why certain 
      logic was changed.

    OUTPUT:
    - Returns a list of all archived versions, including timestamps, paths to 
      the old files, and the 'failure_reason' logged during those iterations.
    """
    dict_path = os.path.join(directory, "script_dictionary.json")
    if not os.path.exists(dict_path):
        return "No script dictionary in this directory yet — no prior versions exist. Proceed without consulting history."

    with open(dict_path, 'r') as f:
        data = json.load(f)

    script_data = data.get(filename)
    if not script_data:
        return f"No history found for {filename}. Proceed without consulting history."

    history = script_data.get("history", [])
    if not history:
        return f"No previous history found for {filename}. This is version 1 — no prior attempts to learn from. Proceed."

    # Format the history for the agent
    report = [f"History for {filename} (Current Version: {script_data.get('version')})"]
    for entry in history:
        report.append(
            f"--- Version {entry['version']} ---\n"
            f"Archived at: {entry['archived_at']}\n"
            f"Archive Path: {entry['archived_path']}\n"
            f"Reason for archiving: {entry['failure_reason']}\n"
        )
    
    return "\n".join(report)