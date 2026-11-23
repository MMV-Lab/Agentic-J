"""
Agent-level watchdog — the sibling of `watchdog.py`, one layer up.

`watchdog.py` supervises *scripts*: a Groovy/Python run started by a tool call.
It works well, but it can only see what happens inside `execute_script`. The
2026-08-07 benchmark run showed both real hangs living OUTSIDE that scope:

  * the QA reporter wrote `QA_Checklist_Report.md`, read it back, wrote it
    again — 57 times over 34 minutes, never emitting its typed handoff;
  * the Vision judge blocked forever inside a single `IJ.open()` on the JVM.

Neither is a script run, so neither was supervised, and nothing in the product
stopped either one. This module closes that gap by watching the *agent turn*.

Three tiers, cheapest first — the same shape as the script watchdog:

  Tier 0 (free, deterministic) — the same tool called with the same arguments
  REPEAT_LIMIT times in a row is a spinning loop by definition. No LLM needed,
  and this is what catches the QA case.

  Tier 1 (free, deterministic) — no tool call has *started or finished* for
  STALL_SECONDS. A tool that never returns (a JVM call with no timeout) looks
  exactly like this. Catches the Vision case even when the underlying call is
  uninterruptible.

  Tier 2 (LLM, only on long runtime) — a small model sees the tool-call history
  and rules CONTINUE or KILL, for the runaway that is neither repetitive nor
  stalled, merely endless.

  Tier 3 (free, deterministic) — the odd one out: the turn is HEALTHY and the
  user is still not getting a segmentation they accept. It never kills; it
  switches the strategy to fine-tuning. Read from the usage log rather than the
  tool history, because the evidence is the user's own words across many turns.

Bias is toward CONTINUE, for the same reason as the script watchdog: a slow
subagent is normal, and killing good work is worse than waiting. Every failure
path (no LLM, parse error, missing handle) resolves to "leave it alone".

Killing means injecting SystemExit into the agent's worker thread, exactly as
the Stop button does via `stop_signal`. The caller then returns its graceful
`on_cap()` handoff, so the supervisor still receives a structured result.
"""

import contextvars
import glob
import hashlib
import json
import logging
import os
import threading
import time
from typing import Callable, Optional

log = logging.getLogger(__name__)

# The turn currently being supervised, so the middleware can find its handle.
#
# A ContextVar rather than a thread-local on purpose: LangChain runs tool calls
# on a ThreadPoolExecutor but dispatches them through `copy_context().run(...)`
# (`langchain_core/runnables/config.py`), so a ContextVar set on the agent's
# worker thread reaches the executor threads while a thread-local would not.
# It is set in `stop_signal.SubagentRunner._target`, i.e. inside the worker
# thread — ContextVars are NOT inherited across `Thread.start()`.
CURRENT: "contextvars.ContextVar[Optional[AgentHandle]]" = contextvars.ContextVar(
    "imagentj_agent_watchdog_current", default=None
)

ENABLED = os.environ.get("IMAGENTJ_AGENT_WATCHDOG", "1") not in ("0", "false", "False")

# Identical (tool, args) calls in a row before we call it a spinning loop.
# The observed QA loop repeated a save_markdown/read pair; 6 is comfortably
# above any legitimate retry pattern (a debugger re-reading a file it just
# edited does so once or twice, never six times with byte-identical arguments).
REPEAT_LIMIT = int(os.environ.get("IMAGENTJ_AGENT_WATCHDOG_REPEATS", "6"))

# No tool call started or finished for this long → the current tool is hung.
# Still generous enough for a CPU Cellpose call or a big Bio-Formats open, which
# legitimately take minutes. The Vision hang sat here for 29 minutes.
#
# Lowered 600 -> 300 after measuring where benchmark wall-time actually goes:
# stalls accounted for 40-57% of every run (b03 19.3 min of 48.2, b05 18.9 of
# 33.4), and every one of those waits was the full threshold. Waiting longer buys
# nothing — a probe let the worst offender (plugin_manager) run unbounded and it
# still returned no structured response after 63 minutes, while recovery after a
# kill takes ~2 s. With a 60-minute per-task budget, a 10-minute wait is a sixth
# of the whole allowance.
STALL_SECONDS = float(os.environ.get("IMAGENTJ_AGENT_WATCHDOG_STALL", "300"))

