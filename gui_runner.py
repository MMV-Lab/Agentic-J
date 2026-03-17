"""ImagentJ GUI — chat bubbles + per-conversation usage tracking."""

import sys
sys.path.insert(0, 'src')
import os
import re
import json
import html as html_module
import logging
import jpype
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QListWidget,
    QSplitter, QScrollArea, QMessageBox, QListWidgetItem,
    QSizePolicy, QFrame, QGroupBox, QFileDialog,
)
from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt, QSize, QEvent, QTimer
from queue import Queue

from imagentj.agents import init_agent
from imagentj.imagej_context import get_ij
from imagentj.chat_history import ChatHistoryManager

logging.basicConfig(
    filename="/app/data/imagentj_debug.log",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True,
)
log = logging.getLogger("imagentj")

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts/saved_scripts")

intro_message = """Hello I am ImageJ agent, some call me ImagentJ :)
I can design a step-by-step protocol and, if useful, generate a runnable Groovy macro (and execute/test it if you want).

To get started, please share:
- **Goal:** what you want measured/segmented/processed.
- **Example data:** 1-2 sample images (file type), single image or batch?
- **Targets:** what objects/features to detect; which channel(s) matter.
- **Preprocessing:** background/flat-field correction, denoising needs?
- **Outputs:** tables/measurements, labeled masks/overlays, ROIs, saved images.
- **Constraints:** plugins available (e.g., Fiji with Bio-Formats, MorpholibJ, TrackMate, StarDist), OS, any runtime limits.

If you're unsure, tell me the biological question and show one representative image."""

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_API_KEY"] = "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"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGSMITH_PROJECT"] = "pr-majestic-ecumenist-75"
os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "true"

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
    """Convert plain/markdown text to HTML suitable for a QLabel."""
    escaped = html_module.escape(text)
    lines = escaped.split('\n')

    result: list[str] = []
    in_code = False
    code_lines: list[str] = []

    for line in lines:
        if line.startswith('```'):
            if not in_code:
                in_code = True
                code_lines = []
            else:
                in_code = False
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

        # Headings → bold (same size as body text)
        if line.startswith('### '):
            result.append(f'<b>{line[4:]}</b>')
            continue
        if line.startswith('## '):
            result.append(f'<b>{line[3:]}</b>')
            continue
        if line.startswith('# '):
            result.append(f'<b>{line[2:]}</b>')
            continue
        # Horizontal rules → dropped
        if re.fullmatch(r'[-*_]{3,}', line.strip()):
            continue

        # Inline code
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
    """QLabel that lets its parent layout freely constrain its width."""
    def minimumSizeHint(self):
        sh = super().minimumSizeHint()
        return QSize(1, sh.height())


