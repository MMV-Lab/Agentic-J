"""
benchmark_gui_hooks.py — Benchmark hooks for the ImagentJ GUI.

Supports two modes, both using the full GUI (viewable via noVNC):

  **interactive** (BENCHMARK_INTERACTIVE=true):
      User approves steps and clicks Finish Benchmark manually.

  **auto-pilot** (BENCHMARK_INTERACTIVE=false):
      Auto-approve directive injected into prompt.  When the agent finishes
      its last response, outputs are collected and result.json is written
      automatically.  The user can watch but doesn't need to act.

Integration with gui_runner.py (3 changes)
------------------------------------------
1. Add import::

       from imagentj.benchmark_gui_hooks import is_benchmark_mode, setup_benchmark_gui

2. At end of ``ImageJAgentGUI.__init__``, after ``self._init_session()``::

       if is_benchmark_mode():
           setup_benchmark_gui(self)

3. (Optional) suppress intro message in ``_start_new_thread``::

       if not is_benchmark_mode():
           self.chat_scroll.add_message('ai', intro_message)
"""

import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path

from PySide6.QtWidgets import QPushButton, QMessageBox, QApplication
from PySide6.QtCore import QTimer

_log = logging.getLogger("benchmark_hooks")

# ---------------------------------------------------------------------------
# Qdrant stale lock cleanup
# ---------------------------------------------------------------------------
# When the container exits via os._exit(0), Qdrant doesn't get to clean up
# its lock file. The next docker compose run inherits the same bind mount
# (./qdrant_data:/app/qdrant_data) and Qdrant refuses to start.

def _cleanup_qdrant_locks():
    """Remove all Qdrant lock files. Called at startup and before shutdown."""
    qdrant_path = Path(os.environ.get("QDRANT_DATA_PATH", "/app/qdrant_data"))
    if not qdrant_path.exists():
        return
    for lock in qdrant_path.rglob("*.lock"):
        try:
            lock.unlink()
            _log.info("Removed Qdrant lock: %s", lock)
        except Exception:
            pass
    bare_lock = qdrant_path / ".lock"
    if bare_lock.exists():
        try:
            bare_lock.unlink()
            _log.info("Removed Qdrant lock: %s", bare_lock)
        except Exception:
            pass

# Clean up stale locks from previous runs at import time
if os.environ.get("BENCHMARK_MODE", "").lower() == "true":
    _cleanup_qdrant_locks()

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def is_benchmark_mode() -> bool:
    """True when the container was launched by the benchmark adapter."""
    return os.environ.get("BENCHMARK_MODE", "").lower() == "true"


def is_autopilot() -> bool:
    """True when the benchmark should auto-approve and auto-finish."""
    return (
        is_benchmark_mode()
        and os.environ.get("BENCHMARK_INTERACTIVE", "").lower() != "true"
    )


def _input_dir() -> Path:
    return Path(os.environ.get("BENCHMARK_INPUT_DIR", "/benchmark/input"))


def _output_dir() -> Path:
    return Path(os.environ.get("BENCHMARK_OUTPUT_DIR", "/benchmark/output"))


_IMAGE_EXT = {
    ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp",
    ".nd2", ".czi", ".lif", ".lsm", ".ome.tif", ".ome.tiff",
    ".svs", ".ics", ".ids",
}

_AUTO_APPROVE = (
    "\n\n[SYSTEM — BENCHMARK AUTO-PILOT MODE]\n"
    "This benchmark run is in auto-pilot. A user may be watching but will "
    "not interact.\n"
    "- Treat every confirmation gate as approved (Phase 4b sample "
    "verification, plugin install, etc.).\n"
    "- If you would normally ask for clarification, make a reasonable "
    "default choice and continue.\n"
    "- Proceed through all pipeline phases without pausing.\n"
)