# Total agent-turn runtime that trips the LLM verdict.
MAX_RUNTIME_SECONDS = float(os.environ.get("IMAGENTJ_AGENT_WATCHDOG_MAX_RUNTIME", "900"))

POLL_SECONDS = 5.0
BACKOFF_FACTOR = 2.0
MAX_CHECK_GAP_SECONDS = float(os.environ.get("IMAGENTJ_AGENT_WATCHDOG_MAX_GAP", "900"))

_MAX_HISTORY = 40          # tool calls kept per handle (bounded memory)
_MAX_ARG_CHARS = 400       # per-call argument digest input


class AgentAborted(RuntimeError):
    """Raised in the caller when the agent watchdog terminated an agent turn."""


# ---------------------------------------------------------------------------
# Tier 3 — the user is not getting a segmentation they will accept
# ---------------------------------------------------------------------------
# The other tiers watch for a run that is BROKEN. This one watches for a run that
# is working and still failing the user: the agent adjusts a threshold, the user
# says it is still wrong, the agent adjusts it again. Nothing ends that loop,
# because fine-tuning is only routed when the user asks for it BY NAME — so a user
# who does not know the capability exists never gets offered it, however long they
# go round.
#
# THE SOURCE IS THE USAGE LOG, NOT THE STATE LEDGER. The first version of this read
# `state_ledger.json`, which was wrong in practice: the ledger is written only when
# the supervisor remembers to call `update_state_ledger`, and measured on a real
# session it does NOT record separate retries of the same thresholding step. A
# counter resting on a habit the model may not keep reads zero exactly when it
# matters. `logs/usage_log.json` (and the per-chat `usage_stats.json`) is written by
# the tracker on EVERY query with no model involvement, and it carries the one thing
# that actually defines this problem: the user's own words.
#
# So the count is consecutive user turns expressing dissatisfaction with a
# segmentation. Measured over 194 real chats / 704 queries in this deployment it
# fires on 2, both genuine — e.g. "this is not correct, the nuclei are not detected
# well" -> "but it's not better, there are a lot more nuceli actually" -> "now it's
# finding too many extra compartments". No false positives in that sample.
SEGMENTATION_RETRY_LIMIT = int(os.environ.get("IMAGENTJ_SEGMENTATION_RETRIES", "3"))

# The segmenters and targets this system actually routes to. Deliberately NOT every
# tool with a docs folder — only segmenters that are installed and routed (Labkit included).
_SEG_WORDS = ("segment", "threshold", "mask", "cellpose", "stardist", "micro_sam",
              "microsam", "watershed", "nuclei", "nucleus", "cells", "detect",
              "outline", "label", "labkit", "pixel classif")

# Phrases taken from the logged prompts of real dissatisfied sessions rather than
# invented. Kept literal for that reason — a cleverer generalisation ("no", "not")
# matches ordinary answers like "no time lapse" and fires on the first turn.
_UNHAPPY = ("not correct", "incorrect", "not better", "not good", "not detected",
            "not reasonable", "not all", "too many", "too few", "left out",
            "over-represent", "over represent", "not right", "is wrong", "are wrong",
            "still not", "still wrong", "doesn't work", "does not work", "not enough",
            "these are not", "i want not", "not being detected", "getting counted",
            "being counted", "try again", "not well", "not properly")
_HAPPY = ("works", "worked", "perfect", "looks good", "that's it", "thanks",
          "correct now", "that works", "good now")

_project_root: Optional[str] = None
_retry_announced: set = set()
_last_reported: Optional[int] = None
# Live count, fed by note_prompt as each turn arrives; None until seeded from the log.
_live_streak: Optional[int] = None
_live_prompts: list = []
_prev_seg: bool = False


def note_project(project_root: str) -> None:
    """Told by the state ledger where the project is, to aim at the right usage log."""
    global _project_root
    if project_root:
        _project_root = project_root


