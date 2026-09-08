import jpype
from jpype import JClass, JImplements, JOverride
from matplotlib import text
from langchain.tools import tool
from imagentj.imagej_context import get_ij
import os
import re
import json
from .analyst_tools import run_python_code
import datetime
import shutil
from typing import Optional, Any, List
from pydantic import BaseModel, ConfigDict
from filelock import FileLock
import logging
import threading
import time
from scyjava import jimport
from imagentj import run_control, stop_signal
from .utils import add_line_numbers, strip_line_numbers

log = logging.getLogger(__name__)

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


def _is_unattended_mode() -> bool:
    """Whether scripts are running without a human available to answer dialogs.

    Benchmark auto-pilot predates ``IMAGENTJ_UNATTENDED`` and does not set it, so
    derive the same fact from the benchmark flags as well.  An explicit true
    unattended flag always wins; an explicit false flag only disables the generic
    unattended mode, not benchmark auto-pilot.
    """
    explicit = os.environ.get("IMAGENTJ_UNATTENDED", "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    return (
        os.environ.get("BENCHMARK_MODE", "").strip().lower() == "true"
        and os.environ.get("BENCHMARK_INTERACTIVE", "").strip().lower() != "true"
    )


def _is_dialog_window(window) -> bool:
    """Return True for any java.awt.Dialog/JDialog, modal or modeless.

    ``WaitForUserDialog`` is deliberately modeless at the AWT level but still
    blocks the calling workflow until a button is pressed, so ``isModal()`` is not
    a sufficient unattended-safety test.
    """
    try:
        cls = window.getClass()
        while cls is not None:
            if str(cls.getName()) in {"java.awt.Dialog", "javax.swing.JDialog"}:
                return True
            cls = cls.getSuperclass()
    except Exception:
        pass
    return False


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

    def __init__(
        self,
        snapshot_before: dict,
        poll_interval: float = 0.05,
        modal_grace: float = 0.5,
        unattended: Optional[bool] = None,
    ):
        self._seen = dict(snapshot_before)
        self._errors: list[str] = []
        self._results_count = 0
        self._info: list[str] = []
        self._unattended = _is_unattended_mode() if unattended is None else unattended
        self._poll_interval = poll_interval
        self._modal_grace = modal_grace
        self._pending_modals: dict[str, float] = {}
        self._fatal_dialog: Optional[str] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "_WindowMonitor":
        self._thread.start()
        return self

    def _run(self):
        while not self._stop.is_set():
            self._poll()
            time.sleep(self._poll_interval)

    def _poll(self):
        try:
            Window = jimport("java.awt.Window")
            visible_keys: set[str] = set()
            for window in Window.getWindows():
                if not window.isVisible():
                    continue
                try:
                    title = str(window.getTitle())
                except Exception:
                    title = str(window.getClass().getSimpleName())

                key = f"{window.getClass().getSimpleName()}::{title}"
                visible_keys.add(key)

                if key in self._seen:
                    continue
                if title in _IGNORE_TITLES:
                    self._seen[key] = window
                    continue

                # A macro can instantiate a dialog and immediately satisfy it from
                # recorded options.  Give those transient windows a short grace
                # period, but a modal that remains visible in unattended mode is
                # necessarily waiting for input that will never arrive.  Do not
                # auto-click or dispose it: accepting defaults can silently change a
                # scientific result.  _await_groovy observes this fatal marker and
                # terminates the disposable worker instead.
                if self._unattended and _is_dialog_window(window):
                    first_seen = self._pending_modals.setdefault(key, time.monotonic())
                    if time.monotonic() - first_seen < self._modal_grace:
                        continue
                    text = _read_window_text(window)
                    entry = f"[{title}]" if title else "[Modal dialog]"
                    if text:
                        entry += f"\n{text[:500]}"
                    with self._lock:
                        if self._fatal_dialog is None:
                            self._fatal_dialog = entry
                            self._errors.append(entry)
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

            for key in list(self._pending_modals):
                if key not in visible_keys:
                    self._pending_modals.pop(key, None)
        except Exception:
            pass

    @property
    def fatal_dialog(self) -> Optional[str]:
        with self._lock:
            return self._fatal_dialog

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


# ── Groovy interruption ───────────────────────────────────────────────────
#
# Groovy runs in the shared Fiji JVM, which is what lets a script leave its images
# on screen for the user. Stopping one is subtle, and the obvious approach is
# wrong in a way that silently lies:
#
# ij.py.run_script() is `script().run(...).get()` — the script executes on a
# SciJava pool thread and the caller merely blocks on Future.get(). Interrupting
# the *calling* thread therefore only stops us waiting; the script runs happily on.
# We submit the Future ourselves so we can act on the thread that is really doing
# the work.
#
# Abort is then three escalating signals:
#   1. Future.cancel(true) — interrupts the SciJava thread executing the script
#   2. Macro.abort()       — stops the IJ macro interpreter between statements
#   3. IJ.setKeyDown(ESC)  — long-running IJ ops poll IJ.escapePressed() and bail
#
# Interrupting only reaches code that checks the interrupt flag, so on its own it
# cannot stop a pure-CPU `while(true){}` — and there is no hard kill to fall back
# on, JDK 20 having degraded Thread.stop() to always throw
# UnsupportedOperationException. That gap is closed by compiling every script with
# @ThreadInterrupt (see _INTERRUPTIBLE_PREFIX), which injects the missing checks.
#
# Verified on this container (JDK 21.0.10, ImageJ 1.54p): sleep/IO/IJ operations
# and runaway CPU loops all stop. What remains uninterruptible is a blocking call
# *inside a Java library* that ignores interrupts — the transform instruments the
# Groovy code, not the plugin it calls into.
#
# Crucially we do not have to guess which happened. Future.isDone() returns true
# the moment cancel() is called even when the thread keeps running, so instead we
# inspect JVM thread stacks for Groovy frames and report what is actually true.

_ESC_KEYCODE = 27           # java.awt.event.KeyEvent.VK_ESCAPE
_ABORT_GRACE_SECONDS = 5.0  # how long we wait for an abort to actually land