_INTERACTIVE_DIRECTIVE = (
    "\n\n[SYSTEM — BENCHMARK INTERACTIVE MODE]\n"
    "This is a benchmark run, but a real user is present and interacting "
    "with you through the GUI.\n"
    "- Follow your normal pipeline: ask clarifying questions when the task "
    "is ambiguous, present multiple pipeline approaches for the user to "
    "choose from, and request approval at every verification step.\n"
    "- Do NOT skip any user interaction steps. The user expects to be "
    "consulted on decisions — this is NOT auto-pilot.\n"
    "- Behave exactly as you would in a normal session.\n"
    "- Save all outputs to the project folder as usual.\n"
)


# ---------------------------------------------------------------------------
# Fiji / ImageJ dialog auto-dismisser
# ---------------------------------------------------------------------------

def _start_dialog_dismisser():
    """
    Background thread that periodically scans for Java AWT Dialog windows
    (Fiji "OK" confirmations, error popups, etc.) and auto-clicks their
    buttons so they don't block the agent.

    Only runs in auto-pilot mode.
    """
    def _dismiss_loop():
        import jpype

        # Wait for JVM to be ready
        for _ in range(60):
            if jpype.isJVMStarted():
                break
            time.sleep(1)
        else:
            _log.warning("Dialog dismisser: JVM never started")
            return

        if not jpype.isThreadAttachedToJVM():
            jpype.attachThreadToJVM()

        Dialog = jpype.JClass("java.awt.Dialog")
        Window = jpype.JClass("java.awt.Window")
        Button = jpype.JClass("java.awt.Button")
        JButton = jpype.JClass("javax.swing.JButton")

        # Button labels we'll auto-click (case-insensitive)
        _OK_LABELS = {"ok", "yes", "continue", "close", "dismiss", "got it"}

        _log.info("Dialog auto-dismisser started")

        while True:
            time.sleep(1)
            try:
                for window in Window.getWindows():
                    if not isinstance(window, Dialog):
                        continue
                    if not window.isVisible():
                        continue

                    _log.info("Auto-dismissing dialog: %s", window.getTitle())

                    # Try to find and click an OK-like button
                    clicked = False
                    for comp in _get_all_components(window):
                        label = None
                        if isinstance(comp, Button):
                            label = comp.getLabel()
                        elif isinstance(comp, JButton):
                            label = comp.getText()

                        if label and str(label).strip().lower() in _OK_LABELS:
                            _log.info("  Clicking button: %s", label)
                            comp.doClick() if isinstance(comp, JButton) else _awt_click(comp)
                            clicked = True
                            break

                    # If no recognizable button found, just dispose the dialog
                    if not clicked:
                        _log.info("  No OK button found — disposing dialog")
                        window.dispose()

            except Exception as e:
                # JVM might not be ready, or dialog already gone
                _log.debug("Dialog dismisser tick error: %s", e)

    threading.Thread(target=_dismiss_loop, daemon=True).start()


def _get_all_components(container):
    """Recursively get all AWT/Swing components inside a container."""
    result = []
    try:
        for comp in container.getComponents():
            result.append(comp)
            if hasattr(comp, "getComponents"):
                result.extend(_get_all_components(comp))
    except Exception:
        pass
    return result


def _awt_click(button):
    """Simulate a click on an AWT Button by firing an ActionEvent."""
    try:
        import jpype
        ActionEvent = jpype.JClass("java.awt.event.ActionEvent")
        evt = ActionEvent(button, ActionEvent.ACTION_PERFORMED, "")
        for listener in button.getActionListeners():
            listener.actionPerformed(evt)
    except Exception as e:
        _log.debug("AWT click failed: %s", e)


# ---------------------------------------------------------------------------
# Read task + stage images
# ---------------------------------------------------------------------------

def _load_task() -> tuple[str, list[Path]]:
    instruction = ""
    f = _output_dir() / "instruction.txt"
    if f.exists():
        instruction = f.read_text(encoding="utf-8").strip()

    images = sorted(
        p for p in _input_dir().iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXT
    )
    return instruction, images


