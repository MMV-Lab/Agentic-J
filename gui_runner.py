"""ImagentJ GUI — chat bubbles + per-conversation usage tracking."""

import sys
sys.path.insert(0, 'src')
import os
import re
import json
import time
import html as html_module
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import jpype
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QListWidget,
    QSplitter, QScrollArea, QMessageBox, QListWidgetItem,
    QSizePolicy, QFrame, QGroupBox,
    QDialog, QDialogButtonBox, QPlainTextEdit, QCheckBox,
)
from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt, QSize, QEvent, QTimer
from queue import Queue

from imagentj.agents import init_agent
from imagentj.imagej_context import get_ij
from imagentj.chat_history import ChatHistoryManager
from imagentj.tools.analyst_tools import kill_running_processes
import imagentj.stop_signal as stop_signal

from imagentj.benchmark_gui_hooks import is_benchmark_mode, setup_benchmark_gui

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
- **Goal:** what you want measured/segmented/processed/counted etc.
- **Image details:** 1-2 sample images (file type), single image or batch?
- **File location:** file/folder path or is the image open in the window.
- **Outputs:** tables/measurements, labeled masks/overlays, ROIs, saved images, what format.
- **Solving approach (UI/script):** do you want to go click-by-click via user interface or do you want scripts to run in the background for you?
- **Plugin preference:** are there specific plugin/models you want to use.

If you're unsure, tell me what task do you want to solve and provide one representative image."""

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
        try:
            # Guard: C++ widget may have been deleted during shutdown
            self._label.isVisible()
        except RuntimeError:
            return
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
        self._msg_layout.setAlignment(Qt.AlignTop)
        self._last_bubble = None

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)
 
    def resizeEvent(self, event):
        super().resizeEvent(event)
        vp_w = self._scroll.viewport().width()
        if vp_w > 0:
            self._container.setMaximumWidth(vp_w)
 
    def scroll_to_bottom(self, widget: "MessageBubble | None" = None):
        """Scroll to make `widget` visible, or to the last bubble if None.

        Uses ensureWidgetVisible so we land on actual content rather than the
        empty space Qt leaves below AlignTop layouts in a resizable scroll area.
        The zero-delay timer defers the call until after Qt's layout pass.
        """
        def _do_scroll():
            target = widget or self._last_bubble
            if target is not None:
                try:
                    self._scroll.ensureWidgetVisible(target)
                except RuntimeError:
                    pass  # widget deleted during shutdown
        QTimer.singleShot(0, _do_scroll)

    def add_message(self, role: str, text: str, *, auto_scroll: bool = True) -> MessageBubble:
        bubble = MessageBubble(text, role)
        self._msg_layout.addWidget(bubble)
        self._last_bubble = bubble
        if auto_scroll:
            self.scroll_to_bottom(bubble)
        return bubble
 
    def clear_messages(self):
        self._last_bubble = None
        while self._msg_layout.count() > 0:
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class SubagentHeartbeatTimer:
    """Cycles through plausible sub-step messages while a subagent tool is running.
 
    Because subagents are called synchronously (no streaming), we can't receive
    their internal tool calls.  This timer fires every INTERVAL ms and updates
    the status bubble with the next message in the sequence, giving the user
    visual evidence that work is happening.
    """
 
    INTERVAL = 5000   # ms between message rotations
 
 
    # Messages shown while each long-running subagent is in flight.
    # Each list is cycled in order and then repeated.
    STEPS: dict[str, list[str]] = {
        "imagej_coder": [
            "Bio-Imaging Specialist is checking past lessons learned…",
            "Bio-Imaging Specialist is searching ImageJ documentation…",
            "Bio-Imaging Specialist is verifying the Java API…",
            "Bio-Imaging Specialist is writing the Groovy script…",
            "Bio-Imaging Specialist is adding error handling…",
            "Bio-Imaging Specialist is saving the script…",
        ],
        "imagej_debugger": [
            "Debugger is reading the faulty script…",
            "Debugger is checking previous failure history…",
            "Debugger is inspecting the Java API for the correct signature…",
            "Debugger is applying the minimal fix…",
            "Debugger is saving the repaired script…",
        ],
        "python_data_analyst": [
            "Data Scientist is inspecting the CSV structure…",
            "Data Scientist is checking previous script versions…",
            "Data Scientist is selecting appropriate statistical tests…",
            "Data Scientist is writing the analysis script…",
            "Data Scientist is adding publication-quality plot settings…",
            "Data Scientist is saving the script…",
        ],
        # "vlm_judge": [  # VLM disabled
        #     "Vision AI is capturing the ImageJ window…",
        #     "Vision AI is building the comparison panel…",
        #     "Vision AI is sending the image for analysis…",
        #     "Vision AI is evaluating against expected output…",
        #     "Vision AI is compiling the verdict…",
        # ],
        "qa_reporter": [
            "QA Agent is scanning the project folder…",
            "QA Agent is reading script documentation…",
            "QA Agent is reading CSV output headers…",
            "QA Agent is evaluating workflow checklist items…",
            "QA Agent is evaluating image publishing checklist items…",
            "QA Agent is writing the QA report…",
        ],
    }
 
    def __init__(self, tool_name: str, set_status_fn):
        """
        Args:
            tool_name:     one of the keys in STEPS
            set_status_fn: callable(str) — updates the status bubble
        """
        self._steps    = self.STEPS.get(tool_name, [f"Running {tool_name}…"])
        self._set      = set_status_fn
        self._idx      = 0
        self._timer    = QTimer()
        self._timer.setInterval(self.INTERVAL)
        self._timer.timeout.connect(self._tick)
 
    def start(self):
        """Show the first message immediately, then start rotating."""
        self._idx = 0
        self._set(self._steps[0])
        if len(self._steps) > 1:
            self._timer.start()
 
    def stop(self):
        self._timer.stop()
 
    def _tick(self):
        self._idx = (self._idx + 1) % len(self._steps)
        self._set(self._steps[self._idx])

