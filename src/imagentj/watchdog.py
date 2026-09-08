"""
Watchdog that supervises a running script and can terminate it mid-flight.

Why a separate thread rather than "let the supervisor check the output": while a
script runs, the supervisor is blocked inside the synchronous tool call that
started it. It gets the output only after the run returns, which is exactly the
situation we need to escape. Nothing on the agent's own control flow can observe
a run in progress, so supervision has to live outside it.

Two tiers, so the common case costs nothing:

  Tier 1 (free, always on) — output silence and total runtime, read from the
  RunHandle. No LLM involved.

  Tier 2 (LLM, only once a tripwire fires) — a small model sees the script, what
  it was for, how long it has been quiet, and the tail of its output, then rules
  CONTINUE or KILL.

Bias is heavily toward CONTINUE. Bioimage jobs are legitimately long and silent
(cellpose over a big stack, stitching, a slow plugin), and killing a 40-minute
segmentation on a false positive is far worse than waiting out a genuinely stuck
script. Every failure path here — LLM error, parse failure, missing key — resolves
to "leave it alone".
"""

import logging
import os
import threading
import time
from typing import Callable, Optional

from . import run_control

log = logging.getLogger(__name__)

ENABLED = os.environ.get("IMAGENTJ_WATCHDOG", "1") not in ("0", "false", "False")
# Silence that trips the first LLM check. Long enough that a normal plugin step
# or model load does not trigger it.
SILENCE_SECONDS = float(os.environ.get("IMAGENTJ_WATCHDOG_SILENCE", "180"))
# Runtime that trips a check regardless of how chatty the script is. This is the
# ONLY defence against a runaway that deliberately looks alive: a `while (true)`
# printing a heartbeat every few seconds never goes silent, so SILENCE_SECONDS can
# never fire and the silence signal is worthless against it.
#
# Kept short (5 min) precisely because it is that case's only tripwire — at the
# old 25 minutes a spinning loop burned a core for 25 minutes before anyone looked.
# The cost of checking early is one nano call per run; the backoff below then
# spaces out re-checks, so a legitimate multi-hour job is judged only a handful of
# times. Being early here is cheap; being late is not.
MAX_RUNTIME_SECONDS = float(os.environ.get("IMAGENTJ_WATCHDOG_MAX_RUNTIME", "300"))
POLL_SECONDS = 5.0
# After a CONTINUE verdict we back off multiplicatively, so a long legitimate job
# is not re-judged every few minutes at increasing cost.
BACKOFF_FACTOR = 2.0
# ...but the backoff is capped. Unbounded doubling means a run that goes stuck
# after the third check effectively stops being watched at all.
MAX_CHECK_GAP_SECONDS = float(os.environ.get("IMAGENTJ_WATCHDOG_MAX_GAP", "600"))

# Fraction of the container's memory limit at which a run is killed outright.
#
# This is a THIRD tripwire, and unlike silence and runtime it does not consult the
# LLM. Two reasons. There is nothing to judge — a run about to exhaust the
# container must die whether or not its logic is sound. And we are racing the
# kernel's OOM killer, which shows no such restraint: it kills the whole container,
# taking the app, the user's open images, and this watchdog with it. A verdict call
# takes seconds we may not have.
#
# Only out-of-process runs are covered; an in-process Groovy script has no
# footprint separable from the app's own.
MEMORY_FRACTION = float(os.environ.get("IMAGENTJ_WATCHDOG_MEM_FRACTION", "0.85"))

_MAX_CODE_CHARS = 3_000
_MAX_TAIL_CHARS = 2_500

# GUI hook — set by gui_runner so a watchdog kill can surface in the chat instead
# of only in the log.
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
        log.exception("watchdog notifier failed")