def _usage_log_path() -> Optional[str]:
    """The project's usage log, else the most recently touched chat's.

    Deliberately discoverable without being told: the ledger hook that sets
    `_project_root` is itself a model-dependent call, and Tier 3 exists precisely
    because those cannot be relied on.
    """
    if _project_root:
        p = os.path.join(_project_root, "logs", "usage_log.json")
        if os.path.exists(p):
            return p
    base = os.environ.get("CHAT_DATA_PATH", "/app/data/chats")
    try:
        found = glob.glob(os.path.join(base, "*", "usage_stats.json"))
        return max(found, key=os.path.getmtime) if found else None
    except Exception:
        return None


def _classify(text: str, prev_was_segmentation: bool) -> str:
    """One user turn: 'happy', 'unhappy', 'seg' or 'other'.

    A complaint counts only in a segmentation context — either it names something
    segmentation-related itself, or the turn before it did. "but it's not better"
    carries no vocabulary of its own and is the most common shape of the second and
    third complaint, so without the carried context the streak never reaches three.
    """
    t = (text or "").lower()
    if any(w in t for w in _HAPPY):
        return "happy"
    seg = any(w in t for w in _SEG_WORDS)
    if any(w in t for w in _UNHAPPY) and (seg or prev_was_segmentation):
        return "unhappy"
    return "seg" if seg else "other"


def unhappy_streak(path: Optional[str] = None, force_log: bool = False) -> tuple:
    """(streak, the prompts in it) — consecutive dissatisfied segmentation turns.

    Prefers the live count fed by `note_prompt`, which is a turn ahead of the log.
    """
    if not force_log and path is None and _live_streak is not None:
        return _live_streak, list(_live_prompts)
    path = path or _usage_log_path()
    if not path:
        return 0, []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            queries = (json.load(fh) or {}).get("queries") or []
    except Exception:
        return 0, []                    # no log yet, or mid-write: say nothing
    streak, prompts, prev_seg = 0, [], False
    for q in queries:
        text = (q.get("prompt_preview") or "").strip()
        if not text:
            continue
        kind = _classify(text, prev_seg)
        if kind == "happy":
            streak, prompts = 0, []     # the user accepted something: start again
        elif kind == "unhappy":
            streak += 1
            prompts.append(text)
        if kind in ("seg", "unhappy"):
            prev_seg = True
    return streak, prompts


def finetune_directive(path: Optional[str] = None) -> str:
    """The switch, as text for the agent's context. Empty until the limit is reached."""
    streak, prompts = unhappy_streak(path)
    if streak < SEGMENTATION_RETRY_LIMIT:
        return ""
    said = [f"    “{p[:120]}”" for p in prompts[-SEGMENTATION_RETRY_LIMIT:]]
    return "\n".join([
        f"⚠ WATCHDOG: the user has rejected this segmentation {streak} times running:",
        *said,
        "  → STOP TUNING PARAMETERS AND SWITCH TO FINE-TUNING. Three settings have failed;",
        "    that is evidence about the MODEL, not the settings, and a fourth is a worse use",
        "    of the user's patience than teaching the model what they mean.",
        "    Read skills/napari/micro_sam/FINETUNING.md and run its 'is fine-tuning even",
        "    needed?' gate FIRST — no GPU, too few images, or data the stock model already",
        "    covers all rule it out in seconds, and then you say so and keep tuning.",
        "    If the gate passes, tell the user the cost (~20 min of their time annotating",
        "    ~8 small tiles) and start at stage 1, which opens the tile picker and puts the",
        "    decision in front of them anyway.",
        "    This clears as soon as the user says a result is right.",
    ])


def retry_status_line(path: Optional[str] = None) -> str:
    """One line for the container log, so the counter is observable while it runs."""
    streak, prompts = unhappy_streak(path)
    last = f' last: "{prompts[-1][:70]}"' if prompts else ""
    tail = ("  *** LIMIT REACHED -> switching to fine-tuning ***"
            if streak >= SEGMENTATION_RETRY_LIMIT else "")
    return (f"[retry-watch] consecutive rejected segmentations: "
            f"{streak}/{SEGMENTATION_RETRY_LIMIT}{last}{tail}")