def _stage_images(images: list[Path]) -> list[Path]:
    dest = Path("/app/data/benchmark_images")
    dest.mkdir(parents=True, exist_ok=True)
    local = []
    for img in images:
        dst = dest / img.name
        shutil.copy2(str(img), str(dst))
        local.append(dst)
    return local


# ---------------------------------------------------------------------------
# Collect outputs and write sentinel
# ---------------------------------------------------------------------------

def _collect_and_finish(gui, message: str = "") -> None:
    out = _output_dir()
    out.mkdir(parents=True, exist_ok=True)

    # Only copy project folder(s) created during this session
    proj_root = Path("/app/data/projects")
    before = getattr(gui, "_bench_projects_before", set())

    if proj_root.exists():
        current = {d.name for d in proj_root.iterdir() if d.is_dir()}
        new_folders = current - before

        if not new_folders:
            candidates = [d for d in proj_root.iterdir() if d.is_dir()]
            if candidates:
                newest = max(candidates, key=lambda d: d.stat().st_mtime)
                new_folders = {newest.name}

        for folder_name in new_folders:
            src_dir = proj_root / folder_name
            for src in src_dir.rglob("*"):
                if src.is_file():
                    rel = src.relative_to(proj_root)
                    dst = out / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))

    # Usage metrics
    metadata = {}
    if hasattr(gui, "_metrics"):
        m = gui._metrics
        metadata["total_tokens"] = getattr(m, "total_tokens", 0)
        metadata["total_cost_usd"] = getattr(m, "total_cost", 0.0)
        metadata["num_llm_calls"] = getattr(m, "num_calls", 0)
    if hasattr(gui, "_tracker_cb"):
        try:
            metadata["usage_report"] = gui._tracker_cb.get_report()
        except Exception:
            pass

    # Write sentinel — the adapter polls for this file
    (out / "result.json").write_text(json.dumps({
        "success": True,
        "message": message or "Benchmark session completed.",
        "error": "",
        "metadata": metadata,
    }, indent=2, default=str), encoding="utf-8")


def _do_finish_in_background(gui, message: str = "", shutdown: bool = False) -> None:
    """Run the collect in a background thread so the GUI stays responsive."""
    def _work():
        _collect_and_finish(gui, message)

        # Try to show completion message (may fail if widgets are gone)
        try:
            QTimer.singleShot(0, lambda: gui.chat_scroll.add_message(
                "system",
                "✅ Benchmark finished — outputs collected. "
                "The container will shut down in a moment.",
            ))
        except (RuntimeError, Exception):
            pass

        if shutdown:
            # Wait for result.json to flush to host filesystem, then
            # clean up Qdrant locks and force-kill the process.
            import os as _os
            _log.info("Shutdown scheduled — waiting 5 s for filesystem flush …")
            time.sleep(5)

            # Clean up Qdrant lock files so the next run doesn't fail
            _cleanup_qdrant_locks()

            _log.info("Exiting process.")
            _os._exit(0)

    threading.Thread(target=_work, daemon=True).start()


# ---------------------------------------------------------------------------
# Manual Finish button (interactive mode)
# ---------------------------------------------------------------------------