_VERDICT_PROMPT = """You are a watchdog supervising a running bioimage-analysis script.

Your ONLY job is to decide whether this run should be killed right now. You are not \
reviewing code quality and you cannot edit anything.

Default to CONTINUE. These scripts routinely run for many minutes with no output at \
all — loading models, segmenting large stacks, stitching tiles, writing big files. \
Silence alone is NOT evidence of a problem.

Answer KILL only on positive evidence the run is not going to finish usefully:
  - it CANNOT TERMINATE: the loop driving the work has no reachable exit — a
    `while (true)` with no break/return/throw that can fire, or a condition that
    nothing in the loop body can ever make false. This counts NO MATTER HOW MUCH
    OUTPUT IT PRODUCES.
  - the same output repeats over and over (spinning loop)
  - it is blocked waiting for input that will never arrive (a prompt, a dialog, stdin)
  - it hit a fatal error and is now hanging instead of exiting
  - it is clearly doing the wrong thing (e.g. writing to the wrong location,
    reprocessing the same file endlessly, an obvious runaway)
  - it is in an UNBOUNDED WAIT: a loop polling for some external event (a file
    appearing, a lock clearing, a server responding) with no timeout and no exit
    condition it can reach on its own, and it has already waited far longer than
    that event should plausibly take

CRITICAL — LIVELINESS IS NOT PROGRESS. Output flowing does not mean the run will
ever finish. A runaway loop frequently prints heartbeats, counters, elapsed times
or checksums every few seconds, and those numbers change every line, so it does
NOT look like "the same output repeating". Do not accept "it is actively
computing and printing" as a reason to continue — that is exactly what a
non-terminating loop looks like from outside.

Decide termination from the CODE, not from whether output is flowing:
  - BOUNDED work — `for (i = 0; i < n; i++)`, iterating a fixed list of files,
    a training run with a set number of epochs — WILL end. CONTINUE, however long
    it takes and however silent it is.
  - UNBOUNDED work — `while (true)`, or a poll whose condition nothing can
    satisfy — will NEVER end. KILL it, however lively its output looks.

Otherwise answer CONTINUE.

--- SCRIPT PURPOSE ---
{purpose}

--- LANGUAGE ---
{language}

--- CODE ---
{code}

--- RUNTIME ---
Running for {elapsed_min}. No new output for {silent_min}.

--- RECENT OUTPUT (tail) ---
{tail}

Reply with exactly one line:
KILL: <short reason>
or
CONTINUE: <short reason>
"""


def _human_duration(seconds: float) -> str:
    """Minutes read better than raw seconds when judging 'is this too long?'."""
    if seconds < 90:
        return f"{seconds:.0f} seconds"
    return f"{seconds / 60:.1f} minutes"


