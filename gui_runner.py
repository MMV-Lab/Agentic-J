"""
main.py  –  ImagentJ GUI with integrated usage tracking.

Changes vs. original:
  1. Import UsageMetrics, MetricsSignalBridge, UsageTrackerCallback
  2. Added MetricsPanelWidget (right-side bottom panel)
  3. AgentWorker receives the callback and injects it into every stream() call
  4. ImageJAgentGUI wires the bridge signal → panel update + session reset
"""

import sys
sys.path.insert(0, 'src')
import os
import json
import jpype
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QListWidget,
    QSplitter, QGroupBox, QScrollArea, QMessageBox, QFrame
)
from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt
from queue import Queue

from imagentj.agents import init_agent
from imagentj.imagej_context import get_ij
from imagentj.agents import shared_metrics, shared_bridge, shared_tracker




SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts/saved_scripts")
THREAD_ID = "imagej_supervisor_thread"

intro_message = """
Hello I am ImageJ agent, some call me ImagentJ :)
I can design a step-by-step protocol and, if useful, generate a runnable Groovy macro (and execute/test it if you want).

To get started, please share:
- Goal: what you want measured/segmented/processed.
- Example data: 1–2 sample images (file type), single image or batch?
- Targets: what objects/features to detect; which channel(s) matter.
- Preprocessing: background/flat-field correction, denoising needs?
- Outputs: tables/measurements, labeled masks/overlays, ROIs, saved images.
- Constraints: plugins available (e.g., Fiji with Bio-Formats, MorpholibJ, TrackMate, StarDist), OS, any runtime limits.
"""

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_API_KEY"] = "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"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGSMITH_PROJECT"] = "pr-majestic-ecumenist-75"
os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "true"


# ===========================================================================
# Metrics Panel Widget
# ===========================================================================