class MessageBubble(QFrame):
    """A single chat message rendered as a styled bubble."""

    _STYLES = {
        'user':   dict(bg='#2980b9', fg='white',   align='right', label='You'),
        'ai':     dict(bg='#ecf0f1', fg='#2c3e50', align='left',  label='AI'),
        'system': dict(bg='transparent', fg='#7f8c8d', align='left', label=None),
        'error':  dict(bg='#fdecea', fg='#c0392b',  align='left',  label='Error'),
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
        self._msg_layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

        #  Auto-scroll whenever the scrollbar range grows (new content arrived)
        self._scroll.verticalScrollBar().rangeChanged.connect(
            lambda _min, _max: self._scroll.verticalScrollBar().setValue(_max)
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        vp_w = self._scroll.viewport().width()
        if vp_w > 0:
            self._container.setMaximumWidth(vp_w)

    def add_message(self, role: str, text: str) -> MessageBubble:
        bubble = MessageBubble(text, role)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, bubble)
        return bubble

    def clear_messages(self):
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()



# ---------------------------------------------------------------------------
# Metrics panel
# ---------------------------------------------------------------------------

class MetricsPanelWidget(QWidget):
    """Shows token/cost/tool metrics for the active conversation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        header = QLabel("<b>Conversation Metrics</b>")
        header.setAlignment(Qt.AlignCenter)
        root.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)

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

        perf_box = QGroupBox("Performance")
        perf_layout = QVBoxLayout(perf_box)
        perf_layout.setSpacing(2)
        self._lbl_time = QLabel()
        self._lbl_cost = QLabel()
        for lbl in (self._lbl_time, self._lbl_cost):
            lbl.setTextFormat(Qt.RichText)
            perf_layout.addWidget(lbl)
        root.addWidget(perf_box)

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

        self._btn_save = QPushButton("Save Usage Report")
        self._btn_save.setStyleSheet(
            "padding: 4px; background-color: #2980b9; "
            "color: white; border-radius: 3px; font-size: 11px;"
        )
        root.addWidget(self._btn_save)
        root.addStretch()

        self.update_metrics({
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            "thinking_seconds": 0.0, "cost_usd": 0.0,
            "tool_calls": 0, "failed_tool_calls": 0, "soft_error_tool_calls": 0,
        })

    @staticmethod
    def _fmt(name: str, value: str, color: str, bold: bool = False) -> str:
        w = "bold" if bold else "normal"
        return (
            f"<span style='color:#555;'>{name}:</span> "
            f"<span style='color:{color};font-weight:{w};'>{value}</span>"
        )

    @Slot(dict)
    def update_metrics(self, data: dict):
        f = self._fmt
        self._lbl_in.setText(    f("Input",   f"{data['input_tokens']:,}",  "#2980b9"))
        self._lbl_out.setText(   f("Output",  f"{data['output_tokens']:,}", "#27ae60"))
        self._lbl_total.setText( f("Total",   f"{data['total_tokens']:,}",  "#8e44ad", bold=True))

        secs  = data["thinking_seconds"]
        t_str = f"{int(secs//60)}m {int(secs%60)}s" if secs >= 60 else f"{secs:.1f}s"
        self._lbl_time.setText(  f("Think time", t_str,    "#16a085"))

        cost     = data["cost_usd"]
        cost_str = f"${cost:.4f}" if cost >= 0.0001 else "-"
        self._lbl_cost.setText(  f("Est. cost",  cost_str, "#c0392b", bold=True))

        self._lbl_calls.setText( f("Total",       str(data["tool_calls"]),            "#2c3e50"))
        self._lbl_failed.setText(f("Hard errors", str(data["failed_tool_calls"]),     "#e74c3c"))
        self._lbl_soft.setText(  f("Soft errors", str(data["soft_error_tool_calls"]), "#e67e22"))


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class AgentWorker(QObject):
    event_received = Signal(dict)
    finished = Signal()
    error = Signal(str)

    def __init__(self, supervisor, thread_id: str, tracker_callback):
        super().__init__()
        self.supervisor       = supervisor
        self.thread_id        = thread_id
        self.tracker_callback = tracker_callback
        self.tasks            = Queue()
        self._stop_requested  = False

    @Slot()
    def start(self):
        if jpype.isJVMStarted() and not jpype.isThreadAttachedToJVM():
            jpype.attachThreadToJVM()
        while True:
            prompt = self.tasks.get()
            if prompt is None:
                break
            self._stop_requested = False
            self._run_prompt(prompt)

    def _run_prompt(self, user_input: str):
        try:
            config = {
                "configurable": {"thread_id": self.thread_id},
                "callbacks":    [self.tracker_callback],
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
            log.exception(f"_run_prompt exception: {e}")
            self.error.emit(str(e))
        finally:
            log.debug("_run_prompt finished")
            self.finished.emit()

    def submit(self, prompt: str):
        self.tasks.put(prompt)

    def request_stop(self):
        self._stop_requested = True


# ---------------------------------------------------------------------------
# Chat history sidebar
# ---------------------------------------------------------------------------

class ChatHistoryPanel(QWidget):
    thread_selected    = Signal(str)
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
        self.session_list.clear()
        self._thread_ids = []
        for thread_id, meta in threads:
            title    = meta.get("title", "Untitled")
            date_str = meta.get("last_updated", "")[:10]
            item = QListWidgetItem(f"{title}\n{date_str}")
            item.setSizeHint(QSize(0, 52))
            self.session_list.addItem(item)
            self._thread_ids.append(thread_id)

    def set_active(self, thread_id: str):
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
        self.resize(1100, 680)
        self.setAcceptDrops(True)
        self.attached_files: list[str] = []

        self.history_manager = ChatHistoryManager()

        # Streaming state
        self._current_ai_bubble: MessageBubble | None = None
        self._ai_response_buffer: str = ""

        # Agent + tracker (init_agent returns 5 values)
        (self.supervisor,
         self.checkpointer,
         self._metrics,
         self._metrics_bridge,
         self._tracker_cb) = init_agent()

        # --- Main layout ---
        main_layout = QHBoxLayout()
        splitter    = QSplitter(Qt.Horizontal)

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

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.send_button, stretch=4)
        btn_row.addWidget(self.stop_button, stretch=1)

        chat_layout.addWidget(self.chat_scroll,        stretch=3)
        chat_layout.addWidget(self.attachment_status,  stretch=0)
        chat_layout.addWidget(self.input_line,         stretch=1)
        chat_layout.addLayout(btn_row)
        chat_layout.addWidget(self.status_label,       stretch=0)
        chat_widget.setLayout(chat_layout)

        # RIGHT: metrics panel
        self.metrics_panel = MetricsPanelWidget()
        self.metrics_panel.setMinimumWidth(190)
        self.metrics_panel.setMaximumWidth(250)
        self.metrics_panel._btn_save.clicked.connect(self._save_report)

        splitter.addWidget(self.history_panel)
        splitter.addWidget(chat_widget)
        splitter.addWidget(self.metrics_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

        # Wire signals
        self.send_button.clicked.connect(self.on_send)
        self.input_line.installEventFilter(self)
        self._metrics_bridge.updated.connect(self.metrics_panel.update_metrics)

        # Initialize ImageJ
        self.ij = get_ij()
        self.ij.ui().showUI()

        # Worker thread
        self.current_thread_id: str = ""
        self._is_new_thread: bool   = True

        self.thread = QThread()
        self.worker = AgentWorker(self.supervisor, "", self._tracker_cb)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.start)
        self.worker.event_received.connect(self.handle_event)
        self.worker.finished.connect(self.on_agent_finished)
        self.worker.error.connect(self.on_agent_error)
        self.thread.start()

        self._init_session()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _init_session(self):
        threads = self.history_manager.list_threads()
        self.history_panel.populate(threads)
        if threads:
            self._load_thread(threads[0][0])
        else:
            self._start_new_thread()

    def _start_new_thread(self):
        thread_id = self.history_manager.create_thread()
        self.current_thread_id = thread_id
        self.worker.thread_id  = thread_id
        self._is_new_thread    = True
        self._current_ai_bubble   = None
        self._ai_response_buffer  = ""
        self._tracker_cb.switch_thread(thread_id)

        self.chat_scroll.clear_messages()
        self.chat_scroll.add_message('ai', intro_message)

        self.history_panel.populate(self.history_manager.list_threads())
        self.history_panel.set_active(thread_id)

    def _load_thread(self, thread_id: str):
        self.current_thread_id = thread_id
        self.worker.thread_id  = thread_id
        self._is_new_thread    = False
        self._current_ai_bubble  = None
        self._ai_response_buffer = ""
        self._tracker_cb.switch_thread(thread_id)

        self.chat_scroll.clear_messages()

        messages = self.history_manager.get_messages_for_display(self.supervisor, thread_id)
        if not messages:
            self.chat_scroll.add_message('ai', intro_message)
        else:
            for msg in messages:
                msg_type   = getattr(msg, 'type', '') or ''
                content    = _extract_text(getattr(msg, 'content', ''))
                tool_calls = getattr(msg, 'tool_calls', None) or []

                if msg_type == 'human' and content:
                    self.chat_scroll.add_message('user', content)
                elif msg_type == 'ai' and content and not tool_calls:
                    self.chat_scroll.add_message('ai', content)

        self.history_panel.set_active(thread_id)

    # ------------------------------------------------------------------
    # History panel slots
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
    # Report export
    # ------------------------------------------------------------------

    def _save_report(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Usage Report",
            os.path.expanduser("~/imagentj_usage_report.json"),
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            report = self._tracker_cb.get_report()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Saved", f"Report saved to:\n{path}")
        except Exception as e:
            log.exception(f"Failed to save report: {e}")
            QMessageBox.warning(self, "Save Failed", str(e))

    # ------------------------------------------------------------------
    # Drag-and-drop / attachments
    # ------------------------------------------------------------------

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
            self.attachment_status.setStyleSheet(
                "color: #7f8c8d; font-style: italic; padding-left: 5px;"
            )
        else:
            names = [os.path.basename(p) for p in self.attached_files]
            self.attachment_status.setText(f"Attached ({len(names)}): {', '.join(names)}")
            self.attachment_status.setStyleSheet("color: #2980b9; font-weight: bold;")

    # ------------------------------------------------------------------
    # Status / UI helpers
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj == self.input_line and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() == Qt.KeyboardModifier.NoModifier:
                    self.on_send()
                    return True
        return super().eventFilter(obj, event)

    def _agent_is_busy(self) -> bool:
        return not self.send_button.isEnabled()

    def set_status(self, text: str):
        colors = {"Ready": "green", "Thinking...": "blue", "Stopping...": "#e74c3c"}
        color  = colors.get(text, "black")
        self.status_label.setText("Agent is ready to help" if text == "Ready" else text)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

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
                "background-color: #3498db; color: white; font-weight: bold; padding: 8px; border:none;"
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
        log.debug("on_agent_finished called")
        try:
            self._tracker_cb.finish_query()
        except Exception as e:
            log.exception(f"finish_query failed: {e}")
        if hasattr(self, 'worker') and self.worker._stop_requested:
            self.chat_scroll.add_message('system', "Agent stopped.")
        self._current_ai_bubble  = None
        self._ai_response_buffer = ""
        self.set_status("Ready")
        self.set_ui_busy(False)

    def on_agent_error(self, msg: str):
        log.error(f"Agent error: {msg}")
        self.chat_scroll.add_message('error', f"Agent error:\n{msg}")
        self.status_label.setText("Error")
        self.status_label.setStyleSheet("color: red;")
        self.set_ui_busy(False)

    def _execute_agent_query(self, prompt: str):
        self._tracker_cb.start_query(prompt, thread_id=self.current_thread_id)
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
            full_prompt  += f"\n\n[SYSTEM: The user has attached the following files/folders]:\n{file_list_str}"

        display_text = user_input if user_input else '[Attached Files]'
        self.chat_scroll.add_message('user', display_text)
        if self.attached_files:
            display_names = ", ".join([os.path.basename(p) for p in self.attached_files])
            self.chat_scroll.add_message('system', f"Sent with: {display_names}")

        self.input_line.clear()

        self._current_ai_bubble  = None
        self._ai_response_buffer = ""

        current_title = self.history_manager._index.get(
            self.current_thread_id, {}
        ).get("title", "New Chat")
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
                for msg in node_data.get("messages", []):
                    tool_calls = getattr(msg, "tool_calls", [])
                    for tc in tool_calls:
                        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                        args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                        if name == "task":
                            agent_type = args.get("subagent_type", "Specialist")
                            desc       = args.get("description", "")
                            short_desc = (desc[:120] + "...") if len(desc) > 120 else desc
                            self.chat_scroll.add_message(
                                'system', f"Routing to {agent_type}: {short_desc}"
                            )
                        else:
                            self.chat_scroll.add_message('system', f"Calling tool: {name}...")

            if node_name == "model":
                for msg in node_data.get("messages", []):
                    content = getattr(msg, "content", "")
                    if content and not getattr(msg, "tool_calls", None):
                        if self._current_ai_bubble is None:
                            self._ai_response_buffer = content
                            self._current_ai_bubble  = self.chat_scroll.add_message('ai', content)
                        else:
                            self._ai_response_buffer += content
                            self._current_ai_bubble.update_text(self._ai_response_buffer)

        if "tools" in event:
            for tool_msg in event["tools"].get("messages", []):
                name    = getattr(tool_msg, "name", "Tool")
                content = getattr(tool_msg, "content", "")

                # Notify tracker when a project workspace is created
                if name == "setup_analysis_workspace":
                    self._tracker_cb.notify_workspace_created(str(content))

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