# Groovy's @ThreadInterrupt AST transform injects a
# Thread.currentThread().isInterrupted() check into every loop iteration and
# method entry. That is what makes a pure-CPU `while(true){x++}` killable at all:
# Future.cancel(true) sets the interrupt flag, but code that never blocks would
# otherwise never look at it.
#
# Applied by annotating an import — the documented way to attach a script-level
# AST transform — and deliberately kept to ONE line, because it shifts every
# reported error line number by exactly that much (see _fix_line_numbers).
#
# Verified on this container: the spin loop dies, and SciJava `#@` parameter
# injection still resolves behind this line.
_INTERRUPTIBLE_PREFIX = "@groovy.transform.ThreadInterrupt import groovy.transform.Field\n"
_PREFIX_LINES = 1

_SCRIPT_LINE_RE = re.compile(r"(script\.groovy:)(\d+)")


def _fix_line_numbers(text: str) -> str:
    """
    Undo the line shift the @ThreadInterrupt prefix introduces.

    The debugger agent navigates by these numbers, so an uncorrected off-by-one
    would point it at the wrong line of every failing Groovy script.
    """
    return _SCRIPT_LINE_RE.sub(
        lambda m: f"{m.group(1)}{max(int(m.group(2)) - _PREFIX_LINES, 1)}", text
    )
_HARD_TIMEOUT_SECONDS = run_control.HARD_TIMEOUT_SECONDS


def _signal_imagej_abort() -> None:
    """Fire ImageJ's cooperative abort paths. Never raises."""
    try:
        jimport("ij.Macro").abort()
    except Exception:
        pass
    try:
        jimport("ij.IJ").setKeyDown(_ESC_KEYCODE)
    except Exception:
        pass


def _reset_imagej_escape() -> None:
    """
    Clear a latched ESC. Must run before every script: IJ.escapePressed() is
    global JVM state, so an ESC left set by a previous abort would make the next
    script bail out instantly for no visible reason.
    """
    try:
        jimport("ij.IJ").resetEscape()
    except Exception:
        pass


def _groovy_thread_ids() -> set[int]:
    """
    IDs of JVM threads currently executing a Groovy script.

    This is our ground truth for "is it actually still running" — the Future
    cannot tell us, since cancel() marks it done regardless.
    """
    ids: set[int] = set()
    try:
        JThread = jimport("java.lang.Thread")
        for entry in JThread.getAllStackTraces().entrySet():
            frames = " ".join(str(f.getClassName()) for f in entry.getValue())
            if "groovy" in frames.lower():
                ids.add(int(entry.getKey().getId()))
    except Exception:
        pass
    return ids


class _GroovyRunner:
    """
    Submits a Groovy script and keeps hold of the Future and the thread running it.

    Unlike ij.py.run_script this never blocks the caller, so the run stays
    observable and the UI can be handed back the instant a stop is requested.
    """

    def __init__(self, ij, script: str):
        self._ij = ij
        self._script = script
        self._future = None
        self._baseline: set[int] = set()
        self._script_tid: int | None = None

    def start(self) -> "_GroovyRunner":
        # Threads already running Groovy (e.g. an earlier detached runaway) must
        # not be mistaken for this run's thread.
        self._baseline = _groovy_thread_ids()
        self._future = self._ij.script().run(
            "script.groovy", _INTERRUPTIBLE_PREFIX + self._script, True
        )
        return self

    def track_thread(self) -> None:
        """Latch onto this run's SciJava thread. Cheap no-op once found."""
        if self._script_tid is not None:
            return
        new = _groovy_thread_ids() - self._baseline
        if new:
            self._script_tid = next(iter(new))

    def script_thread_running(self) -> bool:
        """
        Is this run's thread still executing Groovy?

        If we never managed to latch onto the thread we fall back to "is any
        Groovy thread running that was not already running when we started" —
        failing to identify the thread must never be reported as a clean stop.
        """
        self.track_thread()
        if self._script_tid is None:
            return bool(_groovy_thread_ids() - self._baseline)
        return self._script_tid in _groovy_thread_ids()

    @property
    def done(self) -> bool:
        try:
            return bool(self._future.isDone())
        except Exception:
            return True

    def cancel(self) -> None:
        try:
            self._future.cancel(True)   # mayInterruptIfRunning
        except Exception:
            pass
        _signal_imagej_abort()

    def result(self):
        """Return the script's result, re-raising the script's own error if it threw."""
        try:
            return self._future.get()
        except Exception as exc:
            # Future.get wraps script failures in ExecutionException; unwrap so the
            # debugger sees the real Groovy error rather than the wrapper.
            cause = getattr(exc, "getCause", None)
            if cause is not None:
                try:
                    inner = cause()
                    if inner is not None:
                        raise RuntimeError(str(inner.toString())) from exc
                except RuntimeError:
                    raise
                except Exception:
                    pass
            raise


def _abort_groovy(runner: "_GroovyRunner") -> bool:
    """
    Stop a Groovy run. Returns True only when the script thread has verifiably
    stopped executing — never on the mere fact that we asked it to.
    """
    runner.cancel()
    deadline = time.monotonic() + _ABORT_GRACE_SECONDS
    while time.monotonic() < deadline:
        if not runner.script_thread_running():
            return True
        time.sleep(0.2)

    log.warning(
        "Groovy script ignored abort (Future.cancel + Macro.abort + ESC) after %.0fs; "
        "detaching — its SciJava thread keeps running until it returns on its own.",
        _ABORT_GRACE_SECONDS,
    )
    return False