# ---------------------------------------------------------------------------
# Metrics panel
# ---------------------------------------------------------------------------

class MetricsPanelWidget(QWidget):
    """Shows token/cost/tool metrics for the active conversation."""

    qa_toggled = Signal(bool)

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

        self._btn_report = QPushButton("Report Issue")
        self._btn_report.setStyleSheet(
            "padding: 4px; background-color: #e74c3c; "
            "color: white; border-radius: 3px; font-size: 11px;"
        )
        root.addWidget(self._btn_report)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep2)

        agent_box = QGroupBox("Agent Options")
        agent_layout = QVBoxLayout(agent_box)
        agent_layout.setSpacing(4)
        self._qa_checkbox = QCheckBox("QA Agent")
        self._qa_checkbox.setChecked(False)
        self._qa_checkbox.setToolTip(
            "Enable the QA Reporter agent.\n"
            "Runs a full audit at project end, checks for publication readiness, and generates\n"
            "QA_Checklist_Report.md. Off by default, \n"
            "as it adds significant cost per workflow."
        )
        self._qa_checkbox.stateChanged.connect(
            lambda _: self.qa_toggled.emit(self._qa_checkbox.isChecked())
        )
        agent_layout.addWidget(self._qa_checkbox)
        root.addWidget(agent_box)

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
# Email helper
# ---------------------------------------------------------------------------

_REPORT_EMAIL = "agentj.help@gmail.com"

