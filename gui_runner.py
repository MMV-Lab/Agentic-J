import sys
sys.path.insert(0, 'src')
import os
import json
import jpype
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QTextEdit, QLineEdit, QPushButton, QLabel, QListWidget, 
    QSplitter, QGroupBox, QScrollArea, QMessageBox
)
from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt
from queue import Queue

# --- Import your existing backend ---
from imagentj.agents import init_agent
from imagentj.imagej_context import get_ij
# Import the specific execution tool directly for the "Run" button
from imagentj.tools import run_script_safe
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts/saved_scripts")

# ----- CONFIG -----
THREAD_ID = "imagej_supervisor_thread"   # keep constant to preserve context

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

If you’re unsure, tell me the biological question and show one representative image—I’ll propose a clear plan and a script you can run.
"""



class AgentWorker(QObject):
    event_received = Signal(dict)
    finished = Signal()
    error = Signal(str)

    def __init__(self, supervisor, thread_id):
        super().__init__()
        self.supervisor = supervisor
        self.thread_id = thread_id
        self.tasks = Queue()
        self._stop_requested = False

    @Slot()
    def start(self):
        # Attach ONCE for lifetime
        if jpype.isJVMStarted() and not jpype.isThreadAttachedToJVM():
            jpype.attachThreadToJVM()

        while True:
            prompt = self.tasks.get()

            if prompt is None:   # poison pill if app closes
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


class ScriptLibraryWidget(QWidget):
    """
    Right-hand panel to list, view, and run saved scripts.
    """
    script_run_requested = Signal(str, str) # language, code

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        
        # 1. Header
        layout.addWidget(QLabel("<b>📜 Script Library</b>"))
        
        # 2. List of Scripts
        self.script_list = QListWidget()
        self.script_list.itemClicked.connect(self.display_details)
        layout.addWidget(self.script_list)
        
        # 3. Details Area (Description + Inputs)
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
        
        # 4. Buttons (Refresh & Run)
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
        
        # Data storage
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

        # Scan folder for .json metadata files
        try:
            files = sorted(os.listdir(SCRIPTS_DIR))
            json_files = [f for f in files if f.endswith(".json")]
            
            if not json_files:
                self.script_list.addItem("No scripts found.")
                return

            for json_file in json_files:
                # Load metadata
                meta_path = os.path.join(SCRIPTS_DIR, json_file)
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    
                    # Load the actual code content
                    script_filename = meta.get("script_file")
                    code_path = os.path.join(SCRIPTS_DIR, script_filename)
                    
                    if os.path.exists(code_path):
                        with open(code_path, "r", encoding="utf-8") as cf:
                            meta["code"] = cf.read()
                        
                        # Add to internal list and UI
                        self.scripts_data.append(meta)
                        self.script_list.addItem(meta.get("name", json_file))
                    else:
                        print(f"Warning: Script code file missing for {json_file}")
                        
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
            # Confirm with user regarding inputs
            msg = f"Ensure the following requirements are met before running:\n\n{self.current_selection.get('inputs')}\n\nProceed?"
            reply = QMessageBox.question(self, 'Run Script', msg, QMessageBox.Yes | QMessageBox.No)

            if reply == QMessageBox.Yes:
                self.script_run_requested.emit(
                    self.current_selection.get("language", "groovy"),
                    self.current_selection.get("code")
                )


class ImageJAgentGUI(QWidget):
    # Signal to trigger the worker (This is the fix for the freezing)
    start_agent_work = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ImagentJ - AI Supervisor & Script Library")
        self.resize(1200, 700) 
        
        # --- 1. Enable Drag and Drop ---
        self.setAcceptDrops(True)
        self.attached_files = [] # Store full paths here

        # --- Main Layout (Splitter) ---
        main_layout = QHBoxLayout()
        splitter = QSplitter(Qt.Horizontal)

        # --- LEFT: Chat Interface ---
        chat_widget = QWidget()
        chat_layout = QVBoxLayout()
        
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        
        # --- 2. Attachment Status Label ---
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

        # Button row: Send (stretch) + Stop
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.send_button, stretch=4)  # Send takes 80%
        button_layout.addWidget(self.stop_button, stretch=1)  # Stop takes 20%

        chat_layout.addWidget(self.output_area)
        chat_layout.addWidget(self.attachment_status) # Add label above input
        chat_layout.addWidget(self.input_line)
        chat_layout.addLayout(button_layout)
        chat_layout.addWidget(self.status_label)
        chat_widget.setLayout(chat_layout)

        # --- RIGHT: Script Library ---
        self.library_widget = ScriptLibraryWidget()
        self.library_widget.script_run_requested.connect(self.run_saved_script)

        splitter.addWidget(chat_widget)
        splitter.addWidget(self.library_widget)
        splitter.setStretchFactor(0, 3) 
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

        # ----- Connect UI signals -----
        self.send_button.clicked.connect(self.on_send)
        self.input_line.returnPressed.connect(self.on_send)

        # ----- Initialize ImageJ & Agent -----
        self.ij = get_ij()
        self.ij.ui().showUI()
        self.supervisor, self.checkpointer = init_agent()


        self.thread = QThread()
        self.worker = AgentWorker(self.supervisor, THREAD_ID)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.start)
        self.worker.event_received.connect(self.handle_event)
        self.worker.finished.connect(self.on_agent_finished)
        self.worker.error.connect(self.on_agent_error)

        self.thread.start()
        
        self.output_area.append(intro_message) 
        self.output_area.append("Use the panel on the right to recall saved scripts or drag files here.")

    # --- 3. Drag and Drop Overrides ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        for url in urls:
            file_path = url.toLocalFile()
            if file_path not in self.attached_files:
                self.attached_files.append(file_path)
        
        self._update_attachment_ui()

    def _update_attachment_ui(self):
        if not self.attached_files:
            self.attachment_status.setText("No files attached")
        else:
            names = [os.path.basename(p) for p in self.attached_files]
            self.attachment_status.setText(f"📎 Attached ({len(names)}): {', '.join(names)}")
            self.attachment_status.setStyleSheet("color: #2980b9; font-weight: bold;")

    def append_output(self, text):
        self.output_area.append(text)

    def set_status(self, text: str):
        # for differentiating ready and thinking
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

        # Update stop button color based on state
        if busy:
            self.stop_button.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 8px;")
            self.send_button.setStyleSheet("background-color: #bdc3c7; color: #7f8c8d; font-weight: bold; padding: 8px;")
        else:
            self.stop_button.setStyleSheet("background-color: #bdc3c7; color: #7f8c8d; font-weight: bold; padding: 8px;")
            self.send_button.setStyleSheet("background-color: #3498db; color: white; font-weight: bold; padding: 8px;")


    def on_stop(self):
        """Stop the currently running agent."""
        if hasattr(self, 'worker') and self.worker:
            self.append_output("\n<i style='color: #e74c3c;'>🛑 Stopping agent...</i>")
            self.worker.request_stop()
            self.set_status("Stopping...")
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")



    def on_agent_finished(self):
        # Check if agent was stopped by user
        if hasattr(self, 'worker') and self.worker._stop_requested:
            self.append_output("\n<b style='color: green;'>✓ Agent is ready to help</b>")

        self.set_status("Ready")
        self.set_ui_busy(False)

    def on_agent_error(self, msg):
        self.append_output(f"[Agent error]\n{msg}")
        self.status_label.setText("Error")
        self.set_ui_busy(False)
        self.status_label.setStyleSheet("color: red;")

    def _execute_agent_query(self, prompt):
        self.set_status("Thinking...")
        self.set_ui_busy(True)
        self.worker.submit(prompt)

    def on_send(self):
        user_input = self.input_line.text().strip()
        
        # Don't send if both are empty
        if not user_input and not self.attached_files:
            return

        # Prepare prompt
        full_prompt = user_input
        if self.attached_files:
            file_list_str = "\n".join([f"- {p}" for p in self.attached_files])
            full_prompt += f"\n\n[SYSTEM: The user has attached the following files/folders]:\n{file_list_str}"

        # Update UI
        self.append_output(f"\n<b>You:</b> {user_input if user_input else '[Attached Files]'}")
        if self.attached_files:
            display_names = ", ".join([os.path.basename(p) for p in self.attached_files])
            self.append_output(f"<i style='color: #2980b9;'>📎 Sent with: {display_names}</i>")
        
        self.append_output("AI: ...")
        self.input_line.clear()

        # Run Agent
        self._execute_agent_query(full_prompt)

        # Clear attachments for next turn
        self.attached_files = []
        self._update_attachment_ui()


    def run_saved_script(self, language, code):
        """
        Instead of running the code directly, we ask the Agent to do it.
        This keeps the Agent in the loop for context and error handling.
        """
        # 1. Check if Agent is busy
        if self.status_label.text() != "Agent ready to help":
            QMessageBox.warning(self, "Agent Busy", "Please wait for the current task to finish.")
            return

        # 2. Construct a prompt that forces the agent to use the tool
        # We include the code clearly so the agent 'reads' it into memory.
        prompt = (
            f"SYSTEM REQUEST: The user wants to run a saved {language} script from the library.\n"
            f"Please execute the following code immediately using the 'run_script_safe' tool.\n"
            f"Do not change the code unless it fails.\n\n"
            f"CODE:\n```{language}\n{code}\n```"
        )

        # 3. Update UI to show what's happening
        self.output_area.append(f"\n<b>⚙️ Recall Script:</b> Sending to Agent...")

        # 4. Use the standard agent execution helper
        self._execute_agent_query(prompt)

    def on_saved_script_finished(self, result):
        self.output_area.append(f"<pre>{result}</pre>")
        self.set_status("Ready")
        self.set_ui_busy(False)
        self.status_label.setStyleSheet("color: black;")
        self.output_area.append("✅ <b>Execution complete.</b>")

    def handle_event(self, event):
            """
            Parses LangGraph events. Handles Pydantic objects and dictionary formats.
            """
            # 1. Detect Node Transitions (Filtering out Middleware)
            for node_name, node_data in event.items():
                if "Middleware" in node_name:
                    continue
                
                # If the supervisor is active, it's usually making a routing decision
                if node_name == "supervisor" or node_name == "model":
                    # Extract messages which contain the tool_calls
                    messages = node_data.get("messages", [])
                    for msg in messages:
                        # Fix for Pydantic AIMessage: use getattr instead of .get()
                        tool_calls = getattr(msg, "tool_calls", [])
                        
                        for tc in tool_calls:
                            # tool_calls can be dicts or objects
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

                # 2. Text output (Assistant speaking)
                if node_name == "model":
                    for msg in node_data.get("messages", []):
                        content = getattr(msg, "content", "")
                        # Only append if there's text and it's not just a tool call placeholder
                        if content and not getattr(msg, "tool_calls", None):
                            self.append_output(content)

            # 3. Tool / Sub-agent Completion
            if "tools" in event:
                for tool_msg in event["tools"].get("messages", []):
                    name = getattr(tool_msg, "name", "Tool")
                    if name == "task":
                        self.append_output(f"\n✅ <b>Sub-agent task completed.</b>")
                    else:
                        self.append_output(f"\n> 🛠️ <b>{name}</b> finished.")



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageJAgentGUI()
    window.show()
    sys.exit(app.exec())
