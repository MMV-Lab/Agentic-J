import jpype
from jpype import JClass, JImplements, JOverride
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
    Attempt to read text content from a frame.
    Works for TextWindow (Log, Exception, etc.) which expose getTextPanel().
    """
    try:
        text_panel = frame.getTextPanel()
        return str(text_panel.getText()).strip()
    except Exception:
        pass

    # Fallback: recurse into AWT components (same as before)
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


def _collect_new_frames(frames_before: dict, timeout: float = 0.5) -> list[str]:
    """
    Poll for up to `timeout` seconds for new AWT Frames to appear,
    read their text content, close them, and return messages.
    This catches ImageJ TextWindow exceptions which show up in the Window menu.
    """
    messages = []
    deadline = time.monotonic() + timeout

    # Titles to skip — these are permanent ImageJ UI frames
    IGNORE_TITLES = {"ImageJ", "Fiji", "Log", "ROI Manager", "Results", ""}

    while time.monotonic() < deadline:
        _flush_edt()

        current = _get_open_frames()
        new_frames = {
            title: frame
            for title, frame in current.items()
            if title not in frames_before and title not in IGNORE_TITLES
        }

        if new_frames:
            for title, frame in new_frames.items():
                text = _read_frame_text(frame)
                entry = f"[{title}]"
                if text:
                    entry += f"\n{text}"
                messages.append(entry)
                # Close the window
                try:
                    frame.dispose()
                except Exception:
                    pass
            break

        time.sleep(0.05)

    return messages

# ── Popup dialog text extraction ──────────────────────────────────────────

def _read_window_text(window) -> str:
    """
    Read text from any AWT Window. Tries in order:
    1. getTextPanel()  — TextWindow, exception windows
    2. MessageDialog field 'label' → MultiLineLabel field 'lines'
       Required because MessageDialog does NOT add label to getComponents()
       so component recursion never finds it.
    3. Component recursion fallback
    """
    try:
        text_panel = window.getTextPanel()
        text = str(text_panel.getText()).strip()
        if text:
            return text
    except Exception:
        pass

    try:
        cls = window.getClass()
        while cls is not None:
            try:
                label_field = cls.getDeclaredField("label")
                label_field.setAccessible(True)
                multi_label = label_field.get(window)
                if multi_label is not None:
                    lines_field = multi_label.getClass().getDeclaredField("lines")
                    lines_field.setAccessible(True)
                    lines = lines_field.get(multi_label)
                    if lines is not None:
                        text = " ".join(str(l) for l in lines).strip()
                        if text:
                            return text
            except Exception:
                pass
            try:
                cls = cls.getSuperclass()
                if str(cls.getName()) == "java.lang.Object":
                    break
            except Exception:
                break
    except Exception:
        pass

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

    Catches modal dialogs (IJ.error(), "command not found") that BLOCK the
    EDT during execution. These dialogs are already dismissed by the time
    the script returns so neither _collect_new_frames nor any post-execution
    check can see them. Only a concurrent thread can catch them in time.

    Does NOT handle TextWindow exceptions — _collect_new_frames does that.
    """

    def __init__(self, snapshot_before: dict, poll_interval: float = 0.05):
        self._seen         = dict(snapshot_before)
        self._messages: list[str] = []
        self._lock         = threading.Lock()
        self._stop         = threading.Event()
        self._thread       = threading.Thread(target=self._run, daemon=True)

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

                # Read immediately while window is still open
                text  = _read_window_text(window)
                entry = f"[{title}]" if title else "[Window]"
                if text:
                    entry += f"\n{text}"

                with self._lock:
                    self._messages.append(entry)

                self._seen[key] = window

        except Exception:
            pass

    def stop(self) -> list[str]:
        self._stop.set()
        self._thread.join(timeout=2.0)
        with self._lock:
            return list(self._messages)


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


def run_groovy_script(script: str, ij) -> str:
    """
    Execute a Groovy script in ImageJ/Fiji capturing all output channels:

      Channel                    | Mechanism
      ---------------------------|------------------------------------------
      System.out / System.err    | ByteArrayOutputStream redirect
      IJ.log()                   | Log TextWindow text delta
      TextWindow exceptions      | _collect_new_frames via Frame.getFrames()
      Modal dialogs DURING exec  | _WindowMonitor background thread
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
    frames_before  = _get_open_frames()         # unchanged — for TextWindow detection
    windows_before = _snapshot_all_windows()    # new — for modal dialog detection

    monitor = _WindowMonitor(windows_before).start()

    try:
        result = ij.py.run_script("Groovy", script)
        stdout = str(out_stream.toString())
        stderr = str(err_stream.toString())

        ij_log_new      = get_new_ij_log_entries(ij_log_before)
        dialog_messages = monitor.stop()                       # modal dialogs during exec
        window_messages = _collect_new_frames(frames_before)  # TextWindows after exec
        all_messages    = dialog_messages + window_messages

        ij_log_has_error = any(k in ij_log_new.lower()
                               for k in ("error", "exception", "failed", "warning"))
        window_has_error = len(all_messages) > 0

        if stderr.strip() or window_has_error:
            status = "ERROR"
        elif ij_log_has_error:
            status = "WARNING"
        else:
            status = "SUCCESS"

        return (
            f"STATUS: {status}\n"
            "LANGUAGE: Groovy\n"
            f"STDOUT:\n{stdout}\n"
            f"STDERR:\n{stderr}\n"
            f"IJ_LOG:\n{ij_log_new}\n"
            f"EXCEPTION_WINDOWS:\n{chr(10).join(all_messages)}\n"
            f"RESULT:\n{result}"
        )

    except Exception as e:
        ij_log_new      = get_new_ij_log_entries(ij_log_before)
        dialog_messages = monitor.stop()
        window_messages = _collect_new_frames(frames_before)
        all_messages    = dialog_messages + window_messages

        return (
            "STATUS: ERROR\n"
            "LANGUAGE: Groovy\n"
            "STDOUT:\n\n"
            f"STDERR:\n{str(e)}\n{str(err_stream.toString())}\n"
            f"IJ_LOG:\n{ij_log_new}\n"
            f"EXCEPTION_WINDOWS:\n{chr(10).join(all_messages)}\n"
            "RESULT:\nnull"
        )

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

    # Determine failure
    failed = any(k in output.lower() for k in ["error", "exception", "failed"])

    if failed:
        # Close windows created during failed attempt
        for title in new_windows:
            imp = WindowManager.getImage(title)
            if imp:
                imp.changes = False
                imp.close()

            print("Execution failed")
            return output
    else:
        # Success: leave windows visible
        return output

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
        return "Script dictionary does not exist yet. No history available. Start coding to create the first entry!"

    with open(dict_path, 'r') as f:
        data = json.load(f)

    script_data = data.get(filename)
    if not script_data:
        return f"No history found for {filename}."

    history = script_data.get("history", [])
    if not history:
        return f"No previous history found for {filename}. This is version 1. Start coding to create the first entry!"

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