def _send_report_email(subject: str, body: str, attachments: list[tuple[str, bytes]]) -> None:
    """Send a report email from agentj.help@gmail.com to itself via Gmail SMTP.

    Raises RuntimeError if GMAIL_APP_PASSWORD is not set or sending fails.
    attachments: list of (filename, bytes) pairs.
    """
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not app_password:
        raise RuntimeError(
            "GMAIL_APP_PASSWORD is not set in your .env file.\n"
            "Generate an App Password at:\n"
            "  Google Account → Security → 2-Step Verification → App Passwords"
        )

    msg = MIMEMultipart()
    msg["From"] = _REPORT_EMAIL
    msg["To"] = _REPORT_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    for filename, data in attachments:
        part = MIMEApplication(data, Name=filename)
        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        msg.attach(part)

    ctx = ssl.create_default_context()
    import socket

    # Resolve to IPv4 — Docker containers often lack IPv6 (errno 97).
    smtp_ip = socket.getaddrinfo("smtp.gmail.com", 587, socket.AF_INET)[0][4][0]
    smtp_ip_465 = socket.getaddrinfo("smtp.gmail.com", 465, socket.AF_INET)[0][4][0]

    raw = msg.as_bytes()
    try:
        # Port 587 with STARTTLS (preferred)
        with smtplib.SMTP(smtp_ip, 587, timeout=15) as smtp:
            smtp._host = "smtp.gmail.com"  # starttls verifies against hostname, not IP
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()
            smtp.login(_REPORT_EMAIL, app_password)
            smtp.sendmail(_REPORT_EMAIL, _REPORT_EMAIL, raw)
    except (OSError, smtplib.SMTPException):
        # Port 465 implicit TLS fallback (some networks block 587)
        with smtplib.SMTP_SSL(smtp_ip_465, 465, context=ctx, timeout=15) as smtp:
            smtp._host = "smtp.gmail.com"
            smtp.login(_REPORT_EMAIL, app_password)
            smtp.sendmail(_REPORT_EMAIL, _REPORT_EMAIL, raw)


# ---------------------------------------------------------------------------
# Feedback / Error-Report dialog
# ---------------------------------------------------------------------------