def _await_groovy(
    runner: "_GroovyRunner",
    handle: "run_control.RunHandle",
    monitor: _WindowMonitor,
    live_sink=None,
    live_output=None,
) -> bool:
    """
    Wait for the script, honouring stop requests. Returns True if we detached from
    a script that refused to stop.

    `live_sink` matters only for the batch-subprocess path: the script's output is
    captured into JVM buffers, so without echoing it to real stdout the parent
    process would see total silence and its watchdog would judge a perfectly
    healthy long batch job as stuck.
    """
    deadline = time.monotonic() + _HARD_TIMEOUT_SECONDS
    emitted = 0

    def _echo() -> None:
        nonlocal emitted
        if live_sink is None or live_output is None:
            return
        try:
            current = live_output()
            # IJ.log('\\Clear') makes this shrink, so resync instead of slicing
            # with a stale offset (which would emit garbage or nothing at all).
            if len(current) < emitted:
                emitted = 0
            if len(current) > emitted:
                live_sink.write(current[emitted:])
                live_sink.flush()
                emitted = len(current)
        except Exception:
            pass

    while True:
        runner.track_thread()
        _echo()
        fatal_dialog = monitor.fatal_dialog
        if fatal_dialog and not handle.terminated:
            # Never dismiss a dialog in a disposable worker. Closing it can make
            # the plugin accept defaults and let the script execute another write
            # before cooperative cancellation lands. Return the error report now;
            # groovy_worker flushes it and os._exit() kills the entire JVM.
            if os.environ.get("IMAGENTJ_BATCH_WORKER") == "1":
                return False
            handle.terminate(
                "Unexpected modal dialog in unattended execution: "
                + fatal_dialog.replace("\n", " ")[:300],
                by="watchdog",
            )
            return handle.terminate_succeeded is False
        if runner.done and not handle.terminated:
            _echo()
            return False
        # The Stop button trips the global signal; the watchdog flips the handle
        # from its own thread. Both mean stop waiting on this script.
        if stop_signal.is_set() and not handle.terminated:
            handle.terminate("Stopped by user", by="user")
        # Backstop for when the watchdog is disabled — matches the Python path,
        # which bounds its wait via proc.wait(timeout=...).
        elif time.monotonic() > deadline and not handle.terminated:
            handle.terminate(
                f"Exceeded the hard {_HARD_TIMEOUT_SECONDS}s execution limit",
                by="watchdog",
            )
        if handle.terminated:
            # terminate() flips the status before the abort has actually been
            # attempted, so wait for the verdict rather than racing it to None.
            handle.wait_termination_settled(_ABORT_GRACE_SECONDS + 3.0)
            return handle.terminate_succeeded is False
        time.sleep(0.1)


def _stopped_report(handle, out_stream, ij_log_before, monitor, detached: bool) -> str:
    """
    Report for a run that was stopped, whether it aborted cleanly or had to be
    abandoned. Deliberately not shaped like a crash: the supervisor must not hand
    this to the debugger as a bug to repair.
    """
    monitor.stop()
    try:
        partial = str(out_stream.toString())[-1500:]
    except Exception:
        partial = ""
    try:
        ij_log = get_new_ij_log_entries(ij_log_before)[-800:]
    except Exception:
        ij_log = ""

    by_user = handle.killed_by == "user"
    headline = run_control.stop_headline(handle)
    guidance = run_control.stop_guidance(handle)

    tail = (
        "Groovy script ignored the abort and was detached"
        if detached else
        "Groovy script aborted on request"
    )
    parts = [
        f"SUMMARY: {headline} — {tail}",
        f"STATUS: {'STOPPED' if by_user else 'TERMINATED'}",
        "LANGUAGE: Groovy",
        guidance,
    ]
    if detached:
        parts.append(
            "IMPORTANT: the abort (Future.cancel + Macro.abort + ESC) did not land. Groovy "
            "runs inside the shared Fiji JVM and cannot be force-killed (JDK 21 removed "
            "Thread.stop), so this script MAY STILL BE RUNNING in the background and could "
            "keep writing output or opening windows. Scripts are compiled with "
            "@ThreadInterrupt, so a runaway Groovy loop would have stopped — reaching this "
            "state means it is most likely blocked inside a Java plugin call that ignores "
            "interrupts. Warn the user; to stop it for certain, Fiji has to be restarted."
        )
    parts.append(f"PARTIAL_STDOUT:\n{partial}" if partial.strip() else "PARTIAL_STDOUT: (none)")
    parts.append(f"PARTIAL_IJ_LOG:\n{ij_log}" if ij_log.strip() else "PARTIAL_IJ_LOG: (none)")
    return "\n".join(parts)


def _unexpected_dialog_report(
    handle, out_stream, ij_log_before, monitor, detached: bool
) -> str:
    """Actionable failure for a modal dialog detected during unattended work."""
    fatal = monitor.fatal_dialog or "[unknown modal dialog]"
    monitor.stop()
    try:
        partial = str(out_stream.toString())[-1500:]
    except Exception:
        partial = ""
    try:
        ij_log = get_new_ij_log_entries(ij_log_before)[-800:]
    except Exception:
        ij_log = ""

    parts = [
        "SUMMARY: ERROR — unexpected modal dialog in unattended execution",
        "STATUS: ERROR",
        "LANGUAGE: Groovy",
        "UNATTENDED DIALOG BLOCKED:",
        fatal,
        "The script was terminated because nobody can answer a modal dialog in "
        "auto-pilot mode. Do not auto-click it or retry unchanged. Replace the "
        "prompting plugin entry point with a programmatic/windowless API and pass "
        "every required option explicitly.",
    ]
    if os.environ.get("IMAGENTJ_BATCH_WORKER") == "1":
        parts.append(
            "The isolated worker is exiting with the dialog still unanswered; no "
            "post-dialog script statement is allowed to run."
        )
    if detached:
        parts.append(
            "The in-JVM script ignored cooperative abort. If this was an isolated "
            "batch worker it will now exit; otherwise restart Fiji before running "
            "another script."
        )
    if partial.strip():
        parts.append(f"PARTIAL_STDOUT:\n{partial}")
    if ij_log.strip():
        parts.append(f"PARTIAL_IJ_LOG:\n{ij_log}")
    return "\n".join(parts)


def run_groovy_script(script: str, ij, purpose: str = "", live_sink=None) -> str:
    """
    Execute a Groovy script in ImageJ/Fiji, capturing all output channels
    and classifying windows into errors vs. results vs. info.

    Thin wrapper over _run_groovy_script so the @ThreadInterrupt prefix's line
    shift is corrected at exactly one place, on every return path.
    """
    return _fix_line_numbers(_run_groovy_script(script, ij, purpose, live_sink))


