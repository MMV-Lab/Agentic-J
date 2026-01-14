# gui_runner.py
import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel,
)
from PySide6.QtCore import QObject, Signal, Slot, QThread
import os
from agents import init_agent
from imagej_context import get_ij
import tools



os.environ["JAVA_HOME"] = r"C:\Users\lukas.johanns\Downloads\fiji-latest-win64-jdk(1)\Fiji\java\win64"

# ----- CONFIG -----
THREAD_ID = "imagej_supervisor_thread"   # keep constant to preserve context

intro_message = """
Hello I am ImageJ agent, some call me ImagentJ :) 
I can design a step-by-step protocol and, if useful, generate a runnable Groovy macro (and execute/test it if you want).

To get started, please share:
- Goal: what you want measured/segmented/processed.
- Example data: 1–2 sample images (file type), single image or batch?
- Image details: dimensions, channels, z-stacks/time series, pixel size (units).
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

    @Slot(str)
    def run(self, user_input: str):
        try:
            config = {"configurable": {"thread_id": self.thread_id}}
            for event in self.supervisor.stream(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
                stream_mode="updates",
            ):
                self.event_received.emit(event)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

class ImageJAgentGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ImageJ Agent GUI")
        self.resize(800, 600)

        # ----- UI Elements -----
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.input_line = QLineEdit()
        self.send_button = QPushButton("Send")
        self.status_label = QLabel("Ready")

        layout = QVBoxLayout()
        layout.addWidget(self.output_area)
        layout.addWidget(self.input_line)
        layout.addWidget(self.send_button)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        # ----- Connect signals -----
        self.send_button.clicked.connect(self.on_send)
        self.input_line.returnPressed.connect(self.on_send)

        # ----- Initialize ImageJ & Agent -----
        self.ij = get_ij()
        self.ij.ui().showUI()
        self.supervisor, self.checkpointer = init_agent()

        # ----- Show welcome message -----
        self.append_output(intro_message)

    def append_output(self, text):
        self.output_area.append(text)

    def on_agent_finished(self):
        self.status_label.setText("Ready")

    def on_agent_error(self, msg):
        self.append_output(f"[Agent error]\n{msg}")
        self.status_label.setText("Error")

    def on_send(self):
        user_input = self.input_line.text().strip()
        if not user_input:
            return

        self.input_line.clear()
        self.append_output(f"You: {user_input}")
        self.append_output("AI: ...")
        self.status_label.setText("Thinking...")

        # --- Create thread + worker ---
        self.thread = QThread()
        self.worker = AgentWorker(self.supervisor, THREAD_ID)

        self.worker.moveToThread(self.thread)

        # --- Connect signals ---
        self.thread.started.connect(lambda: self.worker.run(user_input))
        self.worker.event_received.connect(self.handle_event)
        self.worker.error.connect(self.on_agent_error)
        self.worker.finished.connect(self.on_agent_finished)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()


    def handle_event(self, event):
        """
        Robust handler for LangGraph streaming events:
        - model messages (assistant text)
        - tool calls (intent)
        - tool results (stdout / stderr)
        """

        # ---------------------------
        # 1) Assistant text messages
        # ---------------------------
        if "model" in event:
            model = event["model"]

            # Render assistant messages (if any)
            for msg in model.get("messages", []):
                content = getattr(msg, "content", None)
                if content:
                    self.append_output(f"AI: {content}")

            # Render tool calls (intent)
            for tool_call in model.get("tool_calls", []):
                name = tool_call.get("name")
                args = tool_call.get("args", {})
                self.append_output(
                    f"\n[AI is calling tool: {name}]\n"
                    f"Arguments:\n{args}\n"
                )

        # ---------------------------
        # 2) Tool execution results
        # ---------------------------
        if "tools" in event:
            for tool_msg in event["tools"].get("messages", []):
                tool_name = getattr(tool_msg, "name", "unknown_tool")

                self.append_output(
                    f"\n=== Using tool {tool_name} ===\n"
                )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageJAgentGUI()
    window.show()
    sys.exit(app.exec())