class FeedbackDialog(QDialog):
    """Modal dialog for collecting user feedback and exporting an error report."""

    def __init__(self, tracker_cb, history_manager, current_thread_id, parent=None):
        super().__init__(parent)
        self._tracker_cb = tracker_cb
        self._history_manager   = history_manager
        self._current_thread_id = current_thread_id
        self.setWindowTitle("Report Issue")
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        desc_label = QLabel(
            "<b>Describe the problem</b><br>"
            "<span style='color:#555; font-size:11px;'>"
            "What did you ask the agent to do, and what went wrong?</span>"
        )
        desc_label.setTextFormat(Qt.RichText)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        self._text_edit = QPlainTextEdit()
        self._text_edit.setPlaceholderText(
            "e.g. 'The script ran but measured 0 cells on my fluorescence image.'"
        )
        self._text_edit.setFixedHeight(120)
        layout.addWidget(self._text_edit)

        options_box = QGroupBox("Export options")
        options_layout = QVBoxLayout(options_box)
        options_layout.setSpacing(4)
        self._chk_usage = QCheckBox("Include usage stats (token counts, cost)")
        self._chk_usage.setChecked(True)
        options_layout.addWidget(self._chk_usage)
        layout.addWidget(options_box)

        conv_box = QGroupBox("Include conversations")
        conv_layout = QVBoxLayout(conv_box)
        conv_layout.setSpacing(2)
        self._conv_list = QListWidget()
        self._conv_list.setSelectionMode(QListWidget.NoSelection)
        threads = self._history_manager.list_threads()
        for thread_id, meta in threads:
            title   = meta.get("title", thread_id)
            display = f"{title[:45]}\u2026" if len(title) > 45 else title
            item = QListWidgetItem(display)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if thread_id == self._current_thread_id else Qt.Unchecked
            )
            item.setData(Qt.UserRole, thread_id)
            self._conv_list.addItem(item)
        self._conv_list.setFixedHeight(min(len(threads), 6) * 22 + 6)
        conv_layout.addWidget(self._conv_list)
        sel_row = QHBoxLayout()
        btn_all  = QPushButton("Select all")
        btn_none = QPushButton("Select none")
        btn_all.setFixedHeight(20)
        btn_none.setFixedHeight(20)
        btn_all.clicked.connect(lambda: self._set_all_checks(Qt.Checked))
        btn_none.clicked.connect(lambda: self._set_all_checks(Qt.Unchecked))
        sel_row.addWidget(btn_all)
        sel_row.addWidget(btn_none)
        conv_layout.addLayout(sel_row)
        layout.addWidget(conv_box)

        info = QLabel(
            "<span style='color:#888; font-size:10px;'>"
            "The report includes: error details and script code from selected conversation, "
            "your description, and basic system info (OS, Python version). "
            "No image data or raw file contents are included. Multiple conversations are exported as a ZIP.</span>"
        )
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_box = QDialogButtonBox()
        btn_box.addButton("Send Report\u2026", QDialogButtonBox.AcceptRole)
        btn_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        btn_box.accepted.connect(self._on_export)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _set_all_checks(self, state):
        for i in range(self._conv_list.count()):
            self._conv_list.item(i).setCheckState(state)

    def _on_export(self):

        selected = []
        for i in range(self._conv_list.count()):
            item = self._conv_list.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))

        if not selected:
            QMessageBox.warning(self, "Nothing selected",
                                "Please select at least one conversation.")
            return
        
        self._tracker_cb.set_user_feedback(self._text_edit.toPlainText().strip())

        include_usage = self._chk_usage.isChecked()

        import io, zipfile as _zipfile
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        feedback_text = self._text_edit.toPlainText().strip()
        try:
            if len(selected) == 1:
                report = self._tracker_cb.get_error_report_for_thread(
                    selected[0], include_usage_stats=include_usage
                )
                fname = f"report_{selected[0][:8]}_{timestamp}.json"
                attachments = [(fname, json.dumps(report, indent=2, ensure_ascii=False).encode())]
            else:
                buf = io.BytesIO()
                with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
                    for thread_id in selected:
                        report = self._tracker_cb.get_error_report_for_thread(
                            thread_id, include_usage_stats=include_usage
                        )
                        zf.writestr(f"report_{thread_id[:8]}.json",
                                    json.dumps(report, indent=2, ensure_ascii=False))
                fname = f"imagentj_issue_{timestamp}.zip"
                attachments = [(fname, buf.getvalue())]

            subject = f"[ImagentJ] Issue Report — {timestamp}"
            body = f"User feedback:\n{feedback_text or '(none provided)'}\n\nAttached: {len(selected)} conversation(s)."
            _send_report_email(subject, body, attachments)
            QMessageBox.information(self, "Report Sent",
                f"Issue report sent to {_REPORT_EMAIL}.\n\nThank you for the feedback!")
            self.accept()
        except Exception as e:
            log.exception(f"Failed to send issue report: {e}")
            reply = QMessageBox.warning(
                self, "Send Failed",
                f"Could not send the report by email:\n{e}\n\n"
                "Would you like to save it to a file instead?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                default_name = os.path.expanduser(
                    f"~/imagentj_issue_{time.strftime('%Y%m%d_%H%M%S')}"
                    f"{'zip' if len(attachments) == 1 and attachments[0][0].endswith('.zip') else 'json'}"
                )
                path, _ = QFileDialog.getSaveFileName(
                    self, "Save Issue Report", default_name,
                    "All files (*)",
                )
                if path:
                    with open(path, "wb") as f:
                        f.write(attachments[0][1])
                    QMessageBox.information(self, "Report Saved",
                        f"Report saved to:\n{path}\n\nPlease send it manually to {_REPORT_EMAIL}.")
                    self.accept()
        


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
            stop_signal.clear()
            self._run_prompt(prompt)

    def _run_prompt(self, user_input: str):
        try:
            config = {
                "configurable": {"thread_id": self.thread_id},
                "callbacks":    [self.tracker_callback],
            }
            gen = self.supervisor.stream(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
                stream_mode="updates",
            )
            for event in gen:
                if self._stop_requested:
                    gen.close()
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
        stop_signal.request_stop()
        # Kill any running subprocesses immediately (Python scripts, etc.)
        killed = kill_running_processes()
        if killed:
            log.info(f"Stop: killed {killed} running subprocess(es)")


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
        self._status_bubble: MessageBubble | None = None
        self._agent_had_error: bool = False

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
        chat_layout.addWidget(self.input_line,         stretch=1)
        chat_layout.addLayout(btn_row)
        chat_layout.addWidget(self.status_label,       stretch=0)
        chat_widget.setLayout(chat_layout)

        # RIGHT: metrics panel
        self.metrics_panel = MetricsPanelWidget()
        self.metrics_panel.setMinimumWidth(190)
        self.metrics_panel.setMaximumWidth(250)
        self.metrics_panel._btn_save.clicked.connect(self._save_report)
        self.metrics_panel._btn_report.clicked.connect(self._open_feedback_dialog)
        self.metrics_panel.qa_toggled.connect(self._on_qa_toggled)

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

        self._current_status_bubble = None
        self._active_tasks = {} # Tracks tool_id -> status_text

        self._init_session()

        if is_benchmark_mode():       
            setup_benchmark_gui(self)

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
        self._status_bubble       = None
        self._tracker_cb.switch_thread(thread_id)

        self.chat_scroll.clear_messages()
        self.chat_scroll.add_message('ai', intro_message)

        self.history_panel.populate(self.history_manager.list_threads())
        self.history_panel.set_active(thread_id)

        if is_benchmark_mode():      
            setup_benchmark_gui(self)

    def _load_thread(self, thread_id: str):
        self.current_thread_id = thread_id
        self.worker.thread_id  = thread_id
        self._is_new_thread    = False
        self._current_ai_bubble  = None
        self._ai_response_buffer = ""
        self._status_bubble      = None
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
                    self.chat_scroll.add_message('user', content, auto_scroll=False)
                elif msg_type == 'ai' and content and not tool_calls:
                    self.chat_scroll.add_message('ai', content, auto_scroll=False)

            # Scroll to the last bubble once all messages are laid out
            self.chat_scroll.scroll_to_bottom()

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
        from PySide6.QtWidgets import QFileDialog
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


    def _open_feedback_dialog(self):
        dlg = FeedbackDialog(
            self._tracker_cb,
            self.history_manager,
            self.current_thread_id,
            parent=self,
        )
        dlg.exec()

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
    # Agent options
    # ------------------------------------------------------------------

    def _on_qa_toggled(self, enabled: bool):
        if self._agent_is_busy():
            # Revert the checkbox — can't reinit while agent is running
            self.metrics_panel._qa_checkbox.blockSignals(True)
            self.metrics_panel._qa_checkbox.setChecked(not enabled)
            self.metrics_panel._qa_checkbox.blockSignals(False)
            self.set_status("Cannot change QA Agent setting while agent is running.")
            return
        (self.supervisor,
         self.checkpointer,
         self._metrics,
         self._metrics_bridge,
         self._tracker_cb) = init_agent(enable_qa=enabled)
        self.worker.supervisor = self.supervisor
        self._metrics_bridge.updated.connect(self.metrics_panel.update_metrics)
        #self.set_status(f"QA Agent {'enabled' if enabled else 'disabled'}.")


    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def on_stop(self):
        if hasattr(self, 'worker') and self.worker:
            self._stop_heartbeat()      # kill rotating prompts immediately
            self._status_bubble = None  # next set_status creates a fresh line
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
        self._status_bubble      = None
        if not self._agent_had_error:
            self.set_status("Ready")
        self._agent_had_error = False
        self.set_ui_busy(False)

    def on_agent_error(self, msg: str):
        log.error(f"Agent error: {msg}")
        self._stop_heartbeat()
        self._agent_had_error    = True
        self._current_ai_bubble  = None
        self._ai_response_buffer = ""
        self._status_bubble      = None
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
        self._agent_had_error    = False

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
    # ------------------------------------------------------------------
    # Event handler (streaming from agent)
    # ------------------------------------------------------------------
    

    
        
        
    def _stop_heartbeat(self):
        """Stop and discard any running heartbeat timer."""
        if getattr(self, "_heartbeat", None) is not None:
            self._heartbeat.stop()
            self._heartbeat = None
            
    
    
    def handle_event(self, event: dict):  # method of ImageJAgentGUI

        # These are the subagent tool names that run for a long time with no streaming.
        _SUBAGENT_TOOLS = {"imagej_coder", "imagej_debugger",
                        "python_data_analyst", "qa_reporter"}  # vlm_judge disabled

        # Non-subagent tool start messages (short, fire-and-forget tools)
        _TOOL_START = {
            "execute_script":            "Executing script on your images (may take a minute)…",
            "rag_retrieve_docs":         "Searching ImageJ documentation…",
            "rag_retrieve_mistakes":     "Checking past lessons learned…",
            "inspect_all_ui_windows":    "Listing open ImageJ windows…",
            "capture_plugin_dialog":     "Reading plugin dialog (taking screenshot)…",
            "extract_image_metadata":    "Reading image metadata & calibration…",
            "setup_analysis_workspace":  "Creating project workspace…",
            "search_fiji_plugins":       "Searching Fiji plugin registry…",
            "install_fiji_plugin":       "Installing Fiji plugin…",
            "internet_search":           "Searching the web…",
            "inspect_folder_tree":       "Inspecting project folder…",
            "smart_file_reader":         "Reading file…",
            "inspect_csv_header":        "Reading CSV structure…",
            "save_coding_experience":    "Saving lesson to experience database…",
            "save_markdown":             "Writing markdown document…",
            "save_reusable_script":      "Saving reusable script to library…",
            "mkdir_copy":                "Copying files…",
            "get_script_info":           "Reading script documentation…",
        }

        _TOOL_DONE = {
            "imagej_coder":              "Bio-Imaging Specialist finished writing the script.",
            "imagej_debugger":           "Debugger finished — script repaired.",
            "python_data_analyst":       "Data Scientist finished.",
            "execute_script":            "Script execution complete.",
            "qa_reporter":               "QA report generated.",
            # "vlm_judge":              "Vision AI inspection complete.",  # VLM disabled
            "setup_analysis_workspace":  "Project workspace ready.",
            "install_fiji_plugin":       "Plugin installed — please restart Fiji.",
        }
    
        # ── Helper: upsert the single status line ────────────────────────────────
        def set_status(text: str):
            if self._status_bubble is None:
                self._status_bubble = self.chat_scroll.add_message('system', text)
            else:
                self._status_bubble.update_text(text)
    
        for node_name, node_data in event.items():
            if "Middleware" in node_name:
                continue
            if node_name == "tools":
                continue  # handled separately below

            messages = node_data.get("messages", []) if isinstance(node_data, dict) else []

            for msg in messages:
                content    = getattr(msg, "content", "") or ""
                tool_calls = getattr(msg, "tool_calls", None) or []
                msg_type   = getattr(msg, "type", "") or ""

                # skip human / tool-result messages
                if msg_type in ("human", "tool"):
                    continue

                # ── AI text (supervisor speaking to user) ─────────────────────
                # Show content whenever present — including when tool_calls is also
                # set (the supervisor's MANDATORY NARRATION comes through as a
                # message with both content and tool_calls on the same object).
                if content:
                    self._stop_heartbeat()
                    self._status_bubble = None

                    if self._current_ai_bubble is None:
                        self._ai_response_buffer = content
                        self._current_ai_bubble  = self.chat_scroll.add_message('ai', content)
                    else:
                        self._ai_response_buffer += content
                        self._current_ai_bubble.update_text(self._ai_response_buffer)

                # ── Tool call announcements ───────────────────────────────────
                if tool_calls:
                    self._current_ai_bubble = None
                    for tc in tool_calls:
                        name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                        args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})

                        # routing announcement for deepagents "task" tool
                        if name == "task":
                            agent_type = args.get("subagent_type", "Specialist")
                            desc       = args.get("description", "")
                            short_desc = (desc[:120] + "…") if len(desc) > 120 else desc
                            set_status(f"Routing to {agent_type}: {short_desc}")
                        elif name in _SUBAGENT_TOOLS:
                            self._stop_heartbeat()
                            self._heartbeat = SubagentHeartbeatTimer(name, set_status)
                            self._heartbeat.start()
                        else:
                            status = _TOOL_START.get(name) or f"Running {name.replace('_', ' ').title()}…"
                            set_status(status)
    
        # ── Tool completion ───────────────────────────────────────────────────────
        if "tools" in event:
            for tool_msg in event["tools"].get("messages", []):
                name    = getattr(tool_msg, "name", "")
                content = getattr(tool_msg, "content", "")
    
                if name == "setup_analysis_workspace":
                    self._tracker_cb.notify_workspace_created(str(content))
    
                # Always stop the heartbeat when any tool (subagent or not) finishes
                if name in _SUBAGENT_TOOLS:
                    self._stop_heartbeat()
    
                done_text = _TOOL_DONE.get(name)
                if done_text:
                    set_status(done_text)
                elif name and name != "task":
                    set_status(f"{name.replace('_', ' ').title()} — done.")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageJAgentGUI()
    window.show()
    sys.exit(app.exec())