def _run_groovy_script(script: str, ij, purpose: str = "", live_sink=None) -> str:
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

    _reset_imagej_escape()
    runner = _GroovyRunner(script=script, ij=ij).start()

    # The redirected System.out buffer is readable while the script runs, so the
    # watchdog gets live progress here exactly as it does from the Python pipes.
    # IJ.log output is folded in too — plenty of Groovy scripts report progress
    # only through IJ.log, and silence is how we decide a run is stuck.
    def _live_output() -> str:
        try:
            text = str(out_stream.toString()) + str(err_stream.toString())
        except Exception:
            text = ""
        try:
            text += get_new_ij_log_entries(ij_log_before)
        except Exception:
            pass
        return text

    handle = run_control.register(run_control.RunHandle(
        language="groovy",
        code=script,
        purpose=purpose,
        terminator=lambda reason, r=runner: _abort_groovy(r),
        output_provider=_live_output,
    ))

    try:
        detached = _await_groovy(runner, handle, monitor, live_sink, _live_output)

        if monitor.fatal_dialog:
            return _unexpected_dialog_report(
                handle, out_stream, ij_log_before, monitor, detached
            )

        # Stopped runs report as stopped whether or not the abort landed — a
        # script that aborted cleanly must not come back looking like a normal
        # SUCCESS/ERROR result the agent would then act on.
        if handle.terminated:
            return _stopped_report(handle, out_stream, ij_log_before, monitor, detached)

        result = runner.result()
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
        handle.mark_finished()
        run_control.unregister(handle)
        # Clear any ESC we latched, so the next script does not inherit an abort.
        _reset_imagej_escape()

# ── Batch execution in a separate, killable Fiji ──────────────────────────
#
# Groovy in the app's own JVM cannot be force-killed. Groovy in its own PROCESS
# can — SIGKILL always wins. The catch is that a second Fiji sees none of the
# user's open images, so this is not a blanket replacement.
#
# The saving asymmetry: the scripts that actually hang are batch jobs, and batch
# jobs source their own images from disk. A script that reads TIFFs in a loop and
# writes a CSV does not care what the user has open, so it can run in a throwaway
# Fiji and be killed outright. Scripts that DO need live state are short and
# interactive, and cooperative interrupt already handles those.
#
# Routing is deliberately conservative: in-process is the default, and a script is
# only sent to a subprocess when it visibly opens its own inputs and never touches
# the live image. Mis-routing a live-state script would break it, whereas
# mis-routing a batch script only costs killability (today's behaviour).

_EXEC_OVERRIDE_RE = re.compile(
    r"^\s*//\s*imagentj-exec:\s*(inprocess|subprocess)\s*$", re.IGNORECASE | re.MULTILINE
)

# Reading any of these means the script depends on state only the app's Fiji has.
_LIVE_STATE_MARKERS = (
    "getcurrentimage",
    "ij.getimage()",
    "wm.getimage()",
)

# Sourcing images this way means the script is self-contained.
_BATCH_MARKERS = (
    "ij.openimage",
    "listfiles",
    "new opener(",
    "bf.openimageplus",
    "ij.open(",
)


# Work that routinely needs GIGABYTES outside the Java heap: BigStitcher fusion
# buffers, and the TensorFlow-backed networks (CSBDeep/StarDist/DeepImageJ), whose
# native allocations `-Xmx` does not bound at all.
_HEAVY_MARKERS = (
    "bigstitcher", "define multi-view", "calculate pairwise shifts",
    "optimize globally", "image fusion", "fuse dataset",
    "csbdeep", "stardist", "deepimagej", "tensorflow", "genericnetwork",
    "trainable weka",
)


def _check_inprocess_heavy(code: str) -> Optional[str]:
    """Refuse a script that needs the LIVE image AND does heavy native work.

    Those two together are the one combination the executor cannot make safe.
    Live state forces in-process execution (the batch worker has its own empty
    Fiji), and in-process means the app's own JVM — so an out-of-memory death
    takes the whole application with it rather than failing one script.

    That is not hypothetical: a container running exactly this was OOM-killed by
    the kernel 3 min 13 s after start (exit 137), while loading a TensorFlow
    SavedModel from a Groovy script the router had logged as
    `routed in-process: uses live state (ij.getimage())`. There was no Java
    OutOfMemoryError to catch — `-Xmx` does not bound TensorFlow's native
    allocations — and the whole session was lost, unsaved.

    The fix is cheap for the caller: read the input from disk instead of the live
    window, which makes the script self-contained, so it runs in the isolated
    batch worker where an OOM costs only that script.
    """
    lowered = code.lower()
    if _EXEC_OVERRIDE_RE.search(code):
        return None  # an explicit override is a deliberate choice; respect it
    live_hit = next((m for m in _LIVE_STATE_MARKERS if m in lowered), None)
    if not live_hit:
        return None
    heavy_hit = next((m for m in _HEAVY_MARKERS if m in lowered), None)
    if not heavy_hit:
        return None
    return (
        f"SUMMARY: ERROR — heavy work ('{heavy_hit}') combined with live-image state "
        f"('{live_hit}') would run in the app's own JVM\n"
        "STATUS: ERROR\n"
        "LANGUAGE: Groovy\n"
        "PRE-FLIGHT CHECK FAILED (script never executed):\n"
        f"This script reads the LIVE image ({live_hit}), which forces it to run "
        "in-process — inside the application's own Fiji/JVM. It also does heavy work "
        f"({heavy_hit}), whose memory is largely NATIVE and therefore not bounded by "
        "-Xmx. If it exhausts memory there, the kernel kills the entire container: no "
        "Java OutOfMemoryError to catch, no partial results, the whole session lost. A "
        "real run died this way 3 minutes after startup while loading a TensorFlow model.\n"
        "FIX: make the script self-contained so it runs in the isolated batch worker —\n"
        "  - open the input from DISK instead of the live window:\n"
        "      def imp = IJ.openImage(path)          // plain TIFF/PNG\n"
        "      def imp = BF.openImagePlus(opts)[0]   // Bio-Formats formats, windowless\n"
        "  - save any result to disk rather than leaving it in a window.\n"
        "Then an out-of-memory failure costs only this script, and the app survives.\n"
        "If the live window genuinely is the only possible input, say so explicitly with\n"
        "  // imagentj-exec: inprocess\n"
        "on its own line — but expect to lose the session if it runs out of memory."
    )


