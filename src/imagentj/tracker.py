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

import requests
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from PySide6.QtCore import QObject, Signal
import logging
log = logging.getLogger("imagentj")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHATS_DIR = Path(os.environ.get("CHAT_DATA_PATH", "/app/data/chats"))

PRICE_TABLE: dict[str, tuple[float, float, float]] = {
    # model-name-substring                          input    output  cache_factor
    # cache_factor = fraction of p_in charged for cached tokens (None = no caching)
    "gpt-4o-mini":               (0.15,   0.60,  0.50),
    "gpt-4o":                    (2.50,  10.00,  0.50),
    "gpt-4.1-nano":              (0.10,   0.40,  0.25),
    "gpt-4.1-mini":              (0.40,   1.60,  0.25),
    "gpt-4.1":                   (2.00,   8.00,  0.25),
    "o4-mini":                   (1.10,   4.40,  0.50),
    "o4":                        (10.00, 40.00,  0.50),
    "openai/gpt-5-nano":         (0.05,   0.40,  0.50),
    "openai/gpt-5.2":            (1.75,  14.00,  0.50),
    "openai/gpt-5.3-codex":      (1.75,  14.00,  0.50),
    "openai/gpt-5":              (2.00,  16.00,  0.50),  # 5.x fallback
    "default":                   (1.00,   3.00,  None),  # fallback, no cache discount
    "gemini-3-flash-preview":    (0.50,   3.00,  None),
    "kimi-k2.5":                 (0.45,   2.25,  None),
    "claude-opus-4.6":           (10.00, 37.50,  None),
    "deepseek-v3.2":             (0.25,   0.40,  None),
    "anthropic/claude-haiku-4.5":(1.00,   5.00,  None),
    "qwen/qwen3-235b-a22b-2507": (0.071,  0.10,  None),
    "moonshotai/kimi-k2.5":      (0.45,   2.25,  None),
    "z-ai/glm-5":                (0.95,   2.55,  None),
    "mistralai/mistral-small-3.2-24b-instruct": (0.075, 0.2, None),
    "google/gemini-2.5-pro":     (1.25,  10.00,  None),
    "google/gemini-3.1-flash-lite-preview": (0.25, 1.50, None),
    "anthropic/claude-opus-4.6": (5.00,  25.00,  None),
    "anthropic/claude-sonnet-4.6":(3.00, 15.00,  None),
    "google/gemini-3-pro-preview":(2.00, 12.00,  None),
    "google/gemini-3.1-pro-preview-customtools": (2.00, 12.00, None),
}

def _price_for_model(model_name: str) -> tuple[float, float, float | None]:
    lower = model_name.lower()
    for key, prices in PRICE_TABLE.items():
        if key != "default" and key in lower:
            return prices
    return PRICE_TABLE["default"]


# ---------------------------------------------------------------------------
# OpenRouter actual-cost fetcher (optional — only active when key is set)
# ---------------------------------------------------------------------------

