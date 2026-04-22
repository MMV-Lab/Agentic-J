#!/usr/bin/env python3
"""
ImagentJ API Key Setup Wizard.

Shown on first startup when no API key is configured.
Writes to /app/data/api_keys.env (sourced by docker-entrypoint.sh).
"""

import sys
import os
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QButtonGroup,
    QRadioButton, QFrame, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import re
import shlex


OPENAI_RE = re.compile(r"^sk-[A-Za-z0-9_\-]{20,200}$")
OPENROUTER_RE = re.compile(r"^sk-or-v1-[A-Za-z0-9_\-]{20,200}$")


def validate_key(key: str, is_openai: bool) -> bool:
    # Block structural / dangerous chars first
    if any(c in key for c in ['\n', '\r', '\0']):
        return False

    # Provider-specific format
    if is_openai:
        return bool(OPENAI_RE.fullmatch(key))
    else:
        return bool(OPENROUTER_RE.fullmatch(key))

API_KEYS_FILE = "/home/imagentj/api_keys.env"


class SetupWizard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ImagentJ Setup")
        self.setFixedSize(520, 360)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)

        # ── Root layout ──────────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        # ── Title ────────────────────────────────────────────────────────────
        title = QLabel("Welcome to ImagentJ")
        title_font = QFont()
        title_font.setPointSize(17)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        subtitle = QLabel(
            "To get started, enter your API key below.\n"
            "It will be saved to <code>/home/imagentj/api_keys.env</code> "
            "and remembered across restarts."
        )
        subtitle.setTextFormat(Qt.RichText)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #555; font-size: 12px;")
        root.addWidget(subtitle)

        # ── Separator ────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #ddd;")
        root.addWidget(sep)

        # ── Provider selection ────────────────────────────────────────────────
        provider_row = QHBoxLayout()
        provider_label = QLabel("Provider:")
        provider_label.setFixedWidth(70)
        provider_row.addWidget(provider_label)

        self.radio_openai = QRadioButton("OpenAI")
        self.radio_openrouter = QRadioButton("OpenRouter")
        self.radio_openai.setChecked(True)

        self._provider_group = QButtonGroup(self)
        self._provider_group.addButton(self.radio_openai, 0)
        self._provider_group.addButton(self.radio_openrouter, 1)
        self._provider_group.buttonClicked.connect(self._on_provider_changed)

        provider_row.addWidget(self.radio_openai)
        provider_row.addWidget(self.radio_openrouter)
        provider_row.addStretch()
        root.addLayout(provider_row)

        # ── Key input ────────────────────────────────────────────────────────
        key_row = QHBoxLayout()
        key_label = QLabel("API Key:")
        key_label.setFixedWidth(70)
        key_row.addWidget(key_label)

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.Password)
        self.key_input.setPlaceholderText("sk-proj-...")
        self.key_input.setMinimumHeight(34)
        self.key_input.setStyleSheet(
            "font-family: monospace; font-size: 12px; padding: 4px 8px;"
        )
        self.key_input.returnPressed.connect(self._on_submit)
        key_row.addWidget(self.key_input)

        self.toggle_btn = QPushButton("Show")
        self.toggle_btn.setFixedWidth(54)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setStyleSheet("padding: 4px;")
        self.toggle_btn.toggled.connect(self._toggle_visibility)
        key_row.addWidget(self.toggle_btn)

        root.addLayout(key_row)

        # ── Hint label ───────────────────────────────────────────────────────
        self.hint_label = QLabel(
            "Get your key at platform.openai.com/api-keys"
        )
        self.hint_label.setAlignment(Qt.AlignRight)
        self.hint_label.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self.hint_label)

        # ── Spacer + button ──────────────────────────────────────────────────
        root.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.start_btn = QPushButton("Start ImagentJ")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setMinimumWidth(160)
        self.start_btn.setStyleSheet(
            "background-color: #3498db; color: white; font-weight: bold; "
            "font-size: 13px; border: none; border-radius: 5px;"
        )
        self.start_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(self.start_btn)
        root.addLayout(btn_row)

        self.setStyleSheet("QWidget { font-size: 13px; }")

    # ── Slots ────────────────────────────────────────────────────────────────

    def _on_provider_changed(self, _button):
        if self.radio_openai.isChecked():
            self.key_input.setPlaceholderText("sk-proj-...")
            self.hint_label.setText("Get your key at platform.openai.com/api-keys")
        else:
            self.key_input.setPlaceholderText("sk-or-v1-...")
            self.hint_label.setText("Get your key at openrouter.ai/keys")

    def _toggle_visibility(self, checked: bool):
        if checked:
            self.key_input.setEchoMode(QLineEdit.Normal)
            self.toggle_btn.setText("Hide")
        else:
            self.key_input.setEchoMode(QLineEdit.Password)
            self.toggle_btn.setText("Show")

    def _on_submit(self):
        key = self.key_input.text().strip()

        if not key:
            QMessageBox.warning(
                self, "Missing Key",
                "Please enter your API key before continuing."
            )
            self.key_input.setFocus()
            return

        is_openai = self.radio_openai.isChecked()

        if not validate_key(key, is_openai):
            QMessageBox.warning(
                self,
                "Invalid Key",
                "The API key format is invalid for the selected provider."
            )
            self.key_input.setFocus()
            return
                
        env_var = "OPENAI_API_KEY" if self.radio_openai.isChecked() else "OPEN_ROUTER_API_KEY"
        safe_key = shlex.quote(key)
        new_line = f'export {env_var}={safe_key}\n'

        try:
            os.makedirs(os.path.dirname(API_KEYS_FILE), exist_ok=True)

            # Preserve lines for the other provider if the file already exists
            existing_lines: list[str] = []
            if os.path.exists(API_KEYS_FILE):
                with open(API_KEYS_FILE, "r") as fh:
                    for line in fh:
                        if not line.strip().startswith(f"export {env_var}="):
                            existing_lines.append(line)

            with open(API_KEYS_FILE, "w") as fh:
                for line in existing_lines:
                    fh.write(line)
                fh.write(new_line)

        except OSError as exc:
            QMessageBox.critical(
                self, "Write Error",
                f"Could not write to {API_KEYS_FILE}:\n{exc}\n\n",
            )
            return

        self.close()


def main():
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":1"

    app = QApplication(sys.argv)
    wizard = SetupWizard()
    wizard.show()
    wizard.activateWindow()
    wizard.raise_()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