def note_prompt(text: str) -> str:
    """Called with each user turn AS IT ARRIVES. Returns the classification.

    The usage log alone is always one turn behind: `finish_query` writes the record
    when the turn ENDS, so anything polling it during a turn sees only the turns
    before it — the count lagged, the log line appeared on some turns and not others,
    and the third complaint could not trip anything until the fourth had started.
    Feeding the prompt in at `start_query` removes the lag, and gets the FULL text
    rather than the 120-character preview the log stores.

    The log is still read once, to seed the streak after a restart mid-conversation.
    """
    global _live_streak, _live_prompts, _prev_seg
    if _live_streak is None:
        _live_streak, _live_prompts = unhappy_streak(force_log=True)
    kind = _classify(text, _prev_seg)
    if kind == "happy":
        _live_streak, _live_prompts = 0, []
    elif kind == "unhappy":
        _live_streak += 1
        _live_prompts.append(text)
    if kind in ("seg", "unhappy"):
        _prev_seg = True
    # One line per user turn, whatever the verdict. Printing only on change hid the
    # turns that scored 'other', which are exactly the ones worth seeing when the
    # count is not moving and you cannot tell whether the phrase list missed them.
    print(f"[retry-watch] turn={kind:<7} streak={_live_streak}/{SEGMENTATION_RETRY_LIMIT}"
          f"  :: {text[:80]!r}", flush=True)
    _announce_if_due()
    return kind


def pending_directive() -> str:
    """The directive to hand the agent, or empty. Works with no project and no ledger.

    The ledger-context route only exists once a project workspace does, which in fast
    mode on a quick threshold it may not. This is the channel that is always there.
    """
    return finetune_directive()


def _announce_if_due() -> None:
    streak, _ = unhappy_streak()
    if streak < SEGMENTATION_RETRY_LIMIT:
        return
    key = _project_root or _usage_log_path() or "?"
    if key in _retry_announced:
        return
    _retry_announced.add(key)
    _notify(f"Segmentation has been through {streak} rounds you were not happy with. "
            f"Rather than tune the settings again, the assistant will look at "
            f"fine-tuning the model on your own annotations.")


def _check_segmentation_retries() -> None:
    """Poll-loop hook. Only a backstop now — `note_prompt` does the real work."""
    global _last_reported
    streak, _ = unhappy_streak()
    if streak != _last_reported:
        _last_reported = streak
    _announce_if_due()



# GUI hook — set by gui_runner so an agent-watchdog kill surfaces in the chat.
_notifier: Optional[Callable[[str], None]] = None


def set_notifier(fn: Callable[[str], None]) -> None:
    global _notifier
    _notifier = fn


def _notify(message: str) -> None:
    if _notifier is None:
        return
    try:
        _notifier(message)
    except Exception:
        log.exception("agent watchdog notifier failed")


def _digest(name: str, args) -> str:
    """Stable fingerprint of one tool call, so repeats are comparable."""
    try:
        blob = json.dumps(args, sort_keys=True, default=str)[:_MAX_ARG_CHARS]
    except Exception:
        blob = str(args)[:_MAX_ARG_CHARS]
    return hashlib.sha1(f"{name}|{blob}".encode("utf-8", "replace")).hexdigest()[:16]