class _OpenRouterCostFetcher:
    """
    Session-level actual cost tracking via OpenRouter's /auth/key ``usage``
    field (per-key, not account-wide — see OpenRouter docs).

    Usage counter updates on OR's side with a delay after a request completes,
    so we record a baseline at conversation start and poll after a configurable
    delay at query end to let the counter settle.
    """

    _URL = "https://openrouter.ai/api/v1/auth/key"

    def __init__(self, api_key: str):
        self._api_key      = api_key
        self._baseline: float | None = None
        self._baseline_lock = threading.Lock()

    def _fetch_usage(self) -> float | None:
        try:
            r = requests.get(
                self._URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=6,
            )
            if r.status_code == 200:
                return r.json().get("data", {}).get("usage")
        except Exception:
            pass
        return None

    def init_baseline(self):
        """
        Snapshot the current OR usage as the baseline for this conversation.
        Runs in a background thread so it never blocks the GUI.
        """
        def _run():
            usage = self._fetch_usage()
            with self._baseline_lock:
                self._baseline = usage
            if usage is not None:
                log.debug(f"OpenRouter baseline usage: ${usage:.4f}")
            else:
                log.warning("OpenRouter: baseline fetch failed")

        threading.Thread(target=_run, daemon=True).start()

    def get_session_delta(self) -> float | None:
        """
        Return ``current_usage − baseline`` in USD without any sleep.
        Returns None if either value is unavailable.
        """
        current = self._fetch_usage()
        with self._baseline_lock:
            baseline = self._baseline
        if current is None or baseline is None:
            return None
        return max(0.0, current - baseline)


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
    # ── new ──────────────────────────────────────────────────────────────
    model_breakdown: dict = field(default_factory=dict)
    # e.g. {"google/gemini-3-pro-preview": {"input": 70000, "output": 2000, "cost": 0.148},
    #        "anthropic/claude-haiku-4.5":  {"input":  4598, "output":  366, "cost": 0.007}}
    tool_call_log: list = field(default_factory=list)
    # e.g. [{"tool": "imagej_coder", "status": "ok"},
    #        {"tool": "execute_script", "status": "soft_error"}]

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
            "model_breakdown":       self.model_breakdown,   # ← new
            "tool_call_log":         self.tool_call_log,     # ← new
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

    def update_query_cost(self, timestamp: str, actual_cost: float):
        """Patch cost_usd for the query matching *timestamp* and recompute totals."""
        if not self._thread_id:
            return
        data = _read_json(self._conv_path())
        queries = data.get("queries", [])
        for q in reversed(queries):
            if q.get("timestamp") == timestamp:
                q["cost_usd"] = round(actual_cost, 6)
                break
        else:
            return
        data["totals"]["cost_usd"] = round(sum(q["cost_usd"] for q in queries), 6)
        self._write_conv(data)

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

    def __init__(self, metrics, bridge, logger=None):
        super().__init__()
        self._m      = metrics
        self._bridge = bridge
        self._logger = logger or ConversationLogger()

        self._thread_id  = ""
        self._prompt     = ""
        self._q_start    = {}
        self._model_seen = ""
        self._run_models: dict[str, str] = {}   # run_id → model name

        # ── new: per-query accumulators ───────────────────────────────────
        self._q_model_breakdown: dict[str, dict] = {}
        # {"model_name": {"input": int, "output": int, "cost": float}}
        self._q_tool_log: list[dict] = []
        # [{"tool": str, "status": "ok"|"error"|"soft_error"}]

        # ── OpenRouter session-level cost tracking (only when key is set) ──
        or_key = os.environ.get("OPEN_ROUTER_API_KEY", "")
        self._or_fetcher: _OpenRouterCostFetcher | None = (
            _OpenRouterCostFetcher(or_key) if or_key else None
        )
        # Running OR-confirmed cost for the current conversation (USD).
        # Protected by _or_lock; updated once per query after the poll delay.
        self._or_conv_cost: float = 0.0
        self._or_lock = threading.Lock()
        self._or_eager_poll_pending: bool = False

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
        if self._or_fetcher:
            # Fresh OR baseline for this conversation so that new queries
            # accumulate correctly on top of any already-saved cost.
            self._or_fetcher.init_baseline()
            with self._or_lock:
                self._or_conv_cost = 0.0
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
        # reset per-query accumulators
        self._q_model_breakdown = {}
        self._q_tool_log        = []
        self._m.start_thinking()

    def finish_query(self):
        elapsed   = self._m.stop_thinking()
        snap      = self._m.snapshot()
        s         = self._q_start
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

        base = dict(
            timestamp             = timestamp,
            thread_id             = self._thread_id,
            prompt_preview        = (self._prompt[:120] + "…")
                                    if len(self._prompt) > 120 else self._prompt,
            model                 = self._model_seen,
            thinking_seconds      = round(elapsed, 2),
            input_tokens          = snap["input_tokens"]  - s["input"],
            output_tokens         = snap["output_tokens"] - s["output"],
            total_tokens          = (snap["input_tokens"]  - s["input"])
                                  + (snap["output_tokens"] - s["output"]),
            tool_calls            = snap["tool_calls"]            - s["tools"],
            failed_tool_calls     = snap["failed_tool_calls"]     - s["failed"],
            soft_error_tool_calls = snap["soft_error_tool_calls"] - s["soft"],
            model_breakdown       = self._q_model_breakdown,
            tool_call_log         = self._q_tool_log,
        )

        if not self._or_fetcher:
            # Estimated-cost path: write record immediately.
            record = QueryRecord(**base, cost_usd=round(snap["cost_usd"] - s["cost"], 6))
            self._logger.append_query(record, snap)
            return

        # OR path: poll with retries until OR's billing counter moves past the
        # previous conversation total, then attribute the increment to this query.
        fetcher = self._or_fetcher

        def _finalize(
            initial_delay:  float = 2.0,    # wait before first poll
            poll_interval:  float = 3.0,    # seconds between polls
            idle_timeout:   float = 30.0,   # stop after this many seconds with no new charge
            abs_timeout:    float = 120.0,  # hard stop regardless
        ):
            time.sleep(initial_delay)
            abs_deadline     = time.monotonic() + abs_timeout
            last_increase_t  = time.monotonic()
            total_query_cost = 0.0
            record_written   = False

            while True:
                now = time.monotonic()
                if now >= abs_deadline:
                    break
                # Once we have at least one reading, stop when cost has been
                # stable long enough — all delayed charges should have arrived.
                if record_written and (now - last_increase_t) >= idle_timeout:
                    break

                session_cost = fetcher.get_session_delta()

                if session_cost is not None:
                    with self._or_lock:
                        if session_cost > self._or_conv_cost:
                            increment          = session_cost - self._or_conv_cost
                            self._or_conv_cost = session_cost
                        else:
                            increment = 0.0

                    if increment > 0:
                        with self._m._lock:
                            self._m.cost_usd += increment
                        total_query_cost += increment
                        last_increase_t   = time.monotonic()

                        if not record_written:
                            record = QueryRecord(
                                **base, cost_usd=round(total_query_cost, 6)
                            )
                            self._logger.append_query(record, self._m.snapshot())
                            record_written = True
                        else:
                            self._logger.update_query_cost(
                                timestamp, total_query_cost
                            )

                        log.debug(
                            f"OpenRouter: +${increment:.6f}  "
                            f"query total=${total_query_cost:.6f}  "
                            f"session=${session_cost:.6f}"
                        )
                        self._emit()

                time.sleep(poll_interval)

            if not record_written:
                log.warning("OpenRouter: no cost registered within "
                            f"{abs_timeout:.0f}s — query cost not recorded")

        threading.Thread(target=_finalize, daemon=True).start()

    def _schedule_eager_or_poll(self, delay: float = 1.5) -> None:
        """One-shot cost poll triggered by on_llm_end for mid-query UI updates."""
        with self._or_lock:
            if self._or_eager_poll_pending:
                return
            self._or_eager_poll_pending = True

        fetcher = self._or_fetcher

        def _poll():
            time.sleep(delay)
            with self._or_lock:
                self._or_eager_poll_pending = False
            session_cost = fetcher.get_session_delta()
            if session_cost is None:
                return
            with self._or_lock:
                if session_cost > self._or_conv_cost:
                    increment          = session_cost - self._or_conv_cost
                    self._or_conv_cost = session_cost
                else:
                    increment = 0.0
            if increment > 0:
                with self._m._lock:
                    self._m.cost_usd += increment
                self._emit()

        threading.Thread(target=_poll, daemon=True).start()

    def get_report(self) -> dict:
        return self._logger.build_report()

    # ── LLM callbacks ─────────────────────────────────────────────────────

    def on_llm_start(self, serialized: dict, prompts: list, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        kw     = serialized.get("kwargs") or {}
        model  = (kw.get("model_name") or kw.get("model") or
                  serialized.get("name") or "")
        if model:
            self._model_seen = model
            if run_id:
                self._run_models[run_id] = model

    def on_llm_end(self, response: LLMResult, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        model  = self._run_models.pop(run_id, self._model_seen)

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
                    tok  = meta.get("token_usage") or meta.get("usage") or {}
                    added_in  += tok.get("prompt_tokens",     tok.get("input_tokens",  0))
                    added_out += tok.get("completion_tokens", tok.get("output_tokens", 0))

        # Extract cached input tokens for prompt-cache discount (OpenAI direct only)
        cached_in = 0
        if isinstance(usage, dict):
            cached_in = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        if not cached_in:
            for gen_list in response.generations:
                for gen in gen_list:
                    meta = getattr(getattr(gen, "message", None), "response_metadata", {}) or {}
                    tok  = meta.get("token_usage") or meta.get("usage") or {}
                    cached_in = max(cached_in, (tok.get("prompt_tokens_details") or {}).get("cached_tokens", 0))

        if added_in or added_out:
            with self._m._lock:
                self._m.input_tokens  += added_in
                self._m.output_tokens += added_out
                if not self._or_fetcher:
                    # Estimated cost — only applied when OR key is not set
                    p_in, p_out, cache_factor = _price_for_model(model)
                    non_cached = added_in - cached_in
                    if cache_factor is not None and cached_in:
                        cost = (non_cached * p_in + cached_in * p_in * cache_factor + added_out * p_out) / 1_000_000
                    else:
                        cost = (added_in * p_in + added_out * p_out) / 1_000_000
                    self._m.cost_usd += cost

            # ── per-query model breakdown (tokens always; cost only estimated path)
            entry = self._q_model_breakdown.setdefault(
                model, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
            )
            entry["input_tokens"]  += added_in
            entry["output_tokens"] += added_out
            if not self._or_fetcher:
                entry["cost_usd"] = round(entry["cost_usd"] + cost, 6)

            self._emit()

        if self._or_fetcher:
            self._schedule_eager_or_poll()

    # ── Tool callbacks ─────────────────────────────────────────────────────

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs):
        tool_name = (serialized or {}).get("name", "unknown")
        with self._m._lock:
            self._m.tool_calls += 1
        # log the tool call — status filled in by on_tool_end / on_tool_error
        self._q_tool_log.append({"tool": tool_name, "status": "ok"})
        self._emit()

    def on_tool_end(self, output: Any, **kwargs):
        tool_name  = (
            kwargs.get("name") or kwargs.get("tool") or
            (kwargs.get("serialized") or {}).get("name") or ""
        )
        output_str = str(output)

        if tool_name in _EXECUTION_TOOLS and _SOFT_ERROR_RE.search(output_str):
            with self._m._lock:
                self._m.soft_error_tool_calls += 1
            # update status on the last matching tool log entry
            for entry in reversed(self._q_tool_log):
                if entry["tool"] == tool_name and entry["status"] == "ok":
                    entry["status"] = "soft_error"
                    break
            self._emit()

    def on_tool_error(self, error, **kwargs):
        with self._m._lock:
            self._m.failed_tool_calls += 1
        if self._q_tool_log:
            self._q_tool_log[-1]["status"] = "error"
        self._emit()

    def _emit(self):
        """Synchronize UI and Disk storage simultaneously."""
        snapshot = self._m.snapshot()
        
        # 1. Update the UI
        self._bridge.updated.emit(snapshot)
        
        # 2. Update the JSON files (Local and Project)
        self._logger._sync_project()