def _should_run_in_subprocess(code: str) -> tuple[bool, str]:
    """Decide where a Groovy script runs. Returns (use_subprocess, why)."""
    override = _EXEC_OVERRIDE_RE.search(code)
    if override:
        choice = override.group(1).lower() == "subprocess"
        return choice, f"explicit `// imagentj-exec: {override.group(1).lower()}`"

    lowered = code.lower()
    live_hit = next((m for m in _LIVE_STATE_MARKERS if m in lowered), None)
    if live_hit:
        return False, f"uses live state ({live_hit}) — needs the app's Fiji"

    batch_hit = next((m for m in _BATCH_MARKERS if m in lowered), None)
    if batch_hit:
        return True, f"self-contained batch job (opens its own inputs via {batch_hit})"

    return False, "no clear batch signal — defaulting to in-process"


def _batch_env() -> dict:
    """Environment for the worker: smaller heap, no nested watchdog, importable src."""
    env = os.environ.copy()
    # The batch JVM's heap must fit ALONGSIDE the app's, inside the container limit:
    # IMAGENTJ_JVM_HEAP (app, 6g default) + this must stay under the container's
    # memory cap (8g by default here), with room for Python, napari and the OS.
    #
    # Undersizing here is the safe direction. A batch JVM that exhausts its own heap
    # fails only that script, and the app carries on; a container OOM kills the whole
    # app — the exact outcome running batch work out-of-process is meant to prevent.
    # Raise IMAGENTJ_BATCH_HEAP (and the container limit) for memory-hungry batches.
    #
    # Derived rather than fixed: a flat 2g is right under docker-compose's 8 GB cap
    # and badly wrong on an uncapped HPC node, where a reported run had 188-250 GB
    # yet still fused a 4-channel 8x8 mosaic in 2g and died with OutOfMemoryError.
    # A quarter of what is available leaves the app's half plus headroom.
    if os.environ.get("IMAGENTJ_BATCH_HEAP"):
        env["IMAGENTJ_JVM_HEAP"] = os.environ["IMAGENTJ_BATCH_HEAP"]
    else:
        from imagentj.imagej_context import _available_memory_gb
        limit = _available_memory_gb()
        env["IMAGENTJ_JVM_HEAP"] = "2g" if not limit else f"{max(2, limit // 4)}g"
    env["IMAGENTJ_WATCHDOG"] = "0"      # the parent supervises this run
    env["PYTHONUNBUFFERED"] = "1"       # so the watchdog sees progress promptly
    src_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [src_dir, env.get("PYTHONPATH", "")]))
    return env


def _extract_worker_report(stdout: str) -> Optional[str]:
    """Pull the structured report out of Fiji's very chatty stdout."""
    from imagentj.groovy_worker import REPORT_BEGIN, REPORT_END
    if REPORT_BEGIN in stdout and REPORT_END in stdout:
        return stdout.split(REPORT_BEGIN, 1)[1].split(REPORT_END, 1)[0].strip()
    return None


def _run_groovy_subprocess(code: str, purpose: str = "") -> str:
    """
    Run a batch Groovy script in its own Fiji process.

    Reports exactly like the in-process path (the worker reuses run_groovy_script),
    except that a stop here is a genuine kill — never "it may still be running".
    """
    import sys
    import tempfile

    script_path = os.path.join(
        tempfile.gettempdir(), f"imagentj_batch_{os.getpid()}_{int(time.time() * 1000)}.groovy"
    )
    with open(script_path, "w", encoding="utf-8") as script_file:
        script_file.write(code)

    try:
        run = run_control.SupervisedProcess(
            [sys.executable, "-m", "imagentj.groovy_worker", script_path, purpose],
            language="groovy", code=code, purpose=purpose, env=_batch_env(),
        )
    except Exception as exc:
        return f"SUMMARY: ERROR — could not start batch Fiji: {exc}\nSTATUS: ERROR\nLANGUAGE: Groovy"

    try:
        with run:
            run.wait()
            stdout, stderr = run.stdout, run.stderr

            if run.handle.terminated:
                by_user = run.handle.killed_by == "user"
                return "\n".join([
                    f"SUMMARY: {run_control.stop_headline(run.handle)} — batch Groovy process killed",
                    f"STATUS: {'STOPPED' if by_user else 'TERMINATED'}",
                    "LANGUAGE: Groovy",
                    run_control.stop_guidance(run.handle),
                    "The script ran in its own Fiji process and was killed outright, so it is "
                    "definitely no longer running. The app's own Fiji and its open images were "
                    "not affected.",
                    f"PARTIAL_STDOUT:\n{_truncate(stdout, 1500)}" if stdout.strip() else "PARTIAL_STDOUT: (none)",
                ])

            report = _extract_worker_report(stdout)
            if report:
                return report

            # No report means the worker died before finishing — surface why.
            return "\n".join([
                f"SUMMARY: ERROR — batch Fiji exited without a report (code {run.returncode})",
                "STATUS: ERROR",
                "LANGUAGE: Groovy",
                f"STDERR:\n{_truncate(stderr, 1500)}" if stderr.strip() else "STDERR: (none)",
                f"STDOUT:\n{_truncate(stdout, 800)}" if stdout.strip() else "STDOUT: (none)",
            ])
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass


def run_script_safe(language: str, code: str, max_retries: int = 3, purpose: str = "") -> str:
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
    if language.lower() != "groovy":
        raise ValueError(f"Unsupported language: {language}")

    # Self-contained batch jobs go to their own Fiji process, where Stop is a real
    # kill. Everything else stays in the app's Fiji so it can see the live windows.
    use_subprocess, why = _should_run_in_subprocess(code)
    log.info("Groovy execution routed %s: %s",
             "to a batch subprocess" if use_subprocess else "in-process", why)
    if use_subprocess:
        return _run_groovy_subprocess(code, purpose)

    ij = get_ij()

    try:
        last_output = run_groovy_script(code, ij, purpose)
    except Exception as e:
        last_output = f"Exception during execution: {e}"

    # A deliberate stop is not a failed run — return it untouched so the
    # zero-object heuristic below cannot relabel it as an ERROR to be debugged.
    if last_output.lstrip().startswith(("SUMMARY: EXECUTION STOPPED",
                                        "SUMMARY: EXECUTION TERMINATED")):
        return last_output

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