def _message_content_text(content) -> str:
    """Normalize LangChain/OpenAI string or content-block responses."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content or "")


def _ask_llm(handle: "run_control.RunHandle") -> tuple[bool, str]:
    """
    Ask the model whether to kill. Returns (should_kill, reason).

    Imported lazily: agents.py builds the LLMs at import time and imports this
    module, so a top-level import here would cycle.
    """
    try:
        from .agents import llm_nano
    except Exception as exc:
        log.warning("watchdog: no LLM available (%s) — leaving run alone", exc)
        return False, ""

    prompt = _VERDICT_PROMPT.format(
        purpose=handle.purpose or "(not stated)",
        language=handle.language,
        code=handle.code[:_MAX_CODE_CHARS],
        elapsed_min=_human_duration(handle.elapsed),
        silent_min=_human_duration(handle.silent_for()),
        tail=handle.output_tail(_MAX_TAIL_CHARS) or "(no output yet)",
    )
    try:
        reply = llm_nano.invoke(prompt)
        content = reply.content if hasattr(reply, "content") else reply
        text = _message_content_text(content).strip()
    except Exception as exc:
        log.warning("watchdog: verdict call failed (%s) — leaving run alone", exc)
        return False, ""

    first = text.strip().splitlines()[0] if text.strip() else ""
    if first.upper().startswith("KILL"):
        reason = first.split(":", 1)[1].strip() if ":" in first else "watchdog judged the run stuck"
        return True, reason
    return False, first


def _memory_tripped(handle: "run_control.RunHandle") -> Optional[str]:
    """Is this run about to exhaust the container? Returns a reason, or None."""
    limit = run_control.container_memory_limit()
    if limit is None or MEMORY_FRACTION <= 0:
        return None
    rss = handle.rss_bytes()
    if rss is None:
        return None
    if rss < limit * MEMORY_FRACTION:
        return None
    gib = 1024 ** 3
    return (
        f"using {rss / gib:.1f} GiB of the container's {limit / gib:.1f} GiB limit "
        f"({rss / limit:.0%}) — killed to stop the kernel OOM-killing the whole app"
    )


def _supervise(handle: "run_control.RunHandle") -> None:
    """Watch one run until it finishes or gets killed."""
    silence_threshold = SILENCE_SECONDS
    runtime_threshold = MAX_RUNTIME_SECONDS

    while True:
        time.sleep(POLL_SECONDS)

        if handle.terminated or handle.status == "finished":
            return
        if handle not in run_control.active_runs():
            return

        # Memory first, and without asking the LLM — see MEMORY_FRACTION.
        memory_reason = _memory_tripped(handle)
        if memory_reason:
            log.warning("watchdog: killing run %s — %s", handle.run_id, memory_reason)
            killed = handle.terminate(memory_reason, by="watchdog")
            _notify(
                f"Watchdog stopped the running {handle.language} script: {memory_reason}"
                if killed else
                f"Watchdog tried to stop the running {handle.language} script "
                f"({memory_reason}) but it did not respond — the container may still OOM."
            )
            return

        silent = handle.silent_for()
        elapsed = handle.elapsed
        if silent < silence_threshold and elapsed < runtime_threshold:
            continue

        trigger = (
            f"no output for {silent:.0f}s" if silent >= silence_threshold
            else f"running for {elapsed:.0f}s"
        )
        log.info("watchdog: checking run %s (%s)", handle.run_id, trigger)

        should_kill, reason = _ask_llm(handle)
        if should_kill:
            full_reason = f"{reason} (after {elapsed:.0f}s, {trigger})"
            log.warning("watchdog: killing run %s — %s", handle.run_id, full_reason)
            killed = handle.terminate(full_reason, by="watchdog")
            _notify(
                f"Watchdog stopped the running {handle.language} script: {full_reason}"
                if killed else
                f"Watchdog tried to stop the running {handle.language} script "
                f"({full_reason}) but it did not respond — it may still be running."
            )
            return

        # Cleared. Back off both tripwires so a long legitimate job is judged less
        # and less often — but cap the growth, otherwise a run that goes stuck
        # after a few clean verdicts would never be looked at again.
        silence_threshold = silent + min(silent * (BACKOFF_FACTOR - 1), MAX_CHECK_GAP_SECONDS)
        runtime_threshold = elapsed + min(elapsed * (BACKOFF_FACTOR - 1), MAX_CHECK_GAP_SECONDS)
        log.info(
            "watchdog: run %s cleared (%s); next check after %.0fs silence / %.0fs runtime",
            handle.run_id, reason or "continue", silence_threshold, runtime_threshold,
        )


def _on_run_registered(handle: "run_control.RunHandle") -> None:
    if not ENABLED:
        return
    threading.Thread(
        target=_supervise,
        args=(handle,),
        daemon=True,
        name=f"watchdog-{handle.run_id}",
    ).start()


def install() -> None:
    """Wire the watchdog into the run registry. Safe to call more than once."""
    run_control.set_register_hook(_on_run_registered)
    log.info(
        "watchdog %s (silence=%.0fs, max_runtime=%.0fs)",
        "enabled" if ENABLED else "disabled", SILENCE_SECONDS, MAX_RUNTIME_SECONDS,
    )