def _on_finish_clicked(gui) -> None:
    reply = QMessageBox.question(
        gui, "Finish Benchmark",
        "Are you done with this benchmark task?\n\n"
        "All project outputs will be collected.\n"
        "The container will shut down automatically.",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return

    gui.chat_scroll.add_message("system", "Collecting outputs — please wait …")
    _do_finish_in_background(gui, "Interactive session completed by user.", shutdown=True)


# ---------------------------------------------------------------------------
# Auto-finish hook (auto-pilot mode)
# ---------------------------------------------------------------------------

def _hook_auto_finish(gui) -> None:
    """
    Monkey-patch ``on_agent_finished`` so that when the agent finishes its
    last response in auto-pilot mode, we automatically collect outputs and
    write result.json.

    We track how many agent calls we've seen. The first call is the
    benchmark task itself. We wait for it to finish, then add a short delay
    to let any final file writes complete, then trigger the collect.
    """
    original_on_finished = gui.on_agent_finished

    def _patched_on_finished():
        # Call the original handler first (resets UI state, etc.)
        original_on_finished()

        # Don't auto-finish if already done
        if getattr(gui, "_bench_auto_finished", False):
            return

        gui._bench_auto_finished = True

        gui.chat_scroll.add_message(
            "system",
            "Auto-pilot: agent finished — collecting outputs in 10 s …",
        )

        # Give the agent's last file writes a moment to flush
        QTimer.singleShot(10000, lambda: _do_finish_in_background(
            gui, "Auto-pilot session completed.", shutdown=True,
        ))

    gui.on_agent_finished = _patched_on_finished


# ---------------------------------------------------------------------------
# Auto-send the benchmark task
# ---------------------------------------------------------------------------

def _auto_send(gui) -> None:
    gui._start_new_thread()

    instruction, images = _load_task()
    if not instruction:
        gui.chat_scroll.add_message(
            "error",
            f"Benchmark: no instruction.txt found in {_output_dir()}",
        )
        return

    local_images = _stage_images(images) if images else []
    file_list = "\n".join(f"- {p}" for p in local_images)

    prompt = (
        f"{instruction}\n\n"
        f"[SYSTEM: Input images]:\n{file_list}\n\n"
        f"[SYSTEM: This is a BENCHMARK run. Save ALL outputs to "
        f"{_output_dir().resolve()} as well as the project folder.]\n"
    )

    # In auto-pilot mode, append the auto-approve directive
    if is_autopilot():
        prompt += _AUTO_APPROVE
    else:
        prompt += _INTERACTIVE_DIRECTIVE

    mode_label = "AUTO-PILOT" if is_autopilot() else "INTERACTIVE"
    gui.chat_scroll.add_message(
        "system",
        f"Benchmark [{mode_label}] — {len(local_images)} image(s). "
        "Sending to agent …",
    )

    gui.attached_files = [str(p) for p in local_images]
    gui._update_attachment_ui()
    gui.input_line.setPlainText(prompt)
    gui.on_send()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def setup_benchmark_gui(gui) -> None:
    """
    Call once at the end of ``ImageJAgentGUI.__init__()`` when
    ``is_benchmark_mode()`` is True.
    """
    # Guard — only run once
    if getattr(gui, "_bench_setup_done", False):
        return
    gui._bench_setup_done = True
    gui._bench_auto_finished = False

    # ── Snapshot existing projects ───────────────────────────────────
    proj_root = Path("/app/data/projects")
    if proj_root.exists():
        gui._bench_projects_before = {
            d.name for d in proj_root.iterdir() if d.is_dir()
        }
    else:
        gui._bench_projects_before = set()

    # ── Finish Benchmark button (always shown — works as manual
    #    override even in auto-pilot mode) ────────────────────────────
    btn = QPushButton("✅  Finish Benchmark")
    btn.setStyleSheet(
        "QPushButton {"
        "  background-color: #27ae60; color: white; font-weight: bold;"
        "  font-size: 14px; padding: 10px 20px; border-radius: 6px;"
        "  border: 2px solid #1e8449;"
        "}"
        "QPushButton:hover { background-color: #2ecc71; }"
        "QPushButton:pressed { background-color: #1e8449; }"
    )
    btn.setToolTip("Collect all outputs and end the benchmark session.")
    btn.clicked.connect(lambda: _on_finish_clicked(gui))

    chat_widget = gui.chat_scroll.parent()
    layout = chat_widget.layout()
    if layout is not None:
        layout.insertWidget(1, btn)

    # ── Fiji dialog auto-dismisser (both modes — blocks script execution) ─
    _start_dialog_dismisser()

    # ── Auto-pilot: hook on_agent_finished for auto-collect ──────────
    if is_autopilot():
        _hook_auto_finish(gui)

    # ── Auto-send the task after the GUI finishes rendering ──────────
    QTimer.singleShot(3000, lambda: _auto_send(gui))