# `edits` used to be an untyped `list`. That produced `{"items": {}}` in the tool
# schema, and OpenAI rejects it outright once the tool is bound in strict mode —
# which is exactly what ProviderStrategy does. The resulting 400 is what blocked
# the coder, debugger and analyst from taking the fix that removed
# plugin_manager's forced-tool-call stall.
#
# Getting past that needs a NESTED schema that is strict-clean on its own.
# LangChain's strict conversion rewrites only the top level of a tool's
# parameters (it sets additionalProperties=false and lists every property in
# `required` there); it does not descend into `edits.anyOf[0].items`. So the item
# model has to arrive already compliant.
#
# That means the schema must be STRICT while validation stays FORGIVING, and in
# pydantic those pull in opposite directions: what puts a field in `required` is
# having no default, and what emits `additionalProperties: false` is
# `extra="forbid"` — but both of those turn a slightly-off batch into a hard
# ValidationError raised BEFORE edit_script runs. That is not a recoverable
# error here:
# `handle_validation_error` defaults to False on a @tool, and ToolNode's default
# handler re-raises anything that isn't a ToolInvocationError, so one malformed
# `edits` list would take down the agent turn — and, since these agents are
# themselves tools of the supervisor, potentially the session with it.
#
# So every field keeps a default and extras are ignored (nothing raises), and
# `_strict_schema` stamps the strict-mode requirements onto the emitted schema
# instead. The real validation stays where it always was, inside edit_script,
# where a bad batch returns a readable error the model can act on.
#
# The one-line docstring is deliberate too — a class docstring is copied into the
# tool schema as `description` and re-sent on every call.
def _strict_schema(schema: dict) -> None:
    schema["additionalProperties"] = False
    schema["required"] = list((schema.get("properties") or {}).keys())


class ScriptEdit(BaseModel):
    """One surgical patch: replace old_string with new_string."""
    model_config = ConfigDict(extra="ignore", json_schema_extra=_strict_schema)
    old_string: Optional[str] = None
    new_string: Optional[str] = None
    replace_all: Optional[bool] = None