class AgentHandle:
    """One in-flight agent turn: its worker thread and its tool-call history."""

    def __init__(self, name: str):
        self.name = name
        self.started = time.monotonic()
        self.thread: Optional[threading.Thread] = None
        self.terminated = False
        self.finished = False
        self.kill_reason = ""
        self._lock = threading.Lock()
        self._calls: list[tuple[str, str, float]] = []   # (tool, digest, at)
        self._last_event = time.monotonic()
        self._inflight: Optional[str] = None

    # ── recorded by the middleware ───────────────────────────────────────────
    def call_started(self, tool: str, args) -> None:
        with self._lock:
            self._calls.append((tool, _digest(tool, args), time.monotonic()))
            del self._calls[:-_MAX_HISTORY]
            self._last_event = time.monotonic()
            self._inflight = tool

    def call_finished(self, tool: str) -> None:
        with self._lock:
            self._last_event = time.monotonic()
            self._inflight = None

    # ── read by the supervisor ───────────────────────────────────────────────
    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def quiet_for(self) -> float:
        with self._lock:
            return time.monotonic() - self._last_event

    def inflight(self) -> Optional[str]:
        with self._lock:
            return self._inflight

    def repeat_run(self) -> tuple[int, str]:
        """Length of the trailing run of identical calls, and that tool's name."""
        with self._lock:
            if not self._calls:
                return 0, ""
            last_tool, last_digest, _ = self._calls[-1]
            n = 0
            for tool, digest, _at in reversed(self._calls):
                if digest != last_digest:
                    break
                n += 1
            return n, last_tool

    def history(self, limit: int = 15) -> str:
        with self._lock:
            recent = self._calls[-limit:]
        if not recent:
            return "(no tool calls yet)"
        t0 = self.started
        return "\n".join(f"  +{at - t0:6.0f}s  {tool}" for tool, _d, at in recent)

    # ── termination ──────────────────────────────────────────────────────────
    def terminate(self, reason: str) -> bool:
        """Inject SystemExit into the agent's worker thread. Returns True if sent."""
        from . import stop_signal   # local import: stop_signal must not import us

        self.kill_reason = reason
        self.terminated = True
        thread = self.thread
        if thread is None or not thread.is_alive():
            return False
        stop_signal._inject_exit(thread)
        return True


_VERDICT_PROMPT = """You are a watchdog supervising a running AI agent (not a script).

Your ONLY job is to decide whether this agent turn should be killed right now.

Default to CONTINUE. Agents legitimately take many turns: reading documentation,
inspecting files, writing and revising a script, waiting on a slow tool.

Answer KILL only on positive evidence the turn will not finish usefully:
  - it is repeating the same tool call over and over with no new information
    (e.g. writing a file then reading it back, again and again)
  - it is re-reading files it has already read instead of producing its result
  - it is clearly stuck in a cycle rather than converging on an answer

Answer CONTINUE if the tool calls show varied, forward-moving work, or if the
agent is simply waiting on one slow tool.

--- AGENT ---
{name}

--- RUNTIME ---
Running for {elapsed}. Last tool activity {quiet} ago. Currently inside: {inflight}

--- RECENT TOOL CALLS (oldest first) ---
{history}

Reply with exactly one line:
KILL: <short reason>
or
CONTINUE: <short reason>
"""


def _human(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} seconds"
    return f"{seconds / 60:.1f} minutes"


def _ask_llm(handle: AgentHandle) -> tuple[bool, str]:
    """Ask the small model whether to kill. Any failure means 'leave it alone'."""
    try:
        from .agents import llm_nano
    except Exception as exc:
        log.warning("agent watchdog: no LLM available (%s) — leaving turn alone", exc)
        return False, ""

    prompt = _VERDICT_PROMPT.format(
        name=handle.name,
        elapsed=_human(handle.elapsed),
        quiet=_human(handle.quiet_for()),
        inflight=handle.inflight() or "(between tool calls)",
        history=handle.history(),
    )
    try:
        reply = llm_nano.invoke(prompt)
        text = (reply.content if hasattr(reply, "content") else str(reply))
    except Exception as exc:
        log.warning("agent watchdog: verdict call failed (%s) — leaving turn alone", exc)
        return False, ""

    if isinstance(text, list):
        text = " ".join(str(part) for part in text)
    first = str(text).strip().splitlines()[0] if str(text).strip() else ""
    if first.upper().startswith("KILL"):
        reason = first.split(":", 1)[1].strip() if ":" in first else "agent judged stuck"
        return True, reason
    return False, first


def _kill(handle: AgentHandle, reason: str) -> None:
    log.warning("agent watchdog: killing %s — %s", handle.name, reason)
    sent = handle.terminate(reason)
    _notify(
        f"Watchdog stopped the {handle.name} agent: {reason}"
        if sent else
        f"Watchdog flagged the {handle.name} agent ({reason}) but it did not respond."
    )


