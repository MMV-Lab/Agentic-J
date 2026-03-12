import sys
sys.path.insert(0, 'src')
import os
import re
import json
import html as html_module
import jpype
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QListWidget,
    QSplitter, QScrollArea, QMessageBox, QListWidgetItem,
    QSizePolicy, QFrame,
)
from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt, QSize, QEvent, QTimer
from queue import Queue

# --- Import your existing backend ---
from imagentj.agents import init_agent
from imagentj.imagej_context import get_ij
from imagentj.tools import run_script_safe
from imagentj.chat_history import ChatHistoryManager

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts/saved_scripts")

intro_message = """Hello I am ImageJ agent, some call me ImagentJ :)
I can design a step-by-step protocol and, if useful, generate a runnable Groovy macro (and execute/test it if you want).

To get started, please share:
- **Goal:** what you want measured/segmented/processed.
- **Example data:** 1–2 sample images (file type), single image or batch?
- **Targets:** what objects/features to detect; which channel(s) matter.
- **Preprocessing:** background/flat-field correction, denoising needs?
- **Outputs:** tables/measurements, labeled masks/overlays, ROIs, saved images.
- **Constraints:** plugins available (e.g., Fiji with Bio-Formats, MorpholibJ, TrackMate, StarDist), OS, any runtime limits.

If you're unsure, tell me the biological question and show one representative image—I'll propose a clear plan and a script you can run."""


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _extract_text(content) -> str:
    """Extract plain text from a message content field (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return ""


def _md_to_html(text: str) -> str:
    """Convert plain/markdown text to HTML suitable for a QLabel.

    Processes line-by-line so that code-block content is never touched
    by the inline-formatting rules, and headings / hr are handled properly.
    """
    escaped = html_module.escape(text)
    lines = escaped.split('\n')

    result: list[str] = []
    in_code = False
    code_lines: list[str] = []

    for line in lines:
        # Toggle fenced code blocks
        if line.startswith('```'):
            if not in_code:
                in_code = True
                code_lines = []
            else:
                in_code = False
                # Use <br> for newlines — avoids relying on white-space:pre-wrap
                # (Qt's QLabel HTML renderer has limited CSS support)
                code_html = '<br>'.join(code_lines)
                result.append(
                    '<div style="background:#2b2b2b; color:#f8f8f2; '
                    'padding:10px; border-radius:6px; font-family:monospace; '
                    f'margin:6px 0;">{code_html}</div>'
                )
            continue

        if in_code:
            code_lines.append(line)
            continue

        # --- Block-level elements (headings — rendered as bold, hr — skipped) ---
        if line.startswith('### '):
            result.append(f'<b>{line[4:]}</b>')
            continue
        if line.startswith('## '):
            result.append(f'<b>{line[3:]}</b>')
            continue
        if line.startswith('# '):
            result.append(f'<b>{line[2:]}</b>')
            continue
        if re.fullmatch(r'[-*_]{3,}', line.strip()):
            continue  # drop horizontal rules entirely

        # --- Inline formatting ---
        # Inline code  `code`
        line = re.sub(
            r'`([^`]+)`',
            r'<code style="background:rgba(0,0,0,0.12); padding:1px 4px; '
            r'border-radius:3px; font-family:monospace;">\1</code>',
            line,
        )
        line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
        line = re.sub(r'\*(.+?)\*', r'<i>\1</i>', line)

        result.append(line)

    return '<br>'.join(result)


# ---------------------------------------------------------------------------
# Chat bubble widgets
# ---------------------------------------------------------------------------

class _BubbleLabel(QLabel):
    """QLabel that lets its parent layout freely constrain the width.

    Qt's rich-text engine reports the 'natural' (unwrapped) text width as the
    label's minimum size hint, which can be wider than the scroll area viewport.
    Returning a near-zero minimum width lets the layout engine shrink the label
    to the available space; the HTML renderer then reflows at that width.
    """
    def minimumSizeHint(self):
        sh = super().minimumSizeHint()
        return QSize(1, sh.height())


class MessageBubble(QFrame):
    """A single chat message rendered as a styled bubble."""

    _STYLES = {
        'user': dict(bg='#2980b9',  fg='white',   align='right', label='You'),
        'ai':   dict(bg='#ecf0f1',  fg='#2c3e50', align='left',  label='AI'),
        'system': dict(bg='transparent', fg='#7f8c8d', align='left', label=None),
        'error':  dict(bg='#fdecea',      fg='#c0392b', align='left',  label='Error'),
    }

    def __init__(self, text: str, role: str = 'ai', parent=None):
        super().__init__(parent)
        self.role = role
        s = self._STYLES.get(role, self._STYLES['system'])

        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 2)
        outer.setSpacing(0)

        self._label = _BubbleLabel()
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.RichText)
        self._label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
            | Qt.TextSelectableByKeyboard
            | Qt.LinksAccessibleByMouse
        )
        self._label.setOpenExternalLinks(True)
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        if s['bg'] != 'transparent':
            self._label.setStyleSheet(
                f"background-color:{s['bg']}; color:{s['fg']}; "
                "border-radius:10px; padding:8px 12px; font-size:13px;"
            )
        else:
            self._label.setStyleSheet(
                f"color:{s['fg']}; font-size:11px; font-style:italic; padding:2px 8px;"
            )

        outer.addWidget(self._label)

        self._label_prefix = s['label']
        self.update_text(text)

    def update_text(self, text: str):
        body = _md_to_html(text)
        content = f'<b>{self._label_prefix}:</b> {body}' if self._label_prefix else body
        if self.role == 'user':
            self._label.setText(f'<div align="right">{content}</div>')
        else:
            self._label.setText(content)


class ChatScrollArea(QWidget):
    """Scrollable container for MessageBubble widgets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: white; }")

        self._container = QWidget()
        self._container.setStyleSheet("background: white;")
        self._msg_layout = QVBoxLayout(self._container)
        self._msg_layout.setContentsMargins(8, 8, 8, 8)
        self._msg_layout.setSpacing(6)
        self._msg_layout.addStretch()   # keeps bubbles pinned to top

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Cap the container to the viewport width so labels never overflow.
        # This is the fallback for cases (e.g. history load) where the label's
        # natural text width exceeds the visible area before layout settles.
        vp_w = self._scroll.viewport().width()
        if vp_w > 0:
            self._container.setMaximumWidth(vp_w)

    def add_message(self, role: str, text: str) -> MessageBubble:
        bubble = MessageBubble(text, role)
        # Insert before the trailing stretch so bubbles flow top-to-bottom
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, bubble)
        self._scroll_to_bottom()
        return bubble

    def clear_messages(self):
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _scroll_to_bottom(self):
        QTimer.singleShot(60, lambda: (
            self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            )
        ))


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

        header = QLabel("<b>Chat history</b>")
        header.setStyleSheet("font-size: 13px; padding: 4px 0;")
        layout.addWidget(header)

        self.btn_new = QPushButton("New Chat")
        self.btn_new.setStyleSheet(
            "background-color: #2ecc71; color: white; font-weight: bold; "
            "padding: 6px; border-radius: 4px;"
        )
        self.btn_new.clicked.connect(self.new_chat_requested)
        layout.addWidget(self.btn_new)

        self.session_list = QListWidget()
        self.session_list.setWordWrap(True)
        self.session_list.setStyleSheet(
            "QListWidget { border: 1px solid #ddd; border-radius: 4px; outline: none; }"
            "QListWidget::item { padding: 6px 4px; border-bottom: 1px solid #eee; }"
            "QListWidget::item:selected, "
            "QListWidget::item:selected:active, "
            "QListWidget::item:selected:!active { background-color: #3498db; color: white; }"
            "QListWidget::item:hover:!selected { background-color: #e8f4fd; }"
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

        # Streaming state — tracks the in-progress AI bubble
        self._current_ai_bubble: MessageBubble | None = None
        self._ai_response_buffer: str = ""

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

        self.chat_scroll = ChatScrollArea()

        self.attachment_status = QLabel("No files attached")
        self.attachment_status.setStyleSheet(
            "color: #7f8c8d; font-style: italic; padding-left: 5px;"
        )

        self.input_line = QTextEdit()
        self.input_line.setFixedHeight(120)

        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet(
            "background-color: #3498db; color: white; font-weight: bold; padding: 8px; border:none;"
        )

        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet(
            "background-color: #bdc3c7; color: #7f8c8d; font-weight: bold; padding: 8px; border:none;"
        )
        self.stop_button.clicked.connect(self.on_stop)

        self.status_label = QLabel("Agent is ready to help")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.send_button, stretch=4)
        button_layout.addWidget(self.stop_button, stretch=1)

        chat_layout.addWidget(self.chat_scroll, stretch=3)
        chat_layout.addWidget(self.attachment_status, stretch=0)
        chat_layout.addWidget(self.input_line, stretch=1)
        chat_layout.addLayout(button_layout)
        chat_layout.addWidget(self.status_label, stretch=0)
        chat_widget.setLayout(chat_layout)

        splitter.addWidget(self.history_panel)
        splitter.addWidget(chat_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

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
        self.current_thread_id: str = ""
        self._is_new_thread: bool = True

        self.thread = QThread()
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
            most_recent_id, _ = threads[0]
            self._load_thread(most_recent_id)
        else:
            self._start_new_thread()

    def _start_new_thread(self):
        """Create a new thread ID and show the intro message."""
        thread_id = self.history_manager.create_thread()
        self.current_thread_id = thread_id
        self.worker.thread_id = thread_id
        self._is_new_thread = True
        self._current_ai_bubble = None
        self._ai_response_buffer = ""

        self.chat_scroll.clear_messages()
        self.chat_scroll.add_message('ai', intro_message)

        self.history_panel.populate(self.history_manager.list_threads())
        self.history_panel.set_active(thread_id)

    def _load_thread(self, thread_id: str):
        """Set the active thread and replay its saved messages as bubbles."""
        self.current_thread_id = thread_id
        self.worker.thread_id = thread_id
        self._is_new_thread = False
        self._current_ai_bubble = None
        self._ai_response_buffer = ""

        self.chat_scroll.clear_messages()

        messages = self.history_manager.get_messages_for_display(self.supervisor, thread_id)
        if not messages:
            self.chat_scroll.add_message('ai', intro_message)
        else:
            for msg in messages:
                msg_type = getattr(msg, 'type', '') or ''
                content = _extract_text(getattr(msg, 'content', ''))
                tool_calls = getattr(msg, 'tool_calls', None) or []

                if msg_type == 'human' and content:
                    self.chat_scroll.add_message('user', content)
                elif msg_type == 'ai' and content and not tool_calls:
                    self.chat_scroll.add_message('ai', content)
                # tool / system messages are intentionally omitted

        self.history_panel.set_active(thread_id)

    # ------------------------------------------------------------------
    # Public slots wired to the history panel
    # ------------------------------------------------------------------

    def new_chat(self):
        if self._agent_is_busy():
            QMessageBox.warning(self, "Agent Busy", "Please wait for the current task to finish.")
            return
        self._start_new_thread()

    def switch_thread(self, thread_id: str):
        if thread_id == self.current_thread_id:
            return
        if self._agent_is_busy():
            QMessageBox.warning(self, "Agent Busy", "Please wait for the current task to finish.")
            return
        self._load_thread(thread_id)

    # ------------------------------------------------------------------
    # Drag-and-drop / attachments
    # ------------------------------------------------------------------

    def _update_attachment_ui(self):
        if not self.attached_files:
            self.attachment_status.setText("No files attached")
            self.attachment_status.setStyleSheet(
                "color: #7f8c8d; font-style: italic; padding-left: 5px;"
            )
        else:
            names = [os.path.basename(p) for p in self.attached_files]
            self.attachment_status.setText(f"Attached ({len(names)}): {', '.join(names)}")
            self.attachment_status.setStyleSheet("color: #2980b9; font-weight: bold;")

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj == self.input_line and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() == Qt.KeyboardModifier.NoModifier:
                    self.on_send()
                    return True  # block newline
        return super().eventFilter(obj, event)

    def _agent_is_busy(self) -> bool:
        return self.send_button.isEnabled() is False

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
            self.chat_scroll.add_message('system', "Stopping agent...")
            self.worker.request_stop()
            self.set_status("Stopping...")

    def on_agent_finished(self):
        if hasattr(self, 'worker') and self.worker._stop_requested:
            self.chat_scroll.add_message('system', "Agent stopped.")
        self._current_ai_bubble = None
        self._ai_response_buffer = ""
        self.set_status("Ready")
        self.set_ui_busy(False)

    def on_agent_error(self, msg: str):
        self.chat_scroll.add_message('error', f"Agent error:\n{msg}")
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

        # Show user bubble
        display_text = user_input if user_input else '[Attached Files]'
        self.chat_scroll.add_message('user', display_text)
        if self.attached_files:
            display_names = ", ".join([os.path.basename(p) for p in self.attached_files])
            self.chat_scroll.add_message('system', f"Sent with: {display_names}")

        self.input_line.clear()

        # Reset streaming state (new AI response expected)
        self._current_ai_bubble = None
        self._ai_response_buffer = ""

        # --- Update history metadata ---
        current_title = self.history_manager._index.get(self.current_thread_id, {}).get("title", "New Chat")
        if current_title == "New Chat" and user_input:
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
                            self.chat_scroll.add_message(
                                'system',
                                f"Routing to {agent_type}: {short_desc}",
                            )
                        else:
                            self.chat_scroll.add_message('system', f"Calling tool: {name}...")

            if node_name == "model":
                for msg in node_data.get("messages", []):
                    content = getattr(msg, "content", "")
                    if content and not getattr(msg, "tool_calls", None):
                        # Stream into the AI bubble, creating it on first chunk
                        if self._current_ai_bubble is None:
                            self._ai_response_buffer = content
                            self._current_ai_bubble = self.chat_scroll.add_message('ai', content)
                        else:
                            self._ai_response_buffer += content
                            self._current_ai_bubble.update_text(self._ai_response_buffer)

        if "tools" in event:
            for tool_msg in event["tools"].get("messages", []):
                name = getattr(tool_msg, "name", "Tool")
                if name == "task":
                    self.chat_scroll.add_message('system', "Sub-agent task completed.")
                else:
                    self.chat_scroll.add_message('system', f"{name} finished.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageJAgentGUI()
    window.show()
    sys.exit(app.exec())