@tool("edit_script")
def edit_script(directory: str, filename: str,
                old_string: Optional[str] = None, new_string: Optional[str] = None,
                edits: Optional[List[ScriptEdit]] = None,
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
            # `edits` is typed as List[ScriptEdit], so LangChain validates and hands
            # back ScriptEdit instances. Direct callers (tests, internal code, and any
            # path that bypasses the tool wrapper) still pass plain dicts, so accept
            # both rather than depending on which side of the wrapper we are on.
            if isinstance(e, ScriptEdit):
                e = e.model_dump()
            if not isinstance(e, dict) or "old_string" not in e or "new_string" not in e:
                return "Error: each item in 'edits' must be an object with 'old_string' and 'new_string'."
            if e["old_string"] is None or e["new_string"] is None:
                return "Error: each item in 'edits' must have a non-null 'old_string' and 'new_string'."
            # replace_all is required by the schema but nullable; None means "no".
            edit_list.append((strip_line_numbers(e["old_string"]), strip_line_numbers(e["new_string"]),
                              bool(e.get("replace_all") or False)))
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



# ── Pre-flight static checks (catch known-bad patterns before touching the JVM) ──
#
# This deployment's Cellpose model directory (/home/imagentj/.cellpose/models) renamed
# the nuclei model from "nuclei" to "nucleitorch_0". The old name is not merely stale
# documentation: cellpose CLI passed the wrong/missing model id, which quietly finds 0
# objects on a plausible-looking run or errors deep inside the BIOP wrapper. The name
# keeps resurfacing because it is baked into MANY existing script files (old project
# scripts, learned-memory recipes) that the coder can legally reuse verbatim via
# copy_file — fixing the recipe library alone does not fix those. A dict (not a single
# constant) so a future re-map only needs a new entry here.
_RENAMED_CELLPOSE_MODELS = {
    "nuclei": "nucleitorch_0",
}

_MODEL_ASSIGN_RE = re.compile(r"\.model\b\s*=\s*(.+?)\s*(?://.*)?$", re.MULTILINE)
_STRING_LITERAL_RE = re.compile(r"""^(['"])(.*)\1$""", re.DOTALL)
_VAR_STRING_DEF_RE = re.compile(r"\b(?:def|final\s+String|String)\s+(\w+)\s*=\s*(['\"])(.*?)\2")


def _resolve_string_value(rhs: str, code: str) -> Optional[str]:
    """Resolve a right-hand side to its string value: either a literal directly, or a
    variable traced back to its own string-literal assignment earlier in the script.
    Returns None if it can't be resolved statically (e.g. built from concatenation or a
    method call) — such cases are skipped, never flagged, so this only ever reports what
    it can prove is wrong."""
    rhs = rhs.strip().rstrip(";")
    lit = _STRING_LITERAL_RE.match(rhs)
    if lit:
        return lit.group(2)
    m = re.match(r"^(\w+)$", rhs)
    if not m:
        return None
    var = m.group(1)
    for name, _, value in _VAR_STRING_DEF_RE.findall(code):
        if name == var:
            return value
    return None


def _check_cellpose_model_name(code: str) -> Optional[str]:
    """Static guard: reject a Groovy script whose BIOP Cellpose `.model` is set to a
    renamed/retired model id (see _RENAMED_CELLPOSE_MODELS) before it ever reaches the
    JVM. Returns an error report in the same SUMMARY/STATUS/LANGUAGE shape as a real
    execution failure, or None if nothing is wrong (or nothing could be statically
    resolved)."""
    if "cellpose" not in code.lower():
        return None
    for m in _MODEL_ASSIGN_RE.finditer(code):
        value = _resolve_string_value(m.group(1), code)
        if value in _RENAMED_CELLPOSE_MODELS:
            correct = _RENAMED_CELLPOSE_MODELS[value]
            return (
                f"SUMMARY: ERROR — Cellpose model '{value}' is renamed to '{correct}' "
                "on this deployment\n"
                "STATUS: ERROR\n"
                "LANGUAGE: Groovy\n"
                "PRE-FLIGHT CHECK FAILED (script never executed):\n"
                f"This deployment's Cellpose model directory no longer has a model "
                f"called '{value}' — it was renamed to '{correct}' "
                "(/home/imagentj/.cellpose/models). Using the old name silently finds "
                "0 objects or fails deep inside the BIOP wrapper, not as a clear "
                "'model not found' error.\n"
                f"FIX: set the model to '{correct}' instead of '{value}'.\n"
                "This value was likely copied from an older script or a stale learned-"
                "memory recipe — check for other '" + value + "' occurrences if you "
                "based this script on an existing file."
            )
    return None


_IJ_OPEN_CALL_RE = re.compile(
    r"\bIJ\s*\.\s*open(?:Image)?\s*\(\s*([^,\n\)]+)",
    re.MULTILINE,
)
# Formats HandleExtraFileTypes hands to Bio-Formats. `.ome.tif` is listed first
# because its suffix is plain `.tif`, so an extension check alone misses it.
_BIOFORMATS_EXT_RE = re.compile(
    r"\.(?:ome\.tiff?|lif|czi|nd2|lsm|oib|oif|ims|vsi|scn|svs|ndpi|dv|zvi|ipl|seq|stk|flex|mvd2|cif)\b",
    re.IGNORECASE,
)


def _check_bioformats_dialog_open(code: str) -> Optional[str]:
    """Static guard: reject a Groovy script that opens a Bio-Formats format via
    IJ.open/IJ.openImage.

    That dispatch takes Bio-Formats' *prompting* path and builds a modal importer
    dialog. Under Xvfb it cannot be answered and dialog construction throws
    `no ComponentUI class for: javax.swing.JSeparator`; the import retries forever.

    Only fires when an individual IJ.open* call's first argument can be resolved
    statically to a Bio-Formats path. Merely mentioning an LSM elsewhere in a
    script that uses IJ.openImage for prepared TIFFs must not trip this guard.
    Unresolved expressions are left to the runtime dialog monitor.
    """
    bad_path = None
    ext = None
    for call in _IJ_OPEN_CALL_RE.finditer(_without_groovy_comments(code)):
        resolved = _resolve_string_value(call.group(1), code)
        if resolved is None:
            continue
        match = _BIOFORMATS_EXT_RE.search(resolved)
        if match:
            bad_path = resolved
            ext = match.group(0)
            break
    if bad_path is None or ext is None:
        return None
    return (
        f"SUMMARY: ERROR — '{ext}' must not be opened with IJ.open/IJ.openImage\n"
        "STATUS: ERROR\n"
        "LANGUAGE: Groovy\n"
        "PRE-FLIGHT CHECK FAILED (script never executed):\n"
        f"`{bad_path}` is a Bio-Formats path. IJ.open/IJ.openImage dispatch it through "
        "HandleExtraFileTypes to Bio-Formats' PROMPTING importer, which builds a modal "
        "dialog. In an unattended run nobody can answer it, and under Xvfb the "
        "look-and-feel cannot supply UI delegates, so it throws `java.lang.Error: no "
        "ComponentUI class for: javax.swing.JSeparator` and retries forever — a real run "
        "lost its entire 7200 s budget this way.\n"
        "FIX: open it windowless instead —\n"
        "    import loci.plugins.BF\n"
        "    import loci.plugins.in.ImporterOptions\n"
        "    def opts = new ImporterOptions()\n"
        "    opts.setWindowless(true)   // REQUIRED — skips ImporterPrompter\n"
        "    opts.setId(path)\n"
        "    def imp = BF.openImagePlus(opts)[0]\n"
        "Setting the `bioformats.windowless` IJ preference does NOT work (verified against "
        "bio-formats_plugins 8.5.0) — only setWindowless(true) does."
    )


_UNATTENDED_DIALOG_PATTERNS = (
    (re.compile(r"\bnew\s+(?:ij\.gui\.)?(?:NonBlocking)?GenericDialog\s*\("),
     "GenericDialog"),
    (re.compile(r"\bnew\s+(?:ij\.gui\.)?WaitForUserDialog\s*\("),
     "WaitForUserDialog"),
    (re.compile(r"\b(?:javax\.swing\.)?JOptionPane\s*\."), "JOptionPane"),
    (re.compile(r"\bnew\s+(?:java\.awt\.)?(?:Dialog|FileDialog)\s*\("),
     "AWT Dialog"),
    (re.compile(r"\bnew\s+(?:javax\.swing\.)?JDialog\s*\("), "JDialog"),
    (re.compile(r"\bnew\s+(?:ij\.io\.)?(?:OpenDialog|SaveDialog|DirectoryChooser)\s*\("),
     "file chooser dialog"),
    (re.compile(r"\bIJ\s*\.\s*(?:error|showMessage(?:WithCancel)?|getString|getNumber)\s*\("),
     "interactive IJ prompt"),
    (re.compile(
        r"\bIJ\s*\.\s*runPlugIn\s*\([^;\n]*[\"']ij\.plugin\.ZProjector[\"']",
        re.IGNORECASE,
    ), "prompting ZProjector plugin entry point"),
)


def _without_groovy_comments(code: str) -> str:
    """Remove comments before conservative unattended-dialog preflight checks."""
    without_blocks = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    return "\n".join(line.split("//", 1)[0] for line in without_blocks.splitlines())


def _check_unattended_dialog_usage(code: str) -> Optional[str]:
    """Reject explicit prompting APIs before an unattended script reaches Fiji.

    This intentionally complements, rather than replaces, _WindowMonitor: an
    ``IJ.run`` command can create a dialog inside a plugin JAR even when the Groovy
    source contains no dialog class at all.
    """
    readable = _without_groovy_comments(code)
    hit = next(
        ((pattern.search(readable), label) for pattern, label in _UNATTENDED_DIALOG_PATTERNS
         if pattern.search(readable)),
        None,
    )
    if hit is None:
        return None
    match, label = hit
    snippet = match.group(0).strip().replace("\n", " ")[:160]
    return (
        f"SUMMARY: ERROR — {label} is not allowed in unattended execution\n"
        "STATUS: ERROR\n"
        "LANGUAGE: Groovy\n"
        "PRE-FLIGHT CHECK FAILED (script never executed):\n"
        f"Detected `{snippet}`. Auto-pilot runs have no human to answer dialogs, "
        "and automatically accepting defaults can silently produce the wrong "
        "scientific result. Use a direct programmatic/windowless API instead and "
        "throw an exception for errors. For Z projection use "
        "`ij.plugin.ZProjector.run(imp, 'max')`; do not use "
        "`IJ.runPlugIn(..., 'ij.plugin.ZProjector', ...)`."
    )


def _check_bigstitcher_direct_loader_z(code: str) -> Optional[str]:
    """Require a singleton-Z guard for BigStitcher's direct TIFF loader.

    BigStitcher 3.0.8 can enter a repeated ``LazyDownsample2x`` exception loop
    when phase correlation downsamples XY on direct/virtual multichannel TIFFs
    that still contain several Z planes.  A static check cannot inspect the
    files, so accept either explicit per-channel projection or an executable
    ``getNSlices()`` validation before dataset definition.
    """
    readable = _without_groovy_comments(code)
    is_direct_bigstitcher = (
        "Define Multi-View Dataset" in readable
        and "Load raw data directly (no resaving)" in readable
        and "Calculate pairwise shifts" in readable
    )
    if not is_direct_bigstitcher:
        return None
    has_projection = bool(re.search(r"\bZProjector\s*\.\s*run\s*\(", readable))
    has_singleton_guard = bool(
        re.search(r"\bgetNSlices\s*\(\s*\)\s*(?:!=|>|==)\s*1\b", readable)
    )
    if has_projection or has_singleton_guard:
        return None
    return (
        "SUMMARY: ERROR — BigStitcher direct loading requires singleton-Z prepared tiles\n"
        "STATUS: ERROR\n"
        "LANGUAGE: Groovy\n"
        "PRE-FLIGHT CHECK FAILED (script never executed):\n"
        "The script directly/virtually loads prepared TIFFs and performs phase-correlation "
        "downsampling, but it neither projects Z nor verifies `getNSlices() == 1`. "
        "BigStitcher 3.0.8 can otherwise repeat `LazyDownsample2x` / "
        "`ArrayIndexOutOfBoundsException` indefinitely on 4C x multi-Z TIFFs.\n"
        "FIX: before `Define Multi-View Dataset`, either split every channel and call "
        "`ZProjector.run(channelImp, 'max')`, then merge/save one C x 1Z x 1T TIFF per "
        "tile; or open and validate every already-projected tile with an executable "
        "`if (imp.getNSlices() != 1) throw ...` guard. Keep `downsample_in_z=1`."
    )


_OOM_RE = re.compile(
    r"java\.lang\.OutOfMemoryError"
    r"|OutOfMemoryError"
    r"|GC overhead limit exceeded"
    r"|numpy\.core\._exceptions\._ArrayMemoryError"
    r"|\bMemoryError\b"
    r"|Unable to allocate .* for an array",
    re.IGNORECASE,
)


def _check_out_of_memory(output: str) -> Optional[str]:
    """Return a loud, actionable banner if the run ran out of memory, else None.

    Counts occurrences because a heap-exhausted JVM typically emits many, and a
    high count is the clearest signal that nothing after the first one is
    trustworthy.
    """
    if not output:
        return None
    hits = _OOM_RE.findall(output)
    if not hits:
        return None
    heap = os.environ.get("IMAGENTJ_BATCH_HEAP") or os.environ.get("IMAGENTJ_JVM_HEAP") or "the default"
    return (
        "SUMMARY: ERROR — the run exhausted available memory "
        f"({len(hits)} out-of-memory error(s) in the output)\n"
        "STATUS: ERROR\n"
        "OUT OF MEMORY — treat every result below as UNRELIABLE.\n"
        "The process ran out of heap. Output produced after the first occurrence is "
        "partial or missing, and an OutOfMemoryError does NOT always stop the script or "
        "produce a normal traceback, so a run can look like it merely 'finished quietly'.\n"
        f"Current batch heap: {heap}.\n"
        "FIX — do NOT simply re-run unchanged. Either:\n"
        "  1. Process fewer images / a smaller region / fewer slices per run, or tile the work;\n"
        "  2. Avoid holding whole volumes in memory — stream or process plane-by-plane;\n"
        "  3. If the machine genuinely has the memory, raise IMAGENTJ_BATCH_HEAP "
        "(and IMAGENTJ_JVM_HEAP for the main app) and retry."
    )


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

    if filename.endswith('.groovy'):
        preflight_error = (_check_cellpose_model_name(code_content)
                           or _check_bioformats_dialog_open(code_content)
                           or _check_bigstitcher_direct_loader_z(code_content)
                           or _check_inprocess_heavy(code_content)
                           or (_check_unattended_dialog_usage(code_content)
                               if _is_unattended_mode() else None))
        if preflight_error:
            return preflight_error

    # The registered description is what the script is *supposed* to do — the
    # watchdog needs it to tell "slow but on track" from "doing the wrong thing".
    purpose = _existing_description(directory, filename) or filename

    # Route based on extension
    if filename.endswith('.py'):
        # Calls your existing run_python_code function
        output = run_python_code(code_content, directory, purpose=purpose)
    elif filename.endswith('.groovy'):
        # Calls your existing run_script_safe function
        output = run_script_safe(language="groovy", code=code_content, purpose=purpose)
    else:
        return f"Error: File extension of {filename} is not supported for execution."

    # An out-of-memory death is not self-announcing. The JVM throws
    # OutOfMemoryError from its UncaughtExceptionHandler and the script simply
    # stops producing output — no traceback in the usual place, no non-zero exit
    # the caller checks. In a reported run the agent read straight past 37 of them,
    # carried on issuing RAG searches, wrote nothing further, and sat idle for 113
    # minutes until the wall clock. Name it explicitly so the model can react.
    oom_note = _check_out_of_memory(output)
    if oom_note:
        output = oom_note + "\n\n--- original output ---\n" + output

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