def _supervise(handle: AgentHandle) -> None:
    """Watch one agent turn until it finishes or gets killed."""
    runtime_threshold = MAX_RUNTIME_SECONDS

    while True:
        time.sleep(POLL_SECONDS)

        if handle.finished or handle.terminated:
            return
        if handle.thread is not None and not handle.thread.is_alive():
            return

        # Tier 0 — a spinning loop, provable from the call log alone.
        repeats, tool = handle.repeat_run()
        if repeats >= REPEAT_LIMIT:
            _kill(handle, f"repeated the same '{tool}' call {repeats}× with identical "
                          f"arguments — spinning loop")
            return

        # Tier 3 — working, but not producing anything the user accepts. Never kills:
        # the turn is healthy, it is the STRATEGY that needs to change.
        try:
            _check_segmentation_retries()
        except Exception:
            log.debug("agent watchdog: retry check failed", exc_info=True)

        # Tier 1 — a tool that never returned.
        quiet = handle.quiet_for()
        if quiet >= STALL_SECONDS:
            inflight = handle.inflight()
            where = f"inside '{inflight}'" if inflight else "between tool calls"
            _kill(handle, f"no tool activity for {_human(quiet)} {where} — "
                          f"treating as a hung call")
            return

        # Tier 2 — long-running but neither repetitive nor stalled: ask the model.
        elapsed = handle.elapsed
        if elapsed < runtime_threshold:
            continue

        log.info("agent watchdog: checking %s (running for %.0fs)", handle.name, elapsed)
        should_kill, reason = _ask_llm(handle)
        if should_kill:
            _kill(handle, f"{reason} (after {_human(elapsed)})")
            return

        runtime_threshold = elapsed + min(elapsed * (BACKOFF_FACTOR - 1), MAX_CHECK_GAP_SECONDS)
        log.info("agent watchdog: %s cleared (%s); next check after %.0fs runtime",
                 handle.name, reason or "continue", runtime_threshold)


def register(name: str) -> Optional[AgentHandle]:
    """Create a handle and start supervising. Returns None when disabled."""
    if not ENABLED:
        return None
    return AgentHandle(name)


def start(handle: Optional[AgentHandle], thread: threading.Thread) -> None:
    """Attach the worker thread and launch the supervisor."""
    if handle is None:
        return
    handle.thread = thread
    threading.Thread(
        target=_supervise,
        args=(handle,),
        daemon=True,
        name=f"agent-watchdog-{handle.name}",
    ).start()


def release(handle: Optional[AgentHandle]) -> None:
    if handle is not None:
        handle.finished = True


# ---------------------------------------------------------------------------
# Middleware — the only thing that feeds the supervisor
# ---------------------------------------------------------------------------

def _install_middleware_class():
    """Built lazily so importing this module never depends on langchain."""
    from langchain.agents.middleware import AgentMiddleware

    class AgentWatchdogMiddleware(AgentMiddleware):
        """Record every tool call on the supervised turn.

        Deliberately does nothing else: it never blocks, never rewrites the
        request, and swallows its own errors. A monitoring hook that can break
        the agent it monitors is worse than no hook.
        """

        def wrap_tool_call(self, request, handler):
            handle = CURRENT.get()
            name = ""
            if handle is not None:
                try:
                    call = request.tool_call or {}
                    name = call.get("name", "") or ""
                    handle.call_started(name, call.get("args"))
                except Exception:
                    log.debug("agent watchdog: could not record tool call", exc_info=True)
            try:
                return handler(request)
            finally:
                if handle is not None:
                    try:
                        handle.call_finished(name)
                    except Exception:
                        pass

    return AgentWatchdogMiddleware


_MIDDLEWARE_CLASS = None


def middleware():
    """A fresh middleware instance to add to any `create_agent(...)` call."""
    global _MIDDLEWARE_CLASS
    if _MIDDLEWARE_CLASS is None:
        _MIDDLEWARE_CLASS = _install_middleware_class()
    return _MIDDLEWARE_CLASS()
