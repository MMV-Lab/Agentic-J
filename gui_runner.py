import sys
sys.path.insert(0, 'src')
import os
import json
import jpype
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QListWidget,
    QSplitter, QGroupBox, QScrollArea, QMessageBox, QListWidgetItem,
    QSizePolicy,
)
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt, QSize, QEvent
from queue import Queue

# --- Import your existing backend ---
from imagentj.agents import init_agent
from imagentj.imagej_context import get_ij
from imagentj.tools import run_script_safe
from imagentj.chat_history import ChatHistoryManager

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts/saved_scripts")

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

If you're unsure, tell me the biological question and show one representative image—I'll propose a clear plan and a script you can run.
"""


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class AgentWorker(QObject):
    event_received = Signal(dict)
    finished = Signal()
    error = Signal(str)

    def __init__(self, supervisor, thread_id: str):
        super().__init__()
        self.supervisor = supervisor
        self.thread_id = thread_id   # mutable — changed when user switches chat
        self.tasks = Queue()
        self._stop_requested = False

    @Slot()
    def start(self):
        if jpype.isJVMStarted() and not jpype.isThreadAttachedToJVM():
            jpype.attachThreadToJVM()

        while True:
            prompt = self.tasks.get()
            if prompt is None:   # poison pill
                break
            self._stop_requested = False
            self._run_prompt(prompt)

    def _run_prompt(self, user_input):
        try:
            config = {"configurable": {"thread_id": self.thread_id}}
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

    def submit(self, prompt):
        self.tasks.put(prompt)

    def request_stop(self):
        self._stop_requested = True


# ---------------------------------------------------------------------------
# Chat history sidebar
# ---------------------------------------------------------------------------

class ChatHistoryPanel(QWidget):
    """Left-hand panel: session list + New Chat button."""

    thread_selected = Signal(str)   # emits thread_id
    new_chat_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setMinimumWidth(180)
        self.setMaximumWidth(280)

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QLabel("<b>Chat history</b>")
        header.setStyleSheet("font-size: 13px; padding: 4px 0;")
        layout.addWidget(header)

        # New Chat button
        self.btn_new = QPushButton("New Chat")
        self.btn_new.setStyleSheet(
            "background-color: #2ecc71; color: white; font-weight: bold; "
            "padding: 6px; border-radius: 4px;"
        )
        self.btn_new.clicked.connect(self.new_chat_requested)
        layout.addWidget(self.btn_new)

        # Session list
        self.session_list = QListWidget()
        self.session_list.setWordWrap(True)
        self.session_list.setStyleSheet(
            "QListWidget { border: 1px solid #ddd; border-radius: 4px; }"
            "QListWidget::item { padding: 6px 4px; border-bottom: 1px solid #eee; }"
            "QListWidget::item:selected { background-color: #3498db; color: white; }"
        )
        self.session_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.session_list)

        self.setLayout(layout)
        self._thread_ids: list[str] = []

    def populate(self, threads: list[tuple[str, dict]]):
        """Rebuild the list from [(thread_id, metadata), ...]."""
        self.session_list.clear()
        self._thread_ids = []

        for thread_id, meta in threads:
            title = meta.get("title", "Untitled")
            date_str = meta.get("last_updated", "")[:10]

            item = QListWidgetItem(f"{title}\n{date_str}")
            item.setSizeHint(QSize(0, 52))
            self.session_list.addItem(item)
            self._thread_ids.append(thread_id)

    def set_active(self, thread_id: str):
        """Highlight the row for the currently active thread."""
        if thread_id in self._thread_ids:
            self.session_list.setCurrentRow(self._thread_ids.index(thread_id))
        else:
            self.session_list.clearSelection()

    def _on_item_clicked(self, item: QListWidgetItem):
        idx = self.session_list.row(item)
        if 0 <= idx < len(self._thread_ids):
            self.thread_selected.emit(self._thread_ids[idx])


# ---------------------------------------------------------------------------
# Script library (right panel — currently commented out in layout)
# ---------------------------------------------------------------------------

# class ScriptLibraryWidget(QWidget):
#     script_run_requested = Signal(str, str)

#     def __init__(self):
#         super().__init__()
#         layout = QVBoxLayout()
#         layout.addWidget(QLabel("<b>📜 Script Library</b>"))
#         self.script_list = QListWidget()
#         self.script_list.itemClicked.connect(self.display_details)
#         layout.addWidget(self.script_list)

#         self.details_group = QGroupBox("Script Details")
#         details_layout = QVBoxLayout()
#         self.lbl_desc = QLabel("Select a script...")
#         self.lbl_desc.setWordWrap(True)
#         self.lbl_desc.setStyleSheet("color: #555;")
#         self.lbl_inputs = QLabel("")
#         self.lbl_inputs.setWordWrap(True)
#         self.lbl_inputs.setStyleSheet("color: #d35400; font-weight: bold;")
#         details_layout.addWidget(self.lbl_desc)
#         details_layout.addWidget(self.lbl_inputs)
#         details_layout.addStretch()
#         self.details_group.setLayout(details_layout)
#         layout.addWidget(self.details_group)

#         btn_layout = QHBoxLayout()
#         self.btn_refresh = QPushButton("🔄 Refresh")
#         self.btn_refresh.clicked.connect(self.load_scripts)
#         self.btn_run = QPushButton("▶ Run Script")
#         self.btn_run.setEnabled(False)
#         self.btn_run.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
#         self.btn_run.clicked.connect(self.on_run_click)
#         btn_layout.addWidget(self.btn_refresh)
#         btn_layout.addWidget(self.btn_run)
#         layout.addLayout(btn_layout)

#         self.setLayout(layout)
#         self.scripts_data = []
#         self.load_scripts()

#     def load_scripts(self):
#         self.script_list.clear()
#         self.scripts_data = []
#         self.current_selection = None
#         if not os.path.exists(SCRIPTS_DIR):
#             os.makedirs(SCRIPTS_DIR)
#             self.script_list.addItem("Library empty (folder created).")
#             return
#         try:
#             files = sorted(os.listdir(SCRIPTS_DIR))
#             json_files = [f for f in files if f.endswith(".json")]
#             if not json_files:
#                 self.script_list.addItem("No scripts found.")
#                 return
#             for json_file in json_files:
#                 meta_path = os.path.join(SCRIPTS_DIR, json_file)
#                 try:
#                     with open(meta_path, "r", encoding="utf-8") as f:
#                         meta = json.load(f)
#                     script_filename = meta.get("script_file")
#                     code_path = os.path.join(SCRIPTS_DIR, script_filename)
#                     if os.path.exists(code_path):
#                         with open(code_path, "r", encoding="utf-8") as cf:
#                             meta["code"] = cf.read()
#                         self.scripts_data.append(meta)
#                         self.script_list.addItem(meta.get("name", json_file))
#                 except Exception as e:
#                     print(f"Error loading {json_file}: {e}")
#         except Exception as e:
#             self.script_list.addItem("Error scanning folder.")
#             print(e)

#     def display_details(self, item):
#         idx = self.script_list.row(item)
#         if idx < 0 or idx >= len(self.scripts_data):
#             return
#         data = self.scripts_data[idx]
#         self.current_selection = data
#         self.lbl_desc.setText(f"<b>Description:</b><br>{data.get('description', 'No description')}")
#         self.lbl_inputs.setText(f"<b>⚠️ Requires:</b><br>{data.get('inputs', 'None')}")
#         self.btn_run.setEnabled(True)

#     def on_run_click(self):
#         if self.current_selection:
#             msg = (f"Ensure the following requirements are met before running:\n\n"
#                    f"{self.current_selection.get('inputs')}\n\nProceed?")
#             reply = QMessageBox.question(self, 'Run Script', msg, QMessageBox.Yes | QMessageBox.No)
#             if reply == QMessageBox.Yes:
#                 self.script_run_requested.emit(
#                     self.current_selection.get("language", "groovy"),
#                     self.current_selection.get("code"),
#                 )


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class ImageJAgentGUI(QWidget):
    start_agent_work = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ImagentJ - AI Supervisor & Script Library")
        self.resize(720, 680)
        self.setAcceptDrops(True)
        self.attached_files: list[str] = []

        # History manager (metadata index + message retrieval)
        self.history_manager = ChatHistoryManager()

        # --- Main layout: splitter with history panel | chat ---
        main_layout = QHBoxLayout()
        splitter = QSplitter(Qt.Horizontal)



        # LEFT: chat history sidebar
        self.history_panel = ChatHistoryPanel()
        self.history_panel.thread_selected.connect(self.switch_thread)
        self.history_panel.new_chat_requested.connect(self.new_chat)

        # MIDDLE: chat interface
        chat_widget = QWidget()
        chat_layout = QVBoxLayout()

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)

        self.attachment_status = QLabel("No files attached")
        self.attachment_status.setStyleSheet(
            "color: #7f8c8d; font-style: italic; padding-left: 5px;"
        )

        self.input_line = QTextEdit()
        self.input_line.setFixedHeight(120)  # increase input height

        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet(
            "background-color: #3498db; color: white; font-weight: bold; padding: 8px;"
        )

        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet(
            "background-color: #bdc3c7; color: #7f8c8d; font-weight: bold; padding: 8px;"
        )
        self.stop_button.clicked.connect(self.on_stop)

        self.status_label = QLabel("Agent is ready to help")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.send_button, stretch=4)
        button_layout.addWidget(self.stop_button, stretch=1)

        chat_layout.addWidget(self.output_area, stretch=3)
        chat_layout.addWidget(self.attachment_status, stretch=0)
        chat_layout.addWidget(self.input_line, stretch=1)
        chat_layout.addLayout(button_layout)
        chat_layout.addWidget(self.status_label, stretch=0)
        chat_widget.setLayout(chat_layout)

        splitter.addWidget(self.history_panel)
        splitter.addWidget(chat_widget)
        splitter.setStretchFactor(0, 0)   # history panel: fixed / minimal
        splitter.setStretchFactor(1, 1)   # chat area: takes remaining space
        #splitter.setSizes([220, 1000])

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

        # ----- Connect UI signals -----
        self.send_button.clicked.connect(self.on_send)
        self.input_line.installEventFilter(self)


        # ----- Initialize ImageJ & Agent -----
        self.ij = get_ij()
        self.ij.ui().showUI()
        self.supervisor, self.checkpointer = init_agent()

        # ----- Worker thread -----
        # current_thread_id is set in _init_session() below
        self.current_thread_id: str = ""
        self._is_new_thread: bool = True

        self.thread = QThread()
        # Placeholder thread_id — will be set properly in _init_session()
        self.worker = AgentWorker(self.supervisor, "")
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.start)
        self.worker.event_received.connect(self.handle_event)
        self.worker.finished.connect(self.on_agent_finished)
        self.worker.error.connect(self.on_agent_error)

        self.thread.start()

        # ----- Populate history & start session -----
        self._init_session()

    # ------------------------------------------------------------------
    # Session initialisation
    # ------------------------------------------------------------------

    def _init_session(self):
        """Load existing history or create a fresh thread on first run."""
        threads = self.history_manager.list_threads()
        self.history_panel.populate(threads)

        if threads:
            # Restore the most-recent thread
            most_recent_id, _ = threads[0]
            self._load_thread(most_recent_id)
        else:
            # First ever launch — create a blank thread
            self._start_new_thread()

    def _start_new_thread(self):
        """Create a new thread ID and show the intro message."""
        thread_id = self.history_manager.create_thread()
        self.current_thread_id = thread_id
        self.worker.thread_id = thread_id
        self._is_new_thread = True

        self.output_area.clear()
        self.output_area.append(intro_message)

        # Refresh sidebar and highlight new entry
        self.history_panel.populate(self.history_manager.list_threads())
        self.history_panel.set_active(thread_id)

    def _load_thread(self, thread_id: str):
        """Set the active thread and replay its saved messages into the chat area."""
        self.current_thread_id = thread_id
        self.worker.thread_id = thread_id
        self._is_new_thread = False

        self.output_area.clear()

        messages = self.history_manager.get_messages_for_display(self.supervisor, thread_id)
        if not messages:
            self.output_area.append(intro_message)
        else:
            html = self.history_manager.format_messages_as_html(messages)
            self.output_area.setHtml(html)
            # Scroll to bottom
            self.output_area.moveCursor(QTextCursor.End)

        self.history_panel.set_active(thread_id)

    # ------------------------------------------------------------------
    # Public slots wired to the history panel
    # ------------------------------------------------------------------

    def new_chat(self):
        """Triggered by the '+ New Chat' button."""
        if self._agent_is_busy():
            QMessageBox.warning(self, "Agent Busy", "Please wait for the current task to finish.")
            return
        self._start_new_thread()

    def switch_thread(self, thread_id: str):
        """Triggered when the user clicks a session in the sidebar."""
        if thread_id == self.current_thread_id:
            return
        if self._agent_is_busy():
            QMessageBox.warning(self, "Agent Busy", "Please wait for the current task to finish.")
            return
        self._load_thread(thread_id)

    # ------------------------------------------------------------------
    # Drag-and-drop
    # ------------------------------------------------------------------

    # def dragEnterEvent(self, event):
    #     if event.mimeData().hasUrls():
    #         event.acceptProposedAction()

    # def dropEvent(self, event):
    #     for url in event.mimeData().urls():
    #         file_path = url.toLocalFile()
    #         if file_path not in self.attached_files:
    #             self.attached_files.append(file_path)
    #     self._update_attachment_ui()

    def _update_attachment_ui(self):
        if not self.attached_files:
            self.attachment_status.setText("No files attached")
            self.attachment_status.setStyleSheet(
                "color: #7f8c8d; font-style: italic; padding-left: 5px;"
            )
        else:
            names = [os.path.basename(p) for p in self.attached_files]
            self.attachment_status.setText(f"📎 Attached ({len(names)}): {', '.join(names)}")
            self.attachment_status.setStyleSheet("color: #2980b9; font-weight: bold;")

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------


    def eventFilter(self, obj, event):
        if obj == self.input_line and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # Send only if NO modifiers (plain Enter)
                if event.modifiers() == Qt.KeyboardModifier.NoModifier:
                    self.on_send()
                    return True  # block newline
        return super().eventFilter(obj, event)

    def _agent_is_busy(self) -> bool:
        return self.send_button.isEnabled() is False

    def append_output(self, text: str):
        self.output_area.append(text)

    def set_status(self, text: str):
        self.status_label.setText(text)
        if text == "Ready":
            self.status_label.setText("Agent is ready to help")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        elif text == "Thinking...":
            self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        elif text == "Stopping...":
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")

    def set_ui_busy(self, busy: bool):
        self.stop_button.setEnabled(busy)
        self.send_button.setDisabled(busy)
        self.input_line.setDisabled(busy)
        # Also disable history panel while agent runs to prevent mid-stream switch
        self.history_panel.setEnabled(not busy)

        if busy:
            self.stop_button.setStyleSheet(
                "background-color: #e74c3c; color: white; font-weight: bold; padding: 8px;"
            )
            self.send_button.setStyleSheet(
                "background-color: #bdc3c7; color: #7f8c8d; font-weight: bold; padding: 8px;"
            )
        else:
            self.stop_button.setStyleSheet(
                "background-color: #bdc3c7; color: #7f8c8d; font-weight: bold; padding: 8px;"
            )
            self.send_button.setStyleSheet(
                "background-color: #3498db; color: white; font-weight: bold; padding: 8px;"
            )

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def on_stop(self):
        if hasattr(self, 'worker') and self.worker:
            self.append_output("\n<i style='color: #e74c3c;'>🛑 Stopping agent...</i>")
            self.worker.request_stop()
            self.set_status("Stopping...")

    def on_agent_finished(self):
        if hasattr(self, 'worker') and self.worker._stop_requested:
            self.append_output("\n<b style='color: green;'>✓ Agent is ready to help</b>")
        self.set_status("Ready")
        self.set_ui_busy(False)

    def on_agent_error(self, msg: str):
        self.append_output(f"[Agent error]\n{msg}")
        self.status_label.setText("Error")
        self.set_ui_busy(False)
        self.status_label.setStyleSheet("color: red;")

    def _execute_agent_query(self, prompt: str):
        self.set_status("Thinking...")
        self.set_ui_busy(True)
        self.worker.submit(prompt)

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------
        
    def on_send(self):
        user_input = self.input_line.toPlainText().strip()
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

        # --- Update history metadata ---
        current_title = self.history_manager._index.get(self.current_thread_id, {}).get("title", "New Chat")
        if current_title == "New Chat" and user_input:
            # Thread not yet titled: set a human-readable title from the first message
            self.history_manager.update_title(self.current_thread_id, user_input)
            self.history_panel.populate(self.history_manager.list_threads())
            self.history_panel.set_active(self.current_thread_id)
        else:
            self.history_manager.touch_thread(self.current_thread_id)
        self._is_new_thread = False

        self._execute_agent_query(full_prompt)

        self.attached_files = []
        self._update_attachment_ui()



    # ------------------------------------------------------------------
    # Script library integration
    # ------------------------------------------------------------------

    # def run_saved_script(self, language: str, code: str):
    #     if self._agent_is_busy():
    #         QMessageBox.warning(self, "Agent Busy", "Please wait for the current task to finish.")
    #         return
    #     prompt = (
    #         f"SYSTEM REQUEST: The user wants to run a saved {language} script from the library.\n"
    #         f"Please execute the following code immediately using the 'run_script_safe' tool.\n"
    #         f"Do not change the code unless it fails.\n\n"
    #         f"CODE:\n```{language}\n{code}\n```"
    #     )
    #     self.output_area.append(f"\n<b>⚙️ Recall Script:</b> Sending to Agent...")
    #     self._execute_agent_query(prompt)

    # def on_saved_script_finished(self, result: str):
    #     self.output_area.append(f"<pre>{result}</pre>")
    #     self.set_status("Ready")
    #     self.set_ui_busy(False)
    #     self.status_label.setStyleSheet("color: black;")
    #     self.output_area.append("✅ <b>Execution complete.</b>")

    # ------------------------------------------------------------------
    # Event handler (streaming from agent)
    # ------------------------------------------------------------------

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
                            self.append_output(
                                f"\n<div style='color: #e67e22;'><b>🚀 Routing to {agent_type}:</b></div>"
                            )
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    # QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    window = ImageJAgentGUI()
    window.show()
    sys.exit(app.exec())
