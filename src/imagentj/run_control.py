"""
Registry of in-flight script runs — makes a running script observable and killable.

Two things need this. The Stop button needs a handle it can terminate without
waiting for the script to finish, and the watchdog (see watchdog.py) needs to read
a script's output *while it runs* to judge whether it is stuck.

Both were impossible before: run_python_code() blocked in proc.communicate() and
only surfaced output at the end, and the Groovy path blocked the worker thread
inside the JVM with nothing watching it.

Each execution path registers a RunHandle carrying:
  - the code and why it was run (context for the watchdog's verdict)
  - a live output tail, either pushed (Python reader threads) or pulled
    (Groovy: the redirected System.out buffer is readable mid-run)
  - a terminator callable — the path knows how to kill itself; this module
    does not care whether that is a killpg or an ImageJ abort.

Termination is best-effort by design and the two paths differ sharply:
a Python subprocess dies on SIGKILL, whereas an in-JVM Groovy script can only be
asked to stop (see terminate_groovy_run in tools/script_tools.py for why).
"""

import functools
import itertools
import logging
import os
import signal
import subprocess
import threading
import time
from typing import Callable, Optional, Sequence

log = logging.getLogger(__name__)

# How much output we retain per run. The watchdog only ever reads the tail, but a
# generous buffer keeps the final result intact for short/medium scripts.
_MAX_BUFFER_CHARS = 40_000
# What the watchdog actually gets shown.
_TAIL_CHARS = 4_000

_run_ids = itertools.count(1)


class RunHandle:
    """
    Live state of a single script execution.

    Thread-safety: every mutator takes _lock. The execution path writes output,
    the watchdog reads snapshots, and the GUI thread may call terminate() — all
    concurrently.
    """

    def __init__(
        self,
        language: str,
        code: str,
        purpose: str = "",
        terminator: Optional[Callable[[str], bool]] = None,
        output_provider: Optional[Callable[[], str]] = None,
        rss_provider: Optional[Callable[[], int]] = None,
    ):
        self.run_id = next(_run_ids)
        self.language = language
        self.code = code
        self.purpose = purpose
        self.started_at = time.monotonic()

        self._lock = threading.Lock()
        self._buffer: list[str] = []
        self._buffer_len = 0
        self._last_output_at = self.started_at
        # Pull-model runs (Groovy) expose their output through a callable instead
        # of pushing chunks; we diff its length to detect progress.
        self._output_provider = output_provider
        self._provider_len = 0
        # Only out-of-process runs can report this: an in-process Groovy script
        # has no memory footprint separable from the app's own.
        self._rss_provider = rss_provider

        self._terminator = terminator
        self.status = "running"          # running | finished | stopped | killed
        self.kill_reason = ""
        self.killed_by = ""              # user | watchdog
        # None until a stop is attempted; False means the run refused to die and
        # callers must say so instead of reporting a successful stop.
        self.terminate_succeeded: Optional[bool] = None
        self._terminate_lock = threading.Lock()
        # terminate() flips `status` immediately but the terminator itself can take
        # seconds to establish whether the run really stopped. Anyone reading
        # terminate_succeeded must wait for this, or they race the answer and see None.
        self._settled = threading.Event()

    # ── output ───────────────────────────────────────────────────────────

    def append_output(self, chunk: str) -> None:
        """Push model — called by the Python reader threads as bytes arrive."""
        if not chunk:
            return
        with self._lock:
            self._buffer.append(chunk)
            self._buffer_len += len(chunk)
            self._last_output_at = time.monotonic()
            while self._buffer_len > _MAX_BUFFER_CHARS and len(self._buffer) > 1:
                self._buffer_len -= len(self._buffer.pop(0))

    def _refresh_from_provider(self) -> None:
        """Pull model — poll the provider and treat growth as progress."""
        if self._output_provider is None:
            return
        try:
            current = self._output_provider()
        except Exception:
            return
        if len(current) != self._provider_len:
            self._provider_len = len(current)
            self._last_output_at = time.monotonic()
        self._buffer = [current[-_MAX_BUFFER_CHARS:]]
        self._buffer_len = len(self._buffer[0])

    def output_tail(self, chars: int = _TAIL_CHARS) -> str:
        with self._lock:
            self._refresh_from_provider()
            return "".join(self._buffer)[-chars:]

    # ── state ────────────────────────────────────────────────────────────

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def silent_for(self) -> float:
        """Seconds since the last byte of output. The primary stuck-detector."""
        with self._lock:
            self._refresh_from_provider()
            return time.monotonic() - self._last_output_at

    def rss_bytes(self) -> Optional[int]:
        """Resident memory of this run's process tree, or None if not measurable."""
        if self._rss_provider is None:
            return None
        try:
            return self._rss_provider()
        except Exception:
            return None

    @property
    def terminated(self) -> bool:
        return self.status in ("stopped", "killed")

    # ── termination ──────────────────────────────────────────────────────

    def terminate(self, reason: str, by: str = "user") -> bool:
        """
        Ask the execution path to kill this run. Idempotent — the Stop button and
        the watchdog can race and only the first one takes effect.

        Returns True if the terminator reported success. False means the run
        could not be forced down (a CPU-bound Groovy script is the usual case)
        and the caller should surface that honestly rather than claim it stopped.
        """
        with self._terminate_lock:
            if self.terminated:
                return True
            self.status = "stopped" if by == "user" else "killed"
            self.kill_reason = reason
            self.killed_by = by

        if self._terminator is None:
            self.terminate_succeeded = False
            self._settled.set()
            return False
        try:
            self.terminate_succeeded = bool(self._terminator(reason))
        except Exception as exc:
            log.exception("terminator for run %s failed: %s", self.run_id, exc)
            self.terminate_succeeded = False
        finally:
            self._settled.set()
        return self.terminate_succeeded

    def wait_termination_settled(self, timeout: float) -> None:
        """Block until the termination attempt has a verdict (see _settled)."""
        self._settled.wait(timeout)

    def mark_finished(self) -> None:
        if self.status == "running":
            self.status = "finished"

    def snapshot(self) -> dict:
        return {
            "run_id": self.run_id,
            "language": self.language,
            "purpose": self.purpose,
            "elapsed": round(self.elapsed, 1),
            "silent_for": round(self.silent_for(), 1),
            "status": self.status,
            "output_tail": self.output_tail(),
        }


# ── registry ─────────────────────────────────────────────────────────────

_registry_lock = threading.Lock()
_active: list[RunHandle] = []
# Set by watchdog.py at import time so registering a run can start supervision
# without run_control importing the agent/LLM layer (which would cycle).
_on_register: Optional[Callable[[RunHandle], None]] = None


def set_register_hook(hook: Callable[[RunHandle], None]) -> None:
    global _on_register
    _on_register = hook


def register(handle: RunHandle) -> RunHandle:
    with _registry_lock:
        _active.append(handle)
    if _on_register is not None:
        try:
            _on_register(handle)
        except Exception:
            log.exception("run-register hook failed")
    return handle


def unregister(handle: RunHandle) -> None:
    with _registry_lock:
        try:
            _active.remove(handle)
        except ValueError:
            pass


def active_runs() -> list[RunHandle]:
    with _registry_lock:
        return list(_active)


def terminate_all(reason: str = "Stopped by user", by: str = "user") -> list[RunHandle]:
    """
    Terminate every in-flight run. Called by the Stop button.

    Returns the handles it acted on so the caller can report which ones actually
    went down — terminate() returning False is meaningful, not noise.
    """
    handles = active_runs()
    for handle in handles:
        handle.terminate(reason, by=by)
    return handles


# ── Supervised child processes ───────────────────────────────────────────
#
# Both execution paths — Python analyst scripts and batch Groovy — run their work
# in a child process, and both need exactly the same machinery around it. It lives
# here, next to the registry, rather than being written twice and imported across
# module privates.

# Backstop for a run nothing is watching; the watchdog is the real defence and
# normally intervenes long before this. Deliberately generous (2h): setting it
# tight would silently kill the legitimate long jobs these tools exist for
# (cellpose over a big dataset, stitching, DeepImageJ) hours before they finish.
HARD_TIMEOUT_SECONDS = int(os.environ.get("IMAGENTJ_SCRIPT_HARD_TIMEOUT", "7200"))

# SIGTERM first so a script can unwind (flush files, release the GPU), SIGKILL
# after a grace period for anything ignoring it.
_TERM_GRACE_SECONDS = 3.0


@functools.lru_cache(maxsize=1)
def container_memory_limit() -> Optional[int]:
    """
    The container's memory cap in bytes, or None if unlimited/unreadable.

    This is the ceiling the watchdog races: exceed it and the kernel OOM-kills
    the whole container, taking the app — and the watchdog itself — with it.
    """
    for path in (
        "/sys/fs/cgroup/memory.max",                     # cgroup v2
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",   # cgroup v1
    ):
        try:
            with open(path) as handle:
                raw = handle.read().strip()
        except OSError:
            continue
        if raw == "max":
            return None
        try:
            value = int(raw)
        except ValueError:
            continue
        # cgroup v1 reports a huge sentinel rather than "max" when unlimited.
        if value <= 0 or value >= (1 << 62):
            return None
        return value
    return None


def process_tree_rss(pid: int) -> int:
    """
    Resident memory of a process AND everything it spawned, in bytes.

    The tree, not the process: a script that leaks inside a multiprocessing pool
    shows almost nothing on the parent while the container fills up.
    """
    try:
        import psutil

        proc = psutil.Process(pid)
        total = proc.memory_info().rss
        for child in proc.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                pass  # died mid-walk; its memory is already gone
        return total
    except Exception:
        return 0


def terminate_process_group(proc: subprocess.Popen, grace: float = _TERM_GRACE_SECONDS) -> bool:
    """
    Signal a run's whole process group down. Returns True once it is gone.

    The group, not the process: these scripts fan out into multiprocessing pools
    and cellpose/stardist workers, and killing only the direct child leaves those
    orphaned and still burning CPU/GPU.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        return True  # already reaped

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return True
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and proc.poll() is None:
        time.sleep(0.05)

    # SIGKILL the group regardless. The child exiting does not mean the group is
    # empty — a grandchild ignoring SIGTERM would otherwise survive, which is
    # exactly the orphan case this exists to prevent.
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and proc.poll() is None:
        time.sleep(0.05)
    return proc.poll() is not None


def _drain_stream(stream, sink: list[str], handle: RunHandle, label: str) -> None:
    """
    Pump one pipe into both the final transcript and the live handle.

    Reading in a thread is what makes a running script observable at all, and it
    also removes the pipe-buffer deadlock a plain communicate(timeout=...) hides:
    a script printing more than ~64 KB to stderr blocks forever once the pipe fills.
    """
    try:
        for line in iter(stream.readline, ""):
            sink.append(line)
            handle.append_output(line if label == "out" else f"[stderr] {line}")
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


class SupervisedProcess:
    """
    A child process wired into the run registry: killable by the Stop button and
    the watchdog, with its output streamed live so silence is meaningful.

    Use as a context manager — __exit__ guarantees no orphan survives an early
    return or an exception in the caller's own bookkeeping.
    """

    def __init__(
        self,
        cmd: Sequence[str],
        *,
        language: str,
        code: str,
        purpose: str = "",
        env: Optional[dict] = None,
        timeout: Optional[float] = None,
    ):
        self.timeout = timeout if timeout is not None else HARD_TIMEOUT_SECONDS
        self.proc = subprocess.Popen(
            list(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,               # line-buffered: the watchdog sees progress promptly
            start_new_session=True,  # own process group, so the kill takes the whole tree
            env=env,
        )
        self.handle = register(RunHandle(
            language=language,
            code=code,
            purpose=purpose,
            terminator=lambda reason, p=self.proc: terminate_process_group(p),
            rss_provider=lambda pid=self.proc.pid: process_tree_rss(pid),
        ))
        self._out: list[str] = []
        self._err: list[str] = []
        self._readers = [
            threading.Thread(target=_drain_stream, args=(self.proc.stdout, self._out, self.handle, "out"), daemon=True),
            threading.Thread(target=_drain_stream, args=(self.proc.stderr, self._err, self.handle, "err"), daemon=True),
        ]
        for reader in self._readers:
            reader.start()

    def wait(self) -> None:
        """Block until the child exits, bounded by the hard timeout."""
        try:
            self.proc.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            terminate_process_group(self.proc)
            self.handle.terminate(
                f"Exceeded the hard {self.timeout}s execution limit", by="watchdog"
            )
        for reader in self._readers:
            reader.join(timeout=5.0)

    @property
    def stdout(self) -> str:
        return "".join(self._out)

    @property
    def stderr(self) -> str:
        return "".join(self._err)

    @property
    def returncode(self):
        return self.proc.returncode

    def close(self) -> None:
        if self.proc.poll() is None:
            terminate_process_group(self.proc, grace=0.5)
        self.handle.mark_finished()
        unregister(self.handle)

    def __enter__(self) -> "SupervisedProcess":
        return self

    def __exit__(self, *exc_info) -> bool:
        self.close()
        return False


# ── Reporting a deliberate stop ──────────────────────────────────────────
#
# A stop must never read like a crash: the debugger agent treats crash output as
# something to repair, so a user pressing Stop would otherwise kick off a
# fix-the-nonexistent-bug loop. Every execution path says this the same way.

def stop_headline(handle: RunHandle) -> str:
    return (
        "EXECUTION STOPPED BY USER" if handle.killed_by == "user"
        else "EXECUTION TERMINATED BY WATCHDOG"
    )


def stop_guidance(handle: RunHandle) -> str:
    """Tell the agent what a stopped run means and what to do about it."""
    if handle.killed_by == "user":
        return (
            "The user pressed Stop — this is NOT a bug to fix. Do not retry or "
            "debug it; wait for the user's next instruction."
        )
    return (
        f"Reason: {handle.kill_reason}\n"
        "The script was killed while running because it appeared stuck or "
        "misbehaving. This is not a normal crash — review the reason and the "
        "partial output, then decide whether to fix the script, change approach, "
        "or ask the user."
    )
