"""
Global stop signal for cooperative cancellation of subagent tool calls.

Set by AgentWorker.request_stop(); cleared at the start of each new prompt.

SubagentRunner runs agent.invoke() in a daemon thread and polls the stop signal
every POLL_INTERVAL seconds. When stop is set it injects SystemExit into the
thread via PyThreadState_SetAsyncExc, which fires at the next Python bytecode
boundary. This interrupts Python-level code (processing LLM response chunks,
tool dispatch, etc.) but cannot interrupt a C-level socket recv mid-call —
so interruption happens within the current streaming chunk, not necessarily
the current HTTP request.
"""

import ctypes
import threading

POLL_INTERVAL = 0.3   # seconds between stop-signal checks inside SubagentRunner

_stop_event = threading.Event()


def request_stop() -> None:
    _stop_event.set()


def clear() -> None:
    _stop_event.clear()


def is_set() -> bool:
    return _stop_event.is_set()


class StopRequested(RuntimeError):
    """Raised when a stop was requested before or during a subagent call."""


def _inject_exit(thread: threading.Thread) -> None:
    """Inject SystemExit into a running thread via the CPython async-exception API."""
    tid = thread.ident
    if tid is None:
        return
    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(tid),
        ctypes.py_object(SystemExit),
    )


class SubagentRunner:
    """
    Wraps a blocking agent.invoke() call so it can be interrupted by the stop signal.

    Usage::

        runner = SubagentRunner(agent.invoke, {"messages": [...]})
        result = runner.run()          # blocks, but checks stop every POLL_INTERVAL s
        return result["structured_response"]

    If the stop signal is set before or during the call, raises StopRequested.
    The underlying thread is a daemon so it will not keep the process alive.
    """

    def __init__(self, fn, *args, watchdog=None, **kwargs):
        self._fn     = fn
        self._args   = args
        self._kwargs = kwargs
        self._result = None
        self._error: BaseException | None = None
        self._thread: threading.Thread | None = None
        # Optional agent_watchdog.AgentHandle supervising this turn.
        self._watchdog = watchdog

    def _target(self):
        # Bind the watchdog handle INSIDE the worker thread: ContextVars are not
        # inherited across Thread.start(), but LangChain copies the context into
        # its tool-executor threads, so setting it here reaches the middleware.
        if self._watchdog is not None:
            from . import agent_watchdog
            agent_watchdog.CURRENT.set(self._watchdog)
        try:
            self._result = self._fn(*self._args, **self._kwargs)
        except BaseException as exc:
            self._error = exc

    def run(self):
        if is_set():
            raise StopRequested("Stop already requested — subagent not started.")

        self._thread = threading.Thread(target=self._target, daemon=True)
        if self._watchdog is not None:
            from . import agent_watchdog
            agent_watchdog.start(self._watchdog, self._thread)
        self._thread.start()

        while self._thread.is_alive():
            self._thread.join(timeout=POLL_INTERVAL)
            if is_set() and self._thread.is_alive():
                _inject_exit(self._thread)
                self._thread.join(timeout=5.0)   # give it a moment to react
                raise StopRequested("Stop requested — subagent interrupted.")
            if (self._watchdog is not None and self._watchdog.terminated
                    and self._thread.is_alive()):
                # The agent watchdog already injected SystemExit; give the thread
                # a moment, then stop waiting on it either way. A tool blocked in
                # a C call (e.g. a JVM round-trip) cannot be interrupted, so we
                # abandon the daemon thread rather than hang with it — the caller
                # returns its graceful handoff and the pipeline continues.
                self._thread.join(timeout=5.0)
                from . import agent_watchdog
                raise agent_watchdog.AgentAborted(
                    self._watchdog.kill_reason or "agent watchdog terminated the turn")

        # The worker usually dies from the injected SystemExit before the loop
        # above notices, so the abort has to be re-checked here too. Without this
        # the SystemExit we injected is re-raised into the caller and takes the
        # interpreter down instead of degrading into a graceful handoff.
        if self._watchdog is not None and self._watchdog.terminated:
            from . import agent_watchdog
            raise agent_watchdog.AgentAborted(
                self._watchdog.kill_reason or "agent watchdog terminated the turn")

        if self._error is not None:
            if isinstance(self._error, StopRequested):
                raise self._error
            raise self._error  # propagate any real error from the thread
        return self._result