class MetricsPanelWidget(QWidget):
    """
    Compact read-only dashboard showing live token & tool-call statistics
    for the current conversation session.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        header = QLabel("<b>📊 Session Metrics</b>")
        header.setAlignment(Qt.AlignCenter)
        root.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)

        # Token group
        tok_box = QGroupBox("Tokens")
        tok_layout = QVBoxLayout(tok_box)
        tok_layout.setSpacing(2)
        self._lbl_in    = QLabel()
        self._lbl_out   = QLabel()
        self._lbl_total = QLabel()
        for lbl in (self._lbl_in, self._lbl_out, self._lbl_total):
            lbl.setTextFormat(Qt.RichText)
            tok_layout.addWidget(lbl)
        root.addWidget(tok_box)

        # Performance group  (NEW)
        perf_box = QGroupBox("Performance")
        perf_layout = QVBoxLayout(perf_box)
        perf_layout.setSpacing(2)
        self._lbl_time = QLabel()
        self._lbl_cost = QLabel()
        for lbl in (self._lbl_time, self._lbl_cost):
            lbl.setTextFormat(Qt.RichText)
            perf_layout.addWidget(lbl)
        root.addWidget(perf_box)

        # Tool group
        tool_box = QGroupBox("Tool Calls")
        tool_layout = QVBoxLayout(tool_box)
        tool_layout.setSpacing(2)
        self._lbl_calls  = QLabel()
        self._lbl_failed = QLabel()
        self._lbl_soft   = QLabel()
        for lbl in (self._lbl_calls, self._lbl_failed, self._lbl_soft):
            lbl.setTextFormat(Qt.RichText)
            tool_layout.addWidget(lbl)
        root.addWidget(tool_box)

        self._btn_reset = QPushButton("🔁 Reset Session Stats")
        self._btn_reset.setStyleSheet("font-size: 11px; padding: 4px;")
        root.addWidget(self._btn_reset)
        root.addStretch()

        self.update_metrics({
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            "thinking_seconds": 0.0, "cost_usd": 0.0,
            "tool_calls": 0, "failed_tool_calls": 0, "soft_error_tool_calls": 0,
        })

    @staticmethod
    def _make_stat_label(name: str, color: str, bold: bool = False) -> QLabel:
        lbl = QLabel()
        lbl.setProperty("stat_name", name)
        lbl.setProperty("stat_color", color)
        lbl.setProperty("bold", bold)
        lbl.setTextFormat(Qt.RichText)
        return lbl

    def _fmt(self, name: str, value: int, color: str, bold: bool = False) -> str:
        weight = "bold" if bold else "normal"
        return (
            f"<span style='color:#555;'>{name}:</span> "
            f"<span style='color:{color}; font-weight:{weight};'>{value:,}</span>"
        )

    @Slot(dict)
    def update_metrics(self, data: dict):
        def fmt(name, value, color, bold=False):
            w = "bold" if bold else "normal"
            return f"<span style='color:#555;'>{name}:</span> <span style='color:{color};font-weight:{w};'>{value}</span>"

        self._lbl_in.setText(    fmt("Input",    f"{data['input_tokens']:,}",  "#2980b9"))
        self._lbl_out.setText(   fmt("Output",   f"{data['output_tokens']:,}", "#27ae60"))
        self._lbl_total.setText( fmt("Total",    f"{data['total_tokens']:,}",  "#8e44ad", bold=True))

        # Format time as  Xm Ys
        secs  = data["thinking_seconds"]
        t_str = f"{int(secs//60)}m {int(secs%60)}s" if secs >= 60 else f"{secs:.1f}s"
        self._lbl_time.setText(  fmt("⏱ Think time", t_str,                   "#16a085"))

        cost = data["cost_usd"]
        cost_str = f"${cost:.4f}" if cost >= 0.0001 else "—"
        self._lbl_cost.setText(  fmt("💰 Est. cost",  cost_str,                "#c0392b"))

        self._lbl_calls.setText( fmt("Total",       data['tool_calls'],        "#2c3e50"))
        self._lbl_failed.setText(fmt("Hard errors", data['failed_tool_calls'], "#e74c3c"))
        self._lbl_soft.setText(  fmt("Soft errors ⚠", data['soft_error_tool_calls'], "#e67e22"))




# ===========================================================================
# Agent Worker
# ===========================================================================

class AgentWorker(QObject):
    event_received = Signal(dict)
    finished = Signal()
    error = Signal(str)

    def __init__(self, supervisor, thread_id: str, tracker_callback: shared_tracker):
        super().__init__()
        self.supervisor = supervisor
        self.thread_id = thread_id
        self.tracker_callback = tracker_callback
        self.tasks: Queue = Queue()
        self._stop_requested = False

    @Slot()
    def start(self):
        if jpype.isJVMStarted() and not jpype.isThreadAttachedToJVM():
            jpype.attachThreadToJVM()

        while True:
            prompt = self.tasks.get()
            if prompt is None:          # poison pill
                break
            self._stop_requested = False
            self._run_prompt(prompt)

    def _run_prompt(self, user_input: str):
        try:
            config = {
                "configurable": {"thread_id": self.thread_id},
                # Inject tracker alongside any existing callbacks (LangSmith etc.)
                "callbacks": [self.tracker_callback],
            }
            for event in self.supervisor.stream(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
                stream_mode="updates",
            ):
                if self._stop_requested:
                    break
                self.event_received.emit(event)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def submit(self, prompt: str):
        self.tasks.put(prompt)

    def request_stop(self):
        self._stop_requested = True


# ===========================================================================
# Script Library Widget  (unchanged from original)
# ===========================================================================

class ScriptLibraryWidget(QWidget):
    script_run_requested = Signal(str, str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        layout.addWidget(QLabel("<b>📜 Script Library</b>"))

        self.script_list = QListWidget()
        self.script_list.itemClicked.connect(self.display_details)
        layout.addWidget(self.script_list)

        self.details_group = QGroupBox("Script Details")
        details_layout = QVBoxLayout()
        self.lbl_desc = QLabel("Select a script...")
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet("color: #555;")
        self.lbl_inputs = QLabel("")
        self.lbl_inputs.setWordWrap(True)
        self.lbl_inputs.setStyleSheet("color: #d35400; font-weight: bold;")
        details_layout.addWidget(self.lbl_desc)
        details_layout.addWidget(self.lbl_inputs)
        details_layout.addStretch()
        self.details_group.setLayout(details_layout)
        layout.addWidget(self.details_group)

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.clicked.connect(self.load_scripts)
        self.btn_run = QPushButton("▶ Run Script")
        self.btn_run.setEnabled(False)
        self.btn_run.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        self.btn_run.clicked.connect(self.on_run_click)
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_run)
        layout.addLayout(btn_layout)

        self.setLayout(layout)
        self.scripts_data = []
        self.load_scripts()

    def load_scripts(self):
        self.script_list.clear()
        self.scripts_data = []
        self.current_selection = None
        if not os.path.exists(SCRIPTS_DIR):
            os.makedirs(SCRIPTS_DIR)
            self.script_list.addItem("Library empty (folder created).")
            return
        try:
            files = sorted(os.listdir(SCRIPTS_DIR))
            json_files = [f for f in files if f.endswith(".json")]
            if not json_files:
                self.script_list.addItem("No scripts found.")
                return
            for json_file in json_files:
                meta_path = os.path.join(SCRIPTS_DIR, json_file)
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    script_filename = meta.get("script_file")
                    code_path = os.path.join(SCRIPTS_DIR, script_filename)
                    if os.path.exists(code_path):
                        with open(code_path, "r", encoding="utf-8") as cf:
                            meta["code"] = cf.read()
                        self.scripts_data.append(meta)
                        self.script_list.addItem(meta.get("name", json_file))
                except Exception as e:
                    print(f"Error loading {json_file}: {e}")
        except Exception as e:
            self.script_list.addItem("Error scanning folder.")
            print(e)

    def display_details(self, item):
        idx = self.script_list.row(item)
        if idx < 0 or idx >= len(self.scripts_data):
            return
        data = self.scripts_data[idx]
        self.current_selection = data
        self.lbl_desc.setText(f"<b>Description:</b><br>{data.get('description', 'No description')}")
        self.lbl_inputs.setText(f"<b>⚠️ Requires:</b><br>{data.get('inputs', 'None')}")
        self.btn_run.setEnabled(True)

    def on_run_click(self):
        if self.current_selection:
            msg = (f"Ensure the following requirements are met before running:\n\n"
                   f"{self.current_selection.get('inputs')}\n\nProceed?")
            reply = QMessageBox.question(self, 'Run Script', msg,
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.script_run_requested.emit(
                    self.current_selection.get("language", "groovy"),
                    self.current_selection.get("code"),
                )


# ===========================================================================
# Main GUI
# ===========================================================================

class ImageJAgentGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ImagentJ - AI Supervisor & Script Library")
        self.resize(1400, 700)
        self.setAcceptDrops(True)
        self.attached_files: list[str] = []

        # ── Metrics infrastructure ──────────────────────────────────────────
        self._metrics        = shared_metrics
        self._metrics_bridge = shared_bridge
        self._tracker_cb     = shared_tracker

        # ── Build UI ────────────────────────────────────────────────────────
        main_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)

        # LEFT: chat
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.attachment_status = QLabel("No files attached")
        self.attachment_status.setStyleSheet("color: #7f8c8d; font-style: italic; padding-left: 5px;")
        self.input_line = QLineEdit()
        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet("background-color: #3498db; color: white; font-weight: bold; padding: 8px;")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("background-color: #bdc3c7; color: #7f8c8d; font-weight: bold; padding: 8px;")
        self.stop_button.clicked.connect(self.on_stop)
        self.status_label = QLabel("Agent is ready to help")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.send_button, stretch=4)
        button_layout.addWidget(self.stop_button, stretch=1)

        chat_layout.addWidget(self.output_area)
        chat_layout.addWidget(self.attachment_status)
        chat_layout.addWidget(self.input_line)
        chat_layout.addLayout(button_layout)
        chat_layout.addWidget(self.status_label)

        # MIDDLE: script library
        self.library_widget = ScriptLibraryWidget()
        self.library_widget.script_run_requested.connect(self.run_saved_script)

        # RIGHT: metrics panel
        self.metrics_panel = MetricsPanelWidget()
        self.metrics_panel.setMinimumWidth(180)
        self.metrics_panel.setMaximumWidth(240)
        self.metrics_panel._btn_reset.clicked.connect(self._reset_metrics)

        splitter.addWidget(chat_widget)
        splitter.addWidget(self.library_widget)
        splitter.addWidget(self.metrics_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        main_layout.addWidget(splitter)

        # ── Wire signals ────────────────────────────────────────────────────
        self.send_button.clicked.connect(self.on_send)
        self.input_line.returnPressed.connect(self.on_send)
        self._metrics_bridge.updated.connect(self.metrics_panel.update_metrics)

        # ── ImageJ + Agent setup ────────────────────────────────────────────
        self.ij = get_ij()
        self.ij.ui().showUI()
        self.supervisor, self.checkpointer = init_agent()

        self.thread = QThread()
        self.worker = AgentWorker(self.supervisor, THREAD_ID, self._tracker_cb)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.start)
        self.worker.event_received.connect(self.handle_event)
        self.worker.finished.connect(self.on_agent_finished)
        self.worker.error.connect(self.on_agent_error)
        self.thread.start()

        self.output_area.append(intro_message)
        self.output_area.append("Use the panel on the right to recall saved scripts or drag files here.")

    # ── Metrics helpers ──────────────────────────────────────────────────────

    def _reset_metrics(self):
        self._metrics.reset()
        # emit a zeroed snapshot so the panel refreshes immediately
        self._metrics_bridge.updated.emit(self._metrics.snapshot())

    # ── Drag & drop ──────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p not in self.attached_files:
                self.attached_files.append(p)
        self._update_attachment_ui()

    def _update_attachment_ui(self):
        if not self.attached_files:
            self.attachment_status.setText("No files attached")
            self.attachment_status.setStyleSheet("color: #7f8c8d; font-style: italic; padding-left: 5px;")
        else:
            names = [os.path.basename(p) for p in self.attached_files]
            self.attachment_status.setText(f"📎 Attached ({len(names)}): {', '.join(names)}")
            self.attachment_status.setStyleSheet("color: #2980b9; font-weight: bold;")

    # ── UI helpers ────────────────────────────────────────────────────────────

    def append_output(self, text: str):
        self.output_area.append(text)

    def set_status(self, text: str):
        self.status_label.setText(text)
        colors = {"Ready": "green", "Thinking...": "blue", "Stopping...": "#e74c3c"}
        color = colors.get(text, "black")
        if text == "Ready":
            self.status_label.setText("Agent is ready to help")
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def set_ui_busy(self, busy: bool):
        self.stop_button.setEnabled(busy)
        self.send_button.setDisabled(busy)
        self.input_line.setDisabled(busy)
        if busy:
            self.stop_button.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 8px;")
            self.send_button.setStyleSheet("background-color: #bdc3c7; color: #7f8c8d; font-weight: bold; padding: 8px;")
        else:
            self.stop_button.setStyleSheet("background-color: #bdc3c7; color: #7f8c8d; font-weight: bold; padding: 8px;")
            self.send_button.setStyleSheet("background-color: #3498db; color: white; font-weight: bold; padding: 8px;")

    # ── Agent event handlers ──────────────────────────────────────────────────

    def on_stop(self):
        if hasattr(self, 'worker') and self.worker:
            self.append_output("\n<i style='color: #e74c3c;'>🛑 Stopping agent...</i>")
            self.worker.request_stop()
            self.set_status("Stopping...")

    def on_agent_finished(self):
        print("[DEBUG] on_agent_finished called") 
        try:
            self._tracker_cb.finish_query()
        except Exception as e:
            print(f"[UsageTracker] finish_query failed: {e}")
        
        if self.worker._stop_requested:
            self.append_output("\n<b style='color:green;'>✓ Agent is ready to help</b>")
        self.set_status("Ready")
        self.set_ui_busy(False)

    def on_agent_error(self, msg: str):
        self.append_output(f"[Agent error]\n{msg}")
        self.status_label.setText("Error")
        self.status_label.setStyleSheet("color: red;")
        self.set_ui_busy(False)

    def _execute_agent_query(self, prompt: str):
        self._tracker_cb.start_query(prompt)   # ← starts timer + snapshot
        self.set_status("Thinking...")
        self.set_ui_busy(True)
        self.worker.submit(prompt)

    def on_send(self):
        user_input = self.input_line.text().strip()
        if not user_input and not self.attached_files:
            return

        full_prompt = user_input
        if self.attached_files:
            file_list_str = "\n".join([f"- {p}" for p in self.attached_files])
            full_prompt += f"\n\n[SYSTEM: The user has attached the following files/folders]:\n{file_list_str}"

        self.append_output(f"\n<b>You:</b> {user_input if user_input else '[Attached Files]'}")
        if self.attached_files:
            display_names = ", ".join([os.path.basename(p) for p in self.attached_files])
            self.append_output(f"<i style='color: #2980b9;'>📎 Sent with: {display_names}</i>")

        self.append_output("AI: ...")
        self.input_line.clear()
        self._execute_agent_query(full_prompt)
        self.attached_files = []
        self._update_attachment_ui()

    def run_saved_script(self, language: str, code: str):
        if self.status_label.text() != "Agent is ready to help":
            QMessageBox.warning(self, "Agent Busy", "Please wait for the current task to finish.")
            return
        prompt = (
            f"SYSTEM REQUEST: The user wants to run a saved {language} script from the library.\n"
            f"Please execute the following code immediately using the 'run_script_safe' tool.\n"
            f"Do not change the code unless it fails.\n\n"
            f"CODE:\n```{language}\n{code}\n```"
        )
        self.output_area.append(f"\n<b>⚙️ Recall Script:</b> Sending to Agent...")
        self._execute_agent_query(prompt)

    def handle_event(self, event: dict):
        for node_name, node_data in event.items():
            if "Middleware" in node_name:
                continue
            if node_name in ("supervisor", "model"):
                messages = node_data.get("messages", [])
                for msg in messages:
                    tool_calls = getattr(msg, "tool_calls", [])
                    for tc in tool_calls:
                        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                        args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                        if name == "task":
                            agent_type = args.get("subagent_type", "Specialist")
                            desc = args.get("description", "")
                            short_desc = (desc[:120] + '...') if len(desc) > 120 else desc
                            self.append_output(f"\n<div style='color: #e67e22;'><b>🚀 Routing to {agent_type}:</b></div>")
                            self.append_output(f"<i style='color: #7f8c8d;'>{short_desc}</i>")
                        else:
                            self.append_output(f"\n<i>[System] Calling tool: {name}...</i>")

            if node_name == "model":
                for msg in node_data.get("messages", []):
                    content = getattr(msg, "content", "")
                    if content and not getattr(msg, "tool_calls", None):
                        self.append_output(content)

        if "tools" in event:
            for tool_msg in event["tools"].get("messages", []):
                name = getattr(tool_msg, "name", "Tool")
                if name == "task":
                    self.append_output("\n✅ <b>Sub-agent task completed.</b>")
                else:
                    self.append_output(f"\n> 🛠️ <b>{name}</b> finished.")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageJAgentGUI()
    window.show()
    sys.exit(app.exec())