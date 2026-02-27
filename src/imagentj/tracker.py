"""
usage_tracker.py  –  Real-time token, timing, cost & tool-call metrics.

Tracks (per query + cumulative session):
  • input / output tokens
  • agent thinking time  (excludes user typing / reading time)
  • estimated cost       (configurable price table, $/1M tokens)
  • total / failed / soft-error tool calls

Persistence:
  • Appends one JSON record per completed query to STATS_LOG_PATH.
  • Also writes a cumulative session_totals block on every update.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from PySide6.QtCore import QObject, Signal


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STATS_LOG_PATH = Path("/app/data/usage_stats.json")


# Price in USD per 1 000 000 tokens.  Add / update models here.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    # model-name-substring        input   output
    "qwen3-235b":                (0.00,   0.00),   # academiccloud – free tier
    "gpt-4o":                    (2.50,  10.00),
    "gpt-4o-mini":               (0.15,   0.60),
    "gpt-4.1":                   (2.00,   8.00),
    "claude-opus-4":             (15.00,  75.00),
    "claude-sonnet-4":           (3.00,  15.00),
    "claude-haiku-4":            (0.80,   4.00),
    "default":                   (1.00,   3.00),   # fallback
    "gemini-3-flash-preview":    (0.50,   3.00),   # openrouter – free tier
}

def _price_for_model(model_name: str) -> tuple[float, float]:
    """Return (input_per_1M, output_per_1M) for the closest matching model."""
    lower = model_name.lower()
    for key, prices in PRICE_TABLE.items():
        if key != "default" and key in lower:
            return prices
    return PRICE_TABLE["default"]


# ---------------------------------------------------------------------------
# Soft-error detection (execution tools only)
# ---------------------------------------------------------------------------

_SOFT_ERROR_RE = re.compile(
    r"\b("
    r"error|exception|warning|failed|failure|"
    r"missingmethodexception|missingmethod|no such method|"
    r"groovyruntimeexception|scriptexception|"
    r"could not|unable to|traceback|illegalargument|"
    r"nullpointerexception|indexoutofbounds"
    r")\b",
    re.IGNORECASE,
)
_EXECUTION_TOOLS = {"execute_script", "run_script_safe", "run_python_code"}


# ---------------------------------------------------------------------------
# Per-query record (written to JSON)
# ---------------------------------------------------------------------------

@dataclass
class QueryRecord:
    timestamp: str              = ""
    prompt_preview: str         = ""
    model: str                  = ""
    thinking_seconds: float     = 0.0
    input_tokens: int           = 0
    output_tokens: int          = 0
    total_tokens: int           = 0
    cost_usd: float             = 0.0
    tool_calls: int             = 0
    failed_tool_calls: int      = 0
    soft_error_tool_calls: int  = 0

    def to_dict(self) -> dict:
        return {
            "timestamp":             self.timestamp,
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
# Session-level cumulative metrics
# ---------------------------------------------------------------------------

@dataclass
class UsageMetrics:
    # tokens
    input_tokens: int       = 0
    output_tokens: int      = 0
    # timing
    thinking_seconds: float = 0.0
    _thinking_start: float  = field(default=0.0, repr=False, compare=False)
    _is_thinking: bool      = field(default=False, repr=False, compare=False)
    # cost
    cost_usd: float         = 0.0
    # tools
    tool_calls: int             = 0
    failed_tool_calls: int      = 0
    soft_error_tool_calls: int  = 0

    _lock: threading.Lock = field(default_factory=threading.Lock,
                                  repr=False, compare=False)

    # ── timing control (called from Qt main thread) ──────────────────────

    def start_thinking(self):
        with self._lock:
            self._thinking_start = time.monotonic()
            self._is_thinking = True

    def stop_thinking(self) -> float:
        """Commit elapsed time; returns seconds for this query."""
        with self._lock:
            if not self._is_thinking:
                return 0.0
            elapsed = time.monotonic() - self._thinking_start
            self.thinking_seconds += elapsed
            self._is_thinking = False
            return elapsed

    def live_thinking_seconds(self) -> float:
        """Session total including any in-progress query. Call with lock held OR not."""
        extra = (time.monotonic() - self._thinking_start) if self._is_thinking else 0.0
        return self.thinking_seconds + extra

    # ── helpers ──────────────────────────────────────────────────────────

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
            self.input_tokens = 0
            self.output_tokens = 0
            self.thinking_seconds = 0.0
            self._thinking_start = 0.0
            self._is_thinking = False
            self.cost_usd = 0.0
            self.tool_calls = 0
            self.failed_tool_calls = 0
            self.soft_error_tool_calls = 0


# ---------------------------------------------------------------------------
# Qt signal bridge
# ---------------------------------------------------------------------------

class MetricsSignalBridge(QObject):
    updated = Signal(dict)


# ---------------------------------------------------------------------------
# JSON persistence
# ---------------------------------------------------------------------------

class StatsLogger:
    """Appends one QueryRecord per completed query to a JSON file."""

    def __init__(self, path: Path = STATS_LOG_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append_query(self, record: QueryRecord, session_totals: dict):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                data = {"queries": [], "session_totals": {}}
        else:
            data = {"queries": [], "session_totals": {}}

        data["queries"].append(record.to_dict())
        data["session_totals"] = session_totals

        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# LangChain callback handler
# ---------------------------------------------------------------------------

class UsageTrackerCallback(BaseCallbackHandler):
    """
    Attached directly to each ChatOpenAI instance so it fires for ALL models
    including subagents — regardless of LangGraph config propagation.

    The GUI calls start_query() / finish_query() to bracket thinking time.
    """
    raise_error = False

    def __init__(self, metrics: UsageMetrics, bridge: MetricsSignalBridge,
                 logger: StatsLogger | None = None):
        super().__init__()
        self._m = metrics
        self._bridge = bridge
        self._logger = logger or StatsLogger()
        self._current_prompt: str = ""
        self._query_start_tokens: dict = {}  # tokens at query start for delta
        self._model_seen: str = ""

    def start_query(self, prompt: str = ""):
        """Called by GUI on Send."""
        self._current_prompt = prompt
        self._query_start_tokens = {
            "input":  self._m.input_tokens,
            "output": self._m.output_tokens,
            "tools":  self._m.tool_calls,
            "failed": self._m.failed_tool_calls,
            "soft":   self._m.soft_error_tool_calls,
            "cost":   self._m.cost_usd,
        }
        self._m.start_thinking()

    def finish_query(self):
        """Called by GUI on agent finished."""
        elapsed = self._m.stop_thinking()
        snap = self._m.snapshot()
        s = self._query_start_tokens

        record = QueryRecord(
            timestamp           = time.strftime("%Y-%m-%dT%H:%M:%S"),
            prompt_preview      = (self._current_prompt[:120] + "…")
                                  if len(self._current_prompt) > 120
                                  else self._current_prompt,
            model               = self._model_seen,
            thinking_seconds    = round(elapsed, 2),
            # deltas — what THIS query consumed
            input_tokens        = snap["input_tokens"]  - s["input"],
            output_tokens       = snap["output_tokens"] - s["output"],
            total_tokens        = (snap["input_tokens"]  - s["input"])
                                + (snap["output_tokens"] - s["output"]),
            cost_usd            = round(snap["cost_usd"] - s["cost"], 6),
            tool_calls          = snap["tool_calls"]          - s["tools"],
            failed_tool_calls   = snap["failed_tool_calls"]   - s["failed"],
            soft_error_tool_calls = snap["soft_error_tool_calls"] - s["soft"],
        )
        self._logger.append_query(record, snap)

    # ── Token tracking ────────────────────────────────────────────────────

    def on_llm_start(self, serialized: dict, prompts: list, **kwargs):
        model = (serialized.get("kwargs") or {}).get("model_name", "") or \
                (serialized.get("kwargs") or {}).get("model", "")
        if model:
            self._model_seen = model

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        added_in = added_out = 0

        usage = (response.llm_output or {}).get("token_usage") or \
                (response.llm_output or {}).get("usage")
        if isinstance(usage, dict):
            added_in  = usage.get("prompt_tokens",     0)
            added_out = usage.get("completion_tokens", 0)

        if not (added_in or added_out):
            for gen_list in response.generations:
                for gen in gen_list:
                    meta = getattr(getattr(gen, "message", None), "usage_metadata", None)
                    if meta:
                        added_in  += meta.get("input_tokens",  0)
                        added_out += meta.get("output_tokens", 0)

        if not (added_in or added_out):
            for gen_list in response.generations:
                for gen in gen_list:
                    meta = getattr(getattr(gen, "message", None), "response_metadata", {}) or {}
                    tok = meta.get("token_usage") or meta.get("usage") or {}
                    added_in  += tok.get("prompt_tokens",     tok.get("input_tokens",  0))
                    added_out += tok.get("completion_tokens", tok.get("output_tokens", 0))

        if added_in or added_out:
            price_in, price_out = _price_for_model(self._model_seen)
            added_cost = (added_in * price_in + added_out * price_out) / 1_000_000
            with self._m._lock:
                self._m.input_tokens  += added_in
                self._m.output_tokens += added_out
                self._m.cost_usd      += added_cost
            self._emit()

    # ── Tool tracking ─────────────────────────────────────────────────────

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs: Any):
        with self._m._lock:
            self._m.tool_calls += 1
        self._emit()

    def on_tool_end(self, output: Any, *, name: str = "", **kwargs: Any):
        tool_name = name or (kwargs.get("serialized") or {}).get("name", "")
        if tool_name in _EXECUTION_TOOLS and _SOFT_ERROR_RE.search(str(output)):
            with self._m._lock:
                self._m.soft_error_tool_calls += 1
            self._emit()

    def on_tool_error(self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any):
        with self._m._lock:
            self._m.failed_tool_calls += 1
        self._emit()

    def _emit(self):
        self._bridge.updated.emit(self._m.snapshot())