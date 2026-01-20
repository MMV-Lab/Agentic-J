import sys
import os
import json
import jpype
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QTextEdit, QLineEdit, QPushButton, QLabel, QListWidget, 
    QSplitter, QGroupBox, QScrollArea, QMessageBox
)
from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt

# --- Import your existing backend ---
from agents import init_agent
from imagej_context import get_ij
# Import the specific execution tool directly for the "Run" button
from tools import run_script_safe

SCRIPTS_DIR = "saved_scripts"


os.environ["JAVA_HOME"] = r"C:\Users\lukas.johanns\Downloads\fiji-latest-win64-jdk(1)\Fiji\java\win64"

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
    # Signals to communicate back to the Main Thread
    event_received = Signal(dict)
    finished = Signal()
    error = Signal(str)

    def __init__(self, supervisor, thread_id):
        super().__init__()
        self.supervisor = supervisor
        self.thread_id = thread_id

    @Slot(str)
    def run(self, user_input: str):
        """
        This method runs in the background thread.
        """
        try:
            # --- CRITICAL: Attach this thread to the JVM ---
            # Since ImageJ runs on Java, and this is a new Python thread,
            # we must explicitly attach it to the JVM or ImageJ calls may hang/crash.
            if jpype.isJVMStarted() and not jpype.isThreadAttachedToJVM():
                jpype.attachThreadToJVM()

            config = {"configurable": {"thread_id": self.thread_id}}
            
            # Streaming the agent response
            for event in self.supervisor.stream(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
                stream_mode="updates",
            ):
                # Emit result back to GUI immediately
                self.event_received.emit(event)
                
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


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
        self.resize(1100, 700) # Made wider for the library

        # --- Main Layout (Splitter) ---
        main_layout = QHBoxLayout()
        splitter = QSplitter(Qt.Horizontal)

        # --- LEFT: Chat Interface ---
        chat_widget = QWidget()
        chat_layout = QVBoxLayout()
        
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.input_line = QLineEdit()
        self.send_button = QPushButton("Send")
        self.status_label = QLabel("Ready")

        chat_layout.addWidget(self.output_area)
        chat_layout.addWidget(self.input_line)
        chat_layout.addWidget(self.send_button)
        chat_layout.addWidget(self.status_label)
        chat_widget.setLayout(chat_layout)

        # --- RIGHT: Script Library ---
        self.library_widget = ScriptLibraryWidget()
        # Connect library run signal to execution handler
        self.library_widget.script_run_requested.connect(self.run_saved_script)

        # Add to Splitter
        splitter.addWidget(chat_widget)
        splitter.addWidget(self.library_widget)
        splitter.setStretchFactor(0, 3) # Chat is wider
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
        
        # Introduction
        self.output_area.append(intro_message) 
        self.output_area.append("Use the panel on the right to recall saved scripts.")

    def append_output(self, text):
        self.output_area.append(text)

    def on_agent_finished(self):
        self.status_label.setText("Ready")
        # Optional: Clean up thread resources if desired here
        # self.thread.quit() 

    def on_agent_error(self, msg):
        self.append_output(f"[Agent error]\n{msg}")
        self.status_label.setText("Error")
        self.status_label.setStyleSheet("color: red;")

    def on_send(self):
        user_input = self.input_line.text().strip()
        if not user_input:
            return

        self.input_line.clear()
        self.append_output(f"\n<b>You:</b> {user_input}")
        self.append_output("AI: ...")
        self.status_label.setText("Thinking...")
        self.status_label.setStyleSheet("color: blue;")

        # --- Threading Setup ---
        # 1. Create Thread and Worker
        self.thread = QThread()
        self.worker = AgentWorker(self.supervisor, THREAD_ID)
        
        # 2. Move Worker to Thread
        self.worker.moveToThread(self.thread)

        # 3. Connect Signals
        
        # FIX: Connect our custom Signal to the Worker's run Slot
        self.start_agent_work.connect(self.worker.run)
        
        # Standard cleanup connections
        self.worker.event_received.connect(self.handle_event)
        self.worker.error.connect(self.on_agent_error)
        self.worker.finished.connect(self.on_agent_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # 4. Start the thread
        self.thread.start()

        # 5. Emit the signal to trigger the work
        # This effectively pushes 'user_input' into the background thread's queue
        self.start_agent_work.emit(user_input)


    def run_saved_script(self, language, code):
        """
        Instead of running the code directly, we ask the Agent to do it.
        This keeps the Agent in the loop for context and error handling.
        """
        # 1. Check if Agent is busy
        if self.status_label.text() != "Ready":
            from PySide6.QtWidgets import QMessageBox
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
        self.status_label.setText("Agent Running Script...")
        self.status_label.setStyleSheet("color: blue;")

        # 4. Trigger the standard Agent Worker (Same as on_send)
        # We reuse the existing threading logic!
        self.thread = QThread()
        self.worker = AgentWorker(self.supervisor, THREAD_ID)
        self.worker.moveToThread(self.thread)

        self.start_agent_work.connect(self.worker.run)
        
        self.worker.event_received.connect(self.handle_event)
        self.worker.error.connect(self.on_agent_error)
        self.worker.finished.connect(self.on_agent_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()
        
        # Emit the signal with our constructed prompt
        self.start_agent_work.emit(prompt)

    def on_saved_script_finished(self, result):
        self.output_area.append(f"<pre>{result}</pre>")
        self.status_label.setText("Ready")
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