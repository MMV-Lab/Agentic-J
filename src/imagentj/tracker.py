"""
tracker.py  –  Per-conversation token, timing, cost & tool-call metrics.

Storage layout (mirrors ChatHistoryManager):
    /app/data/chats/<thread_id>/usage_stats.json   ← one file per conversation
    /app/data/projects/<name>/logs/usage_log.json  ← auto-created on workspace setup

The metrics panel always shows the CURRENT conversation only.
On thread switch the GUI calls:
    tracker.switch_thread(thread_id)
which saves the current conversation, resets UsageMetrics, and pre-loads
the new conversation's saved totals — so the panel updates instantly.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from PySide6.QtCore import QObject, Signal
import logging
log = logging.getLogger("imagentj")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHATS_DIR = Path(os.environ.get("CHAT_DATA_PATH", "/app/data/chats"))

PRICE_TABLE: dict[str, tuple[float, float]] = {
    # model-name-substring        input   output
    "gpt-4o":                    (2.50,  10.00),
    "gpt-4o-mini":               (0.15,   0.60),
    "gpt-4.1":                   (2.00,   8.00),
    "claude-opus-4":             (15.00,  75.00),
    "claude-sonnet-4":           (3.00,  15.00),
    "claude-haiku-4":            (0.80,   4.00),
    "default":                   (1.00,   3.00),   # fallback
    "gemini-3-flash-preview":    (0.50,   3.00),   
    "kimi-k2.5":                 (0.45,   2.25),
    "claude-opus-4.6":           (10.00,  37.50),
    "deepseek-v3.2":             (0.25,   0.40),
    "openai/gpt-5.2":            (1.75,   14.00),
    "anthropic/claude-haiku-4.5":(1.00,   5.00),
    "openai/gpt-5.3-codex":      (1.75,   14.00),
    "qwen/qwen3-235b-a22b-2507": (0.071,   0.10),
    "moonshotai/kimi-k2.5":      (0.45,   2.25),
    "z-ai/glm-5":                (0.95,   2.55),
    "mistralai/mistral-small-3.2-24b-instruct": (0.075, 0.2),
}

def _price_for_model(model_name: str) -> tuple[float, float]:
    lower = model_name.lower()
    for key, prices in PRICE_TABLE.items():
        if key != "default" and key in lower:
            return prices
    return PRICE_TABLE["default"]


# ---------------------------------------------------------------------------
# Soft-error detection (execution tools only)
# ---------------------------------------------------------------------------

_SOFT_ERROR_RE = re.compile(
    r"\b(error|exception|warning|failed|failure|"
    r"missingmethodexception|missingmethod|no such method|"
    r"groovyruntimeexception|scriptexception|"
    r"could not|unable to|traceback|illegalargument|"
    r"nullpointerexception|indexoutofbounds)\b",
    re.IGNORECASE,
)
_EXECUTION_TOOLS = {"execute_script", "run_script_safe", "run_python_code"}


# ---------------------------------------------------------------------------
# Per-query record
# ---------------------------------------------------------------------------

@dataclass
class QueryRecord:
    timestamp:             str   = ""
    thread_id:             str   = ""
    prompt_preview:        str   = ""
    model:                 str   = ""
    thinking_seconds:      float = 0.0
    input_tokens:          int   = 0
    output_tokens:         int   = 0
    total_tokens:          int   = 0
    cost_usd:              float = 0.0
    tool_calls:            int   = 0
    failed_tool_calls:     int   = 0
    soft_error_tool_calls: int   = 0

    def to_dict(self) -> dict:
        return {
            "timestamp":             self.timestamp,
            "thread_id":             self.thread_id,
            "prompt_preview":        self.prompt_preview,
            "model":                 self.model,
            "thinking_seconds":      round(self.thinking_seconds, 2),
            "input_tokens":          self.input_tokens,
            "output_tokens":         self.output_tokens,
            "total_tokens":          self.total_tokens,
            "cost_usd":              round(self.cost_usd, 6),
            "tool_calls":            self.tool_calls,
            "failed_tool_calls":     self.failed_tool_calls,
            "soft_error_tool_calls": self.soft_error_tool_calls,
        }


# ---------------------------------------------------------------------------
# Cumulative metrics — always reflects the CURRENT conversation
# ---------------------------------------------------------------------------

@dataclass
class UsageMetrics:
    input_tokens:          int   = 0
    output_tokens:         int   = 0
    thinking_seconds:      float = 0.0
    cost_usd:              float = 0.0
    tool_calls:            int   = 0
    failed_tool_calls:     int   = 0
    soft_error_tool_calls: int   = 0

    _thinking_start: float         = field(default=0.0,  repr=False, compare=False)
    _is_thinking:    bool          = field(default=False, repr=False, compare=False)
    _lock:           threading.RLock = field(
        default_factory=threading.RLock, repr=False, compare=False
    )

    def start_thinking(self):
        with self._lock:
            self._thinking_start = time.monotonic()
            self._is_thinking    = True

    def stop_thinking(self) -> float:
        with self._lock:
            if not self._is_thinking:
                return 0.0
            elapsed = time.monotonic() - self._thinking_start
            self.thinking_seconds += elapsed
            self._is_thinking = False
            return elapsed

    def live_thinking_seconds(self) -> float:
        extra = (time.monotonic() - self._thinking_start) if self._is_thinking else 0.0
        return self.thinking_seconds + extra

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "input_tokens":          self.input_tokens,
                "output_tokens":         self.output_tokens,
                "total_tokens":          self.total_tokens,
                "thinking_seconds":      round(self.live_thinking_seconds(), 1),
                "cost_usd":              round(self.cost_usd, 6),
                "tool_calls":            self.tool_calls,
                "failed_tool_calls":     self.failed_tool_calls,
                "soft_error_tool_calls": self.soft_error_tool_calls,
            }

    def reset(self):
        with self._lock:
            self.input_tokens          = 0
            self.output_tokens         = 0
            self.thinking_seconds      = 0.0
            self._thinking_start       = 0.0
            self._is_thinking          = False
            self.cost_usd              = 0.0
            self.tool_calls            = 0
            self.failed_tool_calls     = 0
            self.soft_error_tool_calls = 0

    def load_from_totals(self, totals: dict):
        """Pre-populate from a saved totals dict on thread switch."""
        with self._lock:
            self.input_tokens          = totals.get("input_tokens",          0)
            self.output_tokens         = totals.get("output_tokens",         0)
            self.thinking_seconds      = totals.get("thinking_seconds",      0.0)
            self.cost_usd              = totals.get("cost_usd",              0.0)
            self.tool_calls            = totals.get("tool_calls",            0)
            self.failed_tool_calls     = totals.get("failed_tool_calls",     0)
            self.soft_error_tool_calls = totals.get("soft_error_tool_calls", 0)


# ---------------------------------------------------------------------------
# Qt signal bridge
# ---------------------------------------------------------------------------

class MetricsSignalBridge(QObject):
    updated = Signal(dict)   # full snapshot → MetricsPanelWidget.update_metrics


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_json(path: Path, data: dict):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        pass  # never let I/O crash the agent


# ---------------------------------------------------------------------------
# Conversation-scoped logger
# ---------------------------------------------------------------------------

class ConversationLogger:
    """
    Writes  /app/data/chats/<thread_id>/usage_stats.json
    and (once a project workspace exists)
            /app/data/projects/<name>/logs/usage_log.json
    """

    def __init__(self, chats_dir: Path = CHATS_DIR):
        self._chats_dir         = chats_dir
        self._thread_id:    str         = ""
        self._project_log:  Path | None = None
        self._project_name: str         = ""

    # ── per-conversation file ─────────────────────────────────────────────

    def _conv_path(self, thread_id: str | None = None) -> Path:
        tid = thread_id or self._thread_id
        return self._chats_dir / tid / "usage_stats.json"

    def set_thread(self, thread_id: str):
        # Always reset — prevents bleed between conversations
        self._project_log  = None
        self._project_name = ""
        self._thread_id    = thread_id

        path = self._conv_path()
        if not path.exists():
            self._write_conv({
                "thread_id": thread_id,
                "created":   time.strftime("%Y-%m-%dT%H:%M:%S"),
                "queries":   [],
                "totals":    {},
            })
        else:
            conv_data  = _read_json(path)
            saved_root = conv_data.get("project_root")
            if saved_root:
                root_path = Path(saved_root)
                if root_path.exists():
                    self._project_log  = root_path / "logs" / "usage_log.json"
                    self._project_name = root_path.name
                    log.debug(f"Restored project log: {self._project_log}")
                    self._sync_project()  # immediate sync on restore
                else:
                    conv_data.pop("project_root", None)
                    self._write_conv(conv_data)

    def load_totals(self, thread_id: str) -> dict:
        """Return saved cumulative totals for a thread (empty dict if none)."""
        data = _read_json(self._conv_path(thread_id))
        return data.get("totals", {})

    def append_query(self, record: QueryRecord, snapshot: dict):
        if not self._thread_id:
            return
        data = _read_json(self._conv_path())
        data.setdefault("queries", []).append(record.to_dict())
        qs = data["queries"]
        data["totals"] = {
            "query_count":           len(qs),
            "input_tokens":          sum(q["input_tokens"]           for q in qs),
            "output_tokens":         sum(q["output_tokens"]          for q in qs),
            "total_tokens":          sum(q["total_tokens"]           for q in qs),
            "thinking_seconds":      round(sum(q["thinking_seconds"] for q in qs), 2),
            "cost_usd":              round(sum(q["cost_usd"]         for q in qs), 6),
            "tool_calls":            sum(q["tool_calls"]             for q in qs),
            "failed_tool_calls":     sum(q["failed_tool_calls"]      for q in qs),
            "soft_error_tool_calls": sum(q["soft_error_tool_calls"]  for q in qs),
        }
        self._write_conv(data)  

    # ── project log ───────────────────────────────────────────────────────

    def set_project_path(self, project_root: Path, project_name: str):
        if self._project_log is not None:
            return
        self._project_log  = project_root / "logs" / "usage_log.json"
        self._project_name = project_name

        # Persist so it survives restarts
        conv_data = _read_json(self._conv_path())
        conv_data["project_root"] = str(project_root)
        self._write_conv(conv_data)   # also triggers _sync_project
        log.debug(f"Project log initialised at: {self._project_log}")

    def _append_to_project(self, record: QueryRecord):
        if not self._project_log:
            return
        # Just mirror the full conversation file — always in sync, no separate logic
        conv_data = _read_json(self._conv_path())
        _write_json(self._project_log, conv_data)

    # ── export ────────────────────────────────────────────────────────────

    def build_report(self, thread_id: str | None = None) -> dict:
        conv    = _read_json(self._conv_path(thread_id or self._thread_id))
        project = _read_json(self._project_log) if self._project_log else {}
        return {
            "exported_at":     time.strftime("%Y-%m-%dT%H:%M:%S"),
            "conversation":    conv,
            "current_project": project,
        }
    
    def _write_conv(self, data: dict):
        """Write conversation file and immediately mirror to project log if active."""
        _write_json(self._conv_path(), data)
        self._sync_project()

    def _sync_project(self):
        """Copy current conversation file into project folder."""
        if not self._project_log:
            return
        conv_data = _read_json(self._conv_path())
        _write_json(self._project_log, conv_data)


# ---------------------------------------------------------------------------
# LangChain callback handler
# ---------------------------------------------------------------------------

class UsageTrackerCallback(BaseCallbackHandler):
    """
    Attached directly to each ChatOpenAI(callbacks=[...]) so it fires for
    every model including subagents, regardless of LangGraph config propagation.
    """
    raise_error = False

    def __init__(self, metrics: UsageMetrics, bridge: MetricsSignalBridge,
                 logger: ConversationLogger | None = None):
        super().__init__()
        self._m      = metrics
        self._bridge = bridge
        self._logger = logger or ConversationLogger()

        # per-query state
        self._thread_id:  str  = ""
        self._prompt:     str  = ""
        self._q_start:    dict = {}
        self._model_seen: str  = ""

    def notify_workspace_created(self, output_str: str):
        """Called by the GUI from handle_event when setup_analysis_workspace completes."""
        for line in output_str.splitlines():
            if line.strip().startswith("Location:"):
                root_path = Path(line.split("Location:", 1)[1].strip())
                self._logger.set_project_path(root_path, root_path.name)
                log.debug(f"Project log path set to: {root_path}")
                break

    # ── GUI control ───────────────────────────────────────────────────────

    def switch_thread(self, thread_id: str):
        """
        Called by the GUI on every thread switch (including app startup).
        Saves nothing — the last finish_query() already wrote the file.
        Resets metrics and pre-loads the new thread's saved totals.
        """
        self._thread_id = thread_id
        self._logger.set_thread(thread_id)
        totals = self._logger.load_totals(thread_id)
        self._m.reset()
        if totals:
            self._m.load_from_totals(totals)
        self._bridge.updated.emit(self._m.snapshot())

    def start_query(self, prompt: str, thread_id: str):
        self._thread_id = thread_id
        self._prompt    = prompt
        self._q_start   = {
            "input":  self._m.input_tokens,
            "output": self._m.output_tokens,
            "tools":  self._m.tool_calls,
            "failed": self._m.failed_tool_calls,
            "soft":   self._m.soft_error_tool_calls,
            "cost":   self._m.cost_usd,
        }
        self._m.start_thinking()

    def finish_query(self):
        elapsed = self._m.stop_thinking()
        snap    = self._m.snapshot()
        s       = self._q_start

        record = QueryRecord(
            timestamp             = time.strftime("%Y-%m-%dT%H:%M:%S"),
            thread_id             = self._thread_id,
            prompt_preview        = (self._prompt[:120] + "…")
                                    if len(self._prompt) > 120 else self._prompt,
            model                 = self._model_seen,
            thinking_seconds      = round(elapsed, 2),
            input_tokens          = snap["input_tokens"]  - s["input"],
            output_tokens         = snap["output_tokens"] - s["output"],
            total_tokens          = (snap["input_tokens"]  - s["input"])
                                  + (snap["output_tokens"] - s["output"]),
            cost_usd              = round(snap["cost_usd"] - s["cost"], 6),
            tool_calls            = snap["tool_calls"]            - s["tools"],
            failed_tool_calls     = snap["failed_tool_calls"]     - s["failed"],
            soft_error_tool_calls = snap["soft_error_tool_calls"] - s["soft"],
        )
        self._logger.append_query(record, snap)

    def get_report(self) -> dict:
        return self._logger.build_report()

    # ── LLM callbacks ─────────────────────────────────────────────────────

    def on_llm_start(self, serialized: dict, prompts: list, **kwargs):
        # Try every known location providers use for the model name
        kw    = serialized.get("kwargs") or {}
        model = (kw.get("model_name") or kw.get("model") or
                 serialized.get("name") or "")
        if model:
            self._model_seen = model

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        added_in = added_out = 0

        # Strategy 1: llm_output dict (OpenAI classic)
        usage = (response.llm_output or {}).get("token_usage") or \
                (response.llm_output or {}).get("usage")
        if isinstance(usage, dict):
            added_in  = usage.get("prompt_tokens",     0)
            added_out = usage.get("completion_tokens", 0)

        # Strategy 2: usage_metadata on AIMessage (LangChain ≥ 0.2)
        if not (added_in or added_out):
            for gen_list in response.generations:
                for gen in gen_list:
                    meta = getattr(getattr(gen, "message", None), "usage_metadata", None)
                    if meta:
                        added_in  += meta.get("input_tokens",  0)
                        added_out += meta.get("output_tokens", 0)

        # Strategy 3: response_metadata (some providers, e.g. Gemini via OpenRouter)
        if not (added_in or added_out):
            for gen_list in response.generations:
                for gen in gen_list:
                    meta = getattr(getattr(gen, "message", None), "response_metadata", {}) or {}
                    tok  = meta.get("token_usage") or meta.get("usage") or {}
                    added_in  += tok.get("prompt_tokens",     tok.get("input_tokens",  0))
                    added_out += tok.get("completion_tokens", tok.get("output_tokens", 0))

        if added_in or added_out:
            p_in, p_out = _price_for_model(self._model_seen)
            cost = (added_in * p_in + added_out * p_out) / 1_000_000
            with self._m._lock:
                self._m.input_tokens  += added_in
                self._m.output_tokens += added_out
                self._m.cost_usd      += cost
            self._emit()
            self._logger._sync_project()

    # ── Tool callbacks ─────────────────────────────────────────────────────

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs: Any):
        with self._m._lock:
            self._m.tool_calls += 1
        self._emit()

    def on_tool_end(self, output: Any, **kwargs: Any):
        tool_name  = (
            kwargs.get("name") or kwargs.get("tool") or
            (kwargs.get("serialized") or {}).get("name") or ""
        )
        output_str = str(output)
        # soft errors only — workspace detection moved to GUI handle_event
        if tool_name in _EXECUTION_TOOLS and _SOFT_ERROR_RE.search(output_str):
            with self._m._lock:
                self._m.soft_error_tool_calls += 1
            self._emit()

    def on_tool_error(self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any):
        with self._m._lock:
            self._m.failed_tool_calls += 1
        self._emit()

    def _emit(self):
        self._bridge.updated.emit(self._m.snapshot())