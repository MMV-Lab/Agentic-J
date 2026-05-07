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



@tool("save_script")  
def save_script(directory: str, filename: str, content: str, description: str, error_context: Optional[str] = None) -> str:
    """
    Saves a script, archives previous versions, and maintains a versioned history in script_dictionary.json.
    
    Args:
        directory: Path to the directory where the script should be saved must look like this:
        Correct:   /app/data/projects/[project_name]/scripts/imagej/
        WRONG:     /app/data/projects/[project_name]/scripts/
        WRONG:     /app/data/projects/[project_name]/
        filename: Name of the script (must be .py or .groovy).
        content: The new source code.
        description: A short and precise summary of what the script does for the supervisor. Maximize information and minimze tokens.
                     Should include key details about the script's functionality, inputs, outputs, and any important parameters or usage notes.
                     This description will be stored in the script_dictionary.json for reference.
        error_context: (Optional) If this is a fix, provide the error message/reason why the 
                       previous version was archived.
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
            # Load existing dictionary
            data = {}
            if os.path.exists(dict_path):
                with open(dict_path, 'r') as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = {}

            # 1. Archive the existing file and its metadata
            if os.path.exists(full_path):
                archive_dir = os.path.join(directory, "archive")
                os.makedirs(archive_dir, exist_ok=True)
                
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                archived_filename = f"{timestamp}_{filename}"
                archived_path = os.path.join(archive_dir, archived_filename)
                
                # Move the actual file
                shutil.move(full_path, archived_path)
                
                # Update Metadata History
                if filename in data:
                    old_entry = data[filename]
                    history_entry = {
                        "archived_at": timestamp,
                        "archived_path": archived_path,
                        "description": old_entry.get("description"),
                        "version": old_entry.get("version", 1),
                        "failure_reason": error_context if error_context else "Updated by user/agent"
                    }
                    
                    # Ensure a history list exists for this filename
                    if "history" not in old_entry:
                        old_entry["history"] = []
                    
                    old_entry["history"].append(history_entry)
                    current_version = old_entry.get("version", 1) + 1
                else:
                    current_version = 2
            else:
                current_version = 1

            # 2. Save the NEW file
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 3. Update the Dictionary with the new active entry
            data[filename] = {
                "full_path": full_path,
                "language": "Python" if filename.endswith('.py') else "Groovy",
                "description": description,
                "version": current_version,
                "last_modified": datetime.datetime.now().isoformat(),
                "history": data.get(filename, {}).get("history", [])
            }

            with open(dict_path, 'w') as f:
                json.dump(data, f, indent=4)

            return f"Successfully saved version {current_version} of {filename}. Previous version archived."

    except Exception as e:
        return f"Error in save_script: {str(e)}"
    


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
        return run_python_code(code_content, directory)
    
    elif filename.endswith('.groovy'):
        # Calls your existing run_script_safe function
        return run_script_safe(language="groovy", code=code_content)

    return f"Error: File extension of {filename} is not supported for execution."

@tool("get_script_info")
def get_script_info(directory: str, filename: str) -> str:
    """
    Retrieves the metadata and functional description for a specific script from the project dictionary.
    
    WHEN TO USE:
    - Use this immediately AFTER the Coder/Architect subagent claims to have saved a script.
    - Use this to VERIFY that the script's logic (e.g., threshold methods, file paths, specific algorithms) 
      matches your original instructions before you attempt to execute it.
    - Use this if you have forgotten what a specific file in the directory does.

    INPUTS:
    - directory: The project root or output folder where 'script_dictionary.json' resides.
    - filename: The exact name of the script (e.g., 'segment_cells.groovy').

    OUTPUT:
    - Returns a formatted string containing the Language and the Coder's detailed description.
    - If the script is not in the dictionary, it returns an error; use this to catch if the 
      subagent failed to log its work.
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
    - Do not use this tool to 'verify' a script for the Supervisor (use get_script_info instead).
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
        return f"--- START OF FILE: {filename} ---\n{content}\n--- END OF FILE